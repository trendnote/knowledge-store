# Task Execution Plan: 2.1.4 - Kafka Client 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.1.4 |
| **Task Name** | Kafka Client 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.2.2 |

### Description
aiokafka 기반 Kafka Producer/Consumer를 구현합니다.

### Acceptance Criteria
- [ ] `src/infrastructure/messaging/kafka.py` 생성
- [ ] Producer 클래스 (메시지 발행)
- [ ] Consumer 클래스 (메시지 구독)
- [ ] JSON 직렬화/역직렬화
- [ ] 연결 상태 확인

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.4 Infrastructure Layer
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 2.3 Message Queue

### 2.2 aiokafka 주요 기능
```python
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

# Producer
producer = AIOKafkaProducer(bootstrap_servers='localhost:9092')
await producer.start()
await producer.send_and_wait('topic', b'message')
await producer.stop()

# Consumer
consumer = AIOKafkaConsumer('topic', bootstrap_servers='localhost:9092')
await consumer.start()
async for msg in consumer:
    print(msg.value)
await consumer.stop()
```

### 2.3 설계 결정
1. **Async Native**: aiokafka 사용 (동기 kafka-python 대신)
2. **JSON Serialization**: dict → JSON bytes 자동 변환
3. **Error Handling**: 재시도 및 데드레터 큐 고려
4. **Graceful Shutdown**: stop() 호출 보장

### 2.4 클래스 구조
```
KafkaProducer
├── __init__(settings: KafkaSettings)
├── start() -> None
├── stop() -> None
├── is_connected() -> bool
├── send(topic, value, key) -> None
└── send_batch(topic, messages) -> None

KafkaConsumer
├── __init__(settings: KafkaSettings, topics, group_id)
├── start() -> None
├── stop() -> None
├── is_connected() -> bool
├── consume() -> AsyncIterator[dict]
└── commit() -> None
```

### 2.5 Topics 정의
```
document.created    # 문서 생성 이벤트
document.updated    # 문서 수정 이벤트
document.deleted    # 문서 삭제 이벤트
sync.completed      # 동기화 완료 이벤트
```

---

## 3. Implementation Steps

### Step 1: KafkaProducer 클래스 구현 (1.5h)

**작업 내용:**
1. KafkaProducer 클래스 정의
2. start/stop 메서드
3. send 메서드
4. JSON 직렬화

**src/infrastructure/messaging/kafka.py:**
```python
"""Kafka async producer and consumer."""
import json
from typing import Any, AsyncIterator

from aiokafka import AIOKafkaProducer, AIOKafkaConsumer

from src.config import KafkaSettings


class KafkaProducer:
    """Async Kafka producer for publishing messages."""

    def __init__(self, settings: KafkaSettings) -> None:
        """Initialize Kafka producer.

        Args:
            settings: Kafka connection settings
        """
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None

    @property
    def producer(self) -> AIOKafkaProducer:
        """Get producer (raises if not started)."""
        if self._producer is None:
            raise RuntimeError("KafkaProducer is not started. Call start() first.")
        return self._producer

    async def start(self) -> None:
        """Start the producer."""
        if self._producer is not None:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",  # Wait for all replicas
            retries=3,
            retry_backoff_ms=100,
        )
        await self._producer.start()

    async def stop(self) -> None:
        """Stop the producer."""
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    def is_connected(self) -> bool:
        """Check if producer is connected."""
        return self._producer is not None

    async def send(
        self,
        topic: str,
        value: dict[str, Any],
        key: str | None = None,
    ) -> None:
        """Send a message to topic.

        Args:
            topic: Topic name
            value: Message value (will be JSON serialized)
            key: Optional message key
        """
        await self.producer.send_and_wait(topic, value=value, key=key)

    async def send_batch(
        self,
        topic: str,
        messages: list[dict[str, Any]],
        keys: list[str | None] | None = None,
    ) -> None:
        """Send multiple messages to topic.

        Args:
            topic: Topic name
            messages: List of message values
            keys: Optional list of message keys
        """
        if keys is None:
            keys = [None] * len(messages)

        if len(messages) != len(keys):
            raise ValueError("messages and keys must have same length")

        for value, key in zip(messages, keys):
            await self.producer.send(topic, value=value, key=key)

        # Flush all pending messages
        await self.producer.flush()
```

**완료 기준:**
- [ ] KafkaProducer 클래스 완성
- [ ] start/stop 메서드 구현
- [ ] send/send_batch 메서드 구현

---

### Step 2: KafkaConsumer 클래스 구현 (1.5h)

**작업 내용:**
1. KafkaConsumer 클래스 정의
2. start/stop 메서드
3. consume async iterator
4. commit 메서드

**src/infrastructure/messaging/kafka.py (계속):**
```python
class KafkaConsumer:
    """Async Kafka consumer for subscribing to messages."""

    def __init__(
        self,
        settings: KafkaSettings,
        topics: list[str],
        group_id: str | None = None,
    ) -> None:
        """Initialize Kafka consumer.

        Args:
            settings: Kafka connection settings
            topics: List of topics to subscribe
            group_id: Consumer group ID (default from settings)
        """
        self._settings = settings
        self._topics = topics
        self._group_id = group_id or settings.consumer_group
        self._consumer: AIOKafkaConsumer | None = None

    @property
    def consumer(self) -> AIOKafkaConsumer:
        """Get consumer (raises if not started)."""
        if self._consumer is None:
            raise RuntimeError("KafkaConsumer is not started. Call start() first.")
        return self._consumer

    async def start(self) -> None:
        """Start the consumer."""
        if self._consumer is not None:
            return

        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._settings.bootstrap_servers,
            group_id=self._group_id,
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
            auto_offset_reset="earliest",
            enable_auto_commit=False,  # Manual commit for reliability
        )
        await self._consumer.start()

    async def stop(self) -> None:
        """Stop the consumer."""
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    def is_connected(self) -> bool:
        """Check if consumer is connected."""
        return self._consumer is not None

    async def consume(self) -> AsyncIterator[dict[str, Any]]:
        """Consume messages from topics.

        Yields:
            Parsed message dictionaries with metadata

        Example:
            async for msg in consumer.consume():
                print(msg["topic"], msg["value"])
                await consumer.commit()
        """
        async for msg in self.consumer:
            yield {
                "topic": msg.topic,
                "partition": msg.partition,
                "offset": msg.offset,
                "key": msg.key,
                "value": msg.value,
                "timestamp": msg.timestamp,
            }

    async def consume_one(self, timeout_ms: int = 1000) -> dict[str, Any] | None:
        """Consume a single message with timeout.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            Message dict or None if timeout
        """
        try:
            data = await self.consumer.getone()
            return {
                "topic": data.topic,
                "partition": data.partition,
                "offset": data.offset,
                "key": data.key,
                "value": data.value,
                "timestamp": data.timestamp,
            }
        except Exception:
            return None

    async def commit(self) -> None:
        """Commit current offsets."""
        await self.consumer.commit()

    async def seek_to_beginning(self) -> None:
        """Seek to beginning of all partitions."""
        await self.consumer.seek_to_beginning()

    async def seek_to_end(self) -> None:
        """Seek to end of all partitions."""
        await self.consumer.seek_to_end()
```

**완료 기준:**
- [ ] KafkaConsumer 클래스 완성
- [ ] start/stop 메서드 구현
- [ ] consume async iterator 구현
- [ ] commit 메서드 구현

---

### Step 3: Factory 함수 및 Event Types (0.5h)

**작업 내용:**
1. Factory 함수
2. Event type 상수 정의
3. __init__.py 설정

**src/infrastructure/messaging/kafka.py (계속):**
```python
# Event Types
class KafkaTopics:
    """Kafka topic names."""
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    SYNC_COMPLETED = "sync.completed"

    @classmethod
    def all_document_topics(cls) -> list[str]:
        """Get all document-related topics."""
        return [
            cls.DOCUMENT_CREATED,
            cls.DOCUMENT_UPDATED,
            cls.DOCUMENT_DELETED,
        ]


# Singleton instances
_producer: KafkaProducer | None = None
_consumers: dict[str, KafkaConsumer] = {}


def get_kafka_producer(settings: KafkaSettings | None = None) -> KafkaProducer:
    """Get or create Kafka producer singleton."""
    global _producer
    if _producer is None:
        if settings is None:
            from src.config import get_settings
            settings = get_settings().kafka
        _producer = KafkaProducer(settings)
    return _producer


def get_kafka_consumer(
    topics: list[str],
    group_id: str | None = None,
    settings: KafkaSettings | None = None,
) -> KafkaConsumer:
    """Get or create Kafka consumer.

    Note: Different topic combinations create different consumers.
    """
    if settings is None:
        from src.config import get_settings
        settings = get_settings().kafka

    key = f"{','.join(sorted(topics))}:{group_id or settings.consumer_group}"

    if key not in _consumers:
        _consumers[key] = KafkaConsumer(settings, topics, group_id)

    return _consumers[key]


async def close_kafka_clients() -> None:
    """Close all Kafka clients."""
    global _producer, _consumers

    if _producer is not None:
        await _producer.stop()
        _producer = None

    for consumer in _consumers.values():
        await consumer.stop()
    _consumers.clear()
```

**src/infrastructure/messaging/__init__.py:**
```python
"""Messaging infrastructure clients."""
from src.infrastructure.messaging.kafka import (
    KafkaProducer,
    KafkaConsumer,
    KafkaTopics,
    get_kafka_producer,
    get_kafka_consumer,
    close_kafka_clients,
)

__all__ = [
    "KafkaProducer",
    "KafkaConsumer",
    "KafkaTopics",
    "get_kafka_producer",
    "get_kafka_consumer",
    "close_kafka_clients",
]
```

**완료 기준:**
- [ ] Factory 함수 구현
- [ ] KafkaTopics 상수 정의
- [ ] __init__.py 설정

---

### Step 4: 테스트 작성 (0.5h)

**작업 내용:**
1. Producer 테스트
2. Consumer 테스트

**tests/unit/test_infrastructure/test_kafka_client.py:**
```python
"""Tests for Kafka client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.messaging.kafka import KafkaProducer, KafkaConsumer, KafkaTopics
from src.config import KafkaSettings


@pytest.fixture
def settings() -> KafkaSettings:
    """Create test settings."""
    return KafkaSettings(
        bootstrap_servers="localhost:9092",
        consumer_group="test-group",
    )


class TestKafkaProducer:
    """Tests for KafkaProducer."""

    @pytest.fixture
    def producer(self, settings: KafkaSettings) -> KafkaProducer:
        """Create test producer."""
        return KafkaProducer(settings)

    async def test_start_creates_producer(self, producer: KafkaProducer) -> None:
        """Test that start creates the underlying producer."""
        mock_producer = AsyncMock()

        with patch("aiokafka.AIOKafkaProducer", return_value=mock_producer):
            await producer.start()

            mock_producer.start.assert_called_once()
            assert producer._producer is not None

    async def test_stop_closes_producer(self, producer: KafkaProducer) -> None:
        """Test that stop closes the producer."""
        mock_producer = AsyncMock()
        producer._producer = mock_producer

        await producer.stop()

        mock_producer.stop.assert_called_once()
        assert producer._producer is None

    async def test_send_message(self, producer: KafkaProducer) -> None:
        """Test sending a message."""
        mock_producer = AsyncMock()
        producer._producer = mock_producer

        await producer.send("test-topic", {"key": "value"}, key="test-key")

        mock_producer.send_and_wait.assert_called_once()

    def test_is_connected(self, producer: KafkaProducer) -> None:
        """Test is_connected property."""
        assert producer.is_connected() is False

        producer._producer = MagicMock()
        assert producer.is_connected() is True


class TestKafkaConsumer:
    """Tests for KafkaConsumer."""

    @pytest.fixture
    def consumer(self, settings: KafkaSettings) -> KafkaConsumer:
        """Create test consumer."""
        return KafkaConsumer(settings, ["test-topic"])

    async def test_start_creates_consumer(self, consumer: KafkaConsumer) -> None:
        """Test that start creates the underlying consumer."""
        mock_consumer = AsyncMock()

        with patch("aiokafka.AIOKafkaConsumer", return_value=mock_consumer):
            await consumer.start()

            mock_consumer.start.assert_called_once()
            assert consumer._consumer is not None

    async def test_stop_closes_consumer(self, consumer: KafkaConsumer) -> None:
        """Test that stop closes the consumer."""
        mock_consumer = AsyncMock()
        consumer._consumer = mock_consumer

        await consumer.stop()

        mock_consumer.stop.assert_called_once()
        assert consumer._consumer is None


class TestKafkaTopics:
    """Tests for KafkaTopics."""

    def test_topic_names(self) -> None:
        """Test topic name constants."""
        assert KafkaTopics.DOCUMENT_CREATED == "document.created"
        assert KafkaTopics.DOCUMENT_UPDATED == "document.updated"
        assert KafkaTopics.DOCUMENT_DELETED == "document.deleted"

    def test_all_document_topics(self) -> None:
        """Test all_document_topics returns correct list."""
        topics = KafkaTopics.all_document_topics()
        assert len(topics) == 3
        assert "document.created" in topics
```

**완료 기준:**
- [ ] Producer 테스트 작성
- [ ] Consumer 테스트 작성
- [ ] Topics 테스트 작성

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_producer_start` | producer start | producer 생성 |
| `test_producer_stop` | producer stop | producer.stop() called |
| `test_producer_send` | 메시지 전송 | send_and_wait called |
| `test_consumer_start` | consumer start | consumer 생성 |
| `test_consumer_stop` | consumer stop | consumer.stop() called |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_produce_consume` | 전송 후 수신 | 메시지 일치 |
| `test_json_serialization` | JSON 직렬화 | dict 형태 수신 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Kafka 미연결 | High | Low | 재시도 로직, 타임아웃 설정 |
| 메시지 손실 | High | Low | acks=all, 수동 commit |
| 직렬화 오류 | Medium | Low | JSON 스키마 검증 |

---

## 6. Definition of Done

- [ ] `src/infrastructure/messaging/kafka.py` 구현
- [ ] KafkaProducer 클래스 완성
- [ ] KafkaConsumer 클래스 완성
- [ ] JSON 직렬화/역직렬화 구현
- [ ] KafkaTopics 상수 정의
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: KafkaProducer | 1.5h | - |
| Step 2: KafkaConsumer | 1.5h | - |
| Step 3: Factory 및 상수 | 0.5h | - |
| Step 4: 테스트 | 0.5h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
