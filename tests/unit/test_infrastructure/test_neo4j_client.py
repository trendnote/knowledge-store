"""Tests for Neo4j client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Neo4jSettings
from src.infrastructure.database.neo4j import (
    Neo4jClient,
    close_neo4j_client,
    get_neo4j_client,
    reset_neo4j_client,
)


@pytest.fixture
def settings() -> Neo4jSettings:
    """Create test settings."""
    return Neo4jSettings(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="test_password",
    )


@pytest.fixture
def client(settings: Neo4jSettings) -> Neo4jClient:
    """Create test client."""
    return Neo4jClient(settings)


class TestNeo4jClientConnection:
    """Tests for Neo4jClient connection management."""

    @pytest.mark.asyncio
    async def test_connect_creates_driver(self, client: Neo4jClient) -> None:
        """Test that connect creates a driver."""
        mock_driver = AsyncMock()

        with patch(
            "src.infrastructure.database.neo4j.AsyncGraphDatabase.driver",
            return_value=mock_driver,
        ):
            await client.connect()

            mock_driver.verify_connectivity.assert_called_once()
            assert client._driver is mock_driver
            assert client.is_connected is True

    @pytest.mark.asyncio
    async def test_connect_is_idempotent(self, client: Neo4jClient) -> None:
        """Test that calling connect multiple times doesn't create new drivers."""
        mock_driver = AsyncMock()
        client._driver = mock_driver

        with patch(
            "src.infrastructure.database.neo4j.AsyncGraphDatabase.driver",
        ) as mock_create:
            await client.connect()

            mock_create.assert_not_called()
            assert client._driver is mock_driver

    @pytest.mark.asyncio
    async def test_close_closes_driver(self, client: Neo4jClient) -> None:
        """Test that close closes the driver."""
        mock_driver = AsyncMock()
        client._driver = mock_driver

        await client.close()

        mock_driver.close.assert_called_once()
        assert client._driver is None
        assert client.is_connected is False

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, client: Neo4jClient) -> None:
        """Test that calling close when not connected is safe."""
        assert client._driver is None
        await client.close()  # Should not raise
        assert client._driver is None

    def test_driver_not_connected_raises(self, client: Neo4jClient) -> None:
        """Test accessing driver before connect raises error."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.driver


class TestNeo4jClientPing:
    """Tests for Neo4jClient ping method."""

    @pytest.mark.asyncio
    async def test_ping_when_connected(self, client: Neo4jClient) -> None:
        """Test ping returns True when connected."""
        mock_driver = AsyncMock()
        client._driver = mock_driver

        result = await client.ping()

        assert result is True
        mock_driver.verify_connectivity.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_when_disconnected(self, client: Neo4jClient) -> None:
        """Test ping returns False when not connected."""
        result = await client.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_on_error(self, client: Neo4jClient) -> None:
        """Test ping returns False on error."""
        mock_driver = AsyncMock()
        mock_driver.verify_connectivity.side_effect = Exception("Connection failed")
        client._driver = mock_driver

        result = await client.ping()

        assert result is False


class TestNeo4jClientSession:
    """Tests for Neo4jClient session context manager."""

    @pytest.mark.asyncio
    async def test_session_context_manager(self, client: Neo4jClient) -> None:
        """Test session context manager works correctly."""
        mock_driver = MagicMock()
        mock_session = AsyncMock()
        mock_driver.session.return_value.__aenter__.return_value = mock_session
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=None)
        client._driver = mock_driver

        async with client.session() as session:
            assert session is mock_session

        mock_driver.session.assert_called_once_with(database="neo4j")

    @pytest.mark.asyncio
    async def test_session_with_custom_database(self, client: Neo4jClient) -> None:
        """Test session with custom database name."""
        mock_driver = MagicMock()
        mock_session = AsyncMock()
        mock_driver.session.return_value.__aenter__.return_value = mock_session
        mock_driver.session.return_value.__aexit__ = AsyncMock(return_value=None)
        client._driver = mock_driver

        async with client.session(database="custom_db") as session:
            assert session is mock_session

        mock_driver.session.assert_called_once_with(database="custom_db")


class TestNeo4jClientQueries:
    """Tests for Neo4jClient query methods."""

    def _create_mock_record(self, data: dict[str, Any]) -> MagicMock:
        """Create a mock Neo4j record."""
        record = MagicMock()
        record.data.return_value = data
        return record

    @pytest.fixture
    def connected_client(self, client: Neo4jClient) -> Neo4jClient:
        """Create a connected client with mocked driver."""
        mock_driver = MagicMock()
        client._driver = mock_driver
        return client

    @pytest.mark.asyncio
    async def test_execute_query(self, connected_client: Neo4jClient) -> None:
        """Test execute_query returns records."""
        mock_record = self._create_mock_record({"name": "test"})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        records = await connected_client.execute_query("MATCH (n) RETURN n")

        assert len(records) == 1
        assert records[0]["name"] == "test"
        mock_session.run.assert_called_once_with("MATCH (n) RETURN n", {})

    @pytest.mark.asyncio
    async def test_execute_query_with_parameters(self, connected_client: Neo4jClient) -> None:
        """Test execute_query with parameters."""
        mock_record = self._create_mock_record({"name": "test"})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        await connected_client.execute_query(
            "MATCH (n {name: $name}) RETURN n",
            {"name": "test"},
        )

        mock_session.run.assert_called_once_with(
            "MATCH (n {name: $name}) RETURN n",
            {"name": "test"},
        )

    @pytest.mark.asyncio
    async def test_execute_read(self, connected_client: Neo4jClient) -> None:
        """Test execute_read with read transaction."""
        mock_record = self._create_mock_record({"count": 10})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()

        async def mock_execute_read(func: Any) -> list[dict[str, Any]]:
            mock_tx = AsyncMock()
            mock_tx.run.return_value = mock_result
            return await func(mock_tx)

        mock_session.execute_read = mock_execute_read
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        records = await connected_client.execute_read("MATCH (n) RETURN count(n) as count")

        assert len(records) == 1
        assert records[0]["count"] == 10

    @pytest.mark.asyncio
    async def test_execute_write(self, connected_client: Neo4jClient) -> None:
        """Test execute_write with write transaction."""
        mock_record = self._create_mock_record({"created": True})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()

        async def mock_execute_write(func: Any) -> list[dict[str, Any]]:
            mock_tx = AsyncMock()
            mock_tx.run.return_value = mock_result
            return await func(mock_tx)

        mock_session.execute_write = mock_execute_write
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        records = await connected_client.execute_write(
            "CREATE (n:Test) RETURN true as created"
        )

        assert len(records) == 1
        assert records[0]["created"] is True


class TestNeo4jClientHelpers:
    """Tests for Neo4jClient helper methods."""

    def _create_mock_record(self, data: dict[str, Any]) -> MagicMock:
        """Create a mock Neo4j record."""
        record = MagicMock()
        record.data.return_value = data
        return record

    @pytest.fixture
    def connected_client(self, client: Neo4jClient) -> Neo4jClient:
        """Create a connected client with mocked driver."""
        mock_driver = MagicMock()
        client._driver = mock_driver
        return client

    @pytest.mark.asyncio
    async def test_execute_query_single(self, connected_client: Neo4jClient) -> None:
        """Test execute_query_single returns single record."""
        mock_record = self._create_mock_record({"name": "test", "value": 42})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        record = await connected_client.execute_query_single("MATCH (n) RETURN n LIMIT 1")

        assert record is not None
        assert record["name"] == "test"
        assert record["value"] == 42

    @pytest.mark.asyncio
    async def test_execute_query_single_returns_none(
        self, connected_client: Neo4jClient
    ) -> None:
        """Test execute_query_single returns None when no results."""

        async def mock_iter() -> Any:
            return
            yield  # Make it an async generator

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        record = await connected_client.execute_query_single("MATCH (n:NonExistent) RETURN n")

        assert record is None

    @pytest.mark.asyncio
    async def test_execute_query_value(self, connected_client: Neo4jClient) -> None:
        """Test execute_query_value returns single value."""
        mock_record = self._create_mock_record({"value": 100})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        value = await connected_client.execute_query_value("RETURN 100 as value")

        assert value == 100

    @pytest.mark.asyncio
    async def test_count_nodes(self, connected_client: Neo4jClient) -> None:
        """Test count_nodes returns node count."""
        mock_record = self._create_mock_record({"value": 42})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        count = await connected_client.count_nodes("Document")

        assert count == 42

    @pytest.mark.asyncio
    async def test_node_exists_true(self, connected_client: Neo4jClient) -> None:
        """Test node_exists returns True when node exists."""
        mock_record = self._create_mock_record({"value": True})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        exists = await connected_client.node_exists("Document", "doc_uuid", "uuid123")

        assert exists is True

    @pytest.mark.asyncio
    async def test_node_exists_false(self, connected_client: Neo4jClient) -> None:
        """Test node_exists returns False when node doesn't exist."""
        mock_record = self._create_mock_record({"value": False})

        async def mock_iter() -> Any:
            yield mock_record

        mock_result = MagicMock()
        mock_result.__aiter__ = lambda self: mock_iter()

        mock_session = AsyncMock()
        mock_session.run.return_value = mock_result
        connected_client._driver.session.return_value.__aenter__.return_value = mock_session
        connected_client._driver.session.return_value.__aexit__ = AsyncMock(return_value=None)

        exists = await connected_client.node_exists("Document", "doc_uuid", "nonexistent")

        assert exists is False


class TestNeo4jClientSingleton:
    """Tests for Neo4jClient singleton functions."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_neo4j_client()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_neo4j_client()

    def test_get_neo4j_client_creates_instance(self, settings: Neo4jSettings) -> None:
        """Test get_neo4j_client creates instance."""
        client = get_neo4j_client(settings)

        assert client is not None
        assert isinstance(client, Neo4jClient)

    def test_get_neo4j_client_returns_same_instance(self, settings: Neo4jSettings) -> None:
        """Test get_neo4j_client returns same instance."""
        client1 = get_neo4j_client(settings)
        client2 = get_neo4j_client(settings)

        assert client1 is client2

    def test_get_neo4j_client_with_auto_settings(self) -> None:
        """Test get_neo4j_client loads settings automatically."""
        mock_neo4j_settings = Neo4jSettings(
            uri="bolt://localhost:7687",
            user="neo4j",
            password="auto_password",
        )
        mock_settings = MagicMock()
        mock_settings.neo4j = mock_neo4j_settings

        with patch("src.config.get_settings", return_value=mock_settings) as mock_get:
            client = get_neo4j_client()

            assert client is not None
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_neo4j_client(self, settings: Neo4jSettings) -> None:
        """Test close_neo4j_client closes and resets singleton."""
        client = get_neo4j_client(settings)
        mock_driver = AsyncMock()
        client._driver = mock_driver

        await close_neo4j_client()

        mock_driver.close.assert_called_once()
        # Verify singleton is reset
        new_client = get_neo4j_client(settings)
        assert new_client is not client

    @pytest.mark.asyncio
    async def test_close_neo4j_client_when_none(self) -> None:
        """Test close_neo4j_client when no client exists."""
        await close_neo4j_client()  # Should not raise
