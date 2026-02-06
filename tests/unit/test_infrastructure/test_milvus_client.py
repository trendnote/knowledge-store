"""Tests for Milvus client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.config import MilvusSettings
from src.infrastructure.database.milvus import (
    MilvusClient,
    close_milvus_client,
    get_milvus_client,
    reset_milvus_client,
)


@pytest.fixture
def settings() -> MilvusSettings:
    """Create test settings."""
    return MilvusSettings(
        host="localhost",
        port=19530,
        collection="test_collection",
    )


@pytest.fixture
def client(settings: MilvusSettings) -> MilvusClient:
    """Create test client."""
    return MilvusClient(settings)


class TestMilvusClientConnection:
    """Tests for MilvusClient connection management."""

    def test_connect_success(self, client: MilvusClient) -> None:
        """Test successful connection."""
        with (
            patch("src.infrastructure.database.milvus.connections.connect") as mock_connect,
            patch("src.infrastructure.database.milvus.utility.has_collection", return_value=True),
            patch("src.infrastructure.database.milvus.Collection") as mock_collection_class,
        ):
            mock_coll = MagicMock()
            mock_collection_class.return_value = mock_coll

            client.connect()

            mock_connect.assert_called_once()
            mock_coll.load.assert_called_once()
            assert client._connected is True
            assert client.is_connected is True

    def test_connect_is_idempotent(self, client: MilvusClient) -> None:
        """Test that calling connect multiple times doesn't reconnect."""
        client._connected = True

        with patch("src.infrastructure.database.milvus.connections.connect") as mock_connect:
            client.connect()

            mock_connect.assert_not_called()

    def test_connect_collection_not_exists_raises(self, client: MilvusClient) -> None:
        """Test that connect raises if collection doesn't exist."""
        with (
            patch("src.infrastructure.database.milvus.connections.connect"),
            patch("src.infrastructure.database.milvus.connections.disconnect"),
            patch("src.infrastructure.database.milvus.utility.has_collection", return_value=False),
            pytest.raises(RuntimeError, match="does not exist"),
        ):
            client.connect()

    def test_disconnect(self, client: MilvusClient) -> None:
        """Test disconnect."""
        client._connected = True
        mock_coll = MagicMock()
        client._collection = mock_coll

        with patch("src.infrastructure.database.milvus.connections.disconnect") as mock_disconnect:
            client.disconnect()

            mock_coll.release.assert_called_once()
            mock_disconnect.assert_called_once()
            assert client._connected is False
            assert client._collection is None

    def test_disconnect_is_idempotent(self, client: MilvusClient) -> None:
        """Test that calling disconnect when not connected is safe."""
        assert client._connected is False
        client.disconnect()  # Should not raise
        assert client._connected is False

    def test_collection_not_connected_raises(self, client: MilvusClient) -> None:
        """Test accessing collection before connect raises error."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.collection


class TestMilvusClientPing:
    """Tests for MilvusClient ping method."""

    def test_ping_when_connected(self, client: MilvusClient) -> None:
        """Test ping returns True when connected."""
        client._connected = True

        with patch("src.infrastructure.database.milvus.utility.list_collections"):
            result = client.ping()

        assert result is True

    def test_ping_when_disconnected(self, client: MilvusClient) -> None:
        """Test ping returns False when not connected."""
        client._connected = False

        result = client.ping()

        assert result is False

    def test_ping_on_error(self, client: MilvusClient) -> None:
        """Test ping returns False on error."""
        client._connected = True

        with patch("src.infrastructure.database.milvus.utility.list_collections", side_effect=Exception("error")):
            result = client.ping()

        assert result is False

    @pytest.mark.asyncio
    async def test_ping_async(self, client: MilvusClient) -> None:
        """Test async ping wrapper."""
        client._connected = True

        with patch("src.infrastructure.database.milvus.utility.list_collections"):
            result = await client.ping_async()

        assert result is True


class TestMilvusClientInsertDelete:
    """Tests for MilvusClient insert/delete operations."""

    @pytest.fixture
    def connected_client(self, client: MilvusClient) -> MilvusClient:
        """Create a connected client with mocked collection."""
        mock_coll = MagicMock()
        client._collection = mock_coll
        client._connected = True
        return client

    def test_insert(self, connected_client: MilvusClient) -> None:
        """Test insert operation."""
        mock_result = MagicMock()
        mock_result.primary_keys = ["uuid1", "uuid2"]
        connected_client._collection.insert.return_value = mock_result  # type: ignore[union-attr]

        data = [
            {"chunk_uuid": "uuid1", "doc_uuid": "doc1"},
            {"chunk_uuid": "uuid2", "doc_uuid": "doc1"},
        ]
        result = connected_client.insert(data)

        assert result == ["uuid1", "uuid2"]
        connected_client._collection.insert.assert_called_once_with(data)  # type: ignore[union-attr]
        connected_client._collection.flush.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_insert_async(self, connected_client: MilvusClient) -> None:
        """Test async insert wrapper."""
        mock_result = MagicMock()
        mock_result.primary_keys = ["uuid1"]
        connected_client._collection.insert.return_value = mock_result  # type: ignore[union-attr]

        data = [{"chunk_uuid": "uuid1"}]
        result = await connected_client.insert_async(data)

        assert result == ["uuid1"]

    def test_delete(self, connected_client: MilvusClient) -> None:
        """Test delete operation."""
        mock_result = MagicMock()
        mock_result.delete_count = 5
        connected_client._collection.delete.return_value = mock_result  # type: ignore[union-attr]

        result = connected_client.delete('doc_uuid == "doc1"')

        assert result == 5
        connected_client._collection.delete.assert_called_once_with('doc_uuid == "doc1"')  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_delete_async(self, connected_client: MilvusClient) -> None:
        """Test async delete wrapper."""
        mock_result = MagicMock()
        mock_result.delete_count = 3
        connected_client._collection.delete.return_value = mock_result  # type: ignore[union-attr]

        result = await connected_client.delete_async('chunk_uuid == "uuid1"')

        assert result == 3

    def test_flush(self, connected_client: MilvusClient) -> None:
        """Test flush operation."""
        connected_client.flush()
        connected_client._collection.flush.assert_called()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_flush_async(self, connected_client: MilvusClient) -> None:
        """Test async flush wrapper."""
        await connected_client.flush_async()
        connected_client._collection.flush.assert_called()  # type: ignore[union-attr]

    def test_count(self, connected_client: MilvusClient) -> None:
        """Test count operation."""
        connected_client._collection.num_entities = 100  # type: ignore[union-attr]

        result = connected_client.count()

        assert result == 100

    @pytest.mark.asyncio
    async def test_count_async(self, connected_client: MilvusClient) -> None:
        """Test async count wrapper."""
        connected_client._collection.num_entities = 50  # type: ignore[union-attr]

        result = await connected_client.count_async()

        assert result == 50


class TestMilvusClientSearch:
    """Tests for MilvusClient search operations."""

    @pytest.fixture
    def connected_client(self, client: MilvusClient) -> MilvusClient:
        """Create a connected client with mocked collection."""
        mock_coll = MagicMock()
        client._collection = mock_coll
        client._connected = True
        return client

    def _create_mock_hit(
        self, id_: str, score: float, distance: float, entity: dict[str, Any]
    ) -> MagicMock:
        """Create a mock search hit."""
        hit = MagicMock()
        hit.id = id_
        hit.score = score
        hit.distance = distance
        hit.entity = entity
        return hit

    def test_dense_search(self, connected_client: MilvusClient) -> None:
        """Test dense vector search."""
        mock_hit = self._create_mock_hit(
            "uuid1", 0.95, 0.05, {"chunk_uuid": "uuid1", "chunk_text": "test"}
        )
        mock_results = [[mock_hit]]
        connected_client._collection.search.return_value = mock_results  # type: ignore[union-attr]

        query_vector = [0.1] * 1024
        results = connected_client.dense_search(query_vector, limit=10)

        assert len(results) == 1
        assert results[0]["id"] == "uuid1"
        assert results[0]["score"] == 0.95
        assert results[0]["chunk_uuid"] == "uuid1"
        assert results[0]["chunk_text"] == "test"

        connected_client._collection.search.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_dense_search_async(self, connected_client: MilvusClient) -> None:
        """Test async dense search wrapper."""
        mock_hit = self._create_mock_hit("uuid1", 0.9, 0.1, {"chunk_uuid": "uuid1"})
        mock_results = [[mock_hit]]
        connected_client._collection.search.return_value = mock_results  # type: ignore[union-attr]

        query_vector = [0.1] * 1024
        results = await connected_client.dense_search_async(query_vector, limit=5)

        assert len(results) == 1
        assert results[0]["id"] == "uuid1"

    def test_dense_search_with_filter(self, connected_client: MilvusClient) -> None:
        """Test dense search with filter expression."""
        mock_results = [[]]
        connected_client._collection.search.return_value = mock_results  # type: ignore[union-attr]

        query_vector = [0.1] * 1024
        connected_client.dense_search(
            query_vector,
            limit=10,
            expr='security_level == "public"',
            output_fields=["chunk_uuid"],
        )

        call_args = connected_client._collection.search.call_args  # type: ignore[union-attr]
        assert call_args.kwargs["expr"] == 'security_level == "public"'
        assert call_args.kwargs["output_fields"] == ["chunk_uuid"]

    def test_sparse_search(self, connected_client: MilvusClient) -> None:
        """Test sparse vector search."""
        mock_hit = self._create_mock_hit(
            "uuid2", 0.85, 0.15, {"chunk_uuid": "uuid2", "chunk_text": "sparse test"}
        )
        mock_results = [[mock_hit]]
        connected_client._collection.search.return_value = mock_results  # type: ignore[union-attr]

        # Create a mock sparse vector (in real usage, this would be scipy.sparse.csr_array)
        mock_sparse = MagicMock()
        results = connected_client.sparse_search(mock_sparse, limit=10)

        assert len(results) == 1
        assert results[0]["id"] == "uuid2"
        assert results[0]["chunk_text"] == "sparse test"

    @pytest.mark.asyncio
    async def test_sparse_search_async(self, connected_client: MilvusClient) -> None:
        """Test async sparse search wrapper."""
        mock_hit = self._create_mock_hit("uuid3", 0.8, 0.2, {"chunk_uuid": "uuid3"})
        mock_results = [[mock_hit]]
        connected_client._collection.search.return_value = mock_results  # type: ignore[union-attr]

        mock_sparse = MagicMock()
        results = await connected_client.sparse_search_async(mock_sparse, limit=5)

        assert len(results) == 1

    def test_hybrid_search(self, connected_client: MilvusClient) -> None:
        """Test hybrid search with RRF reranking."""
        mock_hit = self._create_mock_hit(
            "uuid4", 0.92, 0.08, {"chunk_uuid": "uuid4", "doc_uuid": "doc1"}
        )
        mock_results = [[mock_hit]]
        connected_client._collection.hybrid_search.return_value = mock_results  # type: ignore[union-attr]

        with patch("pymilvus.AnnSearchRequest"), patch("pymilvus.RRFRanker"):
            query_dense = [0.1] * 1024
            query_sparse = MagicMock()
            results = connected_client.hybrid_search(query_dense, query_sparse, limit=10, rrf_k=60)

        assert len(results) == 1
        assert results[0]["id"] == "uuid4"
        assert results[0]["doc_uuid"] == "doc1"
        connected_client._collection.hybrid_search.assert_called_once()  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_hybrid_search_async(self, connected_client: MilvusClient) -> None:
        """Test async hybrid search wrapper."""
        mock_hit = self._create_mock_hit("uuid5", 0.88, 0.12, {"chunk_uuid": "uuid5"})
        mock_results = [[mock_hit]]
        connected_client._collection.hybrid_search.return_value = mock_results  # type: ignore[union-attr]

        with patch("pymilvus.AnnSearchRequest"), patch("pymilvus.RRFRanker"):
            query_dense = [0.1] * 1024
            query_sparse = MagicMock()
            results = await connected_client.hybrid_search_async(query_dense, query_sparse, limit=5)

        assert len(results) == 1


class TestMilvusClientSingleton:
    """Tests for MilvusClient singleton functions."""

    def setup_method(self) -> None:
        """Reset singleton before each test."""
        reset_milvus_client()

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_milvus_client()

    def test_get_milvus_client_creates_instance(self, settings: MilvusSettings) -> None:
        """Test get_milvus_client creates instance."""
        client = get_milvus_client(settings)

        assert client is not None
        assert isinstance(client, MilvusClient)

    def test_get_milvus_client_returns_same_instance(self, settings: MilvusSettings) -> None:
        """Test get_milvus_client returns same instance."""
        client1 = get_milvus_client(settings)
        client2 = get_milvus_client(settings)

        assert client1 is client2

    def test_get_milvus_client_with_auto_settings(self) -> None:
        """Test get_milvus_client loads settings automatically."""
        mock_milvus_settings = MilvusSettings(
            host="localhost",
            port=19530,
            collection="auto_collection",
        )
        mock_settings = MagicMock()
        mock_settings.milvus = mock_milvus_settings

        with patch("src.config.get_settings", return_value=mock_settings) as mock_get:
            client = get_milvus_client()

            assert client is not None
            mock_get.assert_called_once()

    def test_close_milvus_client(self, settings: MilvusSettings) -> None:
        """Test close_milvus_client closes and resets singleton."""
        client = get_milvus_client(settings)
        client._connected = True
        client._collection = MagicMock()

        with patch("src.infrastructure.database.milvus.connections.disconnect"):
            close_milvus_client()

        # Verify singleton is reset
        new_client = get_milvus_client(settings)
        assert new_client is not client

    def test_close_milvus_client_when_none(self) -> None:
        """Test close_milvus_client when no client exists."""
        close_milvus_client()  # Should not raise
