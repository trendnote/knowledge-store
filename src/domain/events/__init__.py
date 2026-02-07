"""Domain events package.

This package provides event models for event-driven architecture:
- Document events: Created, Updated, Deleted
- Sync events: Completed, Failed
"""

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

__all__ = [
    "BaseEvent",
    "DocumentCreatedEvent",
    "DocumentDeletedEvent",
    "DocumentUpdatedEvent",
    "EventType",
    "SyncCompletedEvent",
    "SyncFailedEvent",
    "parse_event",
]
