"""Document event models.

This module provides event models for document-related operations:
- DocumentCreatedEvent: When a new document is created
- DocumentUpdatedEvent: When a document is updated
- DocumentDeletedEvent: When a document is deleted
- SyncCompletedEvent: When synchronization completes
- SyncFailedEvent: When synchronization fails

Events are used for inter-service communication via Kafka.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventType(str, Enum):
    """Event types for document operations."""

    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"


@dataclass
class BaseEvent:
    """Base event model.

    All events inherit from this base class which provides
    common fields and serialization methods.

    Attributes:
        doc_uuid: Document UUID this event relates to
        event_type: Type of the event (set by subclass)
        timestamp: When the event occurred
        metadata: Additional event metadata
    """

    doc_uuid: str
    event_type: EventType = field(default=EventType.DOCUMENT_CREATED)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary.

        Returns:
            Dictionary representation of the event
        """
        return {
            "type": self.event_type.value,
            "doc_uuid": self.doc_uuid,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert event to JSON string.

        Returns:
            JSON string representation
        """
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaseEvent:
        """Create event from dictionary.

        Args:
            data: Dictionary with event data

        Returns:
            BaseEvent instance
        """
        timestamp_str = data.get("timestamp")
        if timestamp_str:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        else:
            timestamp = datetime.utcnow()

        return cls(
            doc_uuid=data["doc_uuid"],
            event_type=EventType(data["type"]),
            timestamp=timestamp,
            metadata=data.get("metadata", {}),
        )


@dataclass
class DocumentCreatedEvent(BaseEvent):
    """Document created event.

    Emitted when a new document is created and indexed.

    Attributes:
        title: Document title
        owner_id: User who created the document
        owner_org: Organization of the owner
        chunk_count: Number of chunks created
    """

    event_type: EventType = field(default=EventType.DOCUMENT_CREATED)
    title: str = ""
    owner_id: str = ""
    owner_org: str = "default"
    chunk_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with document-specific fields."""
        data = super().to_dict()
        data.update({
            "title": self.title,
            "owner_id": self.owner_id,
            "owner_org": self.owner_org,
            "chunk_count": self.chunk_count,
        })
        return data


@dataclass
class DocumentUpdatedEvent(BaseEvent):
    """Document updated event.

    Emitted when a document is modified.

    Attributes:
        title: Updated document title
        updated_by: User who updated the document
        content_changed: Whether content was modified (triggers re-indexing)
        new_chunk_count: Number of chunks after update
    """

    event_type: EventType = field(default=EventType.DOCUMENT_UPDATED)
    title: str = ""
    updated_by: str = ""
    content_changed: bool = False
    new_chunk_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with update-specific fields."""
        data = super().to_dict()
        data.update({
            "title": self.title,
            "updated_by": self.updated_by,
            "content_changed": self.content_changed,
        })
        if self.new_chunk_count is not None:
            data["new_chunk_count"] = self.new_chunk_count
        return data


@dataclass
class DocumentDeletedEvent(BaseEvent):
    """Document deleted event.

    Emitted when a document is deleted.

    Attributes:
        deleted_by: User who deleted the document
        chunk_count: Number of chunks that were deleted
    """

    event_type: EventType = field(default=EventType.DOCUMENT_DELETED)
    deleted_by: str = ""
    chunk_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with deletion-specific fields."""
        data = super().to_dict()
        data.update({
            "deleted_by": self.deleted_by,
            "chunk_count": self.chunk_count,
        })
        return data


@dataclass
class SyncCompletedEvent(BaseEvent):
    """Sync completed event.

    Emitted when data synchronization across stores completes.

    Attributes:
        source_event: Original event that triggered sync
        synced_stores: List of stores that were synchronized
        duration_ms: Time taken for sync in milliseconds
    """

    event_type: EventType = field(default=EventType.SYNC_COMPLETED)
    source_event: str = ""
    synced_stores: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with sync-specific fields."""
        data = super().to_dict()
        data.update({
            "source_event": self.source_event,
            "synced_stores": self.synced_stores,
            "duration_ms": self.duration_ms,
        })
        return data


@dataclass
class SyncFailedEvent(BaseEvent):
    """Sync failed event.

    Emitted when data synchronization fails.

    Attributes:
        source_event: Original event that triggered sync
        error: Error message
        failed_stores: List of stores that failed
        retry_count: Number of retry attempts made
    """

    event_type: EventType = field(default=EventType.SYNC_FAILED)
    source_event: str = ""
    error: str = ""
    failed_stores: list[str] = field(default_factory=list)
    retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary with failure-specific fields."""
        data = super().to_dict()
        data.update({
            "source_event": self.source_event,
            "error": self.error,
            "failed_stores": self.failed_stores,
            "retry_count": self.retry_count,
        })
        return data


def parse_event(data: dict[str, Any]) -> BaseEvent:
    """Parse event from dictionary.

    Factory function that creates the appropriate event type
    based on the 'type' field in the data.

    Args:
        data: Dictionary with event data

    Returns:
        Appropriate event instance

    Raises:
        ValueError: If event type is unknown or missing

    Example:
        >>> event = parse_event({
        ...     "type": "document.created",
        ...     "doc_uuid": "doc-123",
        ...     "title": "My Doc",
        ...     "owner_id": "user1",
        ... })
        >>> isinstance(event, DocumentCreatedEvent)
        True
    """
    event_type_str = data.get("type", "")
    if not event_type_str:
        raise ValueError("Event type is required")

    try:
        event_type = EventType(event_type_str)
    except ValueError:
        raise ValueError(f"Unknown event type: {event_type_str}")

    # Parse timestamp
    timestamp_str = data.get("timestamp")
    if timestamp_str:
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    else:
        timestamp = datetime.utcnow()

    metadata = data.get("metadata", {})

    if event_type == EventType.DOCUMENT_CREATED:
        return DocumentCreatedEvent(
            event_type=event_type,
            doc_uuid=data["doc_uuid"],
            timestamp=timestamp,
            metadata=metadata,
            title=data.get("title", ""),
            owner_id=data.get("owner_id", ""),
            owner_org=data.get("owner_org", "default"),
            chunk_count=data.get("chunk_count", 0),
        )

    elif event_type == EventType.DOCUMENT_UPDATED:
        return DocumentUpdatedEvent(
            event_type=event_type,
            doc_uuid=data["doc_uuid"],
            timestamp=timestamp,
            metadata=metadata,
            title=data.get("title", ""),
            updated_by=data.get("updated_by", ""),
            content_changed=data.get("content_changed", False),
            new_chunk_count=data.get("new_chunk_count"),
        )

    elif event_type == EventType.DOCUMENT_DELETED:
        return DocumentDeletedEvent(
            event_type=event_type,
            doc_uuid=data["doc_uuid"],
            timestamp=timestamp,
            metadata=metadata,
            deleted_by=data.get("deleted_by", ""),
            chunk_count=data.get("chunk_count", 0),
        )

    elif event_type == EventType.SYNC_COMPLETED:
        return SyncCompletedEvent(
            event_type=event_type,
            doc_uuid=data["doc_uuid"],
            timestamp=timestamp,
            metadata=metadata,
            source_event=data.get("source_event", ""),
            synced_stores=data.get("synced_stores", []),
            duration_ms=data.get("duration_ms", 0.0),
        )

    elif event_type == EventType.SYNC_FAILED:
        return SyncFailedEvent(
            event_type=event_type,
            doc_uuid=data["doc_uuid"],
            timestamp=timestamp,
            metadata=metadata,
            source_event=data.get("source_event", ""),
            error=data.get("error", ""),
            failed_stores=data.get("failed_stores", []),
            retry_count=data.get("retry_count", 0),
        )

    else:
        return BaseEvent.from_dict(data)
