"""books / book_chunks access (§4, D-10: pgvector 自前パイプライン).

Schema ownership: creating books / book_chunks (and the pgvector
extension) is the backend migration's responsibility. This module assumes
the tables exist and converts "relation does not exist" into a clear
operator error (SchemaMissingError). The reference DDL lives in
tests/test_books_db_integration.py, copied from pulse-phase2-design.md §4.

Vectors are bound as pgvector text literals ("[1,2,3]") and cast with
::vector — no pgvector client package needed (right-sizing: two queries
do not justify a dependency).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import errors as pg_errors

from pulse_books.errors import SchemaMissingError

# Cosine similarity search over book chunks. Kept as a reusable module-level
# constant: openwebui/book_search_tool.py (A-23) carries a verbatim copy of
# this SQL — it runs in the Open WebUI sandbox and cannot import pulse_books
# — and tests/test_openwebui_tool.py asserts the two stay identical. Change
# both or neither. Parameters: query (vector literal), top_k.
# `<=>` is pgvector's cosine distance; similarity = 1 - distance.
SEARCH_SQL = """
SELECT c.book_id, b.title, c.position, c.content,
       1 - (c.embedding <=> %(query)s::vector) AS similarity
FROM book_chunks c
JOIN books b ON b.id = c.book_id
WHERE c.embedding IS NOT NULL
ORDER BY c.embedding <=> %(query)s::vector, c.book_id, c.position
LIMIT %(top_k)s"""


def format_vector(vector: Sequence[float]) -> str:
    """Render a vector as a pgvector text literal: [0.1,0.2,...]."""
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


@dataclass(frozen=True, slots=True)
class Chunk:
    """One chunk ready for insertion: text plus its embedding."""

    content: str
    embedding: Sequence[float]


@dataclass(frozen=True, slots=True)
class IngestResult:
    book_id: int
    chunk_count: int
    replaced: bool  # True when an earlier import of the same PDF was replaced


@dataclass(frozen=True, slots=True)
class SearchHit:
    book_id: int
    book_title: str
    position: int
    content: str
    similarity: float


class BookStore:
    """books / book_chunks client. The connection must be in autocommit

    mode (same convention as the transcribe worker's JobStore);
    replace_book opens its own explicit transaction where atomicity
    matters.
    """

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def replace_book(self, title: str, file_path: str, chunks: Sequence[Chunk]) -> IngestResult:
        """Insert a book and its chunks; re-ingesting the same PDF replaces it.

        Identity is books.file_path (the resolved path of the source PDF).
        On re-ingest the existing book row is kept (stable id for future
        references, e.g. Phase 3 quiz generation), its chunks are deleted
        and re-inserted — the whole operation is one transaction, so a
        failed re-ingest leaves the previous import intact.
        """
        try:
            with self._conn.transaction():
                row = self._conn.execute(
                    "SELECT id FROM books WHERE file_path = %s ORDER BY id LIMIT 1",
                    (file_path,),
                ).fetchone()

                if row is not None:
                    book_id = int(row[0])
                    replaced = True
                    self._conn.execute(
                        "UPDATE books SET title = %s, imported_at = now() WHERE id = %s",
                        (title, book_id),
                    )
                    self._conn.execute(
                        "DELETE FROM book_chunks WHERE book_id = %s", (book_id,)
                    )
                else:
                    inserted = self._conn.execute(
                        "INSERT INTO books (title, file_path) VALUES (%s, %s) RETURNING id",
                        (title, file_path),
                    ).fetchone()
                    assert inserted is not None  # RETURNING always yields a row
                    book_id = int(inserted[0])
                    replaced = False

                with self._conn.cursor() as cur:
                    cur.executemany(
                        "INSERT INTO book_chunks (book_id, position, content, embedding)"
                        " VALUES (%s, %s, %s, %s::vector)",
                        [
                            (book_id, position, chunk.content, format_vector(chunk.embedding))
                            for position, chunk in enumerate(chunks)
                        ],
                    )
        except (pg_errors.UndefinedTable, pg_errors.UndefinedObject) as exc:
            raise SchemaMissingError(str(exc).strip()) from exc

        return IngestResult(book_id=book_id, chunk_count=len(chunks), replaced=replaced)

    def search(self, query_embedding: Sequence[float], top_k: int = 5) -> list[SearchHit]:
        """Cosine-similarity search over all book chunks (SEARCH_SQL)."""
        try:
            rows = self._conn.execute(
                SEARCH_SQL,
                {"query": format_vector(query_embedding), "top_k": top_k},
            ).fetchall()
        except (pg_errors.UndefinedTable, pg_errors.UndefinedObject) as exc:
            raise SchemaMissingError(str(exc).strip()) from exc

        return [
            SearchHit(
                book_id=int(row[0]),
                book_title=str(row[1]),
                position=int(row[2]),
                content=str(row[3]),
                similarity=float(row[4]),
            )
            for row in rows
        ]
