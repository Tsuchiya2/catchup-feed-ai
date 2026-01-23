"""Voyage AI embedding service implementation.

Voyage AI is the embedding provider recommended by Anthropic for use with Claude.
https://www.voyageai.com/

Models available:
- voyage-3: General purpose, 1024 dimensions (recommended)
- voyage-3-lite: Faster, lower cost, 512 dimensions
- voyage-code-3: Optimized for code, 1024 dimensions

To use this adapter:
1. Get API key from https://dash.voyageai.com/
2. Set VOYAGE_API_KEY in .env
3. Set EMBEDDING_PROVIDER=voyage in .env
"""

import random
import time

import structlog

from catchup_ai.infra.config.settings import get_settings

from .service import (
    EmbeddingError,
    EmbeddingResult,
    EmbeddingService,
    RateLimitError,
)

logger = structlog.get_logger()


class VoyageEmbeddingAdapter(EmbeddingService):
    """Voyage AI implementation of EmbeddingService.

    Uses voyage-3 by default (1024 dimensions).
    API is similar to OpenAI, making it easy to switch.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """Initialize Voyage AI client.

        Args:
            api_key: Voyage API key. If None, uses settings.
            model: Model name. If None, uses settings.
        """
        settings = get_settings()
        self._api_key = api_key or settings.voyage.api_key
        self._model = model or settings.voyage.embedding_model
        self._base_url = "https://api.voyageai.com/v1"
        self._logger = logger.bind(service="voyage_embedding", model=self._model)

        if not self._api_key:
            raise EmbeddingError(
                "Voyage API key not configured. "
                "Set VOYAGE_API_KEY in .env or pass api_key parameter."
            )

        # Lazy import to avoid dependency when not using Voyage
        try:
            import httpx

            self._client = httpx.Client(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=60.0,
            )
        except ImportError:
            raise EmbeddingError(
                "httpx is required for Voyage AI. Install with: uv add httpx"
            )

    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text."""
        return self._embed_with_retry([text])[0]

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts (batch).

        Voyage supports up to 128 texts per request.
        """
        if not texts:
            return []

        # Voyage batch limit is 128
        batch_size = 128
        results: list[EmbeddingResult] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_results = self._embed_with_retry(batch)
            results.extend(batch_results)

        return results

    def _embed_with_retry(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed texts with retry logic."""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                return self._call_api(texts)
            except RateLimitError:
                if attempt == max_retries - 1:
                    raise
                delay = self._calculate_retry_delay(attempt)
                self._logger.warning(
                    "Rate limited, retrying",
                    attempt=attempt + 1,
                    delay=delay,
                )
                time.sleep(delay)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise EmbeddingError(f"Failed after {max_retries} attempts: {e}") from e
                delay = self._calculate_retry_delay(attempt)
                self._logger.warning(
                    "API error, retrying",
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(e),
                )
                time.sleep(delay)

        raise EmbeddingError("Unexpected retry loop exit")

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff + jitter."""
        base_delay = 2**attempt
        max_delay = 30.0
        delay = min(base_delay, max_delay)
        return delay * random.uniform(0.5, 1.5)

    def _call_api(self, texts: list[str]) -> list[EmbeddingResult]:
        """Call Voyage AI API to generate embeddings."""
        self._logger.debug("Calling Voyage AI API", text_count=len(texts))

        response = self._client.post(
            "/embeddings",
            json={
                "input": texts,
                "model": self._model,
            },
        )

        if response.status_code == 429:
            raise RateLimitError()

        if response.status_code != 200:
            raise EmbeddingError(
                f"Voyage API error: {response.status_code} - {response.text}"
            )

        data = response.json()

        results = []
        for item in data["data"]:
            results.append(
                EmbeddingResult(
                    vector=item["embedding"],
                    model=self._model,
                    provider="voyage",
                    tokens_used=data.get("usage", {}).get("total_tokens", 0)
                    // len(texts),
                )
            )

        self._logger.info(
            "Embeddings generated",
            count=len(results),
            total_tokens=data.get("usage", {}).get("total_tokens", 0),
        )

        return results

    def __del__(self):
        """Clean up HTTP client."""
        if hasattr(self, "_client"):
            self._client.close()
