"""book_ingest job execution (D-25): fetch the PDF from the Pi, ingest it.

The dashboard upload (backend PR: internal/usecase/book) stores the PDF on
the Pi under BOOKS_DIR and enqueues kind='book_ingest' with the
Pi-canonical absolute path as the identity key. This module is the
Mac-side executor:

1. download the PDF from the tailnet-only endpoint
   GET {BOOKS_PRIVATE_BASE_URL}/private/books/{filename} — no auth, the
   tailnet bind is the boundary (C-5), same contract as the private feed
2. run the exact same ingest pipeline as the pulse-books CLI
   (PyMuPDF → chunks → Ollama bge-m3 → pgvector), recording
   payload.file_path — never the temp download path — as books.file_path,
   so the dashboard and CLI share one identity semantics (D-25 (4))

C-12: the PDF travels Pi → Mac over Tailscale and its embeddings travel
Mac → Pi the same way; no cloud API sees any of it. The downloaded copy
lives only inside a TemporaryDirectory and is removed on success and
failure alike (生ファイル非永続 — the Pi's BOOKS_DIR copy is the
persistent one).
"""

import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import quote, urlsplit

import psycopg
import structlog

from pulse_books.cli import ingest
from pulse_books.db import BookStore, IngestResult
from pulse_books.embedding import OllamaEmbedder
from pulse_books.errors import PdfExtractionError
from pulse_transcribe.errors import PermanentJobError
from pulse_transcribe.models import BookIngestPayload
from pulse_transcribe.worker import BookHandler

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

# Same download conventions as media.py; 100MB (the upload ceiling) over
# the tailnet fits comfortably in this timeout.
_DOWNLOAD_TIMEOUT_SECONDS = 600.0
_USER_AGENT = "pulse-transcribe/0.1"

# download(url, dest) writes the PDF to dest. Injectable for tests.
Download = Callable[[str, Path], None]


def book_url(base_url: str, filename: str) -> str:
    """The /private/books/{filename} URL for one payload filename."""
    return base_url.rstrip("/") + "/private/books/" + quote(filename)


def download_book(url: str, dest: Path) -> None:
    """Stream the PDF from the Pi's tailnet listener into dest.

    HTTP 404 is permanent: the canonical file is gone from the Pi (deleted
    after upload — the delete API cancels *pending* jobs, so a claimed job
    can still race it); retrying cannot bring it back. Everything else
    (connection refused, 5xx, timeouts) stays retryable.
    """
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as resp:  # noqa: S310
            with dest.open("wb") as out:
                shutil.copyfileobj(resp, out)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise PermanentJobError(
                f"PDF not found on the Pi (HTTP 404 from {url}) — deleted after upload?"
            ) from exc
        raise


def ingest_book(
    payload: BookIngestPayload,
    base_url: str,
    store: BookStore,
    embedder: OllamaEmbedder,
    *,
    download: Download = download_book,
) -> IngestResult:
    """Execute one book_ingest job: fetch to a temp dir, ingest, clean up.

    The temp copy is removed on success and failure alike; extraction
    quality warnings (garbled pages etc.) come from the shared pipeline's
    logs unchanged.
    """
    url = book_url(base_url, payload.filename)
    with TemporaryDirectory(prefix="pulse-book-") as tmp:
        dest = Path(tmp) / payload.filename
        download(url, dest)
        logger.info(
            "book_ingest: pdf downloaded",
            url=url,
            bytes=dest.stat().st_size,
            title=payload.title,
        )
        try:
            return ingest(dest, payload.title, store, embedder, file_path_key=payload.file_path)
        except PdfExtractionError as exc:
            # Deterministic failure: a PDF that cannot be opened or yields
            # no text (broken file, real read password = DRM per C-15,
            # image-only scan) will not fix itself by retrying — fail
            # terminally instead of burning 3 attempts. EmbeddingError
            # (e.g. Ollama down) deliberately stays retryable.
            raise PermanentJobError(str(exc)) from exc


def default_book_handler(base_url: str, conn: psycopg.Connection[Any]) -> BookHandler:
    """The production handler: shared DB connection, local Ollama embedder.

    Reads the pulse_books settings (OLLAMA_HOST / EMBEDDING_MODEL) from the
    same environment the CLI uses. The base URL is operator configuration:
    a bad scheme raises ValueError here, before any job is claimed, and the
    caller (worker.main) downgrades that to "book_ingest disabled" so a
    typo never takes the night's transcription down with it (縮退許容 —
    the jobs stay pending and no attempts are burned).
    """
    scheme = urlsplit(base_url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"BOOKS_PRIVATE_BASE_URL must be http(s), got {base_url!r}")

    from pulse_books.config import Settings as BookSettings

    # Required fields (DATABASE_URL) come from the environment / .env;
    # pydantic-settings validates them at runtime, which mypy cannot see.
    settings = BookSettings()  # type: ignore[call-arg]
    embedder = OllamaEmbedder(host=settings.ollama_host, model=settings.embedding_model)
    store = BookStore(conn)

    def handle(payload: BookIngestPayload) -> None:
        ingest_book(payload, base_url, store, embedder)

    return handle
