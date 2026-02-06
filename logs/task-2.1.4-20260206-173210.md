# Task 2.1.4 Implementation Log

## Task Information

| Item | Value |
|------|-------|
| **Task ID** | 2.1.4 |
| **Task Name** | Kafka Client 구현 |
| **GitHub Issue** | [#13](https://github.com/trendnote/knowledge-store/issues/13) |
| **Task Plan** | [task-2.1.4-plan.md](../docs/task-plans/task-2.1.4-plan.md) |
| **Date** | 2026-02-06 |
| **Status** | Completed |

---

## Summary

aiokafka 기반 Kafka 비동기 메시지 Producer/Consumer를 구현했습니다. JSON 직렬화/역직렬화, 배치 전송, 수동 커밋을 지원합니다.

---

## Implementation Details

### Step 1: KafkaProducer 클래스 구현

**핵심 메서드:**

| Method | Description |
|--------|-------------|
| `start()` | Producer 시작 |
| `stop()` | Producer 종료 |
| `ping()` | 연결 상태 확인 |
| `send()` | 단일 메시지 전송 |
| `send_batch()` | 배치 메시지 전송 |

**주요 설정:**

```python
self._producer = AIOKafkaProducer(
    bootstrap_servers=self._settings.bootstrap_servers,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
    key_serializer=lambda k: k.encode("utf-8") if k else None,
    acks="all",  # Wait for all replicas
)
```

### Step 2: KafkaConsumer 클래스 구현

**핵심 메서드:**

| Method | Description |
|--------|-------------|
| `start()` | Consumer 시작 |
| `stop()` | Consumer 종료 |
| `ping()` | 연결 상태 확인 |
| `consume()` | 메시지 async iterator |
| `consume_one()` | 단일 메시지 조회 |
| `commit()` | 오프셋 커밋 |
| `seek_to_beginning()` | 파티션 처음으로 이동 |
| `seek_to_end()` | 파티션 끝으로 이동 |

**주요 설정:**

```python
self._consumer = AIOKafkaConsumer(
    *self._topics,
    bootstrap_servers=self._settings.bootstrap_servers,
    group_id=self._group_id,
    value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    key_deserializer=lambda k: k.decode("utf-8") if k else None,
    auto_offset_reset="earliest",
    enable_auto_commit=False,  # Manual commit for reliability
)
```

### Step 3: KafkaTopics 상수 정의

| Topic | Description |
|-------|-------------|
| `document.created` | 문서 생성 이벤트 |
| `document.updated` | 문서 수정 이벤트 |
| `document.deleted` | 문서 삭제 이벤트 |
| `sync.completed` | 동기화 완료 이벤트 |

### Step 4: Factory 함수

| Function | Description |
|----------|-------------|
| `get_kafka_producer()` | Producer Singleton 반환 |
| `get_kafka_consumer()` | Consumer 인스턴스 반환 (토픽별 캐싱) |
| `close_kafka_clients()` | 모든 클라이언트 종료 |
| `reset_kafka_clients()` | Singleton 초기화 (테스트용) |

---

## Output Files

### Created Files

1. **src/infrastructure/messaging/kafka.py**
   - KafkaProducer 클래스
   - KafkaConsumer 클래스
   - KafkaTopics 상수
   - Singleton factory 함수

2. **src/infrastructure/messaging/__init__.py**
   - 모듈 export 설정

3. **tests/unit/test_infrastructure/test_kafka_client.py**
   - 37개 단위 테스트

---

## Test Results

### Unit Tests (37개)

```
TestKafkaProducerConnection
  ✅ test_start_creates_producer
  ✅ test_start_is_idempotent
  ✅ test_stop_closes_producer
  ✅ test_stop_is_idempotent
  ✅ test_producer_not_started_raises

TestKafkaProducerSend
  ✅ test_send_message
  ✅ test_send_message_without_key
  ✅ test_send_batch
  ✅ test_send_batch_without_keys
  ✅ test_send_batch_mismatched_lengths_raises

TestKafkaProducerPing
  ✅ test_ping_when_started
  ✅ test_ping_when_not_started
  ✅ test_ping_on_error

TestKafkaConsumerConnection
  ✅ test_start_creates_consumer
  ✅ test_start_is_idempotent
  ✅ test_stop_closes_consumer
  ✅ test_stop_is_idempotent
  ✅ test_consumer_not_started_raises

TestKafkaConsumerConsume
  ✅ test_consume_yields_messages
  ✅ test_consume_one
  ✅ test_consume_one_returns_none_on_error
  ✅ test_commit
  ✅ test_seek_to_beginning
  ✅ test_seek_to_end

TestKafkaConsumerPing
  ✅ test_ping_when_started
  ✅ test_ping_when_not_started
  ✅ test_ping_on_error

TestKafkaTopics
  ✅ test_topic_names
  ✅ test_all_document_topics

TestKafkaSingleton
  ✅ test_get_kafka_producer_creates_instance
  ✅ test_get_kafka_producer_returns_same_instance
  ✅ test_get_kafka_producer_with_auto_settings
  ✅ test_get_kafka_consumer_creates_instance
  ✅ test_get_kafka_consumer_same_topics_returns_same_instance
  ✅ test_get_kafka_consumer_different_topics_returns_different_instance
  ✅ test_close_kafka_clients
  ✅ test_close_kafka_clients_when_none

Coverage: 98% (src/infrastructure/messaging/kafka.py)
```

### Integration Test

```
Connecting to: localhost:9093
Producer started: OK
Producer ping: True
Send message: OK
Send batch: OK
Producer stopped: OK
Consumer started: OK
Consumer ping: True
Consumer stopped: OK
Document topics: 3

Integration test: SUCCESS
```

---

## Acceptance Criteria Checklist

- [x] `src/infrastructure/messaging/kafka.py` 생성
- [x] Producer 클래스 (메시지 발행)
- [x] Consumer 클래스 (메시지 구독)
- [x] JSON 직렬화/역직렬화
- [x] 연결 상태 확인

---

## Definition of Done

- [x] `src/infrastructure/messaging/kafka.py` 구현
- [x] `src/infrastructure/messaging/__init__.py` 설정
- [x] KafkaProducer 클래스 완성
- [x] KafkaConsumer 클래스 완성
- [x] JSON 직렬화/역직렬화 구현
- [x] KafkaTopics 상수 정의
- [x] 모든 단위 테스트 통과 (37개)
- [x] 통합 테스트 통과
- [x] ruff 린트 통과

---

## Usage

```python
from src.infrastructure.messaging import (
    get_kafka_producer,
    get_kafka_consumer,
    KafkaTopics,
)

# Producer
producer = get_kafka_producer()
await producer.start()

# Send single message
await producer.send(
    KafkaTopics.DOCUMENT_CREATED,
    {"doc_uuid": "uuid123", "title": "My Document"},
    key="uuid123"
)

# Send batch
await producer.send_batch(
    KafkaTopics.DOCUMENT_CREATED,
    [{"doc_uuid": "uuid1"}, {"doc_uuid": "uuid2"}],
    keys=["uuid1", "uuid2"]
)

await producer.stop()

# Consumer
consumer = get_kafka_consumer(KafkaTopics.all_document_topics())
await consumer.start()

async for msg in consumer.consume():
    print(f"Topic: {msg['topic']}, Value: {msg['value']}")
    await consumer.commit()

await consumer.stop()
```

---

## API Reference

### KafkaProducer

```python
class KafkaProducer:
    # Properties
    producer: AIOKafkaProducer    # Underlying producer (raises if not started)
    is_started: bool              # Connection status

    # Connection Management
    async def start() -> None
    async def stop() -> None
    async def ping() -> bool

    # Message Sending
    async def send(topic: str, value: dict, key: str | None = None) -> None
    async def send_batch(topic: str, messages: list[dict], keys: list[str | None] | None = None) -> None
```

### KafkaConsumer

```python
class KafkaConsumer:
    # Properties
    consumer: AIOKafkaConsumer    # Underlying consumer (raises if not started)
    is_started: bool              # Connection status

    # Connection Management
    async def start() -> None
    async def stop() -> None
    async def ping() -> bool

    # Message Consuming
    async def consume() -> AsyncIterator[dict]
    async def consume_one(timeout_ms: int = 1000) -> dict | None
    async def commit() -> None
    async def seek_to_beginning() -> None
    async def seek_to_end() -> None
```

### KafkaTopics

```python
class KafkaTopics:
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    SYNC_COMPLETED = "sync.completed"

    @classmethod
    def all_document_topics() -> list[str]
```

---

## Next Steps

- **Task 2.2.1**: Document Repository 구현
  - PostgreSQL 기반 문서 메타데이터 저장소
  - CRUD 연산 구현

---

## Notes

- aiokafka는 네이티브 비동기 Kafka 클라이언트
- `acks="all"` 설정으로 모든 레플리카에 메시지 전달 보장
- `enable_auto_commit=False`로 수동 커밋 사용 (신뢰성 향상)
- Consumer는 토픽+그룹 조합별로 캐싱되어 재사용
- Producer는 Singleton 패턴으로 애플리케이션 전체에서 하나의 인스턴스 사용
- `reset_kafka_clients()`는 테스트 격리를 위해 제공됨
