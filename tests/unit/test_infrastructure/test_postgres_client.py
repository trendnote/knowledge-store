"""Tests for PostgreSQL client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import PostgresSettings
from src.infrastructure.database.postgres import (
    PostgresClient,
    close_postgres_client,
    get_postgres_client,
    reset_postgres_client,
)

if TYPE_CHECKING:
    pass


@pytest.fixture
def settings() -> PostgresSettings:
    """Create test settings."""
    return PostgresSettings(
        host="localhost",
        port=5432,
        db="test_db",
        user="test_user",
        password="test_pass",
    )


@pytest.fixture
def client(settings: PostgresSettings) -> PostgresClient:
    """Create test client."""
    return PostgresClient(settings)


class TestPostgresClientConnection:
    """Tests for PostgresClient connection management."""

    @pytest.mark.asyncio
    async def test_connect_creates_pool(self, client: PostgresClient) -> None:
        """Test that connect creates a connection pool."""
        mock_pool = MagicMock()

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_pool
            await client.connect()

            mock_create.assert_called_once()
            assert client._pool is mock_pool
            assert client.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_is_idempotent(self, client: PostgresClient) -> None:
        """Test that calling connect multiple times doesn't create new pools."""
        mock_pool = MagicMock()
        client._pool = mock_pool

        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_create:
            await client.connect()

            mock_create.assert_not_called()
            assert client._pool is mock_pool

    @pytest.mark.asyncio
    async def test_disconnect_closes_pool(self, client: PostgresClient) -> None:
        """Test that disconnect closes the pool."""
        mock_pool = AsyncMock()
        client._pool = mock_pool

        await client.disconnect()

        mock_pool.close.assert_called_once()
        assert client._pool is None
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_disconnect_is_idempotent(self, client: PostgresClient) -> None:
        """Test that calling disconnect when not connected is safe."""
        assert client._pool is None
        await client.disconnect()  # Should not raise
        assert client._pool is None

    def test_pool_not_connected_raises(self, client: PostgresClient) -> None:
        """Test accessing pool before connect raises error."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.pool


class TestPostgresClientPing:
    """Tests for PostgresClient ping method."""

    @pytest.mark.asyncio
    async def test_ping_success(self, client: PostgresClient) -> None:
        """Test ping returns True when connected."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        client._pool = mock_pool

        result = await client.ping()

        assert result is True
        mock_conn.fetchval.assert_called_once_with("SELECT 1")

    @pytest.mark.asyncio
    async def test_ping_failure_returns_false(self, client: PostgresClient) -> None:
        """Test ping returns False when query fails."""
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.side_effect = Exception("Connection failed")
        client._pool = mock_pool

        result = await client.ping()

        assert result is False

    @pytest.mark.asyncio
    async def test_ping_not_connected_returns_false(self, client: PostgresClient) -> None:
        """Test ping returns False when not connected."""
        result = await client.ping()
        assert result is False


class TestPostgresClientTransaction:
    """Tests for PostgresClient transaction context manager."""

    @pytest.mark.asyncio
    async def test_transaction_context_manager(self, client: PostgresClient) -> None:
        """Test transaction context manager works correctly."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()

        # Create a proper async context manager for transaction
        class MockTransaction:
            async def __aenter__(self) -> MockTransaction:
                return self

            async def __aexit__(self, *args: Any) -> None:
                pass

        mock_conn.transaction.return_value = MockTransaction()
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        client._pool = mock_pool

        async with client.transaction() as conn:
            assert conn is mock_conn

        mock_conn.transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_context_manager(self, client: PostgresClient) -> None:
        """Test acquire context manager works correctly."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        client._pool = mock_pool

        async with client.acquire() as conn:
            assert conn is mock_conn


class TestPostgresClientQueries:
    """Tests for PostgresClient query methods."""

    @pytest.fixture
    def connected_client(self, client: PostgresClient) -> PostgresClient:
        """Create a connected client with mocked pool."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        client._pool = mock_pool
        client._mock_conn = mock_conn  # type: ignore[attr-defined]
        return client

    @pytest.mark.asyncio
    async def test_execute_returns_status(self, connected_client: PostgresClient) -> None:
        """Test execute returns command status."""
        connected_client._mock_conn.execute = AsyncMock(return_value="INSERT 0 1")  # type: ignore[attr-defined]

        result = await connected_client.execute("INSERT INTO test VALUES ($1)", 1)

        assert result == "INSERT 0 1"
        connected_client._mock_conn.execute.assert_called_once_with(  # type: ignore[attr-defined]
            "INSERT INTO test VALUES ($1)", 1
        )

    @pytest.mark.asyncio
    async def test_fetch_returns_records(self, connected_client: PostgresClient) -> None:
        """Test fetch returns list of records."""
        mock_records = [{"id": 1}, {"id": 2}]
        connected_client._mock_conn.fetch = AsyncMock(return_value=mock_records)  # type: ignore[attr-defined]

        result = await connected_client.fetch("SELECT * FROM test")

        assert result == mock_records
        connected_client._mock_conn.fetch.assert_called_once_with("SELECT * FROM test")  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_fetchrow_returns_single_record(self, connected_client: PostgresClient) -> None:
        """Test fetchrow returns single record."""
        mock_record = {"id": 1, "name": "test"}
        connected_client._mock_conn.fetchrow = AsyncMock(return_value=mock_record)  # type: ignore[attr-defined]

        result = await connected_client.fetchrow("SELECT * FROM test WHERE id = $1", 1)

        assert result == mock_record

    @pytest.mark.asyncio
    async def test_fetchrow_returns_none_when_no_results(
        self, connected_client: PostgresClient
    ) -> None:
        """Test fetchrow returns None when no results."""
        connected_client._mock_conn.fetchrow = AsyncMock(return_value=None)  # type: ignore[attr-defined]

        result = await connected_client.fetchrow("SELECT * FROM test WHERE id = $1", 999)

        assert result is None

    @pytest.mark.asyncio
    async def test_fetchval_returns_single_value(self, connected_client: PostgresClient) -> None:
        """Test fetchval returns single value."""
        connected_client._mock_conn.fetchval = AsyncMock(return_value=42)  # type: ignore[attr-defined]

        result = await connected_client.fetchval("SELECT count(*) FROM test")

        assert result == 42

    @pytest.mark.asyncio
    async def test_exists_returns_true_when_row_exists(
        self, connected_client: PostgresClient
    ) -> None:
        """Test exists returns True when row exists."""
        connected_client._mock_conn.fetchval = AsyncMock(return_value=1)  # type: ignore[attr-defined]

        result = await connected_client.exists("SELECT 1 FROM test WHERE id = $1", 1)

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_returns_false_when_no_row(self, connected_client: PostgresClient) -> None:
        """Test exists returns False when no row exists."""
        connected_client._mock_conn.fetchval = AsyncMock(return_value=None)  # type: ignore[attr-defined]

        result = await connected_client.exists("SELECT 1 FROM test WHERE id = $1", 999)

        assert result is False

    @pytest.mark.asyncio
    async def test_executemany(self, connected_client: PostgresClient) -> None:
        """Test executemany with multiple parameter sets."""
        connected_client._mock_conn.executemany = AsyncMock()  # type: ignore[attr-defined]

        args = [("Doc 1",), ("Doc 2",), ("Doc 3",)]
        await connected_client.executemany("INSERT INTO test (name) VALUES ($1)", args)

        connected_client._mock_conn.executemany.assert_called_once_with(  # type: ignore[attr-defined]
            "INSERT INTO test (name) VALUES ($1)", args
        )


class TestPostgresClientSingleton:
    """Tests for PostgresClient singleton functions."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_postgres_client()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_postgres_client()

    def test_get_postgres_client_creates_instance(self, settings: PostgresSettings) -> None:
        """Test get_postgres_client creates instance."""
        client = get_postgres_client(settings)

        assert client is not None
        assert isinstance(client, PostgresClient)

    def test_get_postgres_client_returns_same_instance(self, settings: PostgresSettings) -> None:
        """Test get_postgres_client returns same instance."""
        client1 = get_postgres_client(settings)
        client2 = get_postgres_client(settings)

        assert client1 is client2

    def test_get_postgres_client_with_auto_settings(self) -> None:
        """Test get_postgres_client loads settings automatically."""
        mock_postgres_settings = PostgresSettings(
            host="localhost",
            port=5432,
            db="auto_db",
            user="auto_user",
            password="auto_pass",
        )
        mock_settings = MagicMock()
        mock_settings.postgres = mock_postgres_settings

        with patch("src.config.get_settings", return_value=mock_settings) as mock_get:
            client = get_postgres_client()

            assert client is not None
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_postgres_client(self, settings: PostgresSettings) -> None:
        """Test close_postgres_client closes and resets singleton."""
        client = get_postgres_client(settings)
        mock_pool = AsyncMock()
        client._pool = mock_pool

        await close_postgres_client()

        mock_pool.close.assert_called_once()
        # Verify singleton is reset
        new_client = get_postgres_client(settings)
        assert new_client is not client

    @pytest.mark.asyncio
    async def test_close_postgres_client_when_none(self) -> None:
        """Test close_postgres_client when no client exists."""
        await close_postgres_client()  # Should not raise
