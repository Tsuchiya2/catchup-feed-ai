from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class EmbedArticleRequest(_message.Message):
    __slots__ = ("article_id", "title", "content", "url")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    title: str
    content: str
    url: str
    def __init__(self, article_id: _Optional[int] = ..., title: _Optional[str] = ..., content: _Optional[str] = ..., url: _Optional[str] = ...) -> None: ...

class EmbedArticleResponse(_message.Message):
    __slots__ = ("article_id", "success", "error_message", "embedding_dimension")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_MESSAGE_FIELD_NUMBER: _ClassVar[int]
    EMBEDDING_DIMENSION_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    success: bool
    error_message: str
    embedding_dimension: int
    def __init__(self, article_id: _Optional[int] = ..., success: bool = ..., error_message: _Optional[str] = ..., embedding_dimension: _Optional[int] = ...) -> None: ...

class SearchSimilarRequest(_message.Message):
    __slots__ = ("query", "article_id", "limit", "min_similarity")
    QUERY_FIELD_NUMBER: _ClassVar[int]
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    MIN_SIMILARITY_FIELD_NUMBER: _ClassVar[int]
    query: str
    article_id: int
    limit: int
    min_similarity: float
    def __init__(self, query: _Optional[str] = ..., article_id: _Optional[int] = ..., limit: _Optional[int] = ..., min_similarity: _Optional[float] = ...) -> None: ...

class SearchSimilarResponse(_message.Message):
    __slots__ = ("articles",)
    ARTICLES_FIELD_NUMBER: _ClassVar[int]
    articles: _containers.RepeatedCompositeFieldContainer[SimilarArticle]
    def __init__(self, articles: _Optional[_Iterable[_Union[SimilarArticle, _Mapping]]] = ...) -> None: ...

class SimilarArticle(_message.Message):
    __slots__ = ("article_id", "title", "url", "similarity_score", "snippet")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    SIMILARITY_SCORE_FIELD_NUMBER: _ClassVar[int]
    SNIPPET_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    title: str
    url: str
    similarity_score: float
    snippet: str
    def __init__(self, article_id: _Optional[int] = ..., title: _Optional[str] = ..., url: _Optional[str] = ..., similarity_score: _Optional[float] = ..., snippet: _Optional[str] = ...) -> None: ...

class QueryArticlesRequest(_message.Message):
    __slots__ = ("question", "max_context_articles", "date_range", "categories")
    QUESTION_FIELD_NUMBER: _ClassVar[int]
    MAX_CONTEXT_ARTICLES_FIELD_NUMBER: _ClassVar[int]
    DATE_RANGE_FIELD_NUMBER: _ClassVar[int]
    CATEGORIES_FIELD_NUMBER: _ClassVar[int]
    question: str
    max_context_articles: int
    date_range: DateRange
    categories: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, question: _Optional[str] = ..., max_context_articles: _Optional[int] = ..., date_range: _Optional[_Union[DateRange, _Mapping]] = ..., categories: _Optional[_Iterable[str]] = ...) -> None: ...

class DateRange(_message.Message):
    __slots__ = ("start_date", "end_date")
    START_DATE_FIELD_NUMBER: _ClassVar[int]
    END_DATE_FIELD_NUMBER: _ClassVar[int]
    start_date: str
    end_date: str
    def __init__(self, start_date: _Optional[str] = ..., end_date: _Optional[str] = ...) -> None: ...

class QueryArticlesResponse(_message.Message):
    __slots__ = ("answer", "source_articles", "confidence")
    ANSWER_FIELD_NUMBER: _ClassVar[int]
    SOURCE_ARTICLES_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    answer: str
    source_articles: _containers.RepeatedCompositeFieldContainer[SourceArticle]
    confidence: float
    def __init__(self, answer: _Optional[str] = ..., source_articles: _Optional[_Iterable[_Union[SourceArticle, _Mapping]]] = ..., confidence: _Optional[float] = ...) -> None: ...

class SourceArticle(_message.Message):
    __slots__ = ("article_id", "title", "url", "relevance_score")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    RELEVANCE_SCORE_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    title: str
    url: str
    relevance_score: float
    def __init__(self, article_id: _Optional[int] = ..., title: _Optional[str] = ..., url: _Optional[str] = ..., relevance_score: _Optional[float] = ...) -> None: ...

class GenerateWeeklySummaryRequest(_message.Message):
    __slots__ = ("period", "date_range", "topics", "max_length")
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    DATE_RANGE_FIELD_NUMBER: _ClassVar[int]
    TOPICS_FIELD_NUMBER: _ClassVar[int]
    MAX_LENGTH_FIELD_NUMBER: _ClassVar[int]
    period: str
    date_range: DateRange
    topics: _containers.RepeatedScalarFieldContainer[str]
    max_length: int
    def __init__(self, period: _Optional[str] = ..., date_range: _Optional[_Union[DateRange, _Mapping]] = ..., topics: _Optional[_Iterable[str]] = ..., max_length: _Optional[int] = ...) -> None: ...

class GenerateWeeklySummaryResponse(_message.Message):
    __slots__ = ("summary", "highlights", "articles", "covered_period")
    SUMMARY_FIELD_NUMBER: _ClassVar[int]
    HIGHLIGHTS_FIELD_NUMBER: _ClassVar[int]
    ARTICLES_FIELD_NUMBER: _ClassVar[int]
    COVERED_PERIOD_FIELD_NUMBER: _ClassVar[int]
    summary: str
    highlights: _containers.RepeatedScalarFieldContainer[str]
    articles: _containers.RepeatedCompositeFieldContainer[SummaryArticle]
    covered_period: DateRange
    def __init__(self, summary: _Optional[str] = ..., highlights: _Optional[_Iterable[str]] = ..., articles: _Optional[_Iterable[_Union[SummaryArticle, _Mapping]]] = ..., covered_period: _Optional[_Union[DateRange, _Mapping]] = ...) -> None: ...

class SummaryArticle(_message.Message):
    __slots__ = ("article_id", "title", "url", "category")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    title: str
    url: str
    category: str
    def __init__(self, article_id: _Optional[int] = ..., title: _Optional[str] = ..., url: _Optional[str] = ..., category: _Optional[str] = ...) -> None: ...

class ClassifyArticleRequest(_message.Message):
    __slots__ = ("article_id", "title", "content")
    ARTICLE_ID_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    CONTENT_FIELD_NUMBER: _ClassVar[int]
    article_id: int
    title: str
    content: str
    def __init__(self, article_id: _Optional[int] = ..., title: _Optional[str] = ..., content: _Optional[str] = ...) -> None: ...

class ClassifyArticleResponse(_message.Message):
    __slots__ = ("category", "confidence", "all_scores")
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    ALL_SCORES_FIELD_NUMBER: _ClassVar[int]
    category: str
    confidence: float
    all_scores: _containers.RepeatedCompositeFieldContainer[CategoryScore]
    def __init__(self, category: _Optional[str] = ..., confidence: _Optional[float] = ..., all_scores: _Optional[_Iterable[_Union[CategoryScore, _Mapping]]] = ...) -> None: ...

class CategoryScore(_message.Message):
    __slots__ = ("category", "score")
    CATEGORY_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    category: str
    score: float
    def __init__(self, category: _Optional[str] = ..., score: _Optional[float] = ...) -> None: ...
