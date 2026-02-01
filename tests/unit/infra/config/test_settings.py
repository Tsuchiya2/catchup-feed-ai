"""Tests for application settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from catchup_ai.infra.config.settings import (
    BackendSettings,
    EmbeddingProvider,
    EmbeddingSettings,
    GrpcSettings,
    OpenAISettings,
    Settings,
    VoyageSettings,
    get_settings,
)


class TestEmbeddingSettings:
    """Tests for EmbeddingSettings."""

    def test_default_provider_is_openai(self):
        """Test that default embedding provider is OpenAI."""
        settings = EmbeddingSettings()
        assert settings.provider == EmbeddingProvider.OPENAI

    def test_default_dimension(self):
        """Test that default dimension is 1536."""
        settings = EmbeddingSettings()
        assert settings.dimension == 1536

    def test_provider_from_env(self):
        """Test that provider can be set from environment."""
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "voyage"}):
            settings = EmbeddingSettings()
            assert settings.provider == EmbeddingProvider.VOYAGE


class TestOpenAISettings:
    """Tests for OpenAISettings."""

    def test_default_values(self):
        """Test default OpenAI settings."""
        with patch.dict(os.environ, {}, clear=True):
            settings = OpenAISettings()
            assert settings.api_key == ""
            assert settings.embedding_model == "text-embedding-3-small"
            assert settings.embedding_dimension == 1536
            assert settings.chat_model == "gpt-4o-mini"

    def test_api_key_validation_valid(self):
        """Test that valid API key passes validation."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test123"}):
            settings = OpenAISettings()
            assert settings.api_key == "sk-test123"

    def test_api_key_validation_invalid(self):
        """Test that invalid API key fails validation."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "invalid-key"}):
            with pytest.raises(ValidationError, match="Invalid OpenAI API key"):
                OpenAISettings()

    def test_api_key_validation_empty_allowed(self):
        """Test that empty API key is allowed (for when not using OpenAI)."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            settings = OpenAISettings()
            assert settings.api_key == ""


class TestVoyageSettings:
    """Tests for VoyageSettings."""

    def test_default_values(self):
        """Test default Voyage settings."""
        with patch.dict(os.environ, {}, clear=True):
            settings = VoyageSettings()
            assert settings.api_key == ""
            assert settings.embedding_model == "voyage-3"
            assert settings.embedding_dimension == 1024

    def test_api_key_validation_valid(self):
        """Test that valid Voyage API key passes validation."""
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "pa-test123"}):
            settings = VoyageSettings()
            assert settings.api_key == "pa-test123"

    def test_api_key_validation_invalid(self):
        """Test that invalid Voyage API key fails validation."""
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "invalid-key"}):
            with pytest.raises(ValidationError, match="Invalid Voyage API key"):
                VoyageSettings()


class TestGrpcSettings:
    """Tests for GrpcSettings."""

    def test_default_values(self):
        """Test default gRPC settings."""
        # Clear env vars to test actual defaults
        with patch.dict(os.environ, {"GRPC_PORT": "", "GRPC_HOST": ""}, clear=False):
            os.environ.pop("GRPC_PORT", None)
            os.environ.pop("GRPC_HOST", None)
            settings = GrpcSettings()
            assert settings.host == "0.0.0.0"
            assert settings.port == 50051
            assert settings.max_workers == 10

    def test_address_property(self):
        """Test address property combines host and port."""
        # Clear env vars to test actual defaults
        with patch.dict(os.environ, {"GRPC_PORT": "", "GRPC_HOST": ""}, clear=False):
            os.environ.pop("GRPC_PORT", None)
            os.environ.pop("GRPC_HOST", None)
            settings = GrpcSettings()
            assert settings.address == "0.0.0.0:50051"

    def test_custom_port(self):
        """Test custom port setting."""
        with patch.dict(os.environ, {"GRPC_PORT": "50052"}):
            settings = GrpcSettings()
            assert settings.port == 50052
            assert settings.address == "0.0.0.0:50052"


class TestBackendSettings:
    """Tests for BackendSettings."""

    def test_default_values(self):
        """Test default backend settings."""
        settings = BackendSettings()
        assert settings.grpc_host == "localhost"
        assert settings.grpc_port == 50052
        assert settings.grpc_tls is False

    def test_grpc_address_property(self):
        """Test grpc_address property combines host and port."""
        settings = BackendSettings()
        assert settings.grpc_address == "localhost:50052"

    def test_custom_backend_settings(self):
        """Test custom backend settings from environment."""
        with patch.dict(
            os.environ,
            {
                "BACKEND_GRPC_HOST": "backend.local",
                "BACKEND_GRPC_PORT": "9090",
                "BACKEND_GRPC_TLS": "true",
            },
        ):
            settings = BackendSettings()
            assert settings.grpc_host == "backend.local"
            assert settings.grpc_port == 9090
            assert settings.grpc_tls is True
            assert settings.grpc_address == "backend.local:9090"


class TestSettings:
    """Tests for main Settings class."""

    def test_default_environment(self):
        """Test default environment settings."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.environment == "development"
            assert settings.debug is False
            assert settings.log_level == "INFO"

    def test_sub_settings_access(self):
        """Test accessing sub-settings via properties."""
        settings = Settings()

        assert isinstance(settings.embedding, EmbeddingSettings)
        assert isinstance(settings.openai, OpenAISettings)
        assert isinstance(settings.voyage, VoyageSettings)
        assert isinstance(settings.grpc, GrpcSettings)
        assert isinstance(settings.backend, BackendSettings)


class TestGetSettings:
    """Tests for get_settings singleton function."""

    def test_returns_settings_instance(self):
        """Test that get_settings returns a Settings instance."""
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_returns_cached_instance(self):
        """Test that get_settings returns the same cached instance."""
        get_settings.cache_clear()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2
