from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class StoreEmbeddingRequest(_message.Message):
    __slots__ = ("article_id", "embedding_type", "provider", "model", "dimension", "embedding")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_TYPE_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    embedding_type: str
    provider: str
    model: str
    dimension: int
    embedding: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, article_id: _Optional[int] = ..., embedding_type: _Optional[str] = ..., provider: _Optional[str] = ..., model: _Optional[str] = ..., dimension: _Optional[int] = ..., embedding: _Optional[_Iterable[float]] = ...) -> None: ...

class StoreEmbeddingResponse(_message.Message):
    __slots__ = ("success", "embedding_id", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    embedding_id: int
    error_message: str
    def __init__(self, success: bool = ..., embedding_id: _Optional[int] = ..., error_message: _Optional[str] = ...) -> None: ...

class GetEmbeddingsRequest(_message.Message):
    __slots__ = ("article_id",)
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    def __init__(self, article_id: _Optional[int] = ...) -> None: ...

class GetEmbeddingsResponse(_message.Message):
    __slots__ = ("embeddings",)
    EMBEDDINGS_FIELD_NUMBER: _ClassVar[int]
    embeddings: _containers.RepeatedCompositeFieldContainer[ArticleEmbedding]
    def __init__(self, embeddings: _Optional[_Iterable[_Union[ArticleEmbedding, _Mapping]]] = ...) -> None: ...

class SearchSimilarRequest(_message.Message):
    __slots__ = ("embedding", "embedding_type", "limit")
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_TYPE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    embedding: _containers.RepeatedScalarFieldContainer[float]
    embedding_type: str
    limit: int
    def __init__(self, embedding: _Optional[_Iterable[float]] = ..., embedding_type: _Optional[str] = ..., limit: _Optional[int] = ...) -> None: ...

class SearchSimilarResponse(_message.Message):
    __slots__ = ("articles",)
    ARTICLES_FIELD_NUMBER: _ClassVar[int]
    articles: _containers.RepeatedCompositeFieldContainer[SimilarArticle]
    def __init__(self, articles: _Optional[_Iterable[_Union[SimilarArticle, _Mapping]]] = ...) -> None: ...

class ArticleEmbedding(_message.Message):
    __slots__ = ("id", "article_id", "embedding_type", "provider", "model", "dimension", "embedding", "created_at", "updated_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_TYPE_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    MODEL_FIELD_NUMBER: _ClassVar[int]
    DIMENSION_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    UPDATED_AT_FIELD_NUMBER: _ClassVar[int]
    id: int
    article_id: int
    embedding_type: str
    provider: str
    model: str
    dimension: int
    embedding: _containers.RepeatedScalarFieldContainer[float]
    created_at: str
    updated_at: str
    def __init__(self, id: _Optional[int] = ..., article_id: _Optional[int] = ..., embedding_type: _Optional[str] = ..., provider: _Optional[str] = ..., model: _Optional[str] = ..., dimension: _Optional[int] = ..., embedding: _Optional[_Iterable[float]] = ..., created_at: _Optional[str] = ..., updated_at: _Optional[str] = ...) -> None: ...

class SimilarArticle(_message.Message):
    __slots__ = ("article_id", "similarity")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    similarity: float
    def __init__(self, article_id: _Optional[int] = ..., similarity: _Optional[float] = ...) -> None: ...

class DeleteEmbeddingRequest(_message.Message):
    __slots__ = ("article_id",)
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    def __init__(self, article_id: _Optional[int] = ...) -> None: ...

class DeleteEmbeddingResponse(_message.Message):
    __slots__ = ("success", "deleted_count", "error_message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    DELETED_COUNT_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    deleted_count: int
    error_message: str
    def __init__(self, success: bool = ..., deleted_count: _Optional[int] = ..., error_message: _Optional[str] = ...) -> None: ...
