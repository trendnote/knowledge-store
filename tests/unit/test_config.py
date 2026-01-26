"""Tests for configuration management."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import (
    APISettings,
    EmbeddingSettings,
    KafkaSettings,
    LogSettings,
    MilvusSettings,
    Neo4jSettings,
    PostgresSettings,
    Settings,
    get_settings,
)


class TestPostgresSettings:
    """Tests for PostgresSettings."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test_user",
                "POSTGRES_PASSWORD": "test_pass",
            },
            clear=True,
        ):
            settings = PostgresSettings()
            assert settings.host == "localhost"
            assert settings.port == 5432
            assert settings.db == "knowledge_store"
            assert settings.pool_size == 20
            assert settings.pool_max_overflow == 10

    def test_custom_values_from_env(self) -> None:
        """Test loading custom values from environment."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_HOST": "db.example.com",
                "POSTGRES_PORT": "5433",
                "POSTGRES_DB": "custom_db",
                "POSTGRES_USER": "custom_user",
                "POSTGRES_PASSWORD": "custom_pass",
                "POSTGRES_POOL_SIZE": "50",
            },
            clear=True,
        ):
            settings = PostgresSettings()
            assert settings.host == "db.example.com"
            assert settings.port == 5433
            assert settings.db == "custom_db"
            assert settings.user == "custom_user"
            assert settings.pool_size == 50

    def test_dsn_generation(self) -> None:
        """Test DSN string generation."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test_user",
                "POSTGRES_PASSWORD": "test_pass",
            },
            clear=True,
        ):
            settings = PostgresSettings()
            expected = "postgresql://test_user:test_pass@localhost:5432/knowledge_store"
            assert settings.dsn == expected

    def test_async_dsn_generation(self) -> None:
        """Test async DSN string generation."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test_user",
                "POSTGRES_PASSWORD": "test_pass",
            },
            clear=True,
        ):
            settings = PostgresSettings()
            expected = (
                "postgresql+asyncpg://test_user:test_pass@localhost:5432/knowledge_store"
            )
            assert settings.async_dsn == expected

    def test_required_user_field(self) -> None:
        """Test that user field is required."""
        with patch.dict(
            os.environ,
            {"POSTGRES_PASSWORD": "test_pass"},
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                PostgresSettings()
            assert "POSTGRES_USER" in str(exc_info.value) or "user" in str(exc_info.value)

    def test_required_password_field(self) -> None:
        """Test that password field is required."""
        with patch.dict(
            os.environ,
            {"POSTGRES_USER": "test_user"},
            clear=True,
        ):
            with pytest.raises(ValidationError) as exc_info:
                PostgresSettings()
            assert "POSTGRES_PASSWORD" in str(exc_info.value) or "password" in str(
                exc_info.value
            )

    def test_pool_size_validation(self) -> None:
        """Test pool_size bounds validation."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "POSTGRES_POOL_SIZE": "200",  # Exceeds max of 100
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                PostgresSettings()


class TestMilvusSettings:
    """Tests for MilvusSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = MilvusSettings()
        assert settings.host == "localhost"
        assert settings.port == 19530
        assert settings.collection == "knowledge_chunks"

    def test_uri_property(self) -> None:
        """Test URI generation."""
        settings = MilvusSettings()
        assert settings.uri == "http://localhost:19530"

    def test_custom_values(self) -> None:
        """Test loading custom values from environment."""
        with patch.dict(
            os.environ,
            {
                "MILVUS_HOST": "milvus.example.com",
                "MILVUS_PORT": "19531",
                "MILVUS_COLLECTION": "custom_collection",
            },
            clear=True,
        ):
            settings = MilvusSettings()
            assert settings.host == "milvus.example.com"
            assert settings.port == 19531
            assert settings.collection == "custom_collection"
            assert settings.uri == "http://milvus.example.com:19531"


class TestNeo4jSettings:
    """Tests for Neo4jSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        with patch.dict(
            os.environ,
            {"NEO4J_PASSWORD": "test_pass"},
            clear=True,
        ):
            settings = Neo4jSettings()
            assert settings.uri == "bolt://localhost:7687"
            assert settings.user == "neo4j"

    def test_required_password(self) -> None:
        """Test that password is required."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Neo4jSettings()
            assert "NEO4J_PASSWORD" in str(exc_info.value) or "password" in str(
                exc_info.value
            )

    def test_valid_bolt_uri(self) -> None:
        """Test valid bolt:// URI."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://neo4j.example.com:7687",
                "NEO4J_PASSWORD": "test",
            },
            clear=True,
        ):
            settings = Neo4jSettings()
            assert settings.uri == "bolt://neo4j.example.com:7687"

    def test_valid_neo4j_uri(self) -> None:
        """Test valid neo4j:// URI."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "neo4j://neo4j.example.com:7687",
                "NEO4J_PASSWORD": "test",
            },
            clear=True,
        ):
            settings = Neo4jSettings()
            assert settings.uri == "neo4j://neo4j.example.com:7687"

    def test_invalid_uri(self) -> None:
        """Test that invalid URI raises ValidationError."""
        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "http://invalid-uri",
                "NEO4J_PASSWORD": "test",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Neo4jSettings()


class TestKafkaSettings:
    """Tests for KafkaSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = KafkaSettings()
        assert settings.bootstrap_servers == "localhost:9092"
        assert settings.consumer_group == "knowledge-store"
        assert settings.topic_documents == "documents"
        assert settings.topic_sync == "sync"

    def test_bootstrap_servers_list(self) -> None:
        """Test bootstrap_servers_list property."""
        with patch.dict(
            os.environ,
            {"KAFKA_BOOTSTRAP_SERVERS": "kafka1:9092,kafka2:9092,kafka3:9092"},
            clear=True,
        ):
            settings = KafkaSettings()
            assert settings.bootstrap_servers_list == [
                "kafka1:9092",
                "kafka2:9092",
                "kafka3:9092",
            ]

    def test_single_server_list(self) -> None:
        """Test single server returns list with one element."""
        settings = KafkaSettings()
        assert settings.bootstrap_servers_list == ["localhost:9092"]


class TestEmbeddingSettings:
    """Tests for EmbeddingSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = EmbeddingSettings()
        assert settings.model == "BAAI/bge-m3"
        assert settings.use_fp16 is True
        assert settings.batch_size == 32

    def test_custom_values(self) -> None:
        """Test loading custom values."""
        with patch.dict(
            os.environ,
            {
                "BGE_M3_MODEL": "custom/model",
                "BGE_M3_USE_FP16": "false",
                "BGE_M3_BATCH_SIZE": "64",
            },
            clear=True,
        ):
            settings = EmbeddingSettings()
            assert settings.model == "custom/model"
            assert settings.use_fp16 is False
            assert settings.batch_size == 64

    def test_batch_size_validation(self) -> None:
        """Test batch_size bounds validation."""
        with patch.dict(
            os.environ,
            {"BGE_M3_BATCH_SIZE": "500"},  # Exceeds max of 256
            clear=True,
        ):
            with pytest.raises(ValidationError):
                EmbeddingSettings()


class TestAPISettings:
    """Tests for APISettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = APISettings()
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.prefix == "/api/v1"
        assert settings.cors_origins == ["http://localhost:3000"]


class TestLogSettings:
    """Tests for LogSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = LogSettings()
        assert settings.level == "INFO"
        assert settings.format == "json"

    def test_valid_log_levels(self) -> None:
        """Test valid log levels."""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            with patch.dict(os.environ, {"LOG_LEVEL": level}, clear=True):
                settings = LogSettings()
                assert settings.level == level

    def test_invalid_log_level(self) -> None:
        """Test invalid log level raises error."""
        with patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}, clear=True):
            with pytest.raises(ValidationError):
                LogSettings()


class TestSettings:
    """Tests for main Settings class."""

    @pytest.fixture(autouse=True)
    def clear_settings_cache(self) -> None:
        """Clear settings cache before each test."""
        get_settings.cache_clear()

    def test_default_app_settings(self) -> None:
        """Test default application settings."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "NEO4J_PASSWORD": "test",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.app_name == "knowledge-store"
            assert settings.app_env == "development"
            assert settings.debug is True

    def test_nested_settings_access(self) -> None:
        """Test accessing nested settings."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test_user",
                "POSTGRES_PASSWORD": "test_pass",
                "NEO4J_PASSWORD": "neo4j_pass",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.postgres.user == "test_user"
            assert settings.milvus.host == "localhost"
            assert settings.kafka.consumer_group == "knowledge-store"
            assert settings.embedding.model == "BAAI/bge-m3"

    def test_is_development_property(self) -> None:
        """Test is_development property."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "NEO4J_PASSWORD": "test",
                "APP_ENV": "development",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.is_development is True
            assert settings.is_production is False

    def test_is_production_property(self) -> None:
        """Test is_production property."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "NEO4J_PASSWORD": "test",
                "APP_ENV": "production",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.is_development is False
            assert settings.is_production is True

    def test_get_settings_cached(self) -> None:
        """Test that get_settings returns cached instance."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "NEO4J_PASSWORD": "test",
            },
            clear=True,
        ):
            settings1 = get_settings()
            settings2 = get_settings()
            assert settings1 is settings2

    def test_invalid_app_env(self) -> None:
        """Test that invalid app_env raises error."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "test",
                "NEO4J_PASSWORD": "test",
                "APP_ENV": "invalid_env",
            },
            clear=True,
        ):
            with pytest.raises(ValidationError):
                Settings()


class TestSecretValues:
    """Tests for secret value handling."""

    def test_password_is_secret(self) -> None:
        """Test that passwords are stored as SecretStr."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_USER": "test",
                "POSTGRES_PASSWORD": "secret_password",
            },
            clear=True,
        ):
            settings = PostgresSettings()
            # SecretStr should not reveal value in str representation
            assert "secret_password" not in str(settings.password)
            # But can be accessed via get_secret_value()
            assert settings.password.get_secret_value() == "secret_password"

    def test_neo4j_password_is_secret(self) -> None:
        """Test that Neo4j password is stored as SecretStr."""
        with patch.dict(
            os.environ,
            {"NEO4J_PASSWORD": "neo4j_secret"},
            clear=True,
        ):
            settings = Neo4jSettings()
            assert "neo4j_secret" not in str(settings.password)
            assert settings.password.get_secret_value() == "neo4j_secret"
