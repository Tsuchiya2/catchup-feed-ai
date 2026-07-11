"""Tests for the Open WebUI book-search tool (openwebui/book_search_tool.py).

The tool file is self-contained (it gets pasted into Open WebUI's admin UI
and cannot import pulse_books), so it duplicates SEARCH_SQL and the D-12
dimension guard. The parity tests here pin that duplication to the
originals in src/pulse_books. DB and Ollama are mocked throughout — the
Open WebUI runtime itself never enters CI.
"""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from pulse_books import db as books_db
from pulse_books import embedding as books_embedding

_TOOL_PATH = Path(__file__).resolve().parent.parent / "openwebui" / "book_search_tool.py"


def _load_tool_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("book_search_tool", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool_module()


def vector(seed: float) -> list[float]:
    """A deterministic EMBEDDING_DIM-wide vector."""
    return [seed] + [0.0] * (tool.EMBEDDING_DIM - 1)


class FakePost:
    """Records /api/embed calls and answers with a deterministic vector."""

    def __init__(self, dim: int | None = None) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.dim = dim if dim is not None else tool.EMBEDDING_DIM

    def __call__(self, url: str, body: dict[str, object]) -> object:
        self.calls.append((url, body))
        inputs = body["input"]
        assert isinstance(inputs, list)
        return {"embeddings": [[0.5] + [0.0] * (self.dim - 1) for _ in inputs]}


class FakeConnection:
    """Stands in for psycopg.Connection: records execute() and serves rows."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, object]]] = []

    def execute(self, sql: str, params: dict[str, object]) -> FakeConnection:
        self.calls.append((sql, params))
        return self

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


HIT_ROW = (1, "リーダブルコード", 42, "名前に情報を詰め込む。", 0.83)


# --- parity with src/pulse_books (the originals are the source of truth) ---


def test_search_sql_matches_pulse_books() -> None:
    assert tool.SEARCH_SQL == books_db.SEARCH_SQL


def test_embedding_dim_matches_pulse_books() -> None:
    assert tool.EMBEDDING_DIM == books_embedding.EMBEDDING_DIM


def test_format_vector_matches_pulse_books() -> None:
    values = [0.1, -2.0, 3]
    assert tool.format_vector(values) == books_db.format_vector(values)


def test_format_vector_matches_pulse_books_for_exponent_notation() -> None:
    """str(float) emits exponent notation for tiny values (1e-07); both sides must agree."""
    values = [1e-07, -2.5e-12, 1e20]
    assert tool.format_vector(values) == books_db.format_vector(values)
    assert tool.format_vector(values) == "[1e-07,-2.5e-12,1e+20]"


# --- embed_query ---


def test_embed_query_hits_api_embed_with_model() -> None:
    post = FakePost()

    result = tool.embed_query("http://host.docker.internal:11434/", "bge-m3", "命名", post=post)

    url, body = post.calls[0]
    assert url == "http://host.docker.internal:11434/api/embed"
    assert body == {"model": "bge-m3", "input": ["命名"]}
    assert len(result) == tool.EMBEDDING_DIM


def test_embed_query_wrong_dimension_fails_fast() -> None:
    """The D-12 guard: a non-1024 vector means the wrong model is loaded."""
    with pytest.raises(tool.BookSearchError, match="768 != 1024.*wrong model"):
        tool.embed_query("http://x", "bge-m3", "q", post=FakePost(dim=768))


def test_embed_query_rejects_missing_embeddings() -> None:
    with pytest.raises(tool.BookSearchError, match="exactly one vector"):
        tool.embed_query("http://x", "bge-m3", "q", post=lambda url, body: {"error": "nope"})


def test_embed_query_rejects_non_numeric_vector() -> None:
    with pytest.raises(tool.BookSearchError, match="not a list of numbers"):
        tool.embed_query("http://x", "bge-m3", "q", post=lambda url, body: {"embeddings": ["x"]})


# --- search_chunks ---


def test_search_chunks_binds_vector_literal_and_top_k() -> None:
    conn = FakeConnection(rows=[HIT_ROW])

    hits = tool.search_chunks(conn, [0.1, 0.2], top_k=3)

    sql, params = conn.calls[0]
    assert sql == tool.SEARCH_SQL
    assert params == {"query": "[0.1,0.2]", "top_k": 3}
    assert hits == [
        tool.SearchHit(
            book_id=1,
            book_title="リーダブルコード",
            position=42,
            content="名前に情報を詰め込む。",
            similarity=0.83,
        )
    ]


# --- format_results ---


def test_format_results_empty() -> None:
    assert "見つかりませんでした" in tool.format_results([])


def test_format_results_cites_title_position_similarity() -> None:
    hit = tool.SearchHit(
        book_id=1,
        book_title="リーダブルコード",
        position=42,
        content="  本文です  ",
        similarity=0.8312,
    )

    text = tool.format_results([hit])

    assert "『リーダブルコード』チャンク42(類似度 0.831)" in text
    assert "本文です" in text
    assert "書名" in text  # the citation instruction for the LLM


# --- Tools.search_books (wiring) ---


def _make_tools(database_url: str = "postgres://pi/db") -> Any:
    tools = tool.Tools()
    tools.valves = tool.Tools.Valves(DATABASE_URL=database_url)
    return tools


def test_search_books_end_to_end_with_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    connected: list[dict[str, object]] = []
    conn = FakeConnection(rows=[HIT_ROW])

    def fake_connect(dsn: str, **kwargs: object) -> FakeConnection:
        connected.append({"dsn": dsn, **kwargs})
        return conn

    monkeypatch.setattr(tool, "_post_json", FakePost())
    monkeypatch.setattr(tool.psycopg, "connect", fake_connect)

    answer = _make_tools().search_books("変数の命名")

    assert connected[0]["dsn"] == "postgres://pi/db"
    assert connected[0]["autocommit"] is True
    assert "『リーダブルコード』" in answer
    # TOP_K valve default reaches the SQL
    assert conn.calls[0][1]["top_k"] == 5


def test_search_books_without_database_url_explains_setup() -> None:
    answer = _make_tools(database_url="").search_books("q")

    assert "DATABASE_URL" in answer


def test_search_books_returns_error_string_on_embedding_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken_post(url: str, body: dict[str, object]) -> object:
        raise tool.BookSearchError("cannot reach Ollama")

    monkeypatch.setattr(tool, "_post_json", broken_post)

    answer = _make_tools().search_books("q")

    assert answer.startswith("書籍検索に失敗しました")
    assert "cannot reach Ollama" in answer


def test_valves_defaults_match_design() -> None:
    valves = tool.Tools.Valves()

    assert valves.OLLAMA_HOST == "http://host.docker.internal:11434"
    assert valves.EMBEDDING_MODEL == "bge-m3"
    assert valves.TOP_K == 5


def test_valves_top_k_is_capped() -> None:
    """le=20: a misconfigured TOP_K must not stream every chunk into the LLM."""
    with pytest.raises(ValueError):
        tool.Tools.Valves(TOP_K=21)
