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

from datetime import datetime, timedelta

import grpc
import structlog

from catchup_ai.api.grpc.generated import article_pb2, article_pb2_grpc
from catchup_ai.core.embedding import (
    ArticleEmbeddingInput,
    EmbeddingError,
    EmbeddingService,
    create_embedding_service,
)
from catchup_ai.core.rag import RAGPipeline
from catchup_ai.core.rag.generator import GenerationError
from catchup_ai.core.rag.retriever import RetrievalError
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
        rag_pipeline: RAGPipeline | None = None,
    ):
        """Initialize servicer with required services.

        Args:
            embedding_service: Optional embedding service. If None, creates
                               one using the factory based on configuration.
            embedding_client: Optional backend client. If None, creates one
                              using default settings.
            rag_pipeline: Optional RAG pipeline. If None, creates one
                          using default settings.
        """
        # Use factory to create service based on EMBEDDING_PROVIDER config
        self._embedding_service = embedding_service or create_embedding_service()
        self._embedding_client = embedding_client or EmbeddingClient()
        self._rag_pipeline: RAGPipeline | None = rag_pipeline
        self._settings = get_settings()
        self._logger = logger.bind(servicer="article_ai")

    def _get_rag_pipeline(self) -> RAGPipeline:
        """Lazy initialization of RAG pipeline.

        Returns:
            RAGPipeline instance

        Note:
            RAG pipeline requires LLM API keys which may not be available
            during testing. Lazy initialization allows tests to mock this.
        """
        if self._rag_pipeline is None:
            self._rag_pipeline = RAGPipeline()
        return self._rag_pipeline

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
        """RAG-based question answering over articles.

        Uses the RAG pipeline to:
        1. Retrieve relevant articles based on the question
        2. Generate an answer using LLM with article context

        Args:
            request: QueryArticlesRequest with question and max_context_articles
            context: gRPC context

        Returns:
            QueryArticlesResponse with answer, sources, and confidence
        """
        max_context = request.max_context_articles if request.max_context_articles > 0 else 5

        self._logger.info(
            "QueryArticles request",
            question=request.question[:100] if request.question else "",
            max_context=max_context,
        )

        # Validate request
        if not request.question or not request.question.strip():
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Question is required")
            return article_pb2.QueryArticlesResponse()

        try:
            # Use RAG pipeline to generate answer
            pipeline = self._get_rag_pipeline()
            result = pipeline.query(
                question=request.question,
                max_articles=max_context,
            )

            # Convert source articles to proto format
            sources = [
                article_pb2.SourceArticle(
                    article_id=article.article_id,
                    title=article.title or f"Article {article.article_id}",
                    url=article.url or "",
                    relevance_score=article.similarity_score,
                )
                for article in result.source_articles
            ]

            self._logger.info(
                "QueryArticles completed",
                sources_count=len(sources),
                confidence=result.confidence,
                tokens_used=result.tokens_used,
            )

            return article_pb2.QueryArticlesResponse(
                answer=result.answer,
                source_articles=sources,
                confidence=result.confidence,
            )

        except RetrievalError as e:
            self._logger.error("QueryArticles retrieval failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to retrieve articles: {e}")
            return article_pb2.QueryArticlesResponse()

        except GenerationError as e:
            self._logger.error("QueryArticles generation failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to generate answer: {e}")
            return article_pb2.QueryArticlesResponse()

        except Exception as e:
            self._logger.error("QueryArticles failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return article_pb2.QueryArticlesResponse()

    def GenerateWeeklySummary(
        self,
        request: article_pb2.GenerateWeeklySummaryRequest,
        context: grpc.ServicerContext,
    ) -> article_pb2.GenerateWeeklySummaryResponse:
        """Generate summary of recent articles.

        Uses the RAG pipeline to:
        1. Get recent articles from backend
        2. Generate a summary with key highlights using LLM

        Args:
            request: GenerateWeeklySummaryRequest with period and optional filters
            context: gRPC context

        Returns:
            GenerateWeeklySummaryResponse with summary and highlights
        """
        period = request.period if request.period else "week"

        self._logger.info(
            "GenerateWeeklySummary request",
            period=period,
        )

        try:
            # Calculate date range based on period
            end_date = datetime.now()
            if period == "month":
                start_date = end_date - timedelta(days=30)
            else:
                start_date = end_date - timedelta(days=7)

            # For now, we need to get recent articles from backend
            # Since we don't have a dedicated API, we'll search with a broad query
            # TODO: Add GetRecentArticles API to backend
            pipeline = self._get_rag_pipeline()

            # Use a broad query to get recent articles
            # This is a workaround until we have a proper GetRecentArticles API
            retriever = pipeline._retriever
            recent_articles = retriever.retrieve(
                query="technology news updates",  # Broad query
                limit=20,  # Get more articles for summary
                min_similarity=0.3,  # Lower threshold for broader coverage
            )

            if not recent_articles:
                self._logger.warning("No articles found for summary")
                return article_pb2.GenerateWeeklySummaryResponse(
                    summary="No articles found for this period.",
                    highlights=[],
                    articles=[],
                    covered_period=article_pb2.DateRange(
                        start_date=start_date.isoformat(),
                        end_date=end_date.isoformat(),
                    ),
                )

            # Convert to dict format expected by pipeline.summarize
            articles_data = [
                {
                    "article_id": a.article_id,
                    "title": a.title or f"Article {a.article_id}",
                    "url": a.url or "",
                    "content": a.content or "",
                    "category": "",
                }
                for a in recent_articles
            ]

            # Generate summary
            result = pipeline.summarize(articles=articles_data, period=period)

            # Convert articles to proto format
            summary_articles = [
                article_pb2.SummaryArticle(
                    article_id=a["article_id"],
                    title=a["title"],
                    url=a["url"],
                    category=a.get("category", ""),
                )
                for a in articles_data
            ]

            self._logger.info(
                "GenerateWeeklySummary completed",
                articles_count=len(summary_articles),
                highlights_count=len(result.highlights),
                tokens_used=result.tokens_used,
            )

            return article_pb2.GenerateWeeklySummaryResponse(
                summary=result.summary,
                highlights=result.highlights,
                articles=summary_articles,
                covered_period=article_pb2.DateRange(
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                ),
            )

        except RetrievalError as e:
            self._logger.error("GenerateWeeklySummary retrieval failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to retrieve articles: {e}")
            return article_pb2.GenerateWeeklySummaryResponse()

        except GenerationError as e:
            self._logger.error("GenerateWeeklySummary generation failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Failed to generate summary: {e}")
            return article_pb2.GenerateWeeklySummaryResponse()

        except Exception as e:
            self._logger.error("GenerateWeeklySummary failed", error=str(e))
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
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
