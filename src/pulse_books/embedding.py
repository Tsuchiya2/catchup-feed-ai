"""Ollama embedding client (D-12: bge-m3, 1024 dimensions).

Plain-HTTP call to POST {OLLAMA_HOST}/api/embed using the standard library
(same style as the transcribe worker's downloads — no new SDK dependency).
C-12: book text must never leave the Mac/Pi; this module only ever talks
to the configured Ollama host (default: localhost).

The dimension guard is deliberate and strict: book_chunks.embedding is
vector(1024), and a differently-sized vector means the wrong model is
configured. Failing fast here prevents writing a half-ingested book with
embeddings from a mismatched model.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

import structlog

from pulse_books.errors import EmbeddingError

logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(__name__)

# book_chunks.embedding is vector(1024) — D-12 (bge-m3). Any other width is
# a model mix-up, not a tolerable variation.
EMBEDDING_DIM = 1024

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_MODEL = "bge-m3"
DEFAULT_BATCH_SIZE = 32

_REQUEST_TIMEOUT_SECONDS = 300.0

# post(url, json_body) -> parsed JSON response. Injectable for tests.
PostJson = Callable[[str, dict[str, object]], object]


def _post_json(url: str, body: dict[str, object]) -> object:
    """POST a JSON body and parse the JSON response (stdlib only)."""
    request = urllib.request.Request(  # noqa: S310 — host comes from local config
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as resp:  # noqa: S310
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise EmbeddingError(f"Ollama returned HTTP {exc.code} for {url}: {detail}") from exc
    except OSError as exc:
        raise EmbeddingError(
            f"cannot reach Ollama at {url}: {exc} — is `ollama serve` running?"
        ) from exc
    except ValueError as exc:
        raise EmbeddingError(f"Ollama returned invalid JSON from {url}: {exc}") from exc


class OllamaEmbedder:
    """Batching front end for Ollama's /api/embed endpoint."""

    def __init__(
        self,
        host: str = DEFAULT_OLLAMA_HOST,
        model: str = DEFAULT_MODEL,
        batch_size: int = DEFAULT_BATCH_SIZE,
        post: PostJson = _post_json,
    ) -> None:
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        self._url = host.rstrip("/") + "/api/embed"
        self._model = model
        self._batch_size = batch_size
        self._post = post

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed texts in batches, preserving order.

        Raises EmbeddingError on transport failures, malformed responses,
        or any vector that is not exactly EMBEDDING_DIM wide.
        """
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = list(texts[start : start + self._batch_size])
            vectors.extend(self._embed_batch(batch))
            logger.debug(
                "embedding: batch done",
                model=self._model,
                done=len(vectors),
                total=len(texts),
            )
        return vectors

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text (search queries)."""
        return self.embed([text])[0]

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload = self._post(self._url, {"model": self._model, "input": batch})
        return _parse_embeddings(payload, expected_count=len(batch), model=self._model)


def _parse_embeddings(payload: object, expected_count: int, model: str) -> list[list[float]]:
    """Validate an /api/embed response: shape, count, and dimension."""
    if not isinstance(payload, dict):
        raise EmbeddingError(f"unexpected /api/embed response type: {type(payload).__name__}")
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list):
        raise EmbeddingError(f"/api/embed response has no 'embeddings' list: {payload!r:.500}")
    if len(embeddings) != expected_count:
        raise EmbeddingError(
            f"/api/embed returned {len(embeddings)} vectors for {expected_count} inputs"
        )

    vectors: list[list[float]] = []
    for index, raw in enumerate(embeddings):
        if not isinstance(raw, list) or not all(isinstance(x, int | float) for x in raw):
            raise EmbeddingError(f"/api/embed vector {index} is not a list of numbers")
        if len(raw) != EMBEDDING_DIM:
            raise EmbeddingError(
                f"embedding dimension {len(raw)} != {EMBEDDING_DIM} from model {model!r} — "
                "book_chunks is vector(1024) (D-12: bge-m3); wrong model configured?"
            )
        vectors.append([float(x) for x in raw])
    return vectors
