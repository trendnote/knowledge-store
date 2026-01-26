"""Configuration management using Pydantic Settings.

This module provides centralized configuration management for all
application components including database connections, messaging,
and embedding services.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str = "localhost"
    port: int = 5432
    db: str = "knowledge_store"
    user: str = Field(..., description="PostgreSQL user (required)")
    password: SecretStr = Field(..., description="PostgreSQL password (required)")
    pool_size: int = Field(default=20, ge=1, le=100)
    pool_max_overflow: int = Field(default=10, ge=0, le=50)

    @property
    def dsn(self) -> str:
        """Generate PostgreSQL DSN."""
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )

    @property
    def async_dsn(self) -> str:
        """Generate async PostgreSQL DSN for asyncpg."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.db}"
        )


class MilvusSettings(BaseSettings):
    """Milvus vector database connection settings."""

    model_config = SettingsConfigDict(env_prefix="MILVUS_")

    host: str = "localhost"
    port: int = 19530
    collection: str = "knowledge_chunks"

    @property
    def uri(self) -> str:
        """Generate Milvus URI."""
        return f"http://{self.host}:{self.port}"


class Neo4jSettings(BaseSettings):
    """Neo4j graph database connection settings."""

    model_config = SettingsConfigDict(env_prefix="NEO4J_")

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: SecretStr = Field(..., description="Neo4j password (required)")

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str) -> str:
        """Validate Neo4j URI format."""
        if not v.startswith(("bolt://", "neo4j://", "neo4j+s://", "bolt+s://")):
            raise ValueError("Neo4j URI must start with bolt:// or neo4j://")
        return v


class KafkaSettings(BaseSettings):
    """Kafka messaging settings."""

    model_config = SettingsConfigDict(env_prefix="KAFKA_")

    bootstrap_servers: str = "localhost:9092"
    consumer_group: str = "knowledge-store"
    topic_documents: str = "documents"
    topic_sync: str = "sync"

    @property
    def bootstrap_servers_list(self) -> list[str]:
        """Get bootstrap servers as a list."""
        return [s.strip() for s in self.bootstrap_servers.split(",")]


class EmbeddingSettings(BaseSettings):
    """BGE-M3 embedding model settings."""

    model_config = SettingsConfigDict(env_prefix="BGE_M3_")

    model: str = "BAAI/bge-m3"
    use_fp16: bool = True
    batch_size: int = Field(default=32, ge=1, le=256)


class APISettings(BaseSettings):
    """API server settings."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = "0.0.0.0"
    port: int = 8000
    prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])


class LogSettings(BaseSettings):
    """Logging settings."""

    model_config = SettingsConfigDict(env_prefix="LOG_")

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: str = "json"


class Settings(BaseSettings):
    """Main application settings.

    This class aggregates all configuration settings and provides
    a single point of access for application configuration.

    Settings are loaded from:
    1. Environment variables
    2. .env file (if present)
    3. Default values

    Example:
        >>> settings = get_settings()
        >>> print(settings.postgres.dsn)
        postgresql://user:pass@localhost:5432/knowledge_store
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_name: str = "knowledge-store"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True

    # Sub-settings (loaded from environment with prefixes)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    api: APISettings = Field(default_factory=APISettings)
    log: LogSettings = Field(default_factory=LogSettings)

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance.

    This function uses lru_cache to ensure that settings are only
    loaded once and reused throughout the application lifecycle.

    Returns:
        Settings: The application settings instance.

    Example:
        >>> settings = get_settings()
        >>> settings.app_name
        'knowledge-store'
    """
    return Settings()


# Export all settings classes for direct access
__all__ = [
    "Settings",
    "PostgresSettings",
    "MilvusSettings",
    "Neo4jSettings",
    "KafkaSettings",
    "EmbeddingSettings",
    "APISettings",
    "LogSettings",
    "get_settings",
]
