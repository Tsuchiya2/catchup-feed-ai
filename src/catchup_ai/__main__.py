"""Main entry point for catchup-ai.

Run with: uv run python -m catchup_ai
"""

import structlog

from catchup_ai.api.grpc.server import serve
from catchup_ai.infra.config.settings import get_settings


def configure_logging() -> None:
    """Configure structured logging."""
    settings = get_settings()

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            # Use JSON in production, console in development
            structlog.processors.JSONRenderer()
            if settings.environment == "production"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def main() -> None:
    """Application entry point."""
    configure_logging()
    logger = structlog.get_logger()

    settings = get_settings()
    logger.info(
        "Starting catchup-ai",
        environment=settings.environment,
        debug=settings.debug,
    )

    serve()


if __name__ == "__main__":
    main()
