"""gRPC server for catchup-ai.

Provides the main entry point for starting the gRPC server
with health checking support.
"""

import signal
import sys
from concurrent import futures

import grpc
import structlog
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from catchup_ai.api.grpc.article_servicer import ArticleAIServicer
from catchup_ai.api.grpc.generated import article_pb2_grpc
from catchup_ai.infra.config.settings import get_settings

logger = structlog.get_logger()


def create_server() -> grpc.Server:
    """Create and configure the gRPC server.

    Returns:
        Configured gRPC server (not yet started)
    """
    settings = get_settings()

    # Create server with thread pool
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=settings.grpc.max_workers),
        options=[
            ("grpc.max_send_message_length", settings.grpc.max_message_size),
            ("grpc.max_receive_message_length", settings.grpc.max_message_size),
        ],
    )

    # Register ArticleAI service
    article_servicer = ArticleAIServicer()
    article_pb2_grpc.add_ArticleAIServicer_to_server(article_servicer, server)

    # Register health check service
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # Set service health status
    health_servicer.set(
        "catchup.ai.v1.ArticleAI",
        health_pb2.HealthCheckResponse.SERVING,
    )
    health_servicer.set(
        "",  # Overall server health
        health_pb2.HealthCheckResponse.SERVING,
    )

    # Add port
    server.add_insecure_port(settings.grpc.address)

    logger.info(
        "gRPC server configured",
        address=settings.grpc.address,
        max_workers=settings.grpc.max_workers,
    )

    return server


def serve() -> None:
    """Start the gRPC server and block until shutdown.

    Handles SIGTERM and SIGINT for graceful shutdown.
    """
    settings = get_settings()
    server = create_server()

    # Graceful shutdown handler
    def shutdown_handler(signum, frame):
        logger.info("Shutdown signal received", signal=signum)
        # Grace period for in-flight requests
        event = server.stop(grace=30)
        event.wait()
        logger.info("Server stopped gracefully")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # Start server
    server.start()
    logger.info(
        "gRPC server started",
        address=settings.grpc.address,
        environment=settings.environment,
    )

    # Block until shutdown
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
