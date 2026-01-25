# Task Execution Plan: 4.2.1 - Kafka Consumer 및 Sync Service 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.2.1 |
| **Task Name** | Kafka Consumer 및 Sync Service 구현 |
| **Estimate** | 6h |
| **Priority** | P1 |
| **Dependencies** | Task 2.1.4 |

### Description
Kafka 이벤트를 수신하여 변경 사항을 동기화하는 서비스를 구현합니다.

### Acceptance Criteria
- [ ] `src/services/sync_service.py` 생성
- [ ] `src/infrastructure/messaging/consumer.py` 완성
- [ ] `document.updated` 이벤트 처리
- [ ] `document.deleted` 이벤트 처리
- [ ] 3개 저장소 동기화
- [ ] `sync.completed` 이벤트 발행

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.6 Sync Service
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-4

### 2.2 이벤트 기반 동기화
```
Producer (Document Service)
    │
    ├─► document.created
    ├─► document.updated
    └─► document.deleted
          │
          ▼
      Kafka Topic
          │
          ▼
   Consumer (Sync Service)
          │
          ├─► PostgreSQL 동기화
          ├─► Milvus 동기화
          └─► Neo4j 동기화
                │
                ▼
          sync.completed
```

### 2.3 설계 결정
1. **Consumer Group**: 확장성을 위한 그룹 기반 소비
2. **At-least-once**: 재처리 안전한 이벤트 핸들러
3. **Dead Letter**: 실패 이벤트 별도 처리
4. **Backoff**: 재시도 시 지수 백오프

### 2.4 이벤트 스키마
```python
# document.updated
{
    "type": "document.updated",
    "doc_uuid": "...",
    "title": "...",
    "updated_by": "user1",
    "content_changed": true,
    "timestamp": "2026-01-26T10:00:00Z"
}

# document.deleted
{
    "type": "document.deleted",
    "doc_uuid": "...",
    "deleted_by": "user1",
    "timestamp": "2026-01-26T10:00:00Z"
}
```

---

## 3. Implementation Steps

### Step 1: 이벤트 모델 정의 (1h)

**작업 내용:**
1. 이벤트 기본 모델
2. 구체적인 이벤트 타입
3. 이벤트 파싱

**src/domain/events/document_events.py:**
```python
"""Document event models."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json


class EventType(str, Enum):
    """Event types."""

    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"


@dataclass
class BaseEvent:
    """Base event model."""

    event_type: EventType
    doc_uuid: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.event_type.value,
            "doc_uuid": self.doc_uuid,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseEvent":
        """Create from dictionary."""
        return cls(
            event_type=EventType(data["type"]),
            doc_uuid=data["doc_uuid"],
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.utcnow().isoformat())),
            metadata=data.get("metadata", {}),
        )


@dataclass
class DocumentCreatedEvent(BaseEvent):
    """Document created event."""

    title: str = ""
    owner_id: str = ""
    chunk_count: int = 0

    def __post_init__(self):
        self.event_type = EventType.DOCUMENT_CREATED

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "title": self.title,
            "owner_id": self.owner_id,
            "chunk_count": self.chunk_count,
        })
        return d


@dataclass
class DocumentUpdatedEvent(BaseEvent):
    """Document updated event."""

    title: str = ""
    updated_by: str = ""
    content_changed: bool = False

    def __post_init__(self):
        self.event_type = EventType.DOCUMENT_UPDATED

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "title": self.title,
            "updated_by": self.updated_by,
            "content_changed": self.content_changed,
        })
        return d


@dataclass
class DocumentDeletedEvent(BaseEvent):
    """Document deleted event."""

    deleted_by: str = ""

    def __post_init__(self):
        self.event_type = EventType.DOCUMENT_DELETED

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "deleted_by": self.deleted_by,
        })
        return d


@dataclass
class SyncCompletedEvent(BaseEvent):
    """Sync completed event."""

    source_event: str = ""
    synced_stores: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def __post_init__(self):
        self.event_type = EventType.SYNC_COMPLETED

    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d.update({
            "source_event": self.source_event,
            "synced_stores": self.synced_stores,
            "duration_ms": self.duration_ms,
        })
        return d


def parse_event(data: dict[str, Any]) -> BaseEvent:
    """Parse event from dictionary."""
    event_type = EventType(data.get("type", ""))

    if event_type == EventType.DOCUMENT_CREATED:
        return DocumentCreatedEvent(
            doc_uuid=data["doc_uuid"],
            title=data.get("title", ""),
            owner_id=data.get("owner_id", ""),
            chunk_count=data.get("chunk_count", 0),
        )
    elif event_type == EventType.DOCUMENT_UPDATED:
        return DocumentUpdatedEvent(
            doc_uuid=data["doc_uuid"],
            title=data.get("title", ""),
            updated_by=data.get("updated_by", ""),
            content_changed=data.get("content_changed", False),
        )
    elif event_type == EventType.DOCUMENT_DELETED:
        return DocumentDeletedEvent(
            doc_uuid=data["doc_uuid"],
            deleted_by=data.get("deleted_by", ""),
        )
    else:
        return BaseEvent.from_dict(data)
```

**완료 기준:**
- [ ] BaseEvent 모델
- [ ] 구체적인 이벤트 클래스
- [ ] 이벤트 파싱 함수

---

### Step 2: Kafka Consumer 완성 (1.5h)

**작업 내용:**
1. Consumer 클래스 확장
2. 이벤트 핸들러 등록
3. 에러 처리

**src/infrastructure/messaging/consumer.py:**
```python
"""Kafka consumer implementation."""
import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

from aiokafka import AIOKafkaConsumer
from aiokafka.errors import KafkaError

from src.config import KafkaSettings

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class KafkaConsumer:
    """Async Kafka consumer with event handlers."""

    def __init__(
        self,
        settings: KafkaSettings,
        topics: list[str],
        group_id: str,
    ) -> None:
        """Initialize consumer.

        Args:
            settings: Kafka settings
            topics: Topics to subscribe
            group_id: Consumer group ID
        """
        self._settings = settings
        self._topics = topics
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None
        self._handlers: dict[str, list[EventHandler]] = {}
        self._running = False

    async def start(self) -> None:
        """Start consumer."""
        if self._consumer is not None:
            return

        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._settings.bootstrap_servers,
            group_id=self._group_id,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )

        await self._consumer.start()
        logger.info(f"Consumer started: topics={self._topics}, group={self._group_id}")

    async def stop(self) -> None:
        """Stop consumer."""
        self._running = False
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
            logger.info("Consumer stopped")

    def register_handler(self, event_type: str, handler: EventHandler) -> None:
        """Register event handler.

        Args:
            event_type: Event type to handle
            handler: Async handler function
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Registered handler for {event_type}")

    async def _process_message(self, message: Any) -> None:
        """Process a single message.

        Args:
            message: Kafka message
        """
        try:
            data = message.value
            event_type = data.get("type", "")

            handlers = self._handlers.get(event_type, [])
            if not handlers:
                logger.debug(f"No handlers for event type: {event_type}")
                return

            for handler in handlers:
                try:
                    await handler(data)
                except Exception as e:
                    logger.error(f"Handler error for {event_type}: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Message processing error: {e}", exc_info=True)

    async def consume(self) -> None:
        """Start consuming messages.

        Runs until stop() is called.
        """
        if self._consumer is None:
            await self.start()

        self._running = True
        logger.info("Starting message consumption")

        try:
            async for message in self._consumer:
                if not self._running:
                    break
                await self._process_message(message)
        except KafkaError as e:
            logger.error(f"Kafka error: {e}")
            raise
        finally:
            logger.info("Message consumption stopped")

    async def consume_batch(
        self,
        max_records: int = 100,
        timeout_ms: int = 1000,
    ) -> list[dict[str, Any]]:
        """Consume a batch of messages.

        Args:
            max_records: Maximum records to fetch
            timeout_ms: Timeout in milliseconds

        Returns:
            List of message data
        """
        if self._consumer is None:
            await self.start()

        records = await self._consumer.getmany(
            timeout_ms=timeout_ms,
            max_records=max_records,
        )

        messages = []
        for tp, batch in records.items():
            for message in batch:
                messages.append(message.value)

        return messages
```

**완료 기준:**
- [ ] Consumer 클래스 확장
- [ ] 핸들러 등록 메커니즘
- [ ] 배치 소비 지원

---

### Step 3: Sync Service 구현 (2h)

**작업 내용:**
1. SyncService 클래스
2. 이벤트 핸들러 구현
3. 저장소 동기화 로직

**src/services/sync_service.py:**
```python
"""Sync service for event-driven synchronization."""
import asyncio
import logging
import time
from typing import Any

from src.domain.events.document_events import (
    DocumentDeletedEvent,
    DocumentUpdatedEvent,
    EventType,
    SyncCompletedEvent,
    parse_event,
)
from src.infrastructure.messaging.consumer import KafkaConsumer

logger = logging.getLogger(__name__)


class SyncService:
    """Service for synchronizing data across stores."""

    def __init__(
        self,
        consumer: KafkaConsumer,
        postgres_repo: Any,
        milvus_repo: Any,
        neo4j_repo: Any,
        embedding_service: Any,
        kafka_producer: Any | None = None,
    ) -> None:
        """Initialize sync service.

        Args:
            consumer: Kafka consumer
            postgres_repo: PostgreSQL repository
            milvus_repo: Milvus repository
            neo4j_repo: Neo4j repository
            embedding_service: Embedding service
            kafka_producer: Kafka producer for sync events
        """
        self._consumer = consumer
        self._postgres = postgres_repo
        self._milvus = milvus_repo
        self._neo4j = neo4j_repo
        self._embedding = embedding_service
        self._producer = kafka_producer

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register event handlers."""
        self._consumer.register_handler(
            EventType.DOCUMENT_UPDATED.value,
            self._handle_document_updated,
        )
        self._consumer.register_handler(
            EventType.DOCUMENT_DELETED.value,
            self._handle_document_deleted,
        )

    async def _handle_document_updated(self, data: dict[str, Any]) -> None:
        """Handle document updated event.

        Syncs changes to Milvus and Neo4j if content changed.

        Args:
            data: Event data
        """
        start_time = time.time()
        event = parse_event(data)

        if not isinstance(event, DocumentUpdatedEvent):
            logger.warning(f"Unexpected event type: {type(event)}")
            return

        logger.info(f"Processing document.updated: {event.doc_uuid}")

        synced_stores = []

        try:
            # If content changed, need to re-sync vectors and graph
            if event.content_changed:
                # Get updated chunks from PostgreSQL
                chunks = await self._postgres.get_chunks_by_doc(event.doc_uuid)

                if chunks:
                    # Regenerate embeddings
                    texts = [c.text for c in chunks]
                    embeddings = self._embedding.encode(texts)

                    # Update Milvus
                    await self._milvus.delete_vectors(
                        [c.chunk_uuid for c in chunks]
                    )
                    await self._milvus.insert_vectors([
                        {
                            "chunk_uuid": c.chunk_uuid,
                            "doc_uuid": event.doc_uuid,
                            "dense_embedding": embeddings.dense[i],
                            "sparse_embedding": embeddings.sparse[i],
                            "text_preview": c.text[:100],
                        }
                        for i, c in enumerate(chunks)
                    ])
                    synced_stores.append("milvus")

                    # Update Neo4j
                    await self._neo4j.delete_document_graph(event.doc_uuid)
                    await self._neo4j.create_document_node({
                        "doc_uuid": event.doc_uuid,
                        "title": event.title,
                    })
                    await self._neo4j.create_chunk_nodes([
                        {
                            "chunk_uuid": c.chunk_uuid,
                            "doc_uuid": event.doc_uuid,
                            "text_preview": c.text[:100],
                        }
                        for c in chunks
                    ])
                    synced_stores.append("neo4j")

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Document sync completed: {event.doc_uuid} "
                f"stores={synced_stores} duration={duration_ms:.2f}ms"
            )

            # Publish sync completed event
            await self._publish_sync_completed(
                event.doc_uuid,
                EventType.DOCUMENT_UPDATED.value,
                synced_stores,
                duration_ms,
            )

        except Exception as e:
            logger.error(f"Sync failed for {event.doc_uuid}: {e}", exc_info=True)
            await self._publish_sync_failed(event.doc_uuid, str(e))

    async def _handle_document_deleted(self, data: dict[str, Any]) -> None:
        """Handle document deleted event.

        Ensures data is removed from all stores.

        Args:
            data: Event data
        """
        start_time = time.time()
        event = parse_event(data)

        if not isinstance(event, DocumentDeletedEvent):
            return

        logger.info(f"Processing document.deleted: {event.doc_uuid}")

        synced_stores = []

        try:
            # Delete from Milvus (if any remaining)
            chunks = await self._postgres.get_chunks_by_doc(event.doc_uuid)
            if chunks:
                await self._milvus.delete_vectors([c.chunk_uuid for c in chunks])
                synced_stores.append("milvus")

            # Delete from Neo4j
            await self._neo4j.delete_document_graph(event.doc_uuid)
            synced_stores.append("neo4j")

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"Delete sync completed: {event.doc_uuid}")

            await self._publish_sync_completed(
                event.doc_uuid,
                EventType.DOCUMENT_DELETED.value,
                synced_stores,
                duration_ms,
            )

        except Exception as e:
            logger.error(f"Delete sync failed: {e}", exc_info=True)

    async def _publish_sync_completed(
        self,
        doc_uuid: str,
        source_event: str,
        synced_stores: list[str],
        duration_ms: float,
    ) -> None:
        """Publish sync completed event."""
        if self._producer is None:
            return

        event = SyncCompletedEvent(
            doc_uuid=doc_uuid,
            source_event=source_event,
            synced_stores=synced_stores,
            duration_ms=duration_ms,
        )

        await self._producer.send("sync.completed", event.to_dict())

    async def _publish_sync_failed(self, doc_uuid: str, error: str) -> None:
        """Publish sync failed event."""
        if self._producer is None:
            return

        await self._producer.send("sync.failed", {
            "doc_uuid": doc_uuid,
            "error": error,
        })

    async def start(self) -> None:
        """Start sync service."""
        logger.info("Starting sync service")
        await self._consumer.consume()

    async def stop(self) -> None:
        """Stop sync service."""
        logger.info("Stopping sync service")
        await self._consumer.stop()
```

**완료 기준:**
- [ ] SyncService 클래스
- [ ] document.updated 핸들러
- [ ] document.deleted 핸들러
- [ ] sync.completed 이벤트 발행

---

### Step 4: 테스트 작성 (1.5h)

**작업 내용:**
1. Consumer 테스트
2. SyncService 테스트

**tests/unit/test_services/test_sync_service.py:**
```python
"""Tests for sync service."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.sync_service import SyncService
from src.domain.events.document_events import EventType


@pytest.fixture
def mock_consumer() -> MagicMock:
    """Create mock consumer."""
    mock = MagicMock()
    mock.register_handler = MagicMock()
    mock.consume = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.fixture
def mock_repos() -> dict:
    """Create mock repositories."""
    return {
        "postgres_repo": MagicMock(),
        "milvus_repo": MagicMock(),
        "neo4j_repo": MagicMock(),
        "embedding_service": MagicMock(),
        "kafka_producer": MagicMock(),
    }


@pytest.fixture
def sync_service(mock_consumer: MagicMock, mock_repos: dict) -> SyncService:
    """Create sync service."""
    return SyncService(
        consumer=mock_consumer,
        **mock_repos,
    )


class TestSyncService:
    """Tests for SyncService."""

    def test_registers_handlers(
        self,
        sync_service: SyncService,
        mock_consumer: MagicMock,
    ) -> None:
        """Test handlers are registered."""
        assert mock_consumer.register_handler.call_count == 2

    async def test_handle_document_updated_with_content(
        self,
        sync_service: SyncService,
        mock_repos: dict,
    ) -> None:
        """Test handling document updated with content change."""
        mock_repos["postgres_repo"].get_chunks_by_doc = AsyncMock(
            return_value=[MagicMock(chunk_uuid="c1", text="test")]
        )
        mock_repos["embedding_service"].encode.return_value = MagicMock(
            dense=[[0.1] * 1024],
            sparse=[{1: 0.5}],
        )
        mock_repos["milvus_repo"].delete_vectors = AsyncMock()
        mock_repos["milvus_repo"].insert_vectors = AsyncMock()
        mock_repos["neo4j_repo"].delete_document_graph = AsyncMock()
        mock_repos["neo4j_repo"].create_document_node = AsyncMock()
        mock_repos["neo4j_repo"].create_chunk_nodes = AsyncMock()
        mock_repos["kafka_producer"].send = AsyncMock()

        event_data = {
            "type": "document.updated",
            "doc_uuid": "doc-123",
            "title": "Test",
            "updated_by": "user1",
            "content_changed": True,
        }

        await sync_service._handle_document_updated(event_data)

        mock_repos["milvus_repo"].delete_vectors.assert_called_once()
        mock_repos["milvus_repo"].insert_vectors.assert_called_once()
        mock_repos["neo4j_repo"].delete_document_graph.assert_called_once()

    async def test_handle_document_deleted(
        self,
        sync_service: SyncService,
        mock_repos: dict,
    ) -> None:
        """Test handling document deleted."""
        mock_repos["postgres_repo"].get_chunks_by_doc = AsyncMock(
            return_value=[MagicMock(chunk_uuid="c1")]
        )
        mock_repos["milvus_repo"].delete_vectors = AsyncMock()
        mock_repos["neo4j_repo"].delete_document_graph = AsyncMock()
        mock_repos["kafka_producer"].send = AsyncMock()

        event_data = {
            "type": "document.deleted",
            "doc_uuid": "doc-123",
            "deleted_by": "user1",
        }

        await sync_service._handle_document_deleted(event_data)

        mock_repos["milvus_repo"].delete_vectors.assert_called_once()
        mock_repos["neo4j_repo"].delete_document_graph.assert_called_once()
```

**완료 기준:**
- [ ] 핸들러 등록 테스트
- [ ] 업데이트 이벤트 테스트
- [ ] 삭제 이벤트 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_registers_handlers` | 핸들러 등록 | 2개 등록 |
| `test_handle_updated` | 업데이트 처리 | 동기화 수행 |
| `test_handle_deleted` | 삭제 처리 | 정리 수행 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_sync_within_5min` | 동기화 시간 | < 5분 |
| `test_sync_completion` | 완료 이벤트 | 발행됨 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 메시지 순서 | High | Medium | 이벤트 순서 보장 토픽 |
| 동기화 실패 | High | Low | Dead letter, 재시도 |
| 중복 처리 | Medium | Medium | 멱등성 보장 |

---

## 6. Definition of Done

- [ ] `src/services/sync_service.py` 구현
- [ ] `src/infrastructure/messaging/consumer.py` 완성
- [ ] 이벤트 모델 정의
- [ ] document.updated 핸들러
- [ ] document.deleted 핸들러
- [ ] sync.completed 발행
- [ ] 테스트 작성 및 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 이벤트 모델 | 1h | - |
| Step 2: Consumer 완성 | 1.5h | - |
| Step 3: SyncService | 2h | - |
| Step 4: 테스트 | 1.5h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
