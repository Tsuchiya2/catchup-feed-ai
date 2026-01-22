"""Application settings using pydantic-settings.

Environment variables are loaded from .env file and can be overridden.
All settings are validated at startup.
"""

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProvider(str, Enum):
    """Supported embedding providers."""

    OPENAI = "openai"
    VOYAGE = "voyage"  # Anthropic recommended provider


class EmbeddingSettings(BaseSettings):
    """Embedding service configuration."""

    model_config = SettingsConfigDict(env_prefix="EMBEDDING_")

    provider: EmbeddingProvider = Field(
        default=EmbeddingProvider.OPENAI,
        description="Embedding provider to use (openai or voyage)",
    )
    dimension: int = Field(
        default=1536,
        description="Dimension of embedding vectors",
    )


class DatabaseSettings(BaseSettings):
    """PostgreSQL database configuration."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    name: str = Field(default="catchup_feed", description="Database name")
    user: str = Field(default="postgres", description="Database user")
    password: str = Field(default="postgres", description="Database password")

    @property
    def url(self) -> str:
        """Generate database URL for SQLAlchemy."""
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"

    @property
    def async_url(self) -> str:
        """Generate async database URL for SQLAlchemy."""
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


class OpenAISettings(BaseSettings):
    """OpenAI API configuration."""

    model_config = SettingsConfigDict(env_prefix="OPENAI_")

    api_key: str = Field(default="", description="OpenAI API key")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Model to use for embeddings",
    )
    embedding_dimension: int = Field(
        default=1536,
        description="Dimension of embedding vectors",
    )
    chat_model: str = Field(
        default="gpt-4o-mini",
        description="Model to use for chat/RAG",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        # Allow empty string when not using OpenAI provider
        if v and not v.startswith("sk-"):
            raise ValueError("Invalid OpenAI API key format (must start with sk-)")
        return v


class VoyageSettings(BaseSettings):
    """Voyage AI API configuration (Anthropic recommended embedding provider).

    Voyage AI: https://www.voyageai.com/
    Recommended by Anthropic for embeddings in Claude ecosystem.
    """

    model_config = SettingsConfigDict(env_prefix="VOYAGE_")

    api_key: str = Field(default="", description="Voyage AI API key")
    embedding_model: str = Field(
        default="voyage-3",
        description="Model to use for embeddings (voyage-3, voyage-3-lite, voyage-code-3)",
    )
    embedding_dimension: int = Field(
        default=1024,
        description="Dimension of embedding vectors (voyage-3: 1024)",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        # Allow empty string when not using Voyage provider
        if v and not v.startswith("pa-"):
            raise ValueError("Invalid Voyage API key format (must start with pa-)")
        return v


class GrpcSettings(BaseSettings):
    """gRPC server configuration."""

    model_config = SettingsConfigDict(env_prefix="GRPC_")

    host: str = Field(default="0.0.0.0", description="gRPC server host")
    port: int = Field(default=50051, description="gRPC server port")
    max_workers: int = Field(default=10, description="Maximum number of worker threads")
    max_message_size: int = Field(
        default=100 * 1024 * 1024,  # 100MB
        description="Maximum message size in bytes",
    )

    @property
    def address(self) -> str:
        """Generate server address."""
        return f"{self.host}:{self.port}"


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: str = Field(default="development", description="Runtime environment")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")

    # Sub-settings (loaded separately for better organization)
    @property
    def embedding(self) -> EmbeddingSettings:
        """Embedding service settings."""
        return EmbeddingSettings()

    @property
    def database(self) -> DatabaseSettings:
        """Database settings."""
        return DatabaseSettings()

    @property
    def openai(self) -> OpenAISettings:
        """OpenAI settings."""
        return OpenAISettings()

    @property
    def voyage(self) -> VoyageSettings:
        """Voyage AI settings (Anthropic recommended)."""
        return VoyageSettings()

    @property
    def grpc(self) -> GrpcSettings:
        """gRPC settings."""
        return GrpcSettings()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    Uses lru_cache to ensure settings are loaded only once.
    """
    return Settings()
