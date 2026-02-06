"""Kafka async producer and consumer.

This module provides async clients for Kafka messaging with support for:
- Async Producer with JSON serialization
- Async Consumer with JSON deserialization
- Manual offset commit for reliability
- Batch message sending

Example:
    >>> from src.infrastructure.messaging import get_kafka_producer, get_kafka_consumer
    >>> producer = get_kafka_producer()
    >>> await producer.start()
    >>> await producer.send("topic", {"key": "value"})
    >>> await producer.stop()
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from src.config import KafkaSettings


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


class KafkaProducer:
    """Async Kafka producer for publishing messages.

    This producer provides:
    - Automatic JSON serialization
    - Message key support
    - Batch sending with flush
    - Configurable acknowledgment (acks=all by default)

    Note:
        Uses aiokafka for async operations.
    """

    def __init__(self, settings: KafkaSettings) -> None:
        """Initialize Kafka producer.

        Args:
            settings: Kafka connection settings
        """
        self._settings = settings
        self._producer: AIOKafkaProducer | None = None

    @property
    def producer(self) -> AIOKafkaProducer:
        """Get producer.

        Returns:
            AIOKafkaProducer instance

        Raises:
            RuntimeError: If producer is not started
        """
        if self._producer is None:
            raise RuntimeError("KafkaProducer is not started. Call start() first.")
        return self._producer

    @property
    def is_started(self) -> bool:
        """Check if producer is started."""
        return self._producer is not None

    async def start(self) -> None:
        """Start the producer.

        This method is idempotent - calling it multiple times
        will not create additional producers.
        """
        if self._producer is not None:
            return

        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks="all",  # Wait for all replicas
        )
        await self._producer.start()

    async def stop(self) -> None:
        """Stop the producer.

        This method is idempotent - calling it multiple times is safe.
        """
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def ping(self) -> bool:
        """Check if producer is connected to Kafka.

        Returns:
            True if connected, False otherwise
        """
        if self._producer is None:
            return False
        try:
            # Get cluster metadata to verify connection
            await self._producer.client.force_metadata_update()
            return True
        except Exception:
            return False

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

        Example:
            >>> await producer.send(
            ...     "document.created",
            ...     {"doc_uuid": "uuid123", "title": "My Doc"},
            ...     key="uuid123"
            ... )
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
            keys: Optional list of message keys (must match messages length)

        Raises:
            ValueError: If messages and keys have different lengths

        Example:
            >>> await producer.send_batch(
            ...     "document.created",
            ...     [{"doc_uuid": "uuid1"}, {"doc_uuid": "uuid2"}],
            ...     keys=["uuid1", "uuid2"]
            ... )
        """
        if keys is None:
            keys = [None] * len(messages)

        if len(messages) != len(keys):
            raise ValueError("messages and keys must have same length")

        for value, key in zip(messages, keys, strict=True):
            await self.producer.send(topic, value=value, key=key)

        # Flush all pending messages
        await self.producer.flush()


class KafkaConsumer:
    """Async Kafka consumer for subscribing to messages.

    This consumer provides:
    - Automatic JSON deserialization
    - Manual offset commit for reliability
    - Async iteration over messages
    - Seek operations for replay

    Note:
        Uses aiokafka for async operations.
        Auto-commit is disabled for reliability.
    """

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
        """Get consumer.

        Returns:
            AIOKafkaConsumer instance

        Raises:
            RuntimeError: If consumer is not started
        """
        if self._consumer is None:
            raise RuntimeError("KafkaConsumer is not started. Call start() first.")
        return self._consumer

    @property
    def is_started(self) -> bool:
        """Check if consumer is started."""
        return self._consumer is not None

    async def start(self) -> None:
        """Start the consumer.

        This method is idempotent - calling it multiple times
        will not create additional consumers.
        """
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
        """Stop the consumer.

        This method is idempotent - calling it multiple times is safe.
        """
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def ping(self) -> bool:
        """Check if consumer is connected to Kafka.

        Returns:
            True if connected, False otherwise
        """
        if self._consumer is None:
            return False
        try:
            # Get subscribed topics to verify connection
            return len(self._consumer.subscription()) > 0
        except Exception:
            return False

    async def consume(self) -> AsyncIterator[dict[str, Any]]:
        """Consume messages from topics.

        Yields:
            Parsed message dictionaries with metadata

        Example:
            >>> async for msg in consumer.consume():
            ...     print(msg["topic"], msg["value"])
            ...     await consumer.commit()
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
            timeout_ms: Timeout in milliseconds (not used, kept for API compatibility)

        Returns:
            Message dict or None if no message available
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


# =============================================================================
# Singleton Factory
# =============================================================================

_producer: KafkaProducer | None = None
_consumers: dict[str, KafkaConsumer] = {}


def get_kafka_producer(settings: KafkaSettings | None = None) -> KafkaProducer:
    """Get or create Kafka producer singleton.

    Args:
        settings: Kafka settings (required on first call,
                  or auto-loaded from environment)

    Returns:
        KafkaProducer instance
    """
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

    Note:
        Different topic combinations create different consumers.

    Args:
        topics: List of topics to subscribe
        group_id: Consumer group ID (default from settings)
        settings: Kafka settings (auto-loaded if not provided)

    Returns:
        KafkaConsumer instance
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


def reset_kafka_clients() -> None:
    """Reset all Kafka client singletons (for testing)."""
    global _producer, _consumers
    _producer = None
    _consumers.clear()
