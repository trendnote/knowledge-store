"""Saga coordinator for distributed transactions.

This module provides orchestration for saga-based distributed transactions
across PostgreSQL, Milvus, and Neo4j.

Saga Patterns:
- Create: PostgreSQL → Milvus → Neo4j (with reverse compensation)
- Delete: Neo4j → Milvus → PostgreSQL (with reverse compensation)
- Update: Delete old + Create new

Example:
    >>> coordinator = SagaCoordinator(postgres_repo, milvus_repo, neo4j_repo)
    >>> result = await coordinator.execute_create_saga(document, chunks)
    >>> if not result.success:
    ...     print(f"Failed: {result.error}")
    ...     print(f"Compensated: {result.compensated_steps}")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from src.services.saga.models import SagaContext, SagaResult, SagaStep
from src.services.saga.steps import (
    MilvusCreateStep,
    MilvusDeleteStep,
    Neo4jCreateStep,
    Neo4jDeleteStep,
    PostgresCreateStep,
    PostgresDeleteStep,
    PostgresUpdateStep,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class EmbeddingServiceProtocol(Protocol):
    """Protocol for embedding service used by saga coordinator."""

    def encode(self, texts: list[str]) -> Any:
        """Encode texts to embeddings."""
        ...


class SagaCoordinator:
    """Coordinator for saga-based distributed transactions.

    Orchestrates multi-step transactions across PostgreSQL, Milvus, and Neo4j
    with automatic compensation (rollback) on failure.

    Execution Order:
    - Create: PostgreSQL → Milvus → Neo4j
    - Delete: Neo4j → Milvus → PostgreSQL
    - Update: Delete old vectors/graph → Update PostgreSQL → Create new vectors/graph

    Compensation Order:
    - Always reverse of execution order
    - Continues even if individual compensation fails
    - All failures are logged

    Attributes:
        _postgres_repo: PostgreSQL repository
        _milvus_repo: Milvus repository
        _neo4j_repo: Neo4j repository
        _embedding_service: Optional embedding service

    Example:
        >>> coordinator = SagaCoordinator(
        ...     postgres_repo=postgres,
        ...     milvus_repo=milvus,
        ...     neo4j_repo=neo4j,
        ...     embedding_service=embedder,
        ... )
        >>> result = await coordinator.execute_create_saga(doc, chunks)
    """

    def __init__(
        self,
        postgres_repo: Any,
        milvus_repo: Any,
        neo4j_repo: Any,
        embedding_service: EmbeddingServiceProtocol | None = None,
    ) -> None:
        """Initialize saga coordinator.

        Args:
            postgres_repo: PostgreSQL repository for document storage
            milvus_repo: Milvus repository for vector storage
            neo4j_repo: Neo4j repository for graph storage
            embedding_service: Embedding service for vector generation (optional)
        """
        self._postgres_repo = postgres_repo
        self._milvus_repo = milvus_repo
        self._neo4j_repo = neo4j_repo
        self._embedding_service = embedding_service

    def _get_create_steps(self) -> list[SagaStep]:
        """Get steps for create saga.

        Returns:
            List of steps in execution order
        """
        return [
            PostgresCreateStep(self._postgres_repo),
            MilvusCreateStep(self._milvus_repo),
            Neo4jCreateStep(self._neo4j_repo),
        ]

    def _get_delete_steps(self) -> list[SagaStep]:
        """Get steps for delete saga.

        Returns:
            List of steps in execution order
        """
        return [
            Neo4jDeleteStep(self._neo4j_repo),
            MilvusDeleteStep(self._milvus_repo),
            PostgresDeleteStep(self._postgres_repo),
        ]

    async def _execute_steps(
        self,
        steps: list[SagaStep],
        context: SagaContext,
    ) -> SagaResult:
        """Execute saga steps with compensation on failure.

        Executes each step in order. On failure:
        1. Stops execution
        2. Compensates all previously executed steps in reverse order
        3. Returns result with error and compensation details

        Args:
            steps: List of steps to execute in order
            context: Saga context with data for steps

        Returns:
            SagaResult with execution and compensation details
        """
        result = SagaResult(success=True, doc_uuid=context.doc_uuid)
        executed: list[SagaStep] = []

        for step in steps:
            logger.info(f"Executing saga step: {step.name}")
            step_result = await step.execute(context)

            if step_result.success:
                result.add_executed(step.name, step_result)
                executed.append(step)
                logger.info(f"Step succeeded: {step.name}")
            else:
                logger.error(f"Step failed: {step.name} - {step_result.error}")
                result.success = False
                result.error = f"Step '{step.name}' failed: {step_result.error}"
                result.step_results[step.name] = step_result

                # Compensate in reverse order
                await self._compensate_steps(list(reversed(executed)), context, result)
                break

        return result

    async def _compensate_steps(
        self,
        steps: list[SagaStep],
        context: SagaContext,
        result: SagaResult,
    ) -> None:
        """Compensate executed steps in reverse order.

        Attempts to compensate all steps, continuing even if individual
        compensations fail. All failures are logged.

        Args:
            steps: Steps to compensate (already in reverse order)
            context: Saga context with data for compensation
            result: SagaResult to update with compensation status
        """
        for step in steps:
            logger.info(f"Compensating saga step: {step.name}")
            try:
                comp_result = await step.compensate(context)
                if comp_result.success:
                    result.add_compensated(step.name)
                    logger.info(f"Compensation succeeded: {step.name}")
                else:
                    logger.error(
                        f"Compensation failed for {step.name}: {comp_result.error}"
                    )
            except Exception as e:
                logger.exception(f"Compensation exception for {step.name}: {e}")

    async def execute_create_saga(
        self,
        document: Any,
        chunks: list[Any],
        embeddings: Any | None = None,
    ) -> SagaResult:
        """Execute create saga for document storage.

        Order: PostgreSQL → Milvus → Neo4j
        Compensation: Neo4j → Milvus → PostgreSQL

        If embeddings are not provided and embedding_service is available,
        embeddings will be generated automatically from chunk texts.

        Args:
            document: Document to create (must have doc_uuid)
            chunks: Chunks to create (must have chunk_uuid, chunk_text)
            embeddings: Pre-computed embeddings (optional)

        Returns:
            SagaResult with execution details

        Example:
            >>> result = await coordinator.execute_create_saga(
            ...     document=doc,
            ...     chunks=chunks,
            ... )
            >>> if result.success:
            ...     print(f"Created: {result.doc_uuid}")
        """
        doc_uuid = str(document.doc_uuid) if hasattr(document, "doc_uuid") else str(document.get("doc_uuid", ""))

        # Generate embeddings if not provided
        if embeddings is None and self._embedding_service:
            texts = [getattr(c, "chunk_text", "") or "" for c in chunks]
            if texts:
                logger.info(f"Generating embeddings for {len(texts)} chunks")
                embeddings = self._embedding_service.encode(texts)

        context = SagaContext(
            doc_uuid=doc_uuid,
            document=document,
            chunks=chunks,
            embeddings=embeddings,
        )

        steps = self._get_create_steps()
        return await self._execute_steps(steps, context)

    async def execute_delete_saga(self, doc_uuid: str) -> SagaResult:
        """Execute delete saga for document removal.

        Order: Neo4j → Milvus → PostgreSQL
        Compensation: PostgreSQL → Milvus → Neo4j

        Deletes document from all three stores. If any step fails,
        previously deleted data will be restored where possible.

        Args:
            doc_uuid: Document UUID to delete

        Returns:
            SagaResult with execution details

        Example:
            >>> result = await coordinator.execute_delete_saga("doc-123")
            >>> if result.success:
            ...     print("Deleted from all stores")
        """
        context = SagaContext(doc_uuid=doc_uuid)

        steps = self._get_delete_steps()
        return await self._execute_steps(steps, context)

    async def execute_update_saga(
        self,
        doc_uuid: str,
        document: Any,
        chunks: list[Any],
        embeddings: Any | None = None,
    ) -> SagaResult:
        """Execute update saga (delete old + create new).

        This performs a full update by:
        1. Deleting old vectors from Milvus
        2. Deleting old graph from Neo4j
        3. Updating document in PostgreSQL
        4. Creating new vectors in Milvus
        5. Creating new graph in Neo4j

        Args:
            doc_uuid: Document UUID to update
            document: Updated document data
            chunks: Updated chunks
            embeddings: Pre-computed embeddings (optional)

        Returns:
            SagaResult with execution details
        """
        # Phase 1: Delete old data from Milvus and Neo4j
        logger.info(f"Update saga phase 1: Deleting old data for {doc_uuid}")
        delete_context = SagaContext(doc_uuid=doc_uuid)
        delete_steps: list[SagaStep] = [
            Neo4jDeleteStep(self._neo4j_repo),
            MilvusDeleteStep(self._milvus_repo),
        ]

        delete_result = await self._execute_steps(delete_steps, delete_context)
        if not delete_result.success:
            logger.error(f"Update saga phase 1 failed: {delete_result.error}")
            return delete_result

        # Phase 2: Update PostgreSQL
        logger.info(f"Update saga phase 2: Updating PostgreSQL for {doc_uuid}")
        try:
            update_step = PostgresUpdateStep(self._postgres_repo)
            update_context = SagaContext(
                doc_uuid=doc_uuid,
                document=document,
                chunks=chunks,
            )
            update_result = await update_step.execute(update_context)
            if not update_result.success:
                logger.error(f"PostgreSQL update failed: {update_result.error}")
                # Attempt to restore Neo4j and Milvus
                await self._compensate_steps(
                    list(reversed(delete_steps)), delete_context, delete_result
                )
                return SagaResult(
                    success=False,
                    doc_uuid=doc_uuid,
                    executed_steps=delete_result.executed_steps,
                    error=f"PostgreSQL update failed: {update_result.error}",
                )
        except Exception as e:
            logger.exception(f"PostgreSQL update exception: {e}")
            return SagaResult(
                success=False,
                doc_uuid=doc_uuid,
                executed_steps=delete_result.executed_steps,
                error=str(e),
            )

        # Phase 3: Create new data in Milvus and Neo4j
        logger.info(f"Update saga phase 3: Creating new data for {doc_uuid}")

        # Generate embeddings if not provided
        if embeddings is None and self._embedding_service:
            texts = [getattr(c, "chunk_text", "") or "" for c in chunks]
            if texts:
                embeddings = self._embedding_service.encode(texts)

        create_context = SagaContext(
            doc_uuid=doc_uuid,
            document=document,
            chunks=chunks,
            embeddings=embeddings,
        )
        create_steps: list[SagaStep] = [
            MilvusCreateStep(self._milvus_repo),
            Neo4jCreateStep(self._neo4j_repo),
        ]

        create_result = await self._execute_steps(create_steps, create_context)

        # Merge results
        all_executed = (
            delete_result.executed_steps
            + ["postgres_update"]
            + create_result.executed_steps
        )

        return SagaResult(
            success=create_result.success,
            doc_uuid=doc_uuid,
            executed_steps=all_executed,
            compensated_steps=create_result.compensated_steps,
            error=create_result.error,
            step_results={**delete_result.step_results, **create_result.step_results},
        )


# =============================================================================
# Singleton Factory
# =============================================================================

_coordinator: SagaCoordinator | None = None


def get_saga_coordinator(
    postgres_repo: Any | None = None,
    milvus_repo: Any | None = None,
    neo4j_repo: Any | None = None,
    embedding_service: EmbeddingServiceProtocol | None = None,
) -> SagaCoordinator:
    """Get or create saga coordinator singleton.

    Args:
        postgres_repo: PostgreSQL repository (required on first call)
        milvus_repo: Milvus repository (required on first call)
        neo4j_repo: Neo4j repository (required on first call)
        embedding_service: Embedding service (optional)

    Returns:
        SagaCoordinator instance

    Raises:
        ValueError: If repositories not provided on first call
    """
    global _coordinator
    if _coordinator is None:
        if postgres_repo is None or milvus_repo is None or neo4j_repo is None:
            raise ValueError("All repositories required for first initialization")
        _coordinator = SagaCoordinator(
            postgres_repo=postgres_repo,
            milvus_repo=milvus_repo,
            neo4j_repo=neo4j_repo,
            embedding_service=embedding_service,
        )
    return _coordinator


def close_saga_coordinator() -> None:
    """Close the saga coordinator singleton."""
    global _coordinator
    _coordinator = None


def reset_saga_coordinator() -> None:
    """Reset saga coordinator singleton (for testing)."""
    global _coordinator
    _coordinator = None
