"""FastAPI dependency injection and lifecycle management.

This module provides:
- Client initialization and cleanup
- Service initialization and cleanup
- Dependency injection getters for FastAPI routes

Usage:
    # In lifespan event
    await init_clients()
    await init_services()
    yield
    await close_clients()

    # In routes
    @router.post("/search")
    async def search(
        service: Annotated[SearchService, Depends(get_search_service)]
    ):
        ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.infrastructure.database.milvus import MilvusClient
    from src.infrastructure.database.neo4j import Neo4jClient
    from src.infrastructure.database.postgres import PostgresClient
    from src.infrastructure.embedding.bge_m3 import EmbeddingService
    from src.infrastructure.messaging.kafka import KafkaProducer
    from src.services.acl_service import AclService
    from src.services.audit_service import AuditService
    from src.services.document_service import DocumentService
    from src.services.search_service import SearchService

logger = logging.getLogger(__name__)


# =============================================================================
# Client Instances
# =============================================================================

_postgres_client: PostgresClient | None = None
_milvus_client: MilvusClient | None = None
_neo4j_client: Neo4jClient | None = None
_kafka_producer: KafkaProducer | None = None
_embedding_service: EmbeddingService | None = None


# =============================================================================
# Service Instances
# =============================================================================

_document_service: DocumentService | None = None
_search_service: SearchService | None = None
_acl_service: AclService | None = None
_audit_service: AuditService | None = None


# =============================================================================
# Client Initialization
# =============================================================================


async def init_clients() -> None:
    """Initialize all database and infrastructure clients.

    This function should be called during application startup.
    Initializes connections to PostgreSQL, Milvus, Neo4j, Kafka, and
    the embedding service.
    """
    global _postgres_client, _milvus_client, _neo4j_client
    global _kafka_producer, _embedding_service

    from src.config import get_settings
    from src.infrastructure.database.milvus import get_milvus_client
    from src.infrastructure.database.neo4j import get_neo4j_client
    from src.infrastructure.database.postgres import get_postgres_client
    from src.infrastructure.embedding.bge_m3 import get_embedding_service
    from src.infrastructure.messaging.kafka import get_kafka_producer

    settings = get_settings()

    logger.info("Initializing database clients...")

    # PostgreSQL
    try:
        _postgres_client = get_postgres_client(settings.postgres)
        await _postgres_client.connect()
        logger.info("PostgreSQL connected")
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {e}")
        raise

    # Milvus
    try:
        _milvus_client = get_milvus_client(settings.milvus)
        await _milvus_client.connect()
        logger.info("Milvus connected")
    except Exception as e:
        logger.error(f"Failed to connect to Milvus: {e}")
        raise

    # Neo4j
    try:
        _neo4j_client = get_neo4j_client(settings.neo4j)
        await _neo4j_client.connect()
        logger.info("Neo4j connected")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        raise

    # Kafka
    try:
        _kafka_producer = get_kafka_producer(settings.kafka)
        await _kafka_producer.start()
        logger.info("Kafka producer started")
    except Exception as e:
        logger.error(f"Failed to start Kafka producer: {e}")
        raise

    # Embedding service (lazy initialization)
    try:
        _embedding_service = get_embedding_service(settings.embedding)
        logger.info("Embedding service ready")
    except Exception as e:
        logger.error(f"Failed to initialize embedding service: {e}")
        raise

    logger.info("All clients initialized successfully")


async def init_services() -> None:
    """Initialize all application services.

    This function should be called after init_clients().
    Creates repositories and initializes services.
    """
    global _document_service, _search_service, _acl_service, _audit_service

    from src.repositories.milvus.repository import MilvusRepository
    from src.repositories.neo4j.repository import Neo4jRepository
    from src.repositories.postgres.repository import PostgresRepository
    from src.services.acl_service import AclService
    from src.services.audit_service import AuditService
    from src.services.document_service import DocumentService
    from src.services.saga.coordinator import SagaCoordinator
    from src.services.search_service import SearchService

    logger.info("Initializing services...")

    # Create repositories
    postgres_repo = PostgresRepository(_postgres_client)
    milvus_repo = MilvusRepository(_milvus_client)
    neo4j_repo = Neo4jRepository(_neo4j_client)

    # ACL Service
    _acl_service = AclService(postgres_repo)
    logger.debug("ACL service initialized")

    # Saga Coordinator
    saga = SagaCoordinator(
        postgres_repo=postgres_repo,
        milvus_repo=milvus_repo,
        neo4j_repo=neo4j_repo,
        embedding_service=_embedding_service,
    )
    logger.debug("Saga coordinator initialized")

    # Document Service
    _document_service = DocumentService(
        postgres_repo=postgres_repo,
        saga_coordinator=saga,
        embedding_service=_embedding_service,
        kafka_producer=_kafka_producer,
        acl_service=_acl_service,
    )
    logger.debug("Document service initialized")

    # Search Service
    _search_service = SearchService(
        milvus_repo=milvus_repo,
        embedding_service=_embedding_service,
        acl_service=_acl_service,
        neo4j_repo=neo4j_repo,
    )
    logger.debug("Search service initialized")

    # Audit Service
    _audit_service = AuditService(repository=postgres_repo)
    await _audit_service.start()
    logger.debug("Audit service started")

    # Set global instances for convenience functions
    from src.services.audit_service import set_audit_service

    set_audit_service(_audit_service)

    logger.info("All services initialized successfully")


async def close_clients() -> None:
    """Close all database and infrastructure clients.

    This function should be called during application shutdown.
    Properly closes all connections to prevent resource leaks.
    """
    global _postgres_client, _milvus_client, _neo4j_client
    global _kafka_producer, _audit_service

    logger.info("Closing clients...")

    # Stop audit service first (flushes pending logs)
    if _audit_service:
        try:
            await _audit_service.stop()
            logger.debug("Audit service stopped")
        except Exception as e:
            logger.error(f"Error stopping audit service: {e}")

    # Stop Kafka producer
    if _kafka_producer:
        try:
            await _kafka_producer.stop()
            logger.debug("Kafka producer stopped")
        except Exception as e:
            logger.error(f"Error stopping Kafka producer: {e}")

    # Close Neo4j
    if _neo4j_client:
        try:
            await _neo4j_client.close()
            logger.debug("Neo4j connection closed")
        except Exception as e:
            logger.error(f"Error closing Neo4j: {e}")

    # Close Milvus
    if _milvus_client:
        try:
            await _milvus_client.close()
            logger.debug("Milvus connection closed")
        except Exception as e:
            logger.error(f"Error closing Milvus: {e}")

    # Close PostgreSQL
    if _postgres_client:
        try:
            await _postgres_client.close()
            logger.debug("PostgreSQL connection closed")
        except Exception as e:
            logger.error(f"Error closing PostgreSQL: {e}")

    logger.info("All clients closed")


# =============================================================================
# Dependency Getters
# =============================================================================


async def get_document_service() -> DocumentService:
    """Get document service instance.

    Used as a FastAPI dependency.

    Returns:
        DocumentService instance

    Raises:
        RuntimeError: If service not initialized
    """
    if _document_service is None:
        raise RuntimeError(
            "Document service not initialized. "
            "Ensure init_services() was called during startup."
        )
    return _document_service


async def get_search_service() -> SearchService:
    """Get search service instance.

    Used as a FastAPI dependency.

    Returns:
        SearchService instance

    Raises:
        RuntimeError: If service not initialized
    """
    if _search_service is None:
        raise RuntimeError(
            "Search service not initialized. "
            "Ensure init_services() was called during startup."
        )
    return _search_service


async def get_acl_service() -> AclService:
    """Get ACL service instance.

    Used as a FastAPI dependency.

    Returns:
        AclService instance

    Raises:
        RuntimeError: If service not initialized
    """
    if _acl_service is None:
        raise RuntimeError(
            "ACL service not initialized. "
            "Ensure init_services() was called during startup."
        )
    return _acl_service


async def get_audit_service() -> AuditService:
    """Get audit service instance.

    Used as a FastAPI dependency.

    Returns:
        AuditService instance

    Raises:
        RuntimeError: If service not initialized
    """
    if _audit_service is None:
        raise RuntimeError(
            "Audit service not initialized. "
            "Ensure init_services() was called during startup."
        )
    return _audit_service


def get_clients_for_health() -> dict[str, Any]:
    """Get client references for health checks.

    Returns a dictionary of client instances that can be passed
    to the health router's set_clients() function.

    Returns:
        Dictionary with client references
    """
    return {
        "postgres": _postgres_client,
        "milvus": _milvus_client,
        "neo4j": _neo4j_client,
        "kafka": _kafka_producer,
    }


# =============================================================================
# Service Setters (for testing)
# =============================================================================


def set_document_service(service: DocumentService) -> None:
    """Set document service instance.

    Primarily used for testing.

    Args:
        service: DocumentService instance
    """
    global _document_service
    _document_service = service


def set_search_service(service: SearchService) -> None:
    """Set search service instance.

    Primarily used for testing.

    Args:
        service: SearchService instance
    """
    global _search_service
    _search_service = service


def set_acl_service(service: AclService) -> None:
    """Set ACL service instance.

    Primarily used for testing.

    Args:
        service: AclService instance
    """
    global _acl_service
    _acl_service = service


def reset_dependencies() -> None:
    """Reset all dependency instances.

    Useful for testing to ensure clean state between tests.
    """
    global _postgres_client, _milvus_client, _neo4j_client
    global _kafka_producer, _embedding_service
    global _document_service, _search_service, _acl_service, _audit_service

    _postgres_client = None
    _milvus_client = None
    _neo4j_client = None
    _kafka_producer = None
    _embedding_service = None
    _document_service = None
    _search_service = None
    _acl_service = None
    _audit_service = None
