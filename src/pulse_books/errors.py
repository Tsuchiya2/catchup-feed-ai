"""Error taxonomy for the book RAG ingestion pipeline (§6).

Everything here is an operator-facing CLI failure: pulse-books is run by
hand on the Mac, so each error carries the message the operator needs to
act on (wrong file, Ollama down, backend migration not applied, ...).
"""


class BookPipelineError(Exception):
    """Base class: the CLI turns these into a log line and exit code 1."""


class PdfExtractionError(BookPipelineError):
    """The PDF could not be opened or yielded no text at all.

    Per-page quality problems (broken code blocks, empty pages) are NOT
    errors — the design accepts extraction-quality limits with a warning
    log only. This is raised only when there is nothing to ingest.
    """


class EmbeddingError(BookPipelineError):
    """The Ollama /api/embed call failed or returned an unusable response.

    Includes the dimension guard: a vector that is not exactly 1024 wide
    means the wrong model is configured (book_chunks is vector(1024),
    D-12: bge-m3) and must stop the ingest before anything is written.
    """


class SchemaMissingError(BookPipelineError):
    """books / book_chunks (or the vector type) do not exist yet.

    Table creation is the backend's responsibility (its migration is the
    schema owner); this error tells the operator to apply it.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(
            "books / book_chunks テーブル(または vector 型)がありません。"
            "backend のマイグレーション適用が必要です"
            f"(スキーマは pulse-phase2-design.md §4 が正)。detail: {detail}"
        )
