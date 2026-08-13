"""
title: Pulse Book Search
author: pulse
version: 0.1.0
license: AGPL-3.0-or-later
description: 取り込み済み書籍(Pi の book_chunks)を cosine 類似検索して抜粋を返す(A-23)
requirements: psycopg[binary]>=3.2
"""

# Open WebUI Tool — 管理画面 Workspace → Tools にこのファイルの内容を
# そのまま貼り付けて登録する(手順は README「Open WebUI への Tool 登録手順」)。
#
# 単一ファイル自己完結: Open WebUI のサンドボックスに貼り付けて動かすため
# pulse_books を import できない。SEARCH_SQL / 1024 次元ガードは
# src/pulse_books/{db,embedding}.py と同じ意味論を複製しており、
# tests/test_openwebui_tool.py がその一致を検証する。
#
# C-12(プライバシー分界): このツールが通信するのは Ollama(Mac ローカル、
# コンテナからは host.docker.internal)と Pi の PostgreSQL(Tailscale)のみ。
# 書籍データ・クエリはクラウドに出ない。

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import psycopg
from pydantic import BaseModel, Field

# book_chunks.embedding は vector(1024) — D-12(bge-m3)。別の幅は
# モデルの設定ミスなので即エラーにする(pulse_books.embedding と同じガード)。
EMBEDDING_DIM = 1024

_EMBED_TIMEOUT_SECONDS = 60.0
_CONNECT_TIMEOUT_SECONDS = 10

# pulse_books.db.SEARCH_SQL の複製(意味論を変えないこと)。
# `<=>` は pgvector の cosine distance、similarity = 1 - distance。
SEARCH_SQL = """
SELECT c.book_id, b.title, c.position, c.content,
       1 - (c.embedding <=> %(query)s::vector) AS similarity
FROM book_chunks c
JOIN books b ON b.id = c.book_id
WHERE c.embedding IS NOT NULL
ORDER BY c.embedding <=> %(query)s::vector, c.book_id, c.position
LIMIT %(top_k)s"""

# post(url, json_body) -> parsed JSON response. Injectable for tests.
PostJson = Callable[[str, dict[str, object]], object]


class BookSearchError(Exception):
    """Embedding 呼び出しまたは検索が続行不能(メッセージは LLM に返される)。"""


@dataclass(frozen=True, slots=True)
class SearchHit:
    book_id: int
    book_title: str
    position: int
    content: str
    similarity: float


def _post_json(url: str, body: dict[str, object]) -> object:
    """POST a JSON body and parse the JSON response (stdlib only)."""
    request = urllib.request.Request(  # noqa: S310 — host comes from local valves
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_EMBED_TIMEOUT_SECONDS) as resp:  # noqa: S310
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise BookSearchError(f"Ollama returned HTTP {exc.code} for {url}: {detail}") from exc
    except OSError as exc:
        raise BookSearchError(
            f"cannot reach Ollama at {url}: {exc} — OLLAMA_HOST valve misconfigured?"
        ) from exc
    except ValueError as exc:
        raise BookSearchError(f"Ollama returned invalid JSON from {url}: {exc}") from exc


def format_vector(vector: Sequence[float]) -> str:
    """Render a vector as a pgvector text literal: [0.1,0.2,...]."""
    return "[" + ",".join(str(float(x)) for x in vector) + "]"


def embed_query(host: str, model: str, query: str, post: PostJson | None = None) -> list[float]:
    """Embed one query via Ollama /api/embed, with the D-12 dimension guard."""
    post_json = post if post is not None else _post_json
    payload = post_json(host.rstrip("/") + "/api/embed", {"model": model, "input": [query]})
    if not isinstance(payload, dict):
        raise BookSearchError(f"unexpected /api/embed response type: {type(payload).__name__}")
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != 1:
        raise BookSearchError(f"/api/embed did not return exactly one vector: {payload!r:.500}")
    raw = embeddings[0]
    if not isinstance(raw, list) or not all(isinstance(x, int | float) for x in raw):
        raise BookSearchError("/api/embed vector is not a list of numbers")
    if len(raw) != EMBEDDING_DIM:
        raise BookSearchError(
            f"embedding dimension {len(raw)} != {EMBEDDING_DIM} from model {model!r} — "
            "book_chunks is vector(1024) (D-12: bge-m3); wrong model configured?"
        )
    return [float(x) for x in raw]


def search_chunks(
    conn: psycopg.Connection[Any], query_embedding: Sequence[float], top_k: int
) -> list[SearchHit]:
    """Cosine-similarity search over all book chunks (SEARCH_SQL)."""
    rows = conn.execute(
        SEARCH_SQL,
        {"query": format_vector(query_embedding), "top_k": top_k},
    ).fetchall()
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


def format_results(hits: Sequence[SearchHit]) -> str:
    """LLM が引用しやすい形に整形する(書名・チャンク位置・類似度・本文)。"""
    if not hits:
        return (
            "該当する書籍抜粋は見つかりませんでした"
            "(書籍が未取り込みか、質問が取り込み済み書籍の範囲外)。"
        )
    parts = [
        f"書籍検索結果 {len(hits)} 件(類似度の高い順)。"
        "回答では出典の書名を『』で明記すること。"
    ]
    for rank, hit in enumerate(hits, start=1):
        parts.append(
            f"[{rank}]『{hit.book_title}』チャンク{hit.position}"
            f"(類似度 {hit.similarity:.3f})\n{hit.content.strip()}"
        )
    return "\n\n".join(parts)


class Tools:
    class Valves(BaseModel):
        DATABASE_URL: str = Field(
            default="",
            description=(
                "Pi の PostgreSQL DSN(Tailscale 経由)。Mac の ~/pulse/.env の "
                "DATABASE_URL と同じ値を設定する(必須)"
            ),
        )
        OLLAMA_HOST: str = Field(
            default="http://host.docker.internal:11434",
            description="Ollama の URL。Open WebUI コンテナからは host.docker.internal",
        )
        EMBEDDING_MODEL: str = Field(
            default="bge-m3",
            description=(
                "embedding モデル(D-12: bge-m3、1024次元)。変更は book_chunks の"
                "再生成(全書籍の再取り込み)を伴う"
            ),
        )
        TOP_K: int = Field(
            default=5,
            ge=1,
            le=20,
            description="返すチャンク数(上限20: 誤設定で全チャンクが LLM に流れるのを防ぐ)",
        )

    def __init__(self) -> None:
        self.valves = self.Valves()

    def search_books(self, query: str) -> str:
        """
        取り込み済みの書籍(技術書)の本文から、質問に関連する抜粋を意味検索する。
        書籍の内容・主張・用語・特定の本について質問されたら、まずこのツールを呼び、
        返された抜粋だけを根拠に、出典の書名を挙げて回答すること。

        :param query: 検索クエリ。ユーザーの質問の要点を表す日本語の文でよい
        :return: 関連する書籍抜粋(書名・チャンク位置・類似度つき)
        """
        if not self.valves.DATABASE_URL:
            return "書籍検索は未設定です: この Tool の Valves で DATABASE_URL を設定してください。"
        try:
            embedding = embed_query(
                self.valves.OLLAMA_HOST, self.valves.EMBEDDING_MODEL, query
            )
            with psycopg.connect(
                self.valves.DATABASE_URL,
                autocommit=True,
                connect_timeout=_CONNECT_TIMEOUT_SECONDS,
            ) as conn:
                hits = search_chunks(conn, embedding, self.valves.TOP_K)
        except (BookSearchError, psycopg.Error) as exc:
            return f"書籍検索に失敗しました: {exc}"
        return format_results(hits)
