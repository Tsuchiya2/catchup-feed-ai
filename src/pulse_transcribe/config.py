"""Environment-variable configuration (pydantic-settings).

Same style as radio on the Mac: a DATABASE_URL pointing at the Pi's
PostgreSQL over Tailscale, everything else has a sensible default.
See .env.example for the full annotated list.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Pi PostgreSQL over Tailscale (same DSN style as radio).
    database_url: str

    # faster-whisper (D-11: large-v3-turbo; auto-downloaded on first run, free).
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"  # CTranslate2 device; M3 Mac runs on CPU
    whisper_compute_type: str = "auto"  # e.g. "int8" to speed up CPU inference

    # D-14: total audio transcribed per night (seconds). 7200 = 2 hours.
    nightly_budget_seconds: float = 7200.0

    # jobs table poll interval while idle (backend default is also 10s).
    poll_interval_seconds: float = 10.0

    # D-25: base URL of the Pi's tailnet-only private listener, e.g.
    # "http://<pi の MagicDNS 名>:8081" (the :8081 bind from
    # backend deploy/compose.pi.yml). When set, the worker also consumes
    # kind='book_ingest' jobs, downloading the uploaded PDF from
    # {base}/private/books/{filename} (no auth — the tailnet bind is the
    # boundary, C-5). Unset: book_ingest jobs are left pending.
    books_private_base_url: str | None = None

    log_level: str = "INFO"
