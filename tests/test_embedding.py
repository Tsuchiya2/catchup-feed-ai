"""Tests for the Ollama embedding client (HTTP layer injected, no network)."""

import pytest

from pulse_books.embedding import EMBEDDING_DIM, OllamaEmbedder
from pulse_books.errors import EmbeddingError


def vector(seed: float) -> list[float]:
    """A deterministic EMBEDDING_DIM-wide vector."""
    return [seed] + [0.0] * (EMBEDDING_DIM - 1)


class FakePost:
    """Records /api/embed calls and answers with deterministic vectors."""

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.dim = dim

    def __call__(self, url: str, body: dict[str, object]) -> object:
        self.calls.append((url, body))
        inputs = body["input"]
        assert isinstance(inputs, list)
        return {"embeddings": [[float(i)] + [0.0] * (self.dim - 1) for i in range(len(inputs))]}


def test_embed_batches_and_preserves_order() -> None:
    post = FakePost()
    embedder = OllamaEmbedder(batch_size=3, post=post)

    vectors = embedder.embed([f"text-{i}" for i in range(7)])

    assert len(vectors) == 7
    assert [len(v) for v in vectors] == [EMBEDDING_DIM] * 7
    # 7 texts / batch 3 -> 3 calls of sizes 3, 3, 1.
    batch_inputs = [call[1]["input"] for call in post.calls]
    assert batch_inputs == [
        ["text-0", "text-1", "text-2"],
        ["text-3", "text-4", "text-5"],
        ["text-6"],
    ]


def test_embed_sends_model_and_hits_api_embed() -> None:
    post = FakePost()
    embedder = OllamaEmbedder(host="http://localhost:11434/", model="bge-m3", post=post)

    embedder.embed(["hello"])

    url, body = post.calls[0]
    assert url == "http://localhost:11434/api/embed"
    assert body["model"] == "bge-m3"


def test_wrong_dimension_fails_fast() -> None:
    """The D-12 guard: a non-1024 vector means the wrong model is loaded."""
    embedder = OllamaEmbedder(post=FakePost(dim=768))

    with pytest.raises(EmbeddingError, match="768 != 1024.*wrong model"):
        embedder.embed(["hello"])


def test_vector_count_mismatch_raises() -> None:
    def post(url: str, body: dict[str, object]) -> object:
        return {"embeddings": [vector(1.0)]}  # one vector for two inputs

    embedder = OllamaEmbedder(post=post)

    with pytest.raises(EmbeddingError, match="1 vectors for 2 inputs"):
        embedder.embed(["a", "b"])


def test_missing_embeddings_key_raises() -> None:
    def post(url: str, body: dict[str, object]) -> object:
        return {"error": "model not found"}

    embedder = OllamaEmbedder(post=post)

    with pytest.raises(EmbeddingError, match="no 'embeddings' list"):
        embedder.embed(["a"])


def test_embed_one_returns_single_vector() -> None:
    embedder = OllamaEmbedder(post=FakePost())

    result = embedder.embed_one("query")

    assert len(result) == EMBEDDING_DIM


def test_invalid_batch_size_rejected() -> None:
    with pytest.raises(ValueError, match="batch_size"):
        OllamaEmbedder(batch_size=0)
