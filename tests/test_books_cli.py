"""Tests for the pulse-books ingest/search orchestration (fakes, tiny real PDF)."""

from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from pulse_books import cli
from pulse_books.db import Chunk, IngestResult, SearchHit
from pulse_books.embedding import EMBEDDING_DIM
from pulse_books.errors import PdfExtractionError

MakePdf = Callable[[list[str]], Path]


class FakeEmbedder:
    """Deterministic embedder: vector[0] encodes the call order."""

    def __init__(self) -> None:
        self.embedded: list[str] = []

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            self.embedded.append(text)
            vectors.append([float(len(self.embedded))] + [0.0] * (EMBEDDING_DIM - 1))
        return vectors

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class FakeStore:
    def __init__(self) -> None:
        self.replace_calls: list[tuple[str, str, list[Chunk]]] = []
        self.search_calls: list[tuple[list[float], int]] = []
        self.hits: list[SearchHit] = []

    def replace_book(self, title: str, file_path: str, chunks: Sequence[Chunk]) -> IngestResult:
        self.replace_calls.append((title, file_path, list(chunks)))
        return IngestResult(book_id=1, chunk_count=len(chunks), replaced=False)

    def search(self, query_embedding: Sequence[float], top_k: int = 5) -> list[SearchHit]:
        self.search_calls.append((list(query_embedding), top_k))
        return self.hits


def test_ingest_extracts_chunks_embeds_and_stores(make_pdf: MakePdf) -> None:
    pdf = make_pdf(["Goroutines are lightweight threads.", "Channels connect goroutines."])
    store = FakeStore()
    embedder = FakeEmbedder()

    result = cli.ingest(pdf, "Learning Go", store, embedder)  # type: ignore[arg-type]

    assert result.chunk_count >= 1
    (title, file_path, chunks) = store.replace_calls[0]
    assert title == "Learning Go"
    assert file_path == str(pdf.resolve())
    # Every stored chunk was embedded, pairing text with its vector.
    assert [c.content for c in chunks] == embedder.embedded
    assert all(len(list(c.embedding)) == EMBEDDING_DIM for c in chunks)
    assert "Goroutines are lightweight threads." in " ".join(c.content for c in chunks)


def test_ingest_title_defaults_to_file_stem(make_pdf: MakePdf) -> None:
    pdf = make_pdf(["Some content for the default title test."])
    renamed = pdf.with_name("learning-go.pdf")
    pdf.rename(renamed)
    store = FakeStore()

    cli.ingest(renamed, None, store, FakeEmbedder())  # type: ignore[arg-type]

    assert store.replace_calls[0][0] == "learning-go"


def test_ingest_empty_pdf_raises_before_touching_db(make_pdf: MakePdf) -> None:
    pdf = make_pdf(["", ""])
    store = FakeStore()

    with pytest.raises(PdfExtractionError):
        cli.ingest(pdf, None, store, FakeEmbedder())  # type: ignore[arg-type]

    assert store.replace_calls == []


def test_search_embeds_query_and_passes_top_k() -> None:
    store = FakeStore()
    store.hits = [
        SearchHit(
            book_id=1, book_title="Learning Go", position=3, content="channels", similarity=0.9
        )
    ]

    hits = cli.search("what are channels", 7, store, FakeEmbedder())  # type: ignore[arg-type]

    assert hits == store.hits
    assert store.search_calls[0][1] == 7
    assert len(store.search_calls[0][0]) == EMBEDDING_DIM


def test_format_hit_truncates_long_content() -> None:
    hit = SearchHit(book_id=2, book_title="本", position=0, content="あ" * 500, similarity=0.812)

    line = cli.format_hit(1, hit)

    assert "similarity=0.812" in line
    assert "本" in line
    assert len(line) < 350
    assert line.endswith("…")


def test_cli_ingest_smoke(make_pdf: MakePdf, monkeypatch: pytest.MonkeyPatch) -> None:
    """main() wires argparse -> ingest with the real chunker and fakes at the edges."""
    pdf = make_pdf(["End to end smoke test content."])
    store = FakeStore()

    monkeypatch.setenv("DATABASE_URL", "postgresql://ignored/ignored")

    class FakeConn:
        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: FakeConn())
    monkeypatch.setattr(cli, "BookStore", lambda conn: store)
    monkeypatch.setattr(cli, "OllamaEmbedder", lambda **kwargs: FakeEmbedder())

    exit_code = cli.main(["ingest", str(pdf), "--title", "Smoke"])

    assert exit_code == 0
    assert store.replace_calls[0][0] == "Smoke"


def test_cli_search_reports_schema_missing_as_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing books table exits 1 with the operator-facing message."""
    from pulse_books.errors import SchemaMissingError

    class BrokenStore(FakeStore):
        def search(self, query_embedding: Sequence[float], top_k: int = 5) -> list[SearchHit]:
            raise SchemaMissingError('relation "books" does not exist')

    monkeypatch.setenv("DATABASE_URL", "postgresql://ignored/ignored")

    class FakeConn:
        def __enter__(self) -> "FakeConn":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda *a, **k: FakeConn())
    monkeypatch.setattr(cli, "BookStore", lambda conn: BrokenStore())
    monkeypatch.setattr(cli, "OllamaEmbedder", lambda **kwargs: FakeEmbedder())

    assert cli.main(["search", "anything"]) == 1
