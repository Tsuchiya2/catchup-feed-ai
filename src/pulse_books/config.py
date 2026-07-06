"""Environment-variable configuration for pulse-books (pydantic-settings).

Same style as the transcribe worker: DATABASE_URL points at the Pi's
PostgreSQL over Tailscale (shared with pulse-transcribe / radio),
everything else defaults. See .env.example for the annotated list.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from pulse_books.embedding import DEFAULT_MODEL, DEFAULT_OLLAMA_HOST


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Pi PostgreSQL over Tailscale — the same DSN the transcribe worker uses.
    database_url: str

    # Ollama runs on this Mac; pulse-books is executed locally, so localhost.
    ollama_host: str = DEFAULT_OLLAMA_HOST

    # D-12: bge-m3 (1024 dims). A replacement must also produce 1024 dims
    # (book_chunks is vector(1024)) and requires re-ingesting every book.
    embedding_model: str = DEFAULT_MODEL

    log_level: str = "INFO"
