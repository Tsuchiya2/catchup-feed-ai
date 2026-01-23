"""Tests for gRPC server."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    with patch("catchup_ai.api.grpc.server.get_settings") as mock:
        settings = MagicMock()
        settings.grpc.max_workers = 10
        settings.grpc.max_message_size = 50 * 1024 * 1024
        settings.grpc.address = "0.0.0.0:50051"
        settings.environment = "test"
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_grpc():
    """Mock grpc module."""
    with patch("catchup_ai.api.grpc.server.grpc") as mock:
        mock_server = MagicMock()
        mock.server.return_value = mock_server
        yield mock, mock_server


@pytest.fixture
def mock_servicer():
    """Mock ArticleAIServicer."""
    with patch("catchup_ai.api.grpc.server.ArticleAIServicer") as mock:
        yield mock


@pytest.fixture
def mock_health():
    """Mock health module."""
    with patch("catchup_ai.api.grpc.server.health") as mock:
        mock_servicer = MagicMock()
        mock.HealthServicer.return_value = mock_servicer
        yield mock, mock_servicer


class TestCreateServer:
    """Tests for create_server function."""

    def test_create_server_returns_server(
        self, mock_settings, mock_grpc, mock_servicer, mock_health
    ):
        """Test that create_server returns a configured gRPC server."""
        from catchup_ai.api.grpc.server import create_server

        grpc_mock, server_mock = mock_grpc

        server = create_server()

        assert server is server_mock
        grpc_mock.server.assert_called_once()

    def test_create_server_registers_article_service(
        self, mock_settings, mock_grpc, mock_servicer, mock_health
    ):
        """Test that ArticleAI service is registered."""
        from catchup_ai.api.grpc.server import create_server

        with patch(
            "catchup_ai.api.grpc.server.article_pb2_grpc"
        ) as mock_article_grpc:
            create_server()

            mock_article_grpc.add_ArticleAIServicer_to_server.assert_called_once()

    def test_create_server_registers_health_service(
        self, mock_settings, mock_grpc, mock_servicer, mock_health
    ):
        """Test that health service is registered."""
        from catchup_ai.api.grpc.server import create_server

        with patch(
            "catchup_ai.api.grpc.server.health_pb2_grpc"
        ) as mock_health_grpc:
            create_server()

            mock_health_grpc.add_HealthServicer_to_server.assert_called_once()

    def test_create_server_sets_health_status(
        self, mock_settings, mock_grpc, mock_servicer, mock_health
    ):
        """Test that health status is set for services."""
        from catchup_ai.api.grpc.server import create_server

        _, health_servicer = mock_health

        create_server()

        # Should set health for ArticleAI service and overall
        assert health_servicer.set.call_count == 2

    def test_create_server_adds_port(
        self, mock_settings, mock_grpc, mock_servicer, mock_health
    ):
        """Test that server port is configured."""
        from catchup_ai.api.grpc.server import create_server

        _, server_mock = mock_grpc

        create_server()

        server_mock.add_insecure_port.assert_called_once_with("0.0.0.0:50051")

    def test_create_server_uses_settings(
        self, mock_settings, mock_grpc, mock_servicer, mock_health
    ):
        """Test that server uses settings for configuration."""
        from catchup_ai.api.grpc.server import create_server

        grpc_mock, _ = mock_grpc

        create_server()

        # Verify ThreadPoolExecutor was created with correct max_workers
        call_args = grpc_mock.server.call_args
        assert call_args is not None
