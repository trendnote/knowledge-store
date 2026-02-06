"""Saga step implementations.

This module provides step implementations for saga-based distributed transactions:
- Create Steps: PostgreSQL → Milvus → Neo4j
- Delete Steps: Neo4j → Milvus → PostgreSQL

Each step implements execute() for forward operation and compensate() for rollback.

Example:
    >>> step = PostgresCreateStep(postgres_repo)
    >>> result = await step.execute(context)
    >>> if not result.success:
    ...     await step.compensate(context)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

from src.services.saga.models import SagaContext, StepResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Repository Protocols
# =============================================================================


class PostgresRepositoryProtocol(Protocol):
    """Protocol for PostgreSQL repository operations used by saga steps."""

    async def create_document(self, document: Any) -> Any:
        """Create document."""
        ...

    async def create_chunks(self, chunks: list[Any]) -> list[Any]:
        """Create chunks."""
        ...

    async def get_document(self, doc_uuid: str) -> Any:
        """Get document by UUID."""
        ...

    async def get_chunks_by_doc(self, doc_uuid: str) -> list[Any]:
        """Get chunks by document UUID."""
        ...

    async def update_document(self, doc_uuid: str, document: Any) -> Any:
        """Update document."""
        ...

    async def delete_document(self, doc_uuid: str) -> bool:
        """Delete document."""
        ...

    async def delete_chunks_by_doc(self, doc_uuid: str) -> int:
        """Delete chunks by document UUID."""
        ...


class MilvusRepositoryProtocol(Protocol):
    """Protocol for Milvus repository operations used by saga steps."""

    async def insert_chunks(self, chunks: list[Any]) -> list[str]:
        """Insert chunk vectors."""
        ...

    async def delete_by_doc_uuid(self, doc_uuid: str) -> int:
        """Delete vectors by document UUID."""
        ...

    async def delete_by_chunk_uuids(self, chunk_uuids: list[str]) -> int:
        """Delete vectors by chunk UUIDs."""
        ...


class Neo4jRepositoryProtocol(Protocol):
    """Protocol for Neo4j repository operations used by saga steps."""

    async def create_document_node(self, document: Any) -> str:
        """Create document node."""
        ...

    async def create_chunk_nodes(self, chunks: list[Any]) -> list[str]:
        """Create chunk nodes."""
        ...

    async def create_contains_edges(self, doc_uuid: str, chunk_uuids: list[str]) -> int:
        """Create CONTAINS edges."""
        ...

    async def get_document_graph(self, doc_uuid: str) -> dict[str, Any]:
        """Get document graph."""
        ...

    async def delete_document_graph(self, doc_uuid: str) -> int:
        """Delete document graph."""
        ...


# =============================================================================
# Create Steps
# =============================================================================


class PostgresCreateStep:
    """Step to create document in PostgreSQL.

    Creates document and chunks in PostgreSQL as the first step of create saga.
    Compensation deletes the created document (cascade deletes chunks).
    """

    name = "postgres_create"

    def __init__(self, repository: PostgresRepositoryProtocol) -> None:
        """Initialize with repository.

        Args:
            repository: PostgreSQL repository implementation
        """
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Create document and chunks in PostgreSQL.

        Args:
            context: Saga context with document and chunks

        Returns:
            StepResult with created doc_uuid and chunk count
        """
        try:
            # Create document
            doc = await self._repository.create_document(context.document)
            doc_uuid = str(doc.doc_uuid) if hasattr(doc, "doc_uuid") else context.doc_uuid

            # Create chunks
            chunks = await self._repository.create_chunks(context.chunks)

            context.set_result(self.name, {"doc": doc, "chunks": chunks})

            return StepResult(
                success=True,
                step_name=self.name,
                data={"doc_uuid": doc_uuid, "chunk_count": len(chunks)},
            )
        except Exception as e:
            logger.exception(f"PostgresCreateStep failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Delete document and chunks from PostgreSQL.

        Args:
            context: Saga context with doc_uuid

        Returns:
            StepResult indicating compensation success
        """
        try:
            await self._repository.delete_document(context.doc_uuid)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            logger.exception(f"PostgresCreateStep compensation failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


class MilvusCreateStep:
    """Step to create vectors in Milvus.

    Inserts chunk vectors into Milvus as the second step of create saga.
    Compensation deletes the inserted vectors.
    """

    name = "milvus_create"

    def __init__(self, repository: MilvusRepositoryProtocol) -> None:
        """Initialize with repository.

        Args:
            repository: Milvus repository implementation
        """
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Insert vectors into Milvus.

        Args:
            context: Saga context with chunks and embeddings

        Returns:
            StepResult with inserted chunk count
        """
        try:
            if context.embeddings is None:
                return StepResult(
                    success=False,
                    step_name=self.name,
                    error="No embeddings in context",
                )

            # Build MilvusChunk data for insert
            from src.domain.search import MilvusChunk

            milvus_chunks = []
            for i, chunk in enumerate(context.chunks):
                chunk_uuid = str(chunk.chunk_uuid) if hasattr(chunk, "chunk_uuid") else str(i)
                milvus_chunk = MilvusChunk(
                    chunk_uuid=chunk_uuid,
                    doc_uuid=context.doc_uuid,
                    dense_embedding=context.embeddings.dense[i],
                    sparse_embedding=context.embeddings.sparse[i],
                    chunk_text=getattr(chunk, "chunk_text", "") or "",
                    section_path=getattr(chunk, "section_path", None),
                )
                milvus_chunks.append(milvus_chunk)

            # Insert vectors
            chunk_uuids = await self._repository.insert_chunks(milvus_chunks)

            context.set_result(self.name, {"chunk_uuids": chunk_uuids})

            return StepResult(
                success=True,
                step_name=self.name,
                data={"inserted_count": len(chunk_uuids)},
            )
        except Exception as e:
            logger.exception(f"MilvusCreateStep failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Delete vectors from Milvus.

        Args:
            context: Saga context with chunk info

        Returns:
            StepResult indicating compensation success
        """
        try:
            # Delete by doc_uuid to ensure all vectors are removed
            await self._repository.delete_by_doc_uuid(context.doc_uuid)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            logger.exception(f"MilvusCreateStep compensation failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


class Neo4jCreateStep:
    """Step to create graph nodes in Neo4j.

    Creates document and chunk nodes in Neo4j as the third step of create saga.
    Compensation deletes the created graph.
    """

    name = "neo4j_create"

    def __init__(self, repository: Neo4jRepositoryProtocol) -> None:
        """Initialize with repository.

        Args:
            repository: Neo4j repository implementation
        """
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Create document and chunk nodes in Neo4j.

        Args:
            context: Saga context with document and chunks

        Returns:
            StepResult with created node count
        """
        try:
            from src.domain.graph import ChunkNode, DocumentNode

            # Build DocumentNode
            doc = context.document
            doc_node = DocumentNode(
                doc_uuid=context.doc_uuid,
                title=getattr(doc, "title", "Untitled"),
                source=getattr(doc, "source", "file"),
                security_level=getattr(doc, "security_level", "internal"),
            )

            # Create document node
            await self._repository.create_document_node(doc_node)

            # Build ChunkNodes
            chunk_nodes = []
            chunk_uuids = []
            for i, chunk in enumerate(context.chunks):
                chunk_uuid = str(chunk.chunk_uuid) if hasattr(chunk, "chunk_uuid") else f"{context.doc_uuid}-{i}"
                chunk_uuids.append(chunk_uuid)
                chunk_node = ChunkNode(
                    chunk_uuid=chunk_uuid,
                    doc_uuid=context.doc_uuid,
                    sequence=getattr(chunk, "chunk_no", i),
                    text_preview=(getattr(chunk, "chunk_text", "") or "")[:500],
                    section_path=getattr(chunk, "section_path", None),
                )
                chunk_nodes.append(chunk_node)

            # Create chunk nodes
            await self._repository.create_chunk_nodes(chunk_nodes)

            # Create CONTAINS edges
            await self._repository.create_contains_edges(context.doc_uuid, chunk_uuids)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"node_count": 1 + len(context.chunks)},
            )
        except Exception as e:
            logger.exception(f"Neo4jCreateStep failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Delete document graph from Neo4j.

        Args:
            context: Saga context with doc_uuid

        Returns:
            StepResult indicating compensation success
        """
        try:
            await self._repository.delete_document_graph(context.doc_uuid)
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            logger.exception(f"Neo4jCreateStep compensation failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


# =============================================================================
# Delete Steps
# =============================================================================


class Neo4jDeleteStep:
    """Step to delete graph from Neo4j.

    Deletes document graph from Neo4j as the first step of delete saga.
    Compensation attempts to restore the graph (limited support).
    """

    name = "neo4j_delete"

    def __init__(self, repository: Neo4jRepositoryProtocol) -> None:
        """Initialize with repository.

        Args:
            repository: Neo4j repository implementation
        """
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Delete document graph from Neo4j.

        Args:
            context: Saga context with doc_uuid

        Returns:
            StepResult with deletion status
        """
        try:
            # Get graph data for potential compensation
            graph_data = await self._repository.get_document_graph(context.doc_uuid)
            context.set_result(f"{self.name}_backup", graph_data)

            # Delete graph
            deleted_count = await self._repository.delete_document_graph(context.doc_uuid)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"deleted": True, "deleted_count": deleted_count},
            )
        except Exception as e:
            logger.exception(f"Neo4jDeleteStep failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Restore graph in Neo4j (best effort).

        Note: Full restoration may not be possible.
        Logs warning if backup not available.

        Args:
            context: Saga context with backup data

        Returns:
            StepResult indicating compensation attempt
        """
        try:
            backup = context.get_result(f"{self.name}_backup")
            if backup:
                # Restoration would require recreating nodes and edges
                # This is a simplified implementation - full restore not implemented
                logger.warning(
                    f"Neo4j graph restoration requested but not fully implemented. "
                    f"Backup data available for doc: {context.doc_uuid}"
                )
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            logger.exception(f"Neo4jDeleteStep compensation failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


class MilvusDeleteStep:
    """Step to delete vectors from Milvus.

    Deletes vectors from Milvus as the second step of delete saga.
    Compensation is not fully supported (vectors cannot be restored).
    """

    name = "milvus_delete"

    def __init__(self, repository: MilvusRepositoryProtocol) -> None:
        """Initialize with repository.

        Args:
            repository: Milvus repository implementation
        """
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Delete vectors from Milvus.

        Args:
            context: Saga context with doc_uuid

        Returns:
            StepResult with deletion count
        """
        try:
            # Delete vectors by doc_uuid
            deleted_count = await self._repository.delete_by_doc_uuid(context.doc_uuid)

            context.set_result(f"{self.name}_deleted_count", deleted_count)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"deleted_count": deleted_count},
            )
        except Exception as e:
            logger.exception(f"MilvusDeleteStep failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Attempt to restore vectors in Milvus (not supported).

        Vector restoration is not supported as embeddings are not stored.

        Args:
            context: Saga context

        Returns:
            StepResult indicating compensation not possible
        """
        logger.warning(
            f"Milvus vector restoration not supported. "
            f"Vectors for doc {context.doc_uuid} cannot be restored."
        )
        return StepResult(success=True, step_name=self.name)


class PostgresDeleteStep:
    """Step to delete document from PostgreSQL.

    Deletes document from PostgreSQL as the third step of delete saga.
    Compensation restores the document and chunks from backup.
    """

    name = "postgres_delete"

    def __init__(self, repository: PostgresRepositoryProtocol) -> None:
        """Initialize with repository.

        Args:
            repository: PostgreSQL repository implementation
        """
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Delete document from PostgreSQL.

        Args:
            context: Saga context with doc_uuid

        Returns:
            StepResult with deletion status
        """
        try:
            # Get document for potential compensation
            doc = await self._repository.get_document(context.doc_uuid)
            chunks = await self._repository.get_chunks_by_doc(context.doc_uuid)
            context.set_result(f"{self.name}_backup", {"doc": doc, "chunks": chunks})

            # Delete document (cascades to chunks)
            await self._repository.delete_document(context.doc_uuid)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"deleted": True},
            )
        except Exception as e:
            logger.exception(f"PostgresDeleteStep failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Restore document in PostgreSQL.

        Args:
            context: Saga context with backup data

        Returns:
            StepResult indicating restoration success
        """
        try:
            backup = context.get_result(f"{self.name}_backup")
            if backup and backup.get("doc"):
                await self._repository.create_document(backup["doc"])
                if backup.get("chunks"):
                    await self._repository.create_chunks(backup["chunks"])
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            logger.exception(f"PostgresDeleteStep compensation failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )


# =============================================================================
# Update Steps
# =============================================================================


class PostgresUpdateStep:
    """Step to update document in PostgreSQL.

    Updates document metadata in PostgreSQL.
    Used as part of update saga.
    """

    name = "postgres_update"

    def __init__(self, repository: PostgresRepositoryProtocol) -> None:
        """Initialize with repository.

        Args:
            repository: PostgreSQL repository implementation
        """
        self._repository = repository

    async def execute(self, context: SagaContext) -> StepResult:
        """Update document in PostgreSQL.

        Args:
            context: Saga context with document updates

        Returns:
            StepResult with update status
        """
        try:
            # Get current state for backup
            old_doc = await self._repository.get_document(context.doc_uuid)
            old_chunks = await self._repository.get_chunks_by_doc(context.doc_uuid)
            context.set_result(f"{self.name}_backup", {"doc": old_doc, "chunks": old_chunks})

            # Update document
            await self._repository.update_document(context.doc_uuid, context.document)

            # Delete old chunks and create new ones
            await self._repository.delete_chunks_by_doc(context.doc_uuid)
            if context.chunks:
                await self._repository.create_chunks(context.chunks)

            return StepResult(
                success=True,
                step_name=self.name,
                data={"updated": True, "chunk_count": len(context.chunks)},
            )
        except Exception as e:
            logger.exception(f"PostgresUpdateStep failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=str(e),
            )

    async def compensate(self, context: SagaContext) -> StepResult:
        """Restore original document in PostgreSQL.

        Args:
            context: Saga context with backup data

        Returns:
            StepResult indicating restoration success
        """
        try:
            backup = context.get_result(f"{self.name}_backup")
            if backup and backup.get("doc"):
                await self._repository.update_document(context.doc_uuid, backup["doc"])
                await self._repository.delete_chunks_by_doc(context.doc_uuid)
                if backup.get("chunks"):
                    await self._repository.create_chunks(backup["chunks"])
            return StepResult(success=True, step_name=self.name)
        except Exception as e:
            logger.exception(f"PostgresUpdateStep compensation failed: {e}")
            return StepResult(
                success=False,
                step_name=self.name,
                error=f"Compensation failed: {e}",
            )
