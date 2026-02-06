"""PostgreSQL repository for data access.

This module provides a data access layer for PostgreSQL operations:
- Document CRUD operations
- DocumentVersion management
- Chunk CRUD operations
- ACL (Access Control List) management
- Audit logging

Example:
    >>> from src.repositories.postgres import PostgresRepository
    >>> from src.infrastructure.database import get_postgres_client
    >>> client = get_postgres_client()
    >>> repo = PostgresRepository(client)
    >>> doc = await repo.get_document(doc_uuid)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.domain.document import AclEntry, AuditLog, Chunk, Document, DocumentVersion

if TYPE_CHECKING:
    from src.infrastructure.database.postgres import PostgresClient


class PostgresRepository:
    """PostgreSQL data access layer.

    This repository provides methods for:
    - Document CRUD (create, read, update, delete, list)
    - Version management (create, get latest)
    - Chunk management (create, get, delete, update IDs)
    - ACL management (create, check access, get accessible docs)
    - Audit logging (create, query)
    """

    def __init__(self, client: PostgresClient) -> None:
        """Initialize repository.

        Args:
            client: PostgreSQL client instance
        """
        self._client = client

    # =========================================================================
    # Document CRUD
    # =========================================================================

    async def create_document(self, doc: Document) -> Document:
        """Create a new document.

        Args:
            doc: Document to create

        Returns:
            Created document with generated UUID and timestamps
        """
        query = """
            INSERT INTO documents (
                title, source, source_url, owner_id, owner_org,
                status, security_level
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING doc_uuid, created_at, updated_at
        """
        row = await self._client.fetchrow(
            query,
            doc.title,
            doc.source,
            doc.source_url,
            doc.owner_id,
            doc.owner_org,
            doc.status,
            doc.security_level,
        )

        if row is None:
            raise RuntimeError("Failed to create document")

        return Document(
            doc_uuid=row["doc_uuid"],
            title=doc.title,
            source=doc.source,
            source_url=doc.source_url,
            owner_id=doc.owner_id,
            owner_org=doc.owner_org,
            status=doc.status,
            security_level=doc.security_level,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def get_document(self, doc_uuid: UUID | str) -> Document | None:
        """Get document by UUID.

        Args:
            doc_uuid: Document UUID

        Returns:
            Document or None if not found
        """
        query = "SELECT * FROM documents WHERE doc_uuid = $1"
        row = await self._client.fetchrow(query, str(doc_uuid))

        if row is None:
            return None

        return Document(**dict(row))

    async def update_document(
        self,
        doc_uuid: UUID | str,
        updates: dict[str, Any],
    ) -> Document | None:
        """Update document fields.

        Args:
            doc_uuid: Document UUID
            updates: Fields to update (key: column name, value: new value)

        Returns:
            Updated document or None if not found
        """
        if not updates:
            return await self.get_document(doc_uuid)

        # Build SET clause dynamically
        set_clauses = []
        values: list[Any] = []
        for i, (key, value) in enumerate(updates.items(), start=1):
            set_clauses.append(f"{key} = ${i}")
            values.append(value)

        values.append(str(doc_uuid))
        param_num = len(values)

        query = f"""
            UPDATE documents
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE doc_uuid = ${param_num}
            RETURNING *
        """

        row = await self._client.fetchrow(query, *values)

        if row is None:
            return None

        return Document(**dict(row))

    async def delete_document(self, doc_uuid: UUID | str) -> bool:
        """Delete document (cascade deletes related records).

        Args:
            doc_uuid: Document UUID

        Returns:
            True if deleted, False if not found
        """
        query = "DELETE FROM documents WHERE doc_uuid = $1 RETURNING doc_uuid"
        row = await self._client.fetchrow(query, str(doc_uuid))
        return row is not None

    async def list_documents(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
        owner_id: str | None = None,
        source: str | None = None,
    ) -> list[Document]:
        """List documents with pagination and filters.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip
            status: Filter by status
            owner_id: Filter by owner
            source: Filter by source

        Returns:
            List of documents
        """
        conditions = []
        values: list[Any] = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            values.append(status)
            param_idx += 1

        if owner_id:
            conditions.append(f"owner_id = ${param_idx}")
            values.append(owner_id)
            param_idx += 1

        if source:
            conditions.append(f"source = ${param_idx}")
            values.append(source)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        values.extend([limit, offset])

        query = f"""
            SELECT * FROM documents
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        rows = await self._client.fetch(query, *values)
        return [Document(**dict(row)) for row in rows]

    async def count_documents(
        self,
        status: str | None = None,
        owner_id: str | None = None,
    ) -> int:
        """Count documents with optional filters.

        Args:
            status: Filter by status
            owner_id: Filter by owner

        Returns:
            Document count
        """
        conditions = []
        values: list[Any] = []
        param_idx = 1

        if status:
            conditions.append(f"status = ${param_idx}")
            values.append(status)
            param_idx += 1

        if owner_id:
            conditions.append(f"owner_id = ${param_idx}")
            values.append(owner_id)
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"SELECT COUNT(*) as count FROM documents {where_clause}"
        result = await self._client.fetchval(query, *values)
        return result or 0

    # =========================================================================
    # Document Version CRUD
    # =========================================================================

    async def create_version(self, version: DocumentVersion) -> DocumentVersion:
        """Create a new document version.

        Args:
            version: Version to create

        Returns:
            Created version with generated UUID
        """
        query = """
            INSERT INTO document_versions (
                doc_uuid, version_no, content_hash, content_size,
                effective_from, approved_by, change_summary
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING version_id, created_at
        """
        row = await self._client.fetchrow(
            query,
            str(version.doc_uuid),
            version.version_no,
            version.content_hash,
            version.content_size,
            version.effective_from,
            version.approved_by,
            version.change_summary,
        )

        if row is None:
            raise RuntimeError("Failed to create version")

        return DocumentVersion(
            version_id=row["version_id"],
            doc_uuid=version.doc_uuid,
            version_no=version.version_no,
            content_hash=version.content_hash,
            content_size=version.content_size,
            effective_from=version.effective_from,
            approved_by=version.approved_by,
            change_summary=version.change_summary,
            created_at=row["created_at"],
        )

    async def get_version(self, version_id: UUID | str) -> DocumentVersion | None:
        """Get version by UUID.

        Args:
            version_id: Version UUID

        Returns:
            Version or None if not found
        """
        query = "SELECT * FROM document_versions WHERE version_id = $1"
        row = await self._client.fetchrow(query, str(version_id))

        if row is None:
            return None

        return DocumentVersion(**dict(row))

    async def get_latest_version(self, doc_uuid: UUID | str) -> DocumentVersion | None:
        """Get latest version of document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Latest version or None if no versions exist
        """
        query = """
            SELECT * FROM document_versions
            WHERE doc_uuid = $1
            ORDER BY version_no DESC
            LIMIT 1
        """
        row = await self._client.fetchrow(query, str(doc_uuid))

        if row is None:
            return None

        return DocumentVersion(**dict(row))

    async def get_versions(self, doc_uuid: UUID | str) -> list[DocumentVersion]:
        """Get all versions of a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            List of versions ordered by version_no descending
        """
        query = """
            SELECT * FROM document_versions
            WHERE doc_uuid = $1
            ORDER BY version_no DESC
        """
        rows = await self._client.fetch(query, str(doc_uuid))
        return [DocumentVersion(**dict(row)) for row in rows]

    async def get_next_version_no(self, doc_uuid: UUID | str) -> int:
        """Get next version number for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Next version number (1 if no versions exist)
        """
        query = """
            SELECT COALESCE(MAX(version_no), 0) + 1 as next_no
            FROM document_versions
            WHERE doc_uuid = $1
        """
        result = await self._client.fetchval(query, str(doc_uuid))
        return result or 1

    # =========================================================================
    # Chunk CRUD
    # =========================================================================

    async def create_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """Create multiple chunks in a transaction.

        Args:
            chunks: Chunks to create

        Returns:
            Created chunks with generated UUIDs
        """
        if not chunks:
            return []

        query = """
            INSERT INTO document_chunks (
                doc_uuid, version_id, chunk_no, section_path, chunk_text,
                char_start, char_end, token_count,
                milvus_id, neo4j_node_id, embedding_model
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING chunk_uuid, created_at
        """

        results = []
        async with self._client.transaction() as conn:
            for chunk in chunks:
                row = await conn.fetchrow(
                    query,
                    str(chunk.doc_uuid),
                    str(chunk.version_id),
                    chunk.chunk_no,
                    chunk.section_path,
                    chunk.chunk_text,
                    chunk.char_start,
                    chunk.char_end,
                    chunk.token_count,
                    chunk.milvus_id,
                    chunk.neo4j_node_id,
                    chunk.embedding_model,
                )
                results.append(
                    Chunk(
                        chunk_uuid=row["chunk_uuid"],
                        doc_uuid=chunk.doc_uuid,
                        version_id=chunk.version_id,
                        chunk_no=chunk.chunk_no,
                        section_path=chunk.section_path,
                        chunk_text=chunk.chunk_text,
                        char_start=chunk.char_start,
                        char_end=chunk.char_end,
                        token_count=chunk.token_count,
                        milvus_id=chunk.milvus_id,
                        neo4j_node_id=chunk.neo4j_node_id,
                        embedding_model=chunk.embedding_model,
                        created_at=row["created_at"],
                    )
                )

        return results

    async def get_chunk(self, chunk_uuid: UUID | str) -> Chunk | None:
        """Get chunk by UUID.

        Args:
            chunk_uuid: Chunk UUID

        Returns:
            Chunk or None if not found
        """
        query = "SELECT * FROM document_chunks WHERE chunk_uuid = $1"
        row = await self._client.fetchrow(query, str(chunk_uuid))

        if row is None:
            return None

        return Chunk(**dict(row))

    async def get_chunks_by_doc(self, doc_uuid: UUID | str) -> list[Chunk]:
        """Get all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            List of chunks ordered by chunk_no
        """
        query = """
            SELECT * FROM document_chunks
            WHERE doc_uuid = $1
            ORDER BY chunk_no
        """
        rows = await self._client.fetch(query, str(doc_uuid))
        return [Chunk(**dict(row)) for row in rows]

    async def get_chunks_by_version(self, version_id: UUID | str) -> list[Chunk]:
        """Get all chunks for a version.

        Args:
            version_id: Version UUID

        Returns:
            List of chunks ordered by chunk_no
        """
        query = """
            SELECT * FROM document_chunks
            WHERE version_id = $1
            ORDER BY chunk_no
        """
        rows = await self._client.fetch(query, str(version_id))
        return [Chunk(**dict(row)) for row in rows]

    async def delete_chunks_by_doc(self, doc_uuid: UUID | str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted chunks
        """
        query = "DELETE FROM document_chunks WHERE doc_uuid = $1"
        result = await self._client.execute(query, str(doc_uuid))
        # Extract count from "DELETE X"
        return int(result.split()[-1]) if result else 0

    async def delete_chunks_by_version(self, version_id: UUID | str) -> int:
        """Delete all chunks for a version.

        Args:
            version_id: Version UUID

        Returns:
            Number of deleted chunks
        """
        query = "DELETE FROM document_chunks WHERE version_id = $1"
        result = await self._client.execute(query, str(version_id))
        return int(result.split()[-1]) if result else 0

    async def update_chunk_ids(
        self,
        chunk_uuid: UUID | str,
        milvus_id: str | None = None,
        neo4j_node_id: str | None = None,
    ) -> None:
        """Update chunk external IDs.

        Args:
            chunk_uuid: Chunk UUID
            milvus_id: Milvus entity ID (optional)
            neo4j_node_id: Neo4j node ID (optional)
        """
        updates = []
        values: list[Any] = []
        param_idx = 1

        if milvus_id is not None:
            updates.append(f"milvus_id = ${param_idx}")
            values.append(milvus_id)
            param_idx += 1

        if neo4j_node_id is not None:
            updates.append(f"neo4j_node_id = ${param_idx}")
            values.append(neo4j_node_id)
            param_idx += 1

        if not updates:
            return

        values.append(str(chunk_uuid))
        query = f"""
            UPDATE document_chunks
            SET {', '.join(updates)}
            WHERE chunk_uuid = ${param_idx}
        """
        await self._client.execute(query, *values)

    # =========================================================================
    # ACL Methods
    # =========================================================================

    async def create_acl_entries(self, entries: list[AclEntry]) -> None:
        """Create or update ACL entries.

        Uses UPSERT to handle existing entries by updating permission.

        Args:
            entries: ACL entries to create
        """
        if not entries:
            return

        query = """
            INSERT INTO acl_entries (
                doc_uuid, principal_type, principal_id, permission, granted_by
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (doc_uuid, principal_type, principal_id, permission)
            DO UPDATE SET granted_by = EXCLUDED.granted_by
        """

        async with self._client.transaction() as conn:
            for entry in entries:
                await conn.execute(
                    query,
                    str(entry.doc_uuid),
                    entry.principal_type,
                    entry.principal_id,
                    entry.permission,
                    entry.granted_by,
                )

    async def get_acl_entries(self, doc_uuid: UUID | str) -> list[AclEntry]:
        """Get all ACL entries for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            List of ACL entries
        """
        query = "SELECT * FROM acl_entries WHERE doc_uuid = $1"
        rows = await self._client.fetch(query, str(doc_uuid))
        return [AclEntry(**dict(row)) for row in rows]

    async def get_accessible_doc_uuids(
        self,
        user_id: str,
        user_groups: list[str],
        user_org: str | None = None,
    ) -> list[str]:
        """Get document UUIDs accessible by user.

        Access is granted if:
        1. principal_type='user' AND principal_id=user_id
        2. principal_type='group' AND principal_id IN user_groups
        3. principal_type='org' AND (principal_id=user_org OR principal_id='ALL')

        Args:
            user_id: User ID
            user_groups: User's group IDs
            user_org: User's organization (optional)

        Returns:
            List of accessible document UUIDs
        """
        org_conditions = ["principal_id = 'ALL'"]
        if user_org:
            org_conditions.append(f"principal_id = '{user_org}'")

        query = f"""
            SELECT DISTINCT doc_uuid FROM acl_entries
            WHERE (
                (principal_type = 'user' AND principal_id = $1)
                OR (principal_type = 'group' AND principal_id = ANY($2))
                OR (principal_type = 'org' AND ({' OR '.join(org_conditions)}))
            )
        """
        rows = await self._client.fetch(query, user_id, user_groups)
        return [str(row["doc_uuid"]) for row in rows]

    async def check_access(
        self,
        user_id: str,
        user_groups: list[str],
        doc_uuid: UUID | str,
        permission: str = "read",
        user_org: str | None = None,
    ) -> bool:
        """Check if user has permission on document.

        Permission hierarchy: admin > write > read

        Args:
            user_id: User ID
            user_groups: User's group IDs
            doc_uuid: Document UUID
            permission: Required permission level
            user_org: User's organization (optional)

        Returns:
            True if user has access
        """
        # Permission hierarchy
        if permission == "read":
            permissions = ["read", "write", "admin"]
        elif permission == "write":
            permissions = ["write", "admin"]
        elif permission == "admin":
            permissions = ["admin"]
        else:
            permissions = [permission]

        org_conditions = ["principal_id = 'ALL'"]
        if user_org:
            org_conditions.append(f"principal_id = '{user_org}'")

        query = f"""
            SELECT 1 FROM acl_entries
            WHERE doc_uuid = $1
            AND permission = ANY($2)
            AND (
                (principal_type = 'user' AND principal_id = $3)
                OR (principal_type = 'group' AND principal_id = ANY($4))
                OR (principal_type = 'org' AND ({' OR '.join(org_conditions)}))
            )
            LIMIT 1
        """
        row = await self._client.fetchrow(
            query, str(doc_uuid), permissions, user_id, user_groups
        )
        return row is not None

    async def delete_acl_entries(self, doc_uuid: UUID | str) -> int:
        """Delete all ACL entries for document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted entries
        """
        query = "DELETE FROM acl_entries WHERE doc_uuid = $1"
        result = await self._client.execute(query, str(doc_uuid))
        return int(result.split()[-1]) if result else 0

    # =========================================================================
    # Audit Log Methods
    # =========================================================================

    async def create_audit_log(self, log: AuditLog) -> None:
        """Create audit log entry.

        Args:
            log: Audit log entry
        """
        query = """
            INSERT INTO audit_logs (
                user_id, user_org, action, resource_type, doc_uuid,
                query_text, retrieved_docs, result_count, response_time_ms,
                ip_address, user_agent, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        """

        # Convert UUID list to strings for array column
        retrieved_docs = None
        if log.retrieved_docs:
            retrieved_docs = [str(uuid) for uuid in log.retrieved_docs]

        await self._client.execute(
            query,
            log.user_id,
            log.user_org,
            log.action,
            log.resource_type,
            str(log.doc_uuid) if log.doc_uuid else None,
            log.query_text,
            retrieved_docs,
            log.result_count,
            log.response_time_ms,
            log.ip_address,
            log.user_agent,
            log.metadata,
        )

    async def get_audit_logs(
        self,
        user_id: str | None = None,
        action: str | None = None,
        doc_uuid: UUID | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        """Get audit logs with filters.

        Args:
            user_id: Filter by user
            action: Filter by action
            doc_uuid: Filter by document
            limit: Maximum results
            offset: Results to skip

        Returns:
            List of audit logs ordered by timestamp descending
        """
        conditions = []
        values: list[Any] = []
        param_idx = 1

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            values.append(user_id)
            param_idx += 1

        if action:
            conditions.append(f"action = ${param_idx}")
            values.append(action)
            param_idx += 1

        if doc_uuid:
            conditions.append(f"doc_uuid = ${param_idx}")
            values.append(str(doc_uuid))
            param_idx += 1

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        values.extend([limit, offset])

        query = f"""
            SELECT * FROM audit_logs
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """

        rows = await self._client.fetch(query, *values)
        return [AuditLog(**dict(row)) for row in rows]


# =============================================================================
# Singleton Factory
# =============================================================================

_repository: PostgresRepository | None = None


def get_postgres_repository(
    client: PostgresClient | None = None,
) -> PostgresRepository:
    """Get or create PostgresRepository singleton.

    Args:
        client: PostgreSQL client (auto-loaded if not provided)

    Returns:
        PostgresRepository instance
    """
    global _repository
    if _repository is None:
        if client is None:
            from src.infrastructure.database import get_postgres_client

            client = get_postgres_client()
        _repository = PostgresRepository(client)
    return _repository


def reset_postgres_repository() -> None:
    """Reset the repository singleton (for testing)."""
    global _repository
    _repository = None
