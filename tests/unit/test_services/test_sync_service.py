"""Tests for sync service."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.events.document_events import EventType
from src.services.sync_service import (
    SyncService,
    get_sync_service,
    reset_sync_service,
    set_sync_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_consumer() -> MagicMock:
    """Create mock event consumer."""
    mock = MagicMock()
    mock.register_handler = MagicMock()
    mock.consume = AsyncMock()
    mock.stop = AsyncMock()
    mock.start = AsyncMock()
    mock.is_running = False
    mock.is_started = False
    return mock


@pytest.fixture
def mock_chunk() -> MagicMock:
    """Create mock chunk object."""
    chunk = MagicMock()
    chunk.chunk_uuid = "chunk-123"
    chunk.text = "This is test content for the chunk."
    return chunk


@pytest.fixture
def mock_postgres_repo(mock_chunk: MagicMock) -> MagicMock:
    """Create mock PostgreSQL repository."""
    mock = MagicMock()
    mock.get_chunks_by_doc = AsyncMock(return_value=[mock_chunk])
    mock.get_document = AsyncMock(return_value=MagicMock(
        doc_uuid="doc-123",
        title="Test Document",
    ))
    return mock


@pytest.fixture
def mock_milvus_repo() -> MagicMock:
    """Create mock Milvus repository."""
    mock = MagicMock()
    mock.delete_vectors = AsyncMock()
    mock.insert_vectors = AsyncMock()
    return mock


@pytest.fixture
def mock_neo4j_repo() -> MagicMock:
    """Create mock Neo4j repository."""
    mock = MagicMock()
    mock.delete_document_graph = AsyncMock()
    mock.create_document_node = AsyncMock()
    mock.create_chunk_nodes = AsyncMock()
    return mock


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    mock = MagicMock()
    embeddings = MagicMock()
    embeddings.dense = [[0.1] * 1024]
    embeddings.sparse = [{1: 0.5, 2: 0.3}]
    mock.encode.return_value = embeddings
    return mock


@pytest.fixture
def mock_kafka_producer() -> MagicMock:
    """Create mock Kafka producer."""
    mock = MagicMock()
    mock.send = AsyncMock()
    return mock


@pytest.fixture
def sync_service(
    mock_consumer: MagicMock,
    mock_postgres_repo: MagicMock,
    mock_milvus_repo: MagicMock,
    mock_neo4j_repo: MagicMock,
    mock_embedding_service: MagicMock,
    mock_kafka_producer: MagicMock,
) -> SyncService:
    """Create sync service with mocked dependencies."""
    return SyncService(
        consumer=mock_consumer,
        postgres_repo=mock_postgres_repo,
        milvus_repo=mock_milvus_repo,
        neo4j_repo=mock_neo4j_repo,
        embedding_service=mock_embedding_service,
        kafka_producer=mock_kafka_producer,
    )


# =============================================================================
# Test Handler Registration
# =============================================================================


class TestHandlerRegistration:
    """Tests for event handler registration."""

    def test_registers_update_handler(
        self,
        sync_service: SyncService,
        mock_consumer: MagicMock,
    ) -> None:
        """Test that update handler is registered."""
        calls = mock_consumer.register_handler.call_args_list
        event_types = [call[0][0] for call in calls]
        assert EventType.DOCUMENT_UPDATED.value in event_types

    def test_registers_delete_handler(
        self,
        sync_service: SyncService,
        mock_consumer: MagicMock,
    ) -> None:
        """Test that delete handler is registered."""
        calls = mock_consumer.register_handler.call_args_list
        event_types = [call[0][0] for call in calls]
        assert EventType.DOCUMENT_DELETED.value in event_types

    def test_registers_two_handlers(
        self,
        sync_service: SyncService,
        mock_consumer: MagicMock,
    ) -> None:
        """Test that exactly two handlers are registered."""
        assert mock_consumer.register_handler.call_count == 2


# =============================================================================
# Test Document Updated Handler
# =============================================================================


class TestDocumentUpdatedHandler:
    """Tests for document updated event handler."""

    @pytest.mark.asyncio
    async def test_handle_updated_with_content_change(
        self,
        sync_service: SyncService,
        mock_milvus_repo: MagicMock,
        mock_neo4j_repo: MagicMock,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test handling update with content change."""
        event_data = {
            "type": "document.updated",
            "doc_uuid": "doc-123",
            "title": "Updated Title",
            "updated_by": "user1",
            "content_changed": True,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await sync_service._handle_document_updated(event_data)

        # Verify Milvus operations
        mock_milvus_repo.delete_vectors.assert_called_once()
        mock_milvus_repo.insert_vectors.assert_called_once()

        # Verify Neo4j operations
        mock_neo4j_repo.delete_document_graph.assert_called_once_with("doc-123")
        mock_neo4j_repo.create_document_node.assert_called_once()
        mock_neo4j_repo.create_chunk_nodes.assert_called_once()

        # Verify sync completed event published
        mock_kafka_producer.send.assert_called()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == EventType.SYNC_COMPLETED.value

    @pytest.mark.asyncio
    async def test_handle_updated_without_content_change(
        self,
        sync_service: SyncService,
        mock_milvus_repo: MagicMock,
        mock_neo4j_repo: MagicMock,
    ) -> None:
        """Test handling update without content change skips re-indexing."""
        event_data = {
            "type": "document.updated",
            "doc_uuid": "doc-123",
            "title": "Updated Title",
            "updated_by": "user1",
            "content_changed": False,
        }

        await sync_service._handle_document_updated(event_data)

        # No re-indexing operations should occur
        mock_milvus_repo.delete_vectors.assert_not_called()
        mock_milvus_repo.insert_vectors.assert_not_called()
        mock_neo4j_repo.delete_document_graph.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_updated_no_chunks(
        self,
        sync_service: SyncService,
        mock_postgres_repo: MagicMock,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test handling update when no chunks found."""
        mock_postgres_repo.get_chunks_by_doc = AsyncMock(return_value=[])

        event_data = {
            "type": "document.updated",
            "doc_uuid": "doc-123",
            "title": "Updated Title",
            "updated_by": "user1",
            "content_changed": True,
        }

        await sync_service._handle_document_updated(event_data)

        # No vector operations when no chunks
        mock_milvus_repo.insert_vectors.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_updated_milvus_failure(
        self,
        sync_service: SyncService,
        mock_milvus_repo: MagicMock,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test handling when Milvus sync fails."""
        mock_milvus_repo.delete_vectors = AsyncMock(
            side_effect=Exception("Milvus error")
        )

        event_data = {
            "type": "document.updated",
            "doc_uuid": "doc-123",
            "title": "Updated Title",
            "updated_by": "user1",
            "content_changed": True,
        }

        await sync_service._handle_document_updated(event_data)

        # Should publish sync failed or partial failure
        mock_kafka_producer.send.assert_called()

    @pytest.mark.asyncio
    async def test_handle_updated_unexpected_event_type(
        self,
        sync_service: SyncService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test handling wrong event type logs warning."""
        event_data = {
            "type": "document.created",  # Wrong type
            "doc_uuid": "doc-123",
            "title": "Test",
            "owner_id": "user1",
        }

        await sync_service._handle_document_updated(event_data)

        # Should not process
        mock_milvus_repo.delete_vectors.assert_not_called()


# =============================================================================
# Test Document Deleted Handler
# =============================================================================


class TestDocumentDeletedHandler:
    """Tests for document deleted event handler."""

    @pytest.mark.asyncio
    async def test_handle_deleted_success(
        self,
        sync_service: SyncService,
        mock_milvus_repo: MagicMock,
        mock_neo4j_repo: MagicMock,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test successful document deletion sync."""
        event_data = {
            "type": "document.deleted",
            "doc_uuid": "doc-123",
            "deleted_by": "user1",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await sync_service._handle_document_deleted(event_data)

        # Verify cleanup operations
        mock_milvus_repo.delete_vectors.assert_called_once()
        mock_neo4j_repo.delete_document_graph.assert_called_once_with("doc-123")

        # Verify sync completed event
        mock_kafka_producer.send.assert_called()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == EventType.SYNC_COMPLETED.value

    @pytest.mark.asyncio
    async def test_handle_deleted_no_chunks(
        self,
        sync_service: SyncService,
        mock_postgres_repo: MagicMock,
        mock_milvus_repo: MagicMock,
        mock_neo4j_repo: MagicMock,
    ) -> None:
        """Test deletion when no chunks exist."""
        mock_postgres_repo.get_chunks_by_doc = AsyncMock(return_value=[])

        event_data = {
            "type": "document.deleted",
            "doc_uuid": "doc-123",
            "deleted_by": "user1",
        }

        await sync_service._handle_document_deleted(event_data)

        # Milvus delete should not be called with empty list
        # Neo4j should still be cleaned
        mock_neo4j_repo.delete_document_graph.assert_called_once_with("doc-123")

    @pytest.mark.asyncio
    async def test_handle_deleted_neo4j_failure(
        self,
        sync_service: SyncService,
        mock_neo4j_repo: MagicMock,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test handling when Neo4j deletion fails."""
        mock_neo4j_repo.delete_document_graph = AsyncMock(
            side_effect=Exception("Neo4j error")
        )

        event_data = {
            "type": "document.deleted",
            "doc_uuid": "doc-123",
            "deleted_by": "user1",
        }

        await sync_service._handle_document_deleted(event_data)

        # Should publish failure event
        mock_kafka_producer.send.assert_called()


# =============================================================================
# Test Sync Events Publishing
# =============================================================================


class TestSyncEventPublishing:
    """Tests for sync event publishing."""

    @pytest.mark.asyncio
    async def test_publish_sync_completed(
        self,
        sync_service: SyncService,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test publishing sync completed event."""
        await sync_service._publish_sync_completed(
            doc_uuid="doc-123",
            source_event="document.updated",
            synced_stores=["milvus", "neo4j"],
            duration_ms=150.5,
        )

        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == "sync.completed"
        event_data = call_args[0][1]
        assert event_data["doc_uuid"] == "doc-123"
        assert "milvus" in event_data["synced_stores"]
        assert "neo4j" in event_data["synced_stores"]

    @pytest.mark.asyncio
    async def test_publish_sync_failed(
        self,
        sync_service: SyncService,
        mock_kafka_producer: MagicMock,
    ) -> None:
        """Test publishing sync failed event."""
        await sync_service._publish_sync_failed(
            doc_uuid="doc-123",
            source_event="document.updated",
            error="Connection failed",
            failed_stores=["neo4j"],
            retry_count=2,
        )

        mock_kafka_producer.send.assert_called_once()
        call_args = mock_kafka_producer.send.call_args
        assert call_args[0][0] == "sync.failed"
        event_data = call_args[0][1]
        assert event_data["doc_uuid"] == "doc-123"
        assert event_data["error"] == "Connection failed"
        assert event_data["retry_count"] == 2

    @pytest.mark.asyncio
    async def test_publish_without_producer(
        self,
        mock_consumer: MagicMock,
        mock_postgres_repo: MagicMock,
        mock_milvus_repo: MagicMock,
        mock_neo4j_repo: MagicMock,
        mock_embedding_service: MagicMock,
    ) -> None:
        """Test publishing when no producer configured."""
        service = SyncService(
            consumer=mock_consumer,
            postgres_repo=mock_postgres_repo,
            milvus_repo=mock_milvus_repo,
            neo4j_repo=mock_neo4j_repo,
            embedding_service=mock_embedding_service,
            kafka_producer=None,  # No producer
        )

        # Should not raise
        await service._publish_sync_completed(
            doc_uuid="doc-123",
            source_event="document.updated",
            synced_stores=["milvus"],
            duration_ms=100.0,
        )


# =============================================================================
# Test Service Lifecycle
# =============================================================================


class TestServiceLifecycle:
    """Tests for sync service lifecycle."""

    @pytest.mark.asyncio
    async def test_stop(
        self,
        sync_service: SyncService,
        mock_consumer: MagicMock,
    ) -> None:
        """Test stopping the service."""
        sync_service._running = True

        await sync_service.stop()

        mock_consumer.stop.assert_called_once()
        assert sync_service._running is False

    @pytest.mark.asyncio
    async def test_process_single_event_updated(
        self,
        sync_service: SyncService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test processing single update event."""
        event_data = {
            "type": "document.updated",
            "doc_uuid": "doc-123",
            "title": "Test",
            "updated_by": "user1",
            "content_changed": True,
        }

        await sync_service.process_single_event(event_data)

        mock_milvus_repo.delete_vectors.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_single_event_deleted(
        self,
        sync_service: SyncService,
        mock_neo4j_repo: MagicMock,
    ) -> None:
        """Test processing single delete event."""
        event_data = {
            "type": "document.deleted",
            "doc_uuid": "doc-123",
            "deleted_by": "user1",
        }

        await sync_service.process_single_event(event_data)

        mock_neo4j_repo.delete_document_graph.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_unknown_event_type(
        self,
        sync_service: SyncService,
        mock_milvus_repo: MagicMock,
    ) -> None:
        """Test processing unknown event type."""
        event_data = {
            "type": "unknown.event",
            "doc_uuid": "doc-123",
        }

        await sync_service.process_single_event(event_data)

        # Should not process
        mock_milvus_repo.delete_vectors.assert_not_called()


# =============================================================================
# Test Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def teardown_method(self) -> None:
        """Reset singleton after each test."""
        reset_sync_service()

    def test_set_and_get_sync_service(
        self,
        sync_service: SyncService,
    ) -> None:
        """Test setting and getting sync service."""
        set_sync_service(sync_service)
        retrieved = get_sync_service()
        assert retrieved is sync_service

    def test_get_uninitialized_raises(self) -> None:
        """Test getting uninitialized service raises error."""
        with pytest.raises(RuntimeError) as exc_info:
            get_sync_service()
        assert "not initialized" in str(exc_info.value)

    def test_reset_clears_singleton(
        self,
        sync_service: SyncService,
    ) -> None:
        """Test reset clears singleton."""
        set_sync_service(sync_service)
        reset_sync_service()

        with pytest.raises(RuntimeError):
            get_sync_service()
