"""Saga pattern implementation for distributed transactions.

This module provides saga-based distributed transaction management
across PostgreSQL, Milvus, and Neo4j.

Example:
    >>> from src.services.saga import get_saga_coordinator
    >>> coordinator = get_saga_coordinator(postgres, milvus, neo4j)
    >>> result = await coordinator.execute_create_saga(document, chunks)
"""

from src.services.saga.coordinator import (
    SagaCoordinator,
    close_saga_coordinator,
    get_saga_coordinator,
    reset_saga_coordinator,
)
from src.services.saga.models import (
    SagaContext,
    SagaResult,
    SagaStep,
    StepResult,
    StepStatus,
)
from src.services.saga.steps import (
    MilvusCreateStep,
    MilvusDeleteStep,
    Neo4jCreateStep,
    Neo4jDeleteStep,
    PostgresCreateStep,
    PostgresDeleteStep,
    PostgresUpdateStep,
)

__all__ = [
    # Coordinator
    "SagaCoordinator",
    "get_saga_coordinator",
    "close_saga_coordinator",
    "reset_saga_coordinator",
    # Models
    "SagaContext",
    "SagaResult",
    "SagaStep",
    "StepResult",
    "StepStatus",
    # Steps
    "PostgresCreateStep",
    "MilvusCreateStep",
    "Neo4jCreateStep",
    "Neo4jDeleteStep",
    "MilvusDeleteStep",
    "PostgresDeleteStep",
    "PostgresUpdateStep",
]
