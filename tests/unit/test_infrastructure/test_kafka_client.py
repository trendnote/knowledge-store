"""Tests for Kafka client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import KafkaSettings
from src.infrastructure.messaging.kafka import (
    KafkaConsumer,
    KafkaProducer,
    KafkaTopics,
    close_kafka_clients,
    get_kafka_consumer,
    get_kafka_producer,
    reset_kafka_clients,
)


@pytest.fixture
def settings() -> KafkaSettings:
    """Create test settings."""
    return KafkaSettings(
        bootstrap_servers="localhost:9092",
        consumer_group="test-group",
    )


class TestKafkaProducerConnection:
    """Tests for KafkaProducer connection management."""

    @pytest.fixture
    def producer(self, settings: KafkaSettings) -> KafkaProducer:
        """Create test producer."""
        return KafkaProducer(settings)

    @pytest.mark.asyncio
    async def test_start_creates_producer(self, producer: KafkaProducer) -> None:
        """Test that start creates the underlying producer."""
        mock_producer = AsyncMock()

        with patch(
            "src.infrastructure.messaging.kafka.AIOKafkaProducer",
            return_value=mock_producer,
        ):
            await producer.start()

            mock_producer.start.assert_called_once()
            assert producer._producer is mock_producer
            assert producer.is_started is True

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, producer: KafkaProducer) -> None:
        """Test that calling start multiple times doesn't create new producers."""
        mock_producer = AsyncMock()
        producer._producer = mock_producer

        with patch(
            "src.infrastructure.messaging.kafka.AIOKafkaProducer",
        ) as mock_create:
            await producer.start()

            mock_create.assert_not_called()
            assert producer._producer is mock_producer

    @pytest.mark.asyncio
    async def test_stop_closes_producer(self, producer: KafkaProducer) -> None:
        """Test that stop closes the producer."""
        mock_producer = AsyncMock()
        producer._producer = mock_producer

        await producer.stop()

        mock_producer.stop.assert_called_once()
        assert producer._producer is None
        assert producer.is_started is False

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, producer: KafkaProducer) -> None:
        """Test that calling stop when not started is safe."""
        assert producer._producer is None
        await producer.stop()  # Should not raise
        assert producer._producer is None

    def test_producer_not_started_raises(self, producer: KafkaProducer) -> None:
        """Test accessing producer before start raises error."""
        with pytest.raises(RuntimeError, match="not started"):
            _ = producer.producer


class TestKafkaProducerSend:
    """Tests for KafkaProducer send methods."""

    @pytest.fixture
    def started_producer(self, settings: KafkaSettings) -> KafkaProducer:
        """Create a started producer with mocked underlying producer."""
        producer = KafkaProducer(settings)
        mock_producer = AsyncMock()
        producer._producer = mock_producer
        return producer

    @pytest.mark.asyncio
    async def test_send_message(self, started_producer: KafkaProducer) -> None:
        """Test sending a message."""
        await started_producer.send("test-topic", {"key": "value"}, key="test-key")

        started_producer._producer.send_and_wait.assert_called_once_with(
            "test-topic", value={"key": "value"}, key="test-key"
        )

    @pytest.mark.asyncio
    async def test_send_message_without_key(self, started_producer: KafkaProducer) -> None:
        """Test sending a message without key."""
        await started_producer.send("test-topic", {"data": "test"})

        started_producer._producer.send_and_wait.assert_called_once_with(
            "test-topic", value={"data": "test"}, key=None
        )

    @pytest.mark.asyncio
    async def test_send_batch(self, started_producer: KafkaProducer) -> None:
        """Test sending batch messages."""
        messages = [{"id": 1}, {"id": 2}, {"id": 3}]
        keys = ["key1", "key2", "key3"]

        await started_producer.send_batch("test-topic", messages, keys)

        assert started_producer._producer.send.call_count == 3
        started_producer._producer.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_batch_without_keys(self, started_producer: KafkaProducer) -> None:
        """Test sending batch messages without keys."""
        messages = [{"id": 1}, {"id": 2}]

        await started_producer.send_batch("test-topic", messages)

        assert started_producer._producer.send.call_count == 2

    @pytest.mark.asyncio
    async def test_send_batch_mismatched_lengths_raises(
        self, started_producer: KafkaProducer
    ) -> None:
        """Test that mismatched messages and keys raises error."""
        messages = [{"id": 1}, {"id": 2}]
        keys = ["key1"]

        with pytest.raises(ValueError, match="same length"):
            await started_producer.send_batch("test-topic", messages, keys)


class TestKafkaProducerPing:
    """Tests for KafkaProducer ping method."""

    @pytest.fixture
    def producer(self, settings: KafkaSettings) -> KafkaProducer:
        """Create test producer."""
        return KafkaProducer(settings)

    @pytest.mark.asyncio
    async def test_ping_when_started(self, producer: KafkaProducer) -> None:
        """Test ping returns True when connected."""
        mock_producer = AsyncMock()
        mock_client = AsyncMock()
        mock_producer.client = mock_client
        producer._producer = mock_producer

        result = await producer.ping()

        assert result is True
        mock_client.force_metadata_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_ping_when_not_started(self, producer: KafkaProducer) -> None:
        """Test ping returns False when not started."""
        result = await producer.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_on_error(self, producer: KafkaProducer) -> None:
        """Test ping returns False on error."""
        mock_producer = AsyncMock()
        mock_client = AsyncMock()
        mock_client.force_metadata_update.side_effect = Exception("Connection failed")
        mock_producer.client = mock_client
        producer._producer = mock_producer

        result = await producer.ping()

        assert result is False


class TestKafkaConsumerConnection:
    """Tests for KafkaConsumer connection management."""

    @pytest.fixture
    def consumer(self, settings: KafkaSettings) -> KafkaConsumer:
        """Create test consumer."""
        return KafkaConsumer(settings, ["test-topic"])

    @pytest.mark.asyncio
    async def test_start_creates_consumer(self, consumer: KafkaConsumer) -> None:
        """Test that start creates the underlying consumer."""
        mock_consumer = AsyncMock()

        with patch(
            "src.infrastructure.messaging.kafka.AIOKafkaConsumer",
            return_value=mock_consumer,
        ):
            await consumer.start()

            mock_consumer.start.assert_called_once()
            assert consumer._consumer is mock_consumer
            assert consumer.is_started is True

    @pytest.mark.asyncio
    async def test_start_is_idempotent(self, consumer: KafkaConsumer) -> None:
        """Test that calling start multiple times doesn't create new consumers."""
        mock_consumer = AsyncMock()
        consumer._consumer = mock_consumer

        with patch(
            "src.infrastructure.messaging.kafka.AIOKafkaConsumer",
        ) as mock_create:
            await consumer.start()

            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_closes_consumer(self, consumer: KafkaConsumer) -> None:
        """Test that stop closes the consumer."""
        mock_consumer = AsyncMock()
        consumer._consumer = mock_consumer

        await consumer.stop()

        mock_consumer.stop.assert_called_once()
        assert consumer._consumer is None
        assert consumer.is_started is False

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self, consumer: KafkaConsumer) -> None:
        """Test that calling stop when not started is safe."""
        assert consumer._consumer is None
        await consumer.stop()  # Should not raise
        assert consumer._consumer is None

    def test_consumer_not_started_raises(self, consumer: KafkaConsumer) -> None:
        """Test accessing consumer before start raises error."""
        with pytest.raises(RuntimeError, match="not started"):
            _ = consumer.consumer


class TestKafkaConsumerConsume:
    """Tests for KafkaConsumer consume methods."""

    def _create_mock_message(
        self,
        topic: str = "test-topic",
        partition: int = 0,
        offset: int = 0,
        key: str | None = None,
        value: dict[str, Any] | None = None,
        timestamp: int = 1234567890,
    ) -> MagicMock:
        """Create a mock Kafka message."""
        msg = MagicMock()
        msg.topic = topic
        msg.partition = partition
        msg.offset = offset
        msg.key = key
        msg.value = value or {"test": "data"}
        msg.timestamp = timestamp
        return msg

    @pytest.fixture
    def started_consumer(self, settings: KafkaSettings) -> KafkaConsumer:
        """Create a started consumer with mocked underlying consumer."""
        consumer = KafkaConsumer(settings, ["test-topic"])
        mock_consumer = AsyncMock()
        consumer._consumer = mock_consumer
        return consumer

    @pytest.mark.asyncio
    async def test_consume_yields_messages(self, started_consumer: KafkaConsumer) -> None:
        """Test consume yields formatted messages."""
        mock_msg = self._create_mock_message(
            key="key1", value={"data": "test"}, offset=5
        )

        async def mock_iter() -> Any:
            yield mock_msg

        started_consumer._consumer.__aiter__ = lambda self: mock_iter()

        messages = []
        async for msg in started_consumer.consume():
            messages.append(msg)
            break  # Only consume one message

        assert len(messages) == 1
        assert messages[0]["topic"] == "test-topic"
        assert messages[0]["key"] == "key1"
        assert messages[0]["value"] == {"data": "test"}
        assert messages[0]["offset"] == 5

    @pytest.mark.asyncio
    async def test_consume_one(self, started_consumer: KafkaConsumer) -> None:
        """Test consume_one returns single message."""
        mock_msg = self._create_mock_message(key="key1", value={"id": 1})
        started_consumer._consumer.getone.return_value = mock_msg

        result = await started_consumer.consume_one()

        assert result is not None
        assert result["key"] == "key1"
        assert result["value"] == {"id": 1}

    @pytest.mark.asyncio
    async def test_consume_one_returns_none_on_error(
        self, started_consumer: KafkaConsumer
    ) -> None:
        """Test consume_one returns None on error."""
        started_consumer._consumer.getone.side_effect = Exception("Timeout")

        result = await started_consumer.consume_one()

        assert result is None

    @pytest.mark.asyncio
    async def test_commit(self, started_consumer: KafkaConsumer) -> None:
        """Test commit calls underlying consumer commit."""
        await started_consumer.commit()
        started_consumer._consumer.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_seek_to_beginning(self, started_consumer: KafkaConsumer) -> None:
        """Test seek_to_beginning."""
        await started_consumer.seek_to_beginning()
        started_consumer._consumer.seek_to_beginning.assert_called_once()

    @pytest.mark.asyncio
    async def test_seek_to_end(self, started_consumer: KafkaConsumer) -> None:
        """Test seek_to_end."""
        await started_consumer.seek_to_end()
        started_consumer._consumer.seek_to_end.assert_called_once()


class TestKafkaConsumerPing:
    """Tests for KafkaConsumer ping method."""

    @pytest.fixture
    def consumer(self, settings: KafkaSettings) -> KafkaConsumer:
        """Create test consumer."""
        return KafkaConsumer(settings, ["test-topic"])

    @pytest.mark.asyncio
    async def test_ping_when_started(self, consumer: KafkaConsumer) -> None:
        """Test ping returns True when connected."""
        mock_consumer = MagicMock()
        mock_consumer.subscription.return_value = {"test-topic"}
        consumer._consumer = mock_consumer

        result = await consumer.ping()

        assert result is True

    @pytest.mark.asyncio
    async def test_ping_when_not_started(self, consumer: KafkaConsumer) -> None:
        """Test ping returns False when not started."""
        result = await consumer.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_on_error(self, consumer: KafkaConsumer) -> None:
        """Test ping returns False on error."""
        mock_consumer = MagicMock()
        mock_consumer.subscription.side_effect = Exception("Error")
        consumer._consumer = mock_consumer

        result = await consumer.ping()

        assert result is False


class TestKafkaTopics:
    """Tests for KafkaTopics."""

    def test_topic_names(self) -> None:
        """Test topic name constants."""
        assert KafkaTopics.DOCUMENT_CREATED == "document.created"
        assert KafkaTopics.DOCUMENT_UPDATED == "document.updated"
        assert KafkaTopics.DOCUMENT_DELETED == "document.deleted"
        assert KafkaTopics.SYNC_COMPLETED == "sync.completed"

    def test_all_document_topics(self) -> None:
        """Test all_document_topics returns correct list."""
        topics = KafkaTopics.all_document_topics()
        assert len(topics) == 3
        assert "document.created" in topics
        assert "document.updated" in topics
        assert "document.deleted" in topics


class TestKafkaSingleton:
    """Tests for Kafka singleton functions."""

    def setup_method(self) -> None:
        """Reset singletons before each test."""
        reset_kafka_clients()

    def teardown_method(self) -> None:
        """Reset singletons after each test."""
        reset_kafka_clients()

    def test_get_kafka_producer_creates_instance(self, settings: KafkaSettings) -> None:
        """Test get_kafka_producer creates instance."""
        producer = get_kafka_producer(settings)

        assert producer is not None
        assert isinstance(producer, KafkaProducer)

    def test_get_kafka_producer_returns_same_instance(
        self, settings: KafkaSettings
    ) -> None:
        """Test get_kafka_producer returns same instance."""
        producer1 = get_kafka_producer(settings)
        producer2 = get_kafka_producer(settings)

        assert producer1 is producer2

    def test_get_kafka_producer_with_auto_settings(self) -> None:
        """Test get_kafka_producer loads settings automatically."""
        mock_kafka_settings = KafkaSettings(
            bootstrap_servers="localhost:9092",
            consumer_group="auto-group",
        )
        mock_settings = MagicMock()
        mock_settings.kafka = mock_kafka_settings

        with patch("src.config.get_settings", return_value=mock_settings) as mock_get:
            producer = get_kafka_producer()

            assert producer is not None
            mock_get.assert_called_once()

    def test_get_kafka_consumer_creates_instance(self, settings: KafkaSettings) -> None:
        """Test get_kafka_consumer creates instance."""
        consumer = get_kafka_consumer(["test-topic"], settings=settings)

        assert consumer is not None
        assert isinstance(consumer, KafkaConsumer)

    def test_get_kafka_consumer_same_topics_returns_same_instance(
        self, settings: KafkaSettings
    ) -> None:
        """Test get_kafka_consumer returns same instance for same topics."""
        consumer1 = get_kafka_consumer(["topic1", "topic2"], settings=settings)
        consumer2 = get_kafka_consumer(["topic2", "topic1"], settings=settings)  # Different order

        assert consumer1 is consumer2

    def test_get_kafka_consumer_different_topics_returns_different_instance(
        self, settings: KafkaSettings
    ) -> None:
        """Test get_kafka_consumer returns different instance for different topics."""
        consumer1 = get_kafka_consumer(["topic1"], settings=settings)
        consumer2 = get_kafka_consumer(["topic2"], settings=settings)

        assert consumer1 is not consumer2

    @pytest.mark.asyncio
    async def test_close_kafka_clients(self, settings: KafkaSettings) -> None:
        """Test close_kafka_clients closes all clients."""
        producer = get_kafka_producer(settings)
        consumer = get_kafka_consumer(["test-topic"], settings=settings)

        mock_producer = AsyncMock()
        mock_consumer = AsyncMock()
        producer._producer = mock_producer
        consumer._consumer = mock_consumer

        await close_kafka_clients()

        mock_producer.stop.assert_called_once()
        mock_consumer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_kafka_clients_when_none(self) -> None:
        """Test close_kafka_clients when no clients exist."""
        await close_kafka_clients()  # Should not raise
