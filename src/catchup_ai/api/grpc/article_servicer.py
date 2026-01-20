"""gRPC Article AI Servicer implementation.

Handles incoming gRPC requests and delegates to domain services.
"""

import grpc
import structlog

from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc
from catchup_ai.core.embedding import (
    ArticleEmbeddingInput,
    ArticleVectorRepository,
    EmbeddingError,
    OpenAIEmbeddingAdapter,
)
from catchup_ai.infra.db.session import get_session

logger = structlog.get_logger()


class ArticleAIServicer(article_pb2_grpc.ArticleAIServicer):
    """gRPC servicer for ArticleAI service.

    Implements all RPC methods defined in article.proto.
    """

    def __init__(self):
        """Initialize servicer with required services."""
        self._embedding_service = OpenAIEmbeddingAdapter()
        self._logger = logger.bind(servicer="article_ai")

    def EmbedArticle(
        self,
        request: article_pb2.EmbedArticleRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.EmbedArticleResponse:
        """Generate and store embedding for an article.

        Args:
            request: EmbedArticleRequest with article data
            context: gRPC context

        Returns:
            EmbedArticleResponse with success status
        """
        self._logger.info(
            "EmbedArticle request",
            article_id=request.article_id,
            title=request.title[:50] if request.title else "",
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

            # Store embedding in database
            with get_session() as session:
                repository = ArticleVectorRepository(session)
                success = repository.store_embedding(
                    article_id=request.article_id,
                    embedding=result.vector,
                )

            if success:
                return article_pb2.EmbedArticleResponse(
                    article_id=request.article_id,
                    success=True,
                    embedding_dimension=result.dimension,
                )
            else:
                return article_pb2.EmbedArticleResponse(
                    article_id=request.article_id,
                    success=False,
                    error_message="Article not found in database",
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

        Args:
            request: SearchSimilarRequest with query or article_id
            context: gRPC context

        Returns:
            SearchSimilarResponse with similar articles
        """
        limit = request.limit if request.limit > 0 else 10
        min_similarity = request.min_similarity if request.min_similarity > 0 else 0.5

        self._logger.info(
            "SearchSimilar request",
            search_by=request.WhichOneof("search_by"),
            limit=limit,
        )

        try:
            with get_session() as session:
                repository = ArticleVectorRepository(session)

                # Determine search method based on request
                if request.HasField("query"):
                    # Search by text query - need to embed first
                    embedding_result = self._embedding_service.embed_text(request.query)
                    results = repository.search_similar_by_vector(
                        query_vector=embedding_result.vector,
                        limit=limit,
                        min_similarity=min_similarity,
                    )
                elif request.HasField("article_id"):
                    # Search by article ID
                    results = repository.search_similar_by_article_id(
                        article_id=request.article_id,
                        limit=limit,
                        min_similarity=min_similarity,
                    )
                else:
                    context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                    context.set_details("Either query or article_id must be provided")
                    return article_pb2.SearchSimilarResponse()

            # Convert to response
            articles = [
                article_pb2.SimilarArticle(
                    article_id=r.article_id,
                    title=r.title,
                    url=r.url,
                    similarity_score=r.similarity_score,
                    snippet=r.snippet or "",
                )
                for r in results
            ]

            return article_pb2.SearchSimilarResponse(articles=articles)

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
