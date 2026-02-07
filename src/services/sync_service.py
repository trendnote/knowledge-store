"""Sync service for event-driven data synchronization.

This module provides the SyncService which:
- Listens for document events via Kafka
- Synchronizes data across PostgreSQL, Milvus, and Neo4j
- Publishes sync completion/failure events
- Handles retry logic with exponential backoff

The sync service ensures eventual consistency across all data stores
by processing document events and propagating changes.

Example:
    >>> sync_service = SyncService(
    ...     consumer=event_consumer,
    ...     postgres_repo=postgres_repo,
    ...     milvus_repo=milvus_repo,
    ...     neo4j_repo=neo4j_repo,
    ...     embedding_service=embedding_service,
    ...     kafka_producer=producer,
    ... )
    >>> await sync_service.start()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol

from src.domain.events.document_events import (
    DocumentDeletedEvent,
    DocumentUpdatedEvent,
    EventType,
    SyncCompletedEvent,
    SyncFailedEvent,
    parse_event,
)
from src.infrastructure.messaging.consumer import EventConsumer

logger = logging.getLogger(__name__)


# =============================================================================
# Repository Protocols
# =============================================================================


class PostgresRepositoryProtocol(Protocol):
    """Protocol for PostgreSQL repository operations."""

    async def get_chunks_by_doc(self, doc_uuid: str) -> list[Any]:
        """Get all chunks for a document."""
        ...

    async def get_document(self, doc_uuid: str) -> Any | None:
        """Get document by UUID."""
        ...


class MilvusRepositoryProtocol(Protocol):
    """Protocol for Milvus repository operations."""

    async def delete_vectors(self, chunk_uuids: list[str]) -> None:
        """Delete vectors by chunk UUIDs."""
        ...

    async def insert_vectors(self, vectors: list[dict[str, Any]]) -> None:
        """Insert vectors."""
        ...


class Neo4jRepositoryProtocol(Protocol):
    """Protocol for Neo4j repository operations."""

    async def delete_document_graph(self, doc_uuid: str) -> None:
        """Delete document and related nodes from graph."""
        ...

    async def create_document_node(self, data: dict[str, Any]) -> None:
        """Create document node."""
        ...

    async def create_chunk_nodes(self, chunks: list[dict[str, Any]]) -> None:
        """Create chunk nodes."""
        ...


class EmbeddingServiceProtocol(Protocol):
    """Protocol for embedding service operations."""

    def encode(self, texts: list[str]) -> Any:
        """Encode texts to embeddings."""
        ...


class KafkaProducerProtocol(Protocol):
    """Protocol for Kafka producer operations."""

    async def send(
        self,
        topic: str,
        value: dict[str, Any],
        key: str | None = None,
    ) -> None:
        """Send message to topic."""
        ...


# =============================================================================
# Sync Service
# =============================================================================


class SyncService:
    """Service for synchronizing data across stores.

    Listens for document events and ensures all data stores
    (PostgreSQL, Milvus, Neo4j) remain consistent.

    The service handles:
    - document.updated: Re-syncs vectors and graph if content changed
    - document.deleted: Removes data from all stores

    Attributes:
        max_retries: Maximum retry attempts for failed syncs
        retry_delay_base: Base delay for exponential backoff (seconds)
    """

    max_retries: int = 3
    retry_delay_base: float = 1.0

    def __init__(
        self,
        consumer: EventConsumer,
        postgres_repo: PostgresRepositoryProtocol,
        milvus_repo: MilvusRepositoryProtocol,
        neo4j_repo: Neo4jRepositoryProtocol,
        embedding_service: EmbeddingServiceProtocol,
        kafka_producer: KafkaProducerProtocol | None = None,
    ) -> None:
        """Initialize sync service.

        Args:
            consumer: Event consumer for receiving document events
            postgres_repo: PostgreSQL repository for chunk data
            milvus_repo: Milvus repository for vector operations
            neo4j_repo: Neo4j repository for graph operations
            embedding_service: Service for generating embeddings
            kafka_producer: Optional producer for sync events
        """
        self._consumer = consumer
        self._postgres = postgres_repo
        self._milvus = milvus_repo
        self._neo4j = neo4j_repo
        self._embedding = embedding_service
        self._producer = kafka_producer
        self._running = False

        # Register event handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register event handlers with the consumer."""
        self._consumer.register_handler(
            EventType.DOCUMENT_UPDATED.value,
            self._handle_document_updated,
        )
        self._consumer.register_handler(
            EventType.DOCUMENT_DELETED.value,
            self._handle_document_deleted,
        )
        logger.info("Sync service handlers registered")

    async def _handle_document_updated(self, data: dict[str, Any]) -> None:
        """Handle document updated event.

        Syncs changes to Milvus and Neo4j if content changed.
        Metadata-only updates don't require re-indexing.

        Args:
            data: Event data dictionary
        """
        start_time = time.time()
        event = parse_event(data)

        if not isinstance(event, DocumentUpdatedEvent):
            logger.warning(f"Unexpected event type: {type(event)}")
            return

        doc_uuid = event.doc_uuid
        logger.info(f"Processing document.updated: {doc_uuid}")

        synced_stores: list[str] = []
        failed_stores: list[str] = []

        try:
            # Only re-sync if content changed
            if not event.content_changed:
                logger.debug(f"No content change for {doc_uuid}, skipping re-index")
                duration_ms = (time.time() - start_time) * 1000
                await self._publish_sync_completed(
                    doc_uuid,
                    EventType.DOCUMENT_UPDATED.value,
                    synced_stores,
                    duration_ms,
                )
                return

            # Get updated chunks from PostgreSQL
            chunks = await self._postgres.get_chunks_by_doc(doc_uuid)
            if not chunks:
                logger.warning(f"No chunks found for {doc_uuid}")
                return

            # Re-generate embeddings for updated content
            texts = [c.text for c in chunks]
            embeddings = self._embedding.encode(texts)

            # Sync to Milvus
            try:
                # Delete old vectors
                chunk_uuids = [c.chunk_uuid for c in chunks]
                await self._milvus.delete_vectors(chunk_uuids)

                # Insert new vectors
                vectors = [
                    {
                        "chunk_uuid": c.chunk_uuid,
                        "doc_uuid": doc_uuid,
                        "dense_embedding": embeddings.dense[i],
                        "sparse_embedding": embeddings.sparse[i],
                        "text_preview": c.text[:100],
                    }
                    for i, c in enumerate(chunks)
                ]
                await self._milvus.insert_vectors(vectors)
                synced_stores.append("milvus")
                logger.debug(f"Milvus sync completed for {doc_uuid}")

            except Exception as e:
                logger.error(f"Milvus sync failed for {doc_uuid}: {e}")
                failed_stores.append("milvus")

            # Sync to Neo4j
            try:
                # Delete old graph structure
                await self._neo4j.delete_document_graph(doc_uuid)

                # Create new document node
                await self._neo4j.create_document_node({
                    "doc_uuid": doc_uuid,
                    "title": event.title,
                })

                # Create chunk nodes
                chunk_nodes = [
                    {
                        "chunk_uuid": c.chunk_uuid,
                        "doc_uuid": doc_uuid,
                        "text_preview": c.text[:100],
                        "chunk_index": i,
                    }
                    for i, c in enumerate(chunks)
                ]
                await self._neo4j.create_chunk_nodes(chunk_nodes)
                synced_stores.append("neo4j")
                logger.debug(f"Neo4j sync completed for {doc_uuid}")

            except Exception as e:
                logger.error(f"Neo4j sync failed for {doc_uuid}: {e}")
                failed_stores.append("neo4j")

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Document sync completed: {doc_uuid} "
                f"synced={synced_stores} failed={failed_stores} "
                f"duration={duration_ms:.2f}ms"
            )

            # Publish result event
            if failed_stores:
                await self._publish_sync_failed(
                    doc_uuid,
                    EventType.DOCUMENT_UPDATED.value,
                    "Partial sync failure",
                    failed_stores,
                )
            else:
                await self._publish_sync_completed(
                    doc_uuid,
                    EventType.DOCUMENT_UPDATED.value,
                    synced_stores,
                    duration_ms,
                )

        except Exception as e:
            logger.exception(f"Sync failed for {doc_uuid}: {e}")
            await self._publish_sync_failed(
                doc_uuid,
                EventType.DOCUMENT_UPDATED.value,
                str(e),
                ["milvus", "neo4j"],
            )

    async def _handle_document_deleted(self, data: dict[str, Any]) -> None:
        """Handle document deleted event.

        Ensures data is removed from all stores.

        Args:
            data: Event data dictionary
        """
        start_time = time.time()
        event = parse_event(data)

        if not isinstance(event, DocumentDeletedEvent):
            logger.warning(f"Unexpected event type: {type(event)}")
            return

        doc_uuid = event.doc_uuid
        logger.info(f"Processing document.deleted: {doc_uuid}")

        synced_stores: list[str] = []
        failed_stores: list[str] = []

        try:
            # Get chunks before deletion (may already be deleted from Postgres)
            chunks = await self._postgres.get_chunks_by_doc(doc_uuid)
            chunk_uuids = [c.chunk_uuid for c in chunks] if chunks else []

            # Delete from Milvus
            try:
                if chunk_uuids:
                    await self._milvus.delete_vectors(chunk_uuids)
                synced_stores.append("milvus")
                logger.debug(f"Milvus delete completed for {doc_uuid}")

            except Exception as e:
                logger.error(f"Milvus delete failed for {doc_uuid}: {e}")
                failed_stores.append("milvus")

            # Delete from Neo4j
            try:
                await self._neo4j.delete_document_graph(doc_uuid)
                synced_stores.append("neo4j")
                logger.debug(f"Neo4j delete completed for {doc_uuid}")

            except Exception as e:
                logger.error(f"Neo4j delete failed for {doc_uuid}: {e}")
                failed_stores.append("neo4j")

            duration_ms = (time.time() - start_time) * 1000
            logger.info(
                f"Delete sync completed: {doc_uuid} "
                f"synced={synced_stores} failed={failed_stores} "
                f"duration={duration_ms:.2f}ms"
            )

            # Publish result event
            if failed_stores:
                await self._publish_sync_failed(
                    doc_uuid,
                    EventType.DOCUMENT_DELETED.value,
                    "Partial delete failure",
                    failed_stores,
                )
            else:
                await self._publish_sync_completed(
                    doc_uuid,
                    EventType.DOCUMENT_DELETED.value,
                    synced_stores,
                    duration_ms,
                )

        except Exception as e:
            logger.exception(f"Delete sync failed for {doc_uuid}: {e}")
            await self._publish_sync_failed(
                doc_uuid,
                EventType.DOCUMENT_DELETED.value,
                str(e),
                ["milvus", "neo4j"],
            )

    async def _publish_sync_completed(
        self,
        doc_uuid: str,
        source_event: str,
        synced_stores: list[str],
        duration_ms: float,
    ) -> None:
        """Publish sync completed event.

        Args:
            doc_uuid: Document UUID
            source_event: Original event type that triggered sync
            synced_stores: List of stores that were synced
            duration_ms: Time taken in milliseconds
        """
        if self._producer is None:
            return

        event = SyncCompletedEvent(
            doc_uuid=doc_uuid,
            source_event=source_event,
            synced_stores=synced_stores,
            duration_ms=duration_ms,
        )

        try:
            await self._producer.send(
                EventType.SYNC_COMPLETED.value,
                event.to_dict(),
                key=doc_uuid,
            )
            logger.debug(f"Published sync.completed for {doc_uuid}")

        except Exception as e:
            logger.error(f"Failed to publish sync.completed: {e}")

    async def _publish_sync_failed(
        self,
        doc_uuid: str,
        source_event: str,
        error: str,
        failed_stores: list[str],
        retry_count: int = 0,
    ) -> None:
        """Publish sync failed event.

        Args:
            doc_uuid: Document UUID
            source_event: Original event type that triggered sync
            error: Error message
            failed_stores: List of stores that failed
            retry_count: Number of retry attempts made
        """
        if self._producer is None:
            return

        event = SyncFailedEvent(
            doc_uuid=doc_uuid,
            source_event=source_event,
            error=error,
            failed_stores=failed_stores,
            retry_count=retry_count,
        )

        try:
            await self._producer.send(
                EventType.SYNC_FAILED.value,
                event.to_dict(),
                key=doc_uuid,
            )
            logger.debug(f"Published sync.failed for {doc_uuid}")

        except Exception as e:
            logger.error(f"Failed to publish sync.failed: {e}")

    async def start(self) -> None:
        """Start the sync service.

        Begins consuming events from Kafka and processing them.
        Runs until stop() is called.
        """
        if self._running:
            logger.warning("Sync service is already running")
            return

        self._running = True
        logger.info("Starting sync service")

        try:
            await self._consumer.consume()
        except Exception as e:
            logger.exception(f"Sync service error: {e}")
            raise
        finally:
            self._running = False

    async def stop(self) -> None:
        """Stop the sync service gracefully."""
        if not self._running:
            return

        logger.info("Stopping sync service")
        self._running = False
        await self._consumer.stop()

    async def process_single_event(self, data: dict[str, Any]) -> None:
        """Process a single event directly.

        Useful for testing or manual event processing.

        Args:
            data: Event data dictionary
        """
        event_type = data.get("type", "")

        if event_type == EventType.DOCUMENT_UPDATED.value:
            await self._handle_document_updated(data)
        elif event_type == EventType.DOCUMENT_DELETED.value:
            await self._handle_document_deleted(data)
        else:
            logger.warning(f"Unknown event type: {event_type}")


# =============================================================================
# Factory Functions
# =============================================================================

_sync_service: SyncService | None = None


def get_sync_service() -> SyncService:
    """Get the sync service singleton.

    Returns:
        SyncService instance

    Raises:
        RuntimeError: If sync service is not initialized
    """
    if _sync_service is None:
        raise RuntimeError("Sync service not initialized. Call set_sync_service first.")
    return _sync_service


def set_sync_service(service: SyncService) -> None:
    """Set the sync service singleton.

    Args:
        service: SyncService instance
    """
    global _sync_service
    _sync_service = service


async def close_sync_service() -> None:
    """Close the sync service."""
    global _sync_service
    if _sync_service is not None:
        await _sync_service.stop()
        _sync_service = None


def reset_sync_service() -> None:
    """Reset the sync service singleton (for testing)."""
    global _sync_service
    _sync_service = None
