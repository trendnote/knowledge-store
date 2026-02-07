"""Event-driven Kafka consumer with handler registration.

This module provides an event-driven consumer that:
- Wraps the base KafkaConsumer with handler registration
- Supports multiple handlers per event type
- Provides graceful shutdown and error handling
- Enables batch processing for high-throughput scenarios

Example:
    >>> consumer = EventConsumer(settings, ["document.updated"], "sync-service")
    >>> consumer.register_handler("document.updated", handle_update)
    >>> await consumer.start()
    >>> await consumer.consume()  # Runs until stopped
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

from aiokafka.errors import KafkaError

from src.config import KafkaSettings
from src.infrastructure.messaging.kafka import KafkaConsumer

logger = logging.getLogger(__name__)

# Type alias for event handlers
EventHandler = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class EventConsumer:
    """Event-driven Kafka consumer with handler registration.

    This class wraps KafkaConsumer and adds:
    - Handler registration for specific event types
    - Automatic routing of messages to handlers
    - Error handling per handler
    - Graceful shutdown support

    Note:
        Handlers are called sequentially for each message.
        If you need parallel handler execution, use asyncio.gather
        within your handler.
    """

    def __init__(
        self,
        settings: KafkaSettings,
        topics: list[str],
        group_id: str,
    ) -> None:
        """Initialize event consumer.

        Args:
            settings: Kafka connection settings
            topics: List of topics to subscribe
            group_id: Consumer group ID for this consumer
        """
        self._settings = settings
        self._topics = topics
        self._group_id = group_id
        self._consumer = KafkaConsumer(settings, topics, group_id)
        self._handlers: dict[str, list[EventHandler]] = {}
        self._running = False
        self._started = False

    @property
    def is_running(self) -> bool:
        """Check if consumer is actively consuming."""
        return self._running

    @property
    def is_started(self) -> bool:
        """Check if consumer has been started."""
        return self._started

    async def start(self) -> None:
        """Start the consumer.

        This initializes the underlying Kafka consumer
        but does not start consuming messages.
        Use consume() to start message processing.
        """
        if self._started:
            return

        await self._consumer.start()
        self._started = True
        logger.info(
            f"EventConsumer started: topics={self._topics}, group={self._group_id}"
        )

    async def stop(self) -> None:
        """Stop the consumer gracefully.

        Sets running flag to False and waits for
        current message processing to complete.
        """
        self._running = False

        if self._started:
            await self._consumer.stop()
            self._started = False
            logger.info("EventConsumer stopped")

    def register_handler(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Register a handler for an event type.

        Multiple handlers can be registered for the same event type.
        Handlers are called in registration order.

        Args:
            event_type: Event type to handle (e.g., "document.updated")
            handler: Async function to handle the event

        Example:
            >>> async def handle_update(data: dict) -> None:
            ...     print(f"Updated: {data['doc_uuid']}")
            >>> consumer.register_handler("document.updated", handle_update)
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"Registered handler for event type: {event_type}")

    def unregister_handler(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> bool:
        """Unregister a handler for an event type.

        Args:
            event_type: Event type
            handler: Handler to remove

        Returns:
            True if handler was removed, False if not found
        """
        if event_type not in self._handlers:
            return False

        try:
            self._handlers[event_type].remove(handler)
            logger.debug(f"Unregistered handler for event type: {event_type}")
            return True
        except ValueError:
            return False

    def get_handlers(self, event_type: str) -> list[EventHandler]:
        """Get all handlers for an event type.

        Args:
            event_type: Event type

        Returns:
            List of registered handlers
        """
        return self._handlers.get(event_type, [])

    async def _process_message(self, message: dict[str, Any]) -> None:
        """Process a single message.

        Routes the message to registered handlers based on event type.

        Args:
            message: Kafka message with 'value' containing event data
        """
        try:
            data = message.get("value", {})
            event_type = data.get("type", "")

            if not event_type:
                logger.warning("Received message without event type")
                return

            handlers = self._handlers.get(event_type, [])
            if not handlers:
                logger.debug(f"No handlers registered for event type: {event_type}")
                return

            doc_uuid = data.get("doc_uuid", "unknown")
            logger.debug(f"Processing {event_type} for {doc_uuid}")

            for handler in handlers:
                try:
                    await handler(data)
                except Exception as e:
                    logger.error(
                        f"Handler error for {event_type} ({doc_uuid}): {e}",
                        exc_info=True,
                    )

            # Commit after successful processing
            await self._consumer.commit()

        except Exception as e:
            logger.error(f"Message processing error: {e}", exc_info=True)

    async def consume(self) -> None:
        """Start consuming messages.

        Runs continuously until stop() is called.
        Messages are processed one at a time through registered handlers.

        Raises:
            KafkaError: If Kafka connection fails
        """
        if not self._started:
            await self.start()

        self._running = True
        logger.info("Starting message consumption")

        try:
            async for message in self._consumer.consume():
                if not self._running:
                    break
                await self._process_message(message)

        except KafkaError as e:
            logger.error(f"Kafka error during consumption: {e}")
            raise

        finally:
            logger.info("Message consumption stopped")

    async def consume_batch(
        self,
        max_records: int = 100,
        timeout_ms: int = 1000,
    ) -> list[dict[str, Any]]:
        """Consume a batch of messages.

        This is useful for batch processing scenarios.
        Messages are returned without handler processing.

        Args:
            max_records: Maximum number of records to fetch
            timeout_ms: Timeout in milliseconds (for compatibility)

        Returns:
            List of message values

        Note:
            This method does not call handlers automatically.
            Use _process_message() to route to handlers if needed.
        """
        if not self._started:
            await self.start()

        messages = []

        # Consume up to max_records messages
        for _ in range(max_records):
            msg = await self._consumer.consume_one(timeout_ms)
            if msg is None:
                break
            messages.append(msg.get("value", {}))

        return messages

    async def consume_one(self, timeout_ms: int = 1000) -> dict[str, Any] | None:
        """Consume and process a single message.

        Args:
            timeout_ms: Timeout in milliseconds

        Returns:
            Message data if available, None otherwise
        """
        if not self._started:
            await self.start()

        message = await self._consumer.consume_one(timeout_ms)
        if message:
            await self._process_message(message)
            return message.get("value")
        return None


# =============================================================================
# Factory Functions
# =============================================================================

_event_consumers: dict[str, EventConsumer] = {}


def get_event_consumer(
    topics: list[str],
    group_id: str,
    settings: KafkaSettings | None = None,
) -> EventConsumer:
    """Get or create an event consumer.

    Args:
        topics: List of topics to subscribe
        group_id: Consumer group ID
        settings: Kafka settings (auto-loaded if not provided)

    Returns:
        EventConsumer instance

    Note:
        Consumers are cached by topic+group combination.
    """
    if settings is None:
        from src.config import get_settings

        settings = get_settings().kafka

    key = f"{','.join(sorted(topics))}:{group_id}"

    if key not in _event_consumers:
        _event_consumers[key] = EventConsumer(settings, topics, group_id)

    return _event_consumers[key]


async def close_event_consumers() -> None:
    """Close all event consumers."""
    for consumer in _event_consumers.values():
        await consumer.stop()
    _event_consumers.clear()


def reset_event_consumers() -> None:
    """Reset all event consumer instances (for testing)."""
    _event_consumers.clear()
