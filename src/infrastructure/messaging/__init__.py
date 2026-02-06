"""Messaging infrastructure clients.

This module provides async clients for message queue operations:
- KafkaProducer: Async message producer with JSON serialization
- KafkaConsumer: Async message consumer with JSON deserialization
"""

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
    "KafkaProducer",
    "KafkaConsumer",
    "KafkaTopics",
    "get_kafka_producer",
    "get_kafka_consumer",
    "close_kafka_clients",
    "reset_kafka_clients",
]
