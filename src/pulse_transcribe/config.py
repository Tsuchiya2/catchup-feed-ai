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

    log_level: str = "INFO"
