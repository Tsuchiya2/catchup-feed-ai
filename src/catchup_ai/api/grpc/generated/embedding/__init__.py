"""Generated gRPC code for backend EmbeddingService client."""

from .embedding_pb2 import (
    StoreEmbeddingRequest,
    StoreEmbeddingResponse,
    GetEmbeddingsRequest,
    GetEmbeddingsResponse,
    SearchSimilarRequest,
    SearchSimilarResponse,
    DeleteEmbeddingRequest,
    DeleteEmbeddingResponse,
    ArticleEmbedding,
    SimilarArticle,
)
from .embedding_pb2_grpc import (
    EmbeddingServiceStub,
    EmbeddingServiceServicer,
    add_EmbeddingServiceServicer_to_server,
)

__all__ = [
    # Messages
    "StoreEmbeddingRequest",
    "StoreEmbeddingResponse",
    "GetEmbeddingsRequest",
    "GetEmbeddingsResponse",
    "SearchSimilarRequest",
    "SearchSimilarResponse",
    "DeleteEmbeddingRequest",
    "DeleteEmbeddingResponse",
    "ArticleEmbedding",
    "SimilarArticle",
    # Service
    "EmbeddingServiceStub",
    "EmbeddingServiceServicer",
    "add_EmbeddingServiceServicer_to_server",
]
