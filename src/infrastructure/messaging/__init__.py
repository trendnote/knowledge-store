"""Messaging infrastructure clients.

This module provides async clients for message queue operations:
- KafkaProducer: Async message producer with JSON serialization
- KafkaConsumer: Async message consumer with JSON deserialization
- EventConsumer: Event-driven consumer with handler registration
"""

from src.infrastructure.messaging.consumer import (
    EventConsumer,
    close_event_consumers,
    get_event_consumer,
    reset_event_consumers,
)
from src.infrastructure.messaging.kafka import (
    KafkaConsumer,
    KafkaProducer,
    KafkaTopics,
    close_kafka_clients,
    get_kafka_consumer,
    get_kafka_producer,
    reset_kafka_clients,
)

__all__ = [
    # Kafka clients
    "KafkaProducer",
    "KafkaConsumer",
    "KafkaTopics",
    "get_kafka_producer",
    "get_kafka_consumer",
    "close_kafka_clients",
    "reset_kafka_clients",
    # Event consumer
    "EventConsumer",
    "get_event_consumer",
    "close_event_consumers",
    "reset_event_consumers",
]
