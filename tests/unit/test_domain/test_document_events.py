"""Tests for document event models."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from src.domain.events.document_events import (
    BaseEvent,
    DocumentCreatedEvent,
    DocumentDeletedEvent,
    DocumentUpdatedEvent,
    EventType,
    SyncCompletedEvent,
    SyncFailedEvent,
    parse_event,
)


# =============================================================================
# Test EventType Enum
# =============================================================================


class TestEventType:
    """Tests for EventType enum."""

    def test_document_created_value(self) -> None:
        """Test document created event type value."""
        assert EventType.DOCUMENT_CREATED.value == "document.created"

    def test_document_updated_value(self) -> None:
        """Test document updated event type value."""
        assert EventType.DOCUMENT_UPDATED.value == "document.updated"

    def test_document_deleted_value(self) -> None:
        """Test document deleted event type value."""
        assert EventType.DOCUMENT_DELETED.value == "document.deleted"

    def test_sync_completed_value(self) -> None:
        """Test sync completed event type value."""
        assert EventType.SYNC_COMPLETED.value == "sync.completed"

    def test_sync_failed_value(self) -> None:
        """Test sync failed event type value."""
        assert EventType.SYNC_FAILED.value == "sync.failed"

    def test_enum_from_string(self) -> None:
        """Test creating enum from string."""
        assert EventType("document.created") == EventType.DOCUMENT_CREATED
        assert EventType("document.updated") == EventType.DOCUMENT_UPDATED


# =============================================================================
# Test BaseEvent
# =============================================================================


class TestBaseEvent:
    """Tests for BaseEvent model."""

    def test_create_base_event(self) -> None:
        """Test creating base event."""
        event = BaseEvent(
            event_type=EventType.DOCUMENT_CREATED,
            doc_uuid="doc-123",
        )
        assert event.event_type == EventType.DOCUMENT_CREATED
        assert event.doc_uuid == "doc-123"
        assert isinstance(event.timestamp, datetime)
        assert event.metadata == {}

    def test_to_dict(self) -> None:
        """Test converting event to dictionary."""
        event = BaseEvent(
            event_type=EventType.DOCUMENT_CREATED,
            doc_uuid="doc-123",
            metadata={"key": "value"},
        )
        data = event.to_dict()
        assert data["type"] == "document.created"
        assert data["doc_uuid"] == "doc-123"
        assert data["metadata"]["key"] == "value"
        assert "timestamp" in data

    def test_to_json(self) -> None:
        """Test converting event to JSON."""
        event = BaseEvent(
            event_type=EventType.DOCUMENT_CREATED,
            doc_uuid="doc-123",
        )
        json_str = event.to_json()
        data = json.loads(json_str)
        assert data["type"] == "document.created"
        assert data["doc_uuid"] == "doc-123"

    def test_from_dict(self) -> None:
        """Test creating event from dictionary."""
        data = {
            "type": "document.created",
            "doc_uuid": "doc-123",
            "timestamp": "2026-01-26T10:00:00",
            "metadata": {"key": "value"},
        }
        event = BaseEvent.from_dict(data)
        assert event.event_type == EventType.DOCUMENT_CREATED
        assert event.doc_uuid == "doc-123"
        assert event.metadata["key"] == "value"


# =============================================================================
# Test DocumentCreatedEvent
# =============================================================================


class TestDocumentCreatedEvent:
    """Tests for DocumentCreatedEvent model."""

    def test_create_event(self) -> None:
        """Test creating document created event."""
        event = DocumentCreatedEvent(
            doc_uuid="doc-123",
            title="Test Document",
            owner_id="user1",
            owner_org="engineering",
            chunk_count=5,
        )
        assert event.event_type == EventType.DOCUMENT_CREATED
        assert event.title == "Test Document"
        assert event.owner_id == "user1"
        assert event.owner_org == "engineering"
        assert event.chunk_count == 5

    def test_to_dict_includes_fields(self) -> None:
        """Test to_dict includes document-specific fields."""
        event = DocumentCreatedEvent(
            doc_uuid="doc-123",
            title="Test Document",
            owner_id="user1",
            chunk_count=5,
        )
        data = event.to_dict()
        assert data["title"] == "Test Document"
        assert data["owner_id"] == "user1"
        assert data["chunk_count"] == 5

    def test_default_values(self) -> None:
        """Test default values."""
        event = DocumentCreatedEvent(
            event_type=EventType.DOCUMENT_CREATED,
            doc_uuid="doc-123",
        )
        assert event.title == ""
        assert event.owner_id == ""
        assert event.owner_org == "default"
        assert event.chunk_count == 0


# =============================================================================
# Test DocumentUpdatedEvent
# =============================================================================


class TestDocumentUpdatedEvent:
    """Tests for DocumentUpdatedEvent model."""

    def test_create_event(self) -> None:
        """Test creating document updated event."""
        event = DocumentUpdatedEvent(
            doc_uuid="doc-123",
            title="Updated Title",
            updated_by="user1",
            content_changed=True,
            new_chunk_count=10,
        )
        assert event.event_type == EventType.DOCUMENT_UPDATED
        assert event.title == "Updated Title"
        assert event.updated_by == "user1"
        assert event.content_changed is True
        assert event.new_chunk_count == 10

    def test_to_dict_includes_fields(self) -> None:
        """Test to_dict includes update-specific fields."""
        event = DocumentUpdatedEvent(
            doc_uuid="doc-123",
            title="Updated Title",
            updated_by="user1",
            content_changed=True,
        )
        data = event.to_dict()
        assert data["title"] == "Updated Title"
        assert data["updated_by"] == "user1"
        assert data["content_changed"] is True

    def test_content_changed_default(self) -> None:
        """Test content_changed defaults to False."""
        event = DocumentUpdatedEvent(
            event_type=EventType.DOCUMENT_UPDATED,
            doc_uuid="doc-123",
        )
        assert event.content_changed is False


# =============================================================================
# Test DocumentDeletedEvent
# =============================================================================


class TestDocumentDeletedEvent:
    """Tests for DocumentDeletedEvent model."""

    def test_create_event(self) -> None:
        """Test creating document deleted event."""
        event = DocumentDeletedEvent(
            doc_uuid="doc-123",
            deleted_by="user1",
            chunk_count=5,
        )
        assert event.event_type == EventType.DOCUMENT_DELETED
        assert event.deleted_by == "user1"
        assert event.chunk_count == 5

    def test_to_dict_includes_fields(self) -> None:
        """Test to_dict includes deletion-specific fields."""
        event = DocumentDeletedEvent(
            doc_uuid="doc-123",
            deleted_by="user1",
            chunk_count=5,
        )
        data = event.to_dict()
        assert data["deleted_by"] == "user1"
        assert data["chunk_count"] == 5


# =============================================================================
# Test SyncCompletedEvent
# =============================================================================


class TestSyncCompletedEvent:
    """Tests for SyncCompletedEvent model."""

    def test_create_event(self) -> None:
        """Test creating sync completed event."""
        event = SyncCompletedEvent(
            doc_uuid="doc-123",
            source_event="document.updated",
            synced_stores=["milvus", "neo4j"],
            duration_ms=150.5,
        )
        assert event.event_type == EventType.SYNC_COMPLETED
        assert event.source_event == "document.updated"
        assert "milvus" in event.synced_stores
        assert "neo4j" in event.synced_stores
        assert event.duration_ms == 150.5

    def test_to_dict_includes_fields(self) -> None:
        """Test to_dict includes sync-specific fields."""
        event = SyncCompletedEvent(
            doc_uuid="doc-123",
            source_event="document.updated",
            synced_stores=["milvus"],
            duration_ms=100.0,
        )
        data = event.to_dict()
        assert data["source_event"] == "document.updated"
        assert data["synced_stores"] == ["milvus"]
        assert data["duration_ms"] == 100.0


# =============================================================================
# Test SyncFailedEvent
# =============================================================================


class TestSyncFailedEvent:
    """Tests for SyncFailedEvent model."""

    def test_create_event(self) -> None:
        """Test creating sync failed event."""
        event = SyncFailedEvent(
            doc_uuid="doc-123",
            source_event="document.updated",
            error="Connection failed",
            failed_stores=["neo4j"],
            retry_count=2,
        )
        assert event.event_type == EventType.SYNC_FAILED
        assert event.error == "Connection failed"
        assert "neo4j" in event.failed_stores
        assert event.retry_count == 2

    def test_to_dict_includes_fields(self) -> None:
        """Test to_dict includes failure-specific fields."""
        event = SyncFailedEvent(
            doc_uuid="doc-123",
            source_event="document.deleted",
            error="Timeout",
            failed_stores=["milvus"],
            retry_count=1,
        )
        data = event.to_dict()
        assert data["error"] == "Timeout"
        assert data["failed_stores"] == ["milvus"]
        assert data["retry_count"] == 1


# =============================================================================
# Test parse_event Function
# =============================================================================


class TestParseEvent:
    """Tests for parse_event function."""

    def test_parse_document_created(self) -> None:
        """Test parsing document created event."""
        data = {
            "type": "document.created",
            "doc_uuid": "doc-123",
            "title": "Test Doc",
            "owner_id": "user1",
            "owner_org": "engineering",
            "chunk_count": 5,
        }
        event = parse_event(data)
        assert isinstance(event, DocumentCreatedEvent)
        assert event.title == "Test Doc"
        assert event.owner_id == "user1"

    def test_parse_document_updated(self) -> None:
        """Test parsing document updated event."""
        data = {
            "type": "document.updated",
            "doc_uuid": "doc-123",
            "title": "Updated Title",
            "updated_by": "user1",
            "content_changed": True,
        }
        event = parse_event(data)
        assert isinstance(event, DocumentUpdatedEvent)
        assert event.content_changed is True

    def test_parse_document_deleted(self) -> None:
        """Test parsing document deleted event."""
        data = {
            "type": "document.deleted",
            "doc_uuid": "doc-123",
            "deleted_by": "user1",
            "chunk_count": 5,
        }
        event = parse_event(data)
        assert isinstance(event, DocumentDeletedEvent)
        assert event.deleted_by == "user1"

    def test_parse_sync_completed(self) -> None:
        """Test parsing sync completed event."""
        data = {
            "type": "sync.completed",
            "doc_uuid": "doc-123",
            "source_event": "document.updated",
            "synced_stores": ["milvus", "neo4j"],
            "duration_ms": 150.5,
        }
        event = parse_event(data)
        assert isinstance(event, SyncCompletedEvent)
        assert event.duration_ms == 150.5

    def test_parse_sync_failed(self) -> None:
        """Test parsing sync failed event."""
        data = {
            "type": "sync.failed",
            "doc_uuid": "doc-123",
            "source_event": "document.updated",
            "error": "Connection failed",
            "failed_stores": ["neo4j"],
            "retry_count": 2,
        }
        event = parse_event(data)
        assert isinstance(event, SyncFailedEvent)
        assert event.error == "Connection failed"

    def test_parse_with_timestamp(self) -> None:
        """Test parsing event with timestamp."""
        data = {
            "type": "document.created",
            "doc_uuid": "doc-123",
            "timestamp": "2026-01-26T10:00:00Z",
        }
        event = parse_event(data)
        assert event.timestamp.year == 2026
        assert event.timestamp.month == 1

    def test_parse_missing_type_raises(self) -> None:
        """Test parsing without type raises error."""
        data = {
            "doc_uuid": "doc-123",
        }
        with pytest.raises(ValueError) as exc_info:
            parse_event(data)
        assert "required" in str(exc_info.value).lower()

    def test_parse_unknown_type_raises(self) -> None:
        """Test parsing unknown type raises error."""
        data = {
            "type": "unknown.event",
            "doc_uuid": "doc-123",
        }
        with pytest.raises(ValueError) as exc_info:
            parse_event(data)
        assert "Unknown event type" in str(exc_info.value)

    def test_parse_preserves_metadata(self) -> None:
        """Test parsing preserves metadata."""
        data = {
            "type": "document.created",
            "doc_uuid": "doc-123",
            "metadata": {"custom_key": "custom_value"},
        }
        event = parse_event(data)
        assert event.metadata["custom_key"] == "custom_value"
