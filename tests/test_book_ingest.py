"""book_ingest job execution tests (D-25): download faked, real tiny PDFs.

The ingest pipeline itself is covered by test_books_cli.py; here the focus
is the job-specific glue: URL building, the Pi-canonical identity key, the
temp-file lifecycle, and the 404→permanent classification.
"""

import io
import urllib.error
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from conftest import write_pdf

from pulse_books.db import Chunk, IngestResult, SearchHit
from pulse_books.embedding import EMBEDDING_DIM
from pulse_books.errors import EmbeddingError, PdfExtractionError
from pulse_transcribe.book_ingest import (
    book_url,
    default_book_handler,
    download_book,
    ingest_book,
)
from pulse_transcribe.errors import PermanentJobError
from pulse_transcribe.models import BookIngestPayload

PAYLOAD = BookIngestPayload(file_path="/data/books/learning-go.pdf", title="Learning Go")
BASE_URL = "http://pi.tail-example.ts.net:8081"


class FakeEmbedder:
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[1.0] + [0.0] * (EMBEDDING_DIM - 1) for _ in texts]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class FakeStore:
    def __init__(self) -> None:
        self.replace_calls: list[tuple[str, str, list[Chunk]]] = []

    def replace_book(self, title: str, file_path: str, chunks: Sequence[Chunk]) -> IngestResult:
        self.replace_calls.append((title, file_path, list(chunks)))
        return IngestResult(book_id=1, chunk_count=len(chunks), replaced=False)

    def search(self, query_embedding: Sequence[float], top_k: int = 5) -> list[SearchHit]:
        raise NotImplementedError


def pdf_download(page_texts: list[str]) -> tuple[list[str], list[Path], Any]:
    """A fake download that writes a real PDF; records URLs and dest paths."""
    urls: list[str] = []
    dests: list[Path] = []

    def download(url: str, dest: Path) -> None:
        urls.append(url)
        dests.append(dest)
        write_pdf(dest, page_texts)

    return urls, dests, download


# --- book_url -----------------------------------------------------------------


def test_book_url_joins_and_percent_encodes() -> None:
    assert (
        book_url("http://pi:8081", "learning-go.pdf")
        == "http://pi:8081/private/books/learning-go.pdf"
    )
    # Trailing slash tolerated; non-ASCII / spaces are percent-encoded.
    assert (
        book_url("http://pi:8081/", "日本 語.pdf")
        == "http://pi:8081/private/books/%E6%97%A5%E6%9C%AC%20%E8%AA%9E.pdf"
    )


# --- ingest_book ---------------------------------------------------------------


def test_ingest_book_records_the_pi_canonical_path_not_the_temp_path() -> None:
    store = FakeStore()
    urls, dests, download = pdf_download(["Goroutines are lightweight threads."])

    result = ingest_book(
        PAYLOAD,
        BASE_URL,
        store,  # type: ignore[arg-type]
        FakeEmbedder(),  # type: ignore[arg-type]
        download=download,
    )

    assert result.chunk_count >= 1
    assert urls == [f"{BASE_URL}/private/books/learning-go.pdf"]
    (title, file_path, chunks) = store.replace_calls[0]
    assert title == "Learning Go"  # payload title, not the filename stem
    # D-25 (4): books.file_path is the Pi-canonical identity key.
    assert file_path == "/data/books/learning-go.pdf"
    assert file_path != str(dests[0])
    assert chunks


def test_ingest_book_removes_the_temp_copy_on_success() -> None:
    _, dests, download = pdf_download(["Some content."])

    ingest_book(
        PAYLOAD,
        BASE_URL,
        FakeStore(),  # type: ignore[arg-type]
        FakeEmbedder(),  # type: ignore[arg-type]
        download=download,
    )

    assert not dests[0].exists()
    assert not dests[0].parent.exists()  # 生ファイル非永続


def test_ingest_book_pdf_extraction_failure_is_permanent_and_cleans_up() -> None:
    """A broken/empty PDF is deterministic: PdfExtractionError is wrapped

    into PermanentJobError so the job fails terminally instead of burning
    the 3 attempts. The temp copy is removed either way.
    """
    store = FakeStore()
    _, dests, download = pdf_download(["", ""])  # blank pages → no chunks

    with pytest.raises(PermanentJobError) as excinfo:
        ingest_book(
            PAYLOAD,
            BASE_URL,
            store,  # type: ignore[arg-type]
            FakeEmbedder(),  # type: ignore[arg-type]
            download=download,
        )

    assert isinstance(excinfo.value.__cause__, PdfExtractionError)
    assert not dests[0].parent.exists()
    assert store.replace_calls == []  # nothing written


def test_ingest_book_embedding_failure_stays_retryable() -> None:
    """EmbeddingError (e.g. Ollama down) must NOT be wrapped as permanent."""

    class DownEmbedder:
        def embed(self, texts: Sequence[str]) -> list[list[float]]:
            raise EmbeddingError("cannot reach Ollama")

        def embed_one(self, text: str) -> list[float]:
            return self.embed([text])[0]

    _, _, download = pdf_download(["Some content that chunks fine."])

    with pytest.raises(EmbeddingError):
        ingest_book(
            PAYLOAD,
            BASE_URL,
            FakeStore(),  # type: ignore[arg-type]
            DownEmbedder(),  # type: ignore[arg-type]
            download=download,
        )


def test_ingest_book_download_failure_propagates_and_cleans_up() -> None:
    dirs: list[Path] = []

    def download(url: str, dest: Path) -> None:
        dirs.append(dest.parent)
        raise OSError("connection refused")

    with pytest.raises(OSError):
        ingest_book(
            PAYLOAD,
            BASE_URL,
            FakeStore(),  # type: ignore[arg-type]
            FakeEmbedder(),  # type: ignore[arg-type]
            download=download,
        )

    assert not dirs[0].exists()


# --- download_book --------------------------------------------------------------


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="http://pi:8081/private/books/x.pdf",
        code=code,
        msg="error",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )


def test_download_book_404_is_permanent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_urlopen(request: object, timeout: float = 0.0) -> object:
        raise _http_error(404)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(PermanentJobError, match="404"):
        download_book("http://pi:8081/private/books/x.pdf", tmp_path / "x.pdf")


def test_download_book_other_http_errors_stay_retryable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fake_urlopen(request: object, timeout: float = 0.0) -> object:
        raise _http_error(500)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(urllib.error.HTTPError):
        download_book("http://pi:8081/private/books/x.pdf", tmp_path / "x.pdf")


# --- default_book_handler --------------------------------------------------------


def test_default_book_handler_rejects_a_non_http_base_url() -> None:
    """The scheme check fires before anything touches the DB or env; the

    caller (worker.main) downgrades this to "book_ingest disabled" so the
    night's transcription survives the misconfiguration.
    """
    with pytest.raises(ValueError, match="BOOKS_PRIVATE_BASE_URL"):
        default_book_handler("ftp://pi:8081", None)  # type: ignore[arg-type]
