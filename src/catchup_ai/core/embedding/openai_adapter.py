"""OpenAI embedding service implementation.

Uses text-embedding-3-small model for generating embeddings.
Includes retry logic for handling transient failures.
"""

import random
import time

import structlog
from openai import OpenAI
from openai import RateLimitError as OpenAIRateLimitError

from catchup_ai.infra.config.settings import get_settings

from .service import (
    EmbeddingError,
    EmbeddingResult,
    EmbeddingService,
    RateLimitError,
)

logger = structlog.get_logger()


class OpenAIEmbeddingAdapter(EmbeddingService):
    """OpenAI implementation of EmbeddingService.

    Uses text-embedding-3-small by default (1536 dimensions).
    Handles rate limiting with exponential backoff.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key. If None, uses settings.
            model: Model name. If None, uses settings.
        """
        settings = get_settings()
        self._api_key = api_key or settings.openai.api_key
        self._model = model or settings.openai.embedding_model
        self._client = OpenAI(api_key=self._api_key)
        self._logger = logger.bind(service="openai_embedding", model=self._model)

    def embed_text(self, text: str) -> EmbeddingResult:
        """Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            EmbeddingResult with the vector and metadata

        Raises:
            EmbeddingError: If embedding fails after retries
        """
        return self._embed_with_retry([text])[0]

    def embed_texts(self, texts: list[str]) -> list[EmbeddingResult]:
        """Generate embeddings for multiple texts (batch).

        OpenAI supports up to 2048 texts per request.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResults in the same order

        Raises:
            EmbeddingError: If embedding fails after retries
        """
        if not texts:
            return []

        # OpenAI batch limit is 2048
        batch_size = 2048
        results: list[EmbeddingResult] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_results = self._embed_with_retry(batch)
            results.extend(batch_results)

        return results

    def _embed_with_retry(self, texts: list[str]) -> list[EmbeddingResult]:
        """Embed texts with retry logic for transient failures.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResults

        Raises:
            EmbeddingError: If all retries fail
        """
        # TODO(human): Implement retry strategy
        # This function should call _call_api and handle failures
        # Consider: max retries, backoff strategy, which errors to retry
        delay = self._calculate_retry_delay(attempt=0)  # Initial delay
        max_retries = 3

        for attempt in range(max_retries):
            try:
                return self._call_api(texts)
            except OpenAIRateLimitError as e:
                if attempt == max_retries - 1:
                    raise RateLimitError() from e
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

        # Should not reach here, but satisfy type checker
        raise EmbeddingError("Unexpected retry loop exit")

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate delay before next retry attempt.

        Consider these approaches:
        1. Fixed delay: Always wait the same amount (simple but not optimal)
        2. Exponential backoff: 2^attempt seconds (grows quickly)
        3. Exponential with jitter: Add randomness to prevent thundering herd
        4. Capped exponential: Don't exceed a maximum delay

        Args:
            attempt: The attempt number (0-indexed)

        Returns:
            Delay in seconds before the next retry
        """
        # Placeholder - replace with your implementation
        base_delay = 2 ** attempt
        max_delay = 30.0
        delay = min(base_delay, max_delay)
        return delay * random.uniform(0.5, 1.5)

    def _call_api(self, texts: list[str]) -> list[EmbeddingResult]:
        """Call OpenAI API to generate embeddings.

        Args:
            texts: List of texts to embed

        Returns:
            List of EmbeddingResults
        """
        self._logger.debug("Calling OpenAI API", text_count=len(texts))

        response = self._client.embeddings.create(
            input=texts,
            model=self._model,
        )

        results = []
        for data in response.data:
            results.append(
                EmbeddingResult(
                    vector=data.embedding,
                    model=response.model,
                    provider="openai",
                    tokens_used=response.usage.total_tokens // len(texts),
                )
            )

        self._logger.info(
            "Embeddings generated",
            count=len(results),
            total_tokens=response.usage.total_tokens,
        )

        return results
