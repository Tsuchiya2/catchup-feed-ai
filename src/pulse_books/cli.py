"""pulse-books CLI — book PDF RAG ingestion and search (§6, §9 手順7).

    pulse-books ingest <pdf> [--title TITLE]   # PDF → chunks → embeddings → Pi pgvector
    pulse-books search <query> [--top-k 5]     # cosine search over book_chunks

Runs by hand on the Mac for PDFs that live on the Mac. The other route into
the same pipeline is the dashboard upload (D-25): the backend enqueues
kind='book_ingest' and pulse_transcribe.book_ingest calls ingest() below
with file_path_key set to the Pi-canonical path. `search` verifies an
ingest end to end; the Open WebUI tool (A-23) reuses db.SEARCH_SQL.

C-12: the PDF text and its embeddings only ever travel Mac → Pi (Tailscale).
No cloud API is involved anywhere in this pipeline.
"""

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

import structlog

from pulse_books.chunker import TextChunker
from pulse_books.db import BookStore, Chunk, IngestResult, SearchHit
from pulse_books.embedding import OllamaEmbedder
from pulse_books.errors import BookPipelineError, PdfExtractionError
from pulse_books.pdf import extract_text

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

# How much text goes into one embedding. bge-m3 accepts up to 8K tokens, so
# the constraint is retrieval granularity, not the model: ~1000 characters
# keeps one chunk ≈ one passage worth citing in a chat answer.
CHUNK_SIZE = 1000
CHUNK_MIN_SIZE = 100

_SNIPPET_LENGTH = 200


def ingest(
    pdf_path: Path,
    title: str | None,
    store: BookStore,
    embedder: OllamaEmbedder,
    *,
    file_path_key: str | None = None,
) -> IngestResult:
    """Run the full ingest pipeline for one PDF.

    Idempotent: the book's identity is books.file_path, so running the
    same ingest twice replaces the previous import (BookStore). By default
    the identity is the resolved path of pdf_path (the CLI semantics);
    file_path_key overrides it for callers that ingest from a temporary
    copy — the book_ingest job worker records the Pi-canonical payload
    path, never its own temp download path (D-25 (4)).
    """
    resolved = pdf_path.resolve()
    book_title = title or resolved.stem

    text = extract_text(resolved)

    chunker = TextChunker(chunk_size=CHUNK_SIZE, min_chunk_size=CHUNK_MIN_SIZE)
    chunks = chunker.chunk(text)
    if not chunks:
        raise PdfExtractionError(f"extracted text produced no chunks: {resolved}")
    logger.info("ingest: text chunked", chunks=len(chunks), title=book_title)

    embeddings = embedder.embed([chunk.text for chunk in chunks])
    logger.info("ingest: embeddings generated", vectors=len(embeddings))

    result = store.replace_book(
        title=book_title,
        file_path=file_path_key or str(resolved),
        chunks=[
            Chunk(content=chunk.text, embedding=vector)
            for chunk, vector in zip(chunks, embeddings, strict=True)
        ],
    )
    logger.info(
        "ingest: book stored",
        book_id=result.book_id,
        chunks=result.chunk_count,
        replaced=result.replaced,
        title=book_title,
    )
    return result


def search(query: str, top_k: int, store: BookStore, embedder: OllamaEmbedder) -> list[SearchHit]:
    """Embed the query and run the cosine search (db.SEARCH_SQL)."""
    return store.search(embedder.embed_one(query), top_k=top_k)


def format_hit(rank: int, hit: SearchHit) -> str:
    """One human-readable search result (similarity, source, snippet)."""
    snippet = " ".join(hit.content.split())
    if len(snippet) > _SNIPPET_LENGTH:
        snippet = snippet[:_SNIPPET_LENGTH] + "…"
    return (
        f"[{rank}] similarity={hit.similarity:.3f}  "
        f"{hit.book_title} (book {hit.book_id}, chunk {hit.position})\n"
        f"    {snippet}"
    )


def configure_logging(level: str) -> None:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
    )


def _positive_int(value: str) -> int:
    """argparse type for --top-k: a friendly error instead of a Postgres one."""
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"must be an integer, got {value!r}") from exc
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return number


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-books",
        description="pulse Phase 2 book PDF RAG ingestion (Mac, manual runs)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser(
        "ingest", help="ingest a DRM-free PDF into books / book_chunks (re-run replaces)"
    )
    ingest_parser.add_argument("pdf", type=Path, help="path to the PDF file")
    ingest_parser.add_argument(
        "--title", default=None, help="book title (default: the PDF file name)"
    )

    search_parser = subparsers.add_parser(
        "search", help="cosine-search book_chunks (verification for the ingest)"
    )
    search_parser.add_argument("query", help="natural-language query")
    search_parser.add_argument(
        "--top-k", type=_positive_int, default=5, help="number of chunks to return (default 5)"
    )

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    import psycopg

    from pulse_books.config import Settings

    args = _parse_args(argv)
    # Required fields (DATABASE_URL) come from the environment / .env;
    # pydantic-settings validates them at runtime, which mypy cannot see.
    settings = Settings()  # type: ignore[call-arg]
    configure_logging(settings.log_level)

    embedder = OllamaEmbedder(host=settings.ollama_host, model=settings.embedding_model)

    try:
        # autocommit like the transcribe worker; BookStore opens an explicit
        # transaction where atomicity matters (replace_book).
        with psycopg.connect(settings.database_url, autocommit=True) as conn:
            store = BookStore(conn)
            if args.command == "ingest":
                ingest(args.pdf, args.title, store, embedder)
            else:
                hits = search(args.query, args.top_k, store, embedder)
                if not hits:
                    print("no results (no books ingested yet?)")
                for rank, hit in enumerate(hits, start=1):
                    print(format_hit(rank, hit))
    except BookPipelineError as exc:
        logger.error("pulse-books failed", error=str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
