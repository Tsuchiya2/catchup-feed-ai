"""pulse-books CLI — book PDF RAG ingestion and search (§6, §9 手順7).

    pulse-books ingest <pdf> [--title TITLE]   # PDF → chunks → embeddings → Pi pgvector
    pulse-books search <query> [--top-k 5]     # cosine search over book_chunks

Runs by hand on the Mac (unlike the transcribe worker there is no nightly
schedule — a book is ingested once). `search` exists to verify an ingest
end to end before the Open WebUI integration (next task) reuses
db.SEARCH_SQL.

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
    pdf_path: Path, title: str | None, store: BookStore, embedder: OllamaEmbedder
) -> IngestResult:
    """Run the full ingest pipeline for one PDF.

    Idempotent: the book's identity is its resolved file path, so running
    the same command twice replaces the previous import (BookStore).
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
        file_path=str(resolved),
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
        "--top-k", type=int, default=5, help="number of chunks to return (default 5)"
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
