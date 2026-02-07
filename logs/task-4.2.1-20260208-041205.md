# Task 4.2.1 - Kafka Consumer 및 Sync Service 구현

## Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.2.1 |
| **Task Name** | Kafka Consumer 및 Sync Service 구현 |
| **Estimate** | 6h |
| **Priority** | P1 |
| **Status** | Completed |
| **Date** | 2026-02-08 04:12:05 |
| **GitHub Issue** | https://github.com/trendnote/knowledge-store/issues/28 |

---

## Implementation Summary

### 1. Event Models (`src/domain/events/document_events.py`)

Created comprehensive event models for event-driven architecture:

#### Event Types
- `EventType` enum with values:
  - `DOCUMENT_CREATED`: "document.created"
  - `DOCUMENT_UPDATED`: "document.updated"
  - `DOCUMENT_DELETED`: "document.deleted"
  - `SYNC_COMPLETED`: "sync.completed"
  - `SYNC_FAILED`: "sync.failed"

#### Event Classes
- `BaseEvent`: Base dataclass with doc_uuid, event_type, timestamp, metadata
- `DocumentCreatedEvent`: title, owner_id, owner_org, chunk_count
- `DocumentUpdatedEvent`: title, updated_by, content_changed, new_chunk_count
- `DocumentDeletedEvent`: deleted_by, chunk_count
- `SyncCompletedEvent`: source_event, synced_stores, duration_ms
- `SyncFailedEvent`: source_event, error, failed_stores, retry_count

#### Utilities
- `parse_event()`: Factory function to create appropriate event from dict
- Serialization: `to_dict()`, `to_json()`, `from_dict()`

### 2. Event Consumer (`src/infrastructure/messaging/consumer.py`)

Created `EventConsumer` wrapper with handler registration:

#### Features
- Handler registration per event type
- Multiple handlers per event type support
- Automatic message routing to handlers
- Error handling per handler (doesn't stop other handlers)
- Manual offset commit after successful processing
- Batch processing support
- Graceful shutdown

#### Methods
- `register_handler(event_type, handler)`: Register async handler
- `unregister_handler(event_type, handler)`: Remove handler
- `consume()`: Start continuous consumption
- `consume_batch()`: Consume batch of messages
- `consume_one()`: Consume single message

#### Factory Functions
- `get_event_consumer()`: Get/create cached consumer
- `close_event_consumers()`: Close all consumers
- `reset_event_consumers()`: Reset for testing

### 3. Sync Service (`src/services/sync_service.py`)

Created event-driven synchronization service:

#### Responsibilities
- Listen for document events via Kafka
- Synchronize data across PostgreSQL, Milvus, Neo4j
- Publish sync completion/failure events

#### Event Handlers
1. **document.updated handler**:
   - If content_changed: re-generate embeddings, update Milvus vectors, update Neo4j graph
   - Publishes sync.completed or sync.failed

2. **document.deleted handler**:
   - Delete vectors from Milvus
   - Delete document graph from Neo4j
   - Publishes sync.completed or sync.failed

#### Protocol Interfaces
- `PostgresRepositoryProtocol`
- `MilvusRepositoryProtocol`
- `Neo4jRepositoryProtocol`
- `EmbeddingServiceProtocol`
- `KafkaProducerProtocol`

---

## Test Results

### Unit Tests

```
tests/unit/test_domain/test_document_events.py: 31 passed
tests/unit/test_infrastructure/test_event_consumer.py: 22 passed
tests/unit/test_services/test_sync_service.py: 23 passed

Total: 76 tests passed
```

### Test Categories

#### Event Model Tests (31 tests)
- TestEventType: 6 tests
- TestBaseEvent: 4 tests
- TestDocumentCreatedEvent: 3 tests
- TestDocumentUpdatedEvent: 3 tests
- TestDocumentDeletedEvent: 2 tests
- TestSyncCompletedEvent: 2 tests
- TestSyncFailedEvent: 2 tests
- TestParseEvent: 9 tests

#### Event Consumer Tests (22 tests)
- TestHandlerRegistration: 6 tests
- TestMessageProcessing: 6 tests
- TestConsumerLifecycle: 6 tests
- TestBatchProcessing: 3 tests
- TestFactoryFunctions: 3 tests

#### Sync Service Tests (23 tests)
- TestHandlerRegistration: 3 tests
- TestDocumentUpdatedHandler: 5 tests
- TestDocumentDeletedHandler: 3 tests
- TestSyncEventPublishing: 3 tests
- TestServiceLifecycle: 4 tests
- TestFactoryFunctions: 3 tests

---

## Files Created

| File | Description |
|------|-------------|
| `src/domain/events/__init__.py` | Events package init |
| `src/domain/events/document_events.py` | Event models and parse function |
| `src/infrastructure/messaging/consumer.py` | EventConsumer with handler registration |
| `src/services/sync_service.py` | Sync service for event-driven synchronization |
| `tests/unit/test_domain/__init__.py` | Test domain package init |
| `tests/unit/test_domain/test_document_events.py` | Event model tests |
| `tests/unit/test_infrastructure/test_event_consumer.py` | Event consumer tests |
| `tests/unit/test_services/test_sync_service.py` | Sync service tests |

## Files Modified

| File | Changes |
|------|---------|
| `src/infrastructure/messaging/__init__.py` | Added EventConsumer exports |
| `src/services/__init__.py` | Added SyncService exports |

---

## Architecture Notes

### Event Flow
```
Document Service
    ├─► document.created ─┐
    ├─► document.updated ─┼─► Kafka Topics
    └─► document.deleted ─┘
                          │
                          ▼
                   EventConsumer
                          │
                          ▼
                    SyncService
                          │
           ┌──────────────┼──────────────┐
           ▼              ▼              ▼
       PostgreSQL      Milvus        Neo4j
           │              │              │
           └──────────────┴──────────────┘
                          │
                          ▼
               sync.completed / sync.failed
```

### Design Decisions
1. **EventConsumer wrapper**: Separates handler registration from raw Kafka consumption
2. **Protocol interfaces**: Allows easy mocking for testing
3. **Partial failure handling**: Syncs to each store independently, publishes partial failure if needed
4. **At-least-once semantics**: Manual commit after successful processing

---

## Acceptance Criteria Status

- [x] `src/services/sync_service.py` created
- [x] `src/infrastructure/messaging/consumer.py` completed
- [x] `document.updated` event handling
- [x] `document.deleted` event handling
- [x] 3-store synchronization (PostgreSQL, Milvus, Neo4j)
- [x] `sync.completed` event publishing
- [x] All tests passing

---

## Next Steps

1. Integration testing with real Kafka
2. Add dead letter queue for failed events
3. Implement retry with exponential backoff
4. Add metrics and monitoring

---

## Notes

- Event consumer uses manual offset commit for reliability
- Sync service handles partial failures gracefully
- All handlers are async for non-blocking operation
- Factory functions provide singleton management for testing
