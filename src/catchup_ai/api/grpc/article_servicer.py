"""gRPC Article AI Servicer implementation.

Handles incoming gRPC requests and delegates to domain services.

Architecture:
    - catchup-ai: Embedding generation (this service)
    - catchup-feed-backend: Embedding storage & similarity search

Flow:
    1. Backend calls EmbedArticle → catchup-ai generates embedding → returns vector
    2. Backend stores embedding in article_embeddings table
    3. For SearchSimilar, catchup-ai embeds query → calls backend's SearchSimilar
"""

import grpc
import structlog

from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc
from catchup_ai.core.embedding import (
    ArticleEmbeddingInput,
    EmbeddingError,
    EmbeddingService,
    create_embedding_service,
)
from catchup_ai.infra.config.settings import get_settings
from catchup_ai.infra.grpc import EmbeddingClient

logger = structlog.get_logger()


class ArticleAIServicer(article_pb2_grpc.ArticleAIServicer):
    """gRPC servicer for ArticleAI service.

    Implements all RPC methods defined in article.proto.
    Uses factory pattern to create embedding service based on configuration.

    Architecture note:
        This servicer generates embeddings but does NOT store them.
        Storage is delegated to catchup-feed-backend via EmbeddingClient.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService | None = None,
        embedding_client: EmbeddingClient | None = None,
    ):
        """Initialize servicer with required services.

        Args:
            embedding_service: Optional embedding service. If None, creates
                               one using the factory based on configuration.
            embedding_client: Optional backend client. If None, creates one
                              using default settings.
        """
        # Use factory to create service based on EMBEDDING_PROVIDER config
        self._embedding_service = embedding_service or create_embedding_service()
        self._embedding_client = embedding_client or EmbeddingClient()
        self._settings = get_settings()
        self._logger = logger.bind(servicer="article_ai")

    def EmbedArticle(
        self,
        request: article_pb2.EmbedArticleRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.EmbedArticleResponse:
        """Generate embedding for an article.

        Note: This method generates embeddings but does NOT store them.
        The caller (backend) is responsible for storing via EmbeddingService.

        Args:
            request: EmbedArticleRequest with article data
            context: gRPC context

        Returns:
            EmbedArticleResponse with embedding vector and metadata
        """
        # Determine embedding type (default to "content")
        embedding_type = request.embedding_type if request.embedding_type else "content"

        self._logger.info(
            "EmbedArticle request",
            article_id=request.article_id,
            title=request.title[:50] if request.title else "",
            embedding_type=embedding_type,
        )

        try:
            # Generate embedding
            article_input = ArticleEmbeddingInput(
                article_id=request.article_id,
                title=request.title,
                content=request.content,
                url=request.url or None,
            )
            result = self._embedding_service.embed_article(article_input)

            # Return embedding to caller (backend will store it)
            self._logger.info(
                "Embedding generated successfully",
                article_id=request.article_id,
                dimension=result.dimension,
                provider=result.provider,
                model=result.model,
            )

            return article_pb2.EmbedArticleResponse(
                article_id=request.article_id,
                success=True,
                embedding_dimension=result.dimension,
                embedding=result.vector,
                provider=result.provider,
                model=result.model,
                embedding_type=embedding_type,
            )

        except EmbeddingError as e:
            self._logger.error(
                "Embedding failed",
                article_id=request.article_id,
                error=str(e),
            )
            return article_pb2.EmbedArticleResponse(
                article_id=request.article_id,
                success=False,
                error_message=str(e),
            )

    def SearchSimilar(
        self,
        request: article_pb2.SearchSimilarRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.SearchSimilarResponse:
        """Search for similar articles.

        Flow:
            1. If query text provided: embed it first
            2. Call backend's SearchSimilar with embedding vector
            3. Backend returns article IDs with similarity scores

        Note: Article details (title, url, snippet) are not available from
        backend's SearchSimilar response. The caller should fetch them separately.

        Args:
            request: SearchSimilarRequest with query or article_id
            context: gRPC context

        Returns:
            SearchSimilarResponse with similar articles
        """
        limit = request.limit if request.limit > 0 else 10

        self._logger.info(
            "SearchSimilar request",
            search_by=request.WhichOneof("search_by"),
            limit=limit,
        )

        try:
            # Determine search method based on request
            if request.HasField("query"):
                # Search by text query - embed first, then call backend
                embedding_result = self._embedding_service.embed_text(request.query)
                query_vector = embedding_result.vector
            elif request.HasField("article_id"):
                # Search by article ID - need to get embedding from backend first
                # For now, return error as this requires backend's GetEmbeddings
                context.set_code(grpc.StatusCode.UNIMPLEMENTED)
                context.set_details(
                    "Search by article_id not yet implemented. "
                    "Use query text instead."
                )
                return article_pb2.SearchSimilarResponse()
            else:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Either query or article_id must be provided")
                return article_pb2.SearchSimilarResponse()

            # Call backend's SearchSimilar
            results = self._embedding_client.search_similar(
                embedding=list(query_vector),
                embedding_type="content",  # Default to content embeddings
                limit=limit,
            )

            # Convert to response
            # Note: Backend only returns article_id and similarity.
            # Title, URL, snippet are not available from backend's response.
            articles = [
                article_pb2.SimilarArticle(
                    article_id=r.article_id,
                    title="",  # Not available from backend
                    url="",  # Not available from backend
                    similarity_score=r.similarity,
                    snippet="",  # Not available from backend
                )
                for r in results
            ]

            self._logger.info(
                "SearchSimilar completed",
                results_count=len(articles),
            )

            return article_pb2.SearchSimilarResponse(articles=articles)

        except EmbeddingError as e:
            self._logger.error("SearchSimilar embedding failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Embedding generation failed: {e}")
            return article_pb2.SearchSimilarResponse()

        except Exception as e:
            self._logger.error("SearchSimilar failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return article_pb2.SearchSimilarResponse()

    def QueryArticles(
        self,
        request: article_pb2.QueryArticlesRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.QueryArticlesResponse:
        """RAG-based question answering (placeholder for Week 5-6).

        Args:
            request: QueryArticlesRequest
            context: gRPC context

        Returns:
            QueryArticlesResponse
        """
        # TODO: Implement in Week 5-6 (RAG pipeline)
        self._logger.info("QueryArticles request (not yet implemented)")
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("QueryArticles will be implemented in Week 5-6")
        return article_pb2.QueryArticlesResponse()

    def GenerateWeeklySummary(
        self,
        request: article_pb2.GenerateWeeklySummaryRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.GenerateWeeklySummaryResponse:
        """Generate weekly summary (placeholder for Week 5-6).

        Args:
            request: GenerateWeeklySummaryRequest
            context: gRPC context

        Returns:
            GenerateWeeklySummaryResponse
        """
        # TODO: Implement in Week 5-6 (RAG pipeline)
        self._logger.info("GenerateWeeklySummary request (not yet implemented)")
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("GenerateWeeklySummary will be implemented in Week 5-6")
        return article_pb2.GenerateWeeklySummaryResponse()

    def ClassifyArticle(
        self,
        request: article_pb2.ClassifyArticleRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.ClassifyArticleResponse:
        """Classify article category (placeholder for Week 7-8).

        Args:
            request: ClassifyArticleRequest
            context: gRPC context

        Returns:
            ClassifyArticleResponse
        """
        # TODO: Implement in Week 7-8 (Fine-tuning)
        self._logger.info("ClassifyArticle request (not yet implemented)")
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("ClassifyArticle will be implemented in Week 7-8")
        return article_pb2.ClassifyArticleResponse()
