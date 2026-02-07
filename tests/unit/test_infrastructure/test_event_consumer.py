"""Tests for event consumer."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infrastructure.messaging.consumer import (
    EventConsumer,
    get_event_consumer,
    reset_event_consumers,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock Kafka settings."""
    settings = MagicMock()
    settings.bootstrap_servers = "localhost:9092"
    settings.consumer_group = "test-group"
    return settings


@pytest.fixture
def mock_kafka_consumer() -> MagicMock:
    """Create mock Kafka consumer."""
    mock = MagicMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    mock.commit = AsyncMock()
    mock.consume_one = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def event_consumer(mock_settings: MagicMock) -> EventConsumer:
    """Create event consumer."""
    with patch("src.infrastructure.messaging.consumer.KafkaConsumer") as MockConsumer:
        mock = MagicMock()
        mock.start = AsyncMock()
        mock.stop = AsyncMock()
        mock.commit = AsyncMock()
        MockConsumer.return_value = mock

        consumer = EventConsumer(
            settings=mock_settings,
            topics=["document.updated", "document.deleted"],
            group_id="sync-service",
        )
        consumer._consumer = mock
        return consumer


# =============================================================================
# Test Handler Registration
# =============================================================================


class TestHandlerRegistration:
    """Tests for handler registration."""

    def test_register_single_handler(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test registering a single handler."""
        async def handler(data: dict) -> None:
            pass

        event_consumer.register_handler("document.updated", handler)

        handlers = event_consumer.get_handlers("document.updated")
        assert len(handlers) == 1
        assert handlers[0] is handler

    def test_register_multiple_handlers_same_type(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test registering multiple handlers for same event type."""
        async def handler1(data: dict) -> None:
            pass

        async def handler2(data: dict) -> None:
            pass

        event_consumer.register_handler("document.updated", handler1)
        event_consumer.register_handler("document.updated", handler2)

        handlers = event_consumer.get_handlers("document.updated")
        assert len(handlers) == 2

    def test_register_handlers_different_types(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test registering handlers for different event types."""
        async def update_handler(data: dict) -> None:
            pass

        async def delete_handler(data: dict) -> None:
            pass

        event_consumer.register_handler("document.updated", update_handler)
        event_consumer.register_handler("document.deleted", delete_handler)

        assert len(event_consumer.get_handlers("document.updated")) == 1
        assert len(event_consumer.get_handlers("document.deleted")) == 1

    def test_get_handlers_empty(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test getting handlers when none registered."""
        handlers = event_consumer.get_handlers("nonexistent.event")
        assert handlers == []

    def test_unregister_handler(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test unregistering a handler."""
        async def handler(data: dict) -> None:
            pass

        event_consumer.register_handler("document.updated", handler)
        result = event_consumer.unregister_handler("document.updated", handler)

        assert result is True
        assert len(event_consumer.get_handlers("document.updated")) == 0

    def test_unregister_nonexistent_handler(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test unregistering non-existent handler returns False."""
        async def handler(data: dict) -> None:
            pass

        result = event_consumer.unregister_handler("document.updated", handler)
        assert result is False


# =============================================================================
# Test Message Processing
# =============================================================================


class TestMessageProcessing:
    """Tests for message processing."""

    @pytest.mark.asyncio
    async def test_process_message_calls_handler(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test processing message calls registered handler."""
        handler_called = False
        received_data = {}

        async def handler(data: dict) -> None:
            nonlocal handler_called, received_data
            handler_called = True
            received_data = data

        event_consumer.register_handler("document.updated", handler)

        message = {
            "value": {
                "type": "document.updated",
                "doc_uuid": "doc-123",
                "title": "Test",
            }
        }

        await event_consumer._process_message(message)

        assert handler_called
        assert received_data["doc_uuid"] == "doc-123"

    @pytest.mark.asyncio
    async def test_process_message_calls_multiple_handlers(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test processing message calls all registered handlers."""
        call_count = 0

        async def handler1(data: dict) -> None:
            nonlocal call_count
            call_count += 1

        async def handler2(data: dict) -> None:
            nonlocal call_count
            call_count += 1

        event_consumer.register_handler("document.updated", handler1)
        event_consumer.register_handler("document.updated", handler2)

        message = {
            "value": {
                "type": "document.updated",
                "doc_uuid": "doc-123",
            }
        }

        await event_consumer._process_message(message)

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_process_message_no_handlers(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test processing message with no handlers doesn't error."""
        message = {
            "value": {
                "type": "unregistered.event",
                "doc_uuid": "doc-123",
            }
        }

        # Should not raise
        await event_consumer._process_message(message)

    @pytest.mark.asyncio
    async def test_process_message_missing_type(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test processing message without type."""
        message = {
            "value": {
                "doc_uuid": "doc-123",
            }
        }

        # Should not raise, just log warning
        await event_consumer._process_message(message)

    @pytest.mark.asyncio
    async def test_process_message_handler_error_continues(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test handler error doesn't stop other handlers."""
        call_count = 0

        async def failing_handler(data: dict) -> None:
            raise Exception("Handler error")

        async def success_handler(data: dict) -> None:
            nonlocal call_count
            call_count += 1

        event_consumer.register_handler("document.updated", failing_handler)
        event_consumer.register_handler("document.updated", success_handler)

        message = {
            "value": {
                "type": "document.updated",
                "doc_uuid": "doc-123",
            }
        }

        # Should not raise, and second handler should be called
        await event_consumer._process_message(message)

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_process_message_commits_after_success(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test message is committed after successful processing."""
        async def handler(data: dict) -> None:
            pass

        event_consumer.register_handler("document.updated", handler)

        message = {
            "value": {
                "type": "document.updated",
                "doc_uuid": "doc-123",
            }
        }

        await event_consumer._process_message(message)

        event_consumer._consumer.commit.assert_called_once()


# =============================================================================
# Test Consumer Lifecycle
# =============================================================================


class TestConsumerLifecycle:
    """Tests for consumer lifecycle."""

    @pytest.mark.asyncio
    async def test_start(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test starting the consumer."""
        event_consumer._started = False
        await event_consumer.start()

        event_consumer._consumer.start.assert_called_once()
        assert event_consumer._started is True

    @pytest.mark.asyncio
    async def test_start_idempotent(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test starting already started consumer is safe."""
        event_consumer._started = True

        await event_consumer.start()

        # Should not call start again
        event_consumer._consumer.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test stopping the consumer."""
        event_consumer._started = True
        event_consumer._running = True

        await event_consumer.stop()

        event_consumer._consumer.stop.assert_called_once()
        assert event_consumer._running is False
        assert event_consumer._started is False

    @pytest.mark.asyncio
    async def test_stop_when_not_started(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test stopping non-started consumer is safe."""
        event_consumer._started = False

        await event_consumer.stop()

        event_consumer._consumer.stop.assert_not_called()

    def test_is_running_property(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test is_running property."""
        event_consumer._running = False
        assert event_consumer.is_running is False

        event_consumer._running = True
        assert event_consumer.is_running is True

    def test_is_started_property(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test is_started property."""
        event_consumer._started = False
        assert event_consumer.is_started is False

        event_consumer._started = True
        assert event_consumer.is_started is True


# =============================================================================
# Test Batch Processing
# =============================================================================


class TestBatchProcessing:
    """Tests for batch processing."""

    @pytest.mark.asyncio
    async def test_consume_batch(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test consuming batch of messages."""
        event_consumer._started = True
        event_consumer._consumer.consume_one = AsyncMock(
            side_effect=[
                {"value": {"type": "document.updated", "doc_uuid": "doc-1"}},
                {"value": {"type": "document.updated", "doc_uuid": "doc-2"}},
                None,
            ]
        )

        messages = await event_consumer.consume_batch(max_records=5)

        assert len(messages) == 2
        assert messages[0]["doc_uuid"] == "doc-1"
        assert messages[1]["doc_uuid"] == "doc-2"

    @pytest.mark.asyncio
    async def test_consume_one(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test consuming single message."""
        event_consumer._started = True
        event_consumer._consumer.consume_one = AsyncMock(
            return_value={"value": {"type": "document.updated", "doc_uuid": "doc-123"}}
        )

        async def handler(data: dict) -> None:
            pass

        event_consumer.register_handler("document.updated", handler)

        result = await event_consumer.consume_one()

        assert result is not None
        assert result["doc_uuid"] == "doc-123"

    @pytest.mark.asyncio
    async def test_consume_one_no_message(
        self,
        event_consumer: EventConsumer,
    ) -> None:
        """Test consuming when no message available."""
        event_consumer._started = True
        event_consumer._consumer.consume_one = AsyncMock(return_value=None)

        result = await event_consumer.consume_one()

        assert result is None


# =============================================================================
# Test Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Tests for factory functions."""

    def teardown_method(self) -> None:
        """Reset singletons after each test."""
        reset_event_consumers()

    def test_get_event_consumer_creates_new(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test get_event_consumer creates new consumer."""
        with patch("src.infrastructure.messaging.consumer.KafkaConsumer"):
            consumer = get_event_consumer(
                topics=["test.topic"],
                group_id="test-group",
                settings=mock_settings,
            )

            assert consumer is not None

    def test_get_event_consumer_caches(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test get_event_consumer caches by topics and group."""
        with patch("src.infrastructure.messaging.consumer.KafkaConsumer"):
            consumer1 = get_event_consumer(
                topics=["test.topic"],
                group_id="test-group",
                settings=mock_settings,
            )
            consumer2 = get_event_consumer(
                topics=["test.topic"],
                group_id="test-group",
                settings=mock_settings,
            )

            assert consumer1 is consumer2

    def test_get_event_consumer_different_topics(
        self,
        mock_settings: MagicMock,
    ) -> None:
        """Test different topics create different consumers."""
        with patch("src.infrastructure.messaging.consumer.KafkaConsumer"):
            consumer1 = get_event_consumer(
                topics=["topic.a"],
                group_id="test-group",
                settings=mock_settings,
            )
            consumer2 = get_event_consumer(
                topics=["topic.b"],
                group_id="test-group",
                settings=mock_settings,
            )

            assert consumer1 is not consumer2
