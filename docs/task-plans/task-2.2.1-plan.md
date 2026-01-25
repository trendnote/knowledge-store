# Task Execution Plan: 2.2.1 - PostgreSQL Repository 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.2.1 |
| **Task Name** | PostgreSQL Repository 구현 |
| **Estimate** | 6h |
| **Priority** | P0 |
| **Dependencies** | Task 2.1.1 |

### Description
PostgreSQL 데이터 접근 레이어를 구현합니다.

### Acceptance Criteria
- [ ] `src/repositories/postgres/repository.py` 생성
- [ ] Document CRUD 메서드
- [ ] Chunk CRUD 메서드
- [ ] ACL 조회/생성 메서드
- [ ] Audit Log 생성 메서드
- [ ] SQLAlchemy Models (`models.py`)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.3 Repository Layer
- **Schema**: `docs/architecture/architecture.md` Section 6.1 PostgreSQL Schema

### 2.2 테이블 구조
```
documents       - 문서 메타데이터
document_versions - 버전 관리
document_chunks   - 청크 ID 매핑
acl_entries      - 권한 관리
audit_logs       - 감사 로그
```

### 2.3 설계 결정
1. **Raw SQL**: asyncpg 직접 사용 (SQLAlchemy ORM 대신 성능 우선)
2. **Domain Models**: Pydantic 모델로 데이터 매핑
3. **Transaction**: PostgresClient의 transaction() 활용
4. **Type Safety**: 완전한 타입 힌트

### 2.4 클래스 구조
```
PostgresRepository
├── __init__(client: PostgresClient)
├── Document CRUD
│   ├── create_document(doc) -> Document
│   ├── get_document(doc_uuid) -> Document | None
│   ├── update_document(doc_uuid, updates) -> Document
│   └── delete_document(doc_uuid) -> None
├── Chunk CRUD
│   ├── create_chunks(chunks) -> list[Chunk]
│   ├── get_chunks_by_doc(doc_uuid) -> list[Chunk]
│   └── delete_chunks_by_doc(doc_uuid) -> None
├── ACL
│   ├── create_acl_entries(entries) -> None
│   ├── get_accessible_doc_uuids(user_id, groups) -> list[str]
│   └── check_access(user_id, groups, doc_uuid, perm) -> bool
└── Audit
    └── create_audit_log(log) -> None
```

---

## 3. Implementation Steps

### Step 1: Domain Models 정의 (1h)

**작업 내용:**
1. Document, Chunk, AclEntry, AuditLog Pydantic 모델
2. 데이터베이스 레코드 ↔ 모델 변환

**src/domain/document.py:**
```python
"""Document domain models."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Document entity."""

    doc_uuid: UUID
    title: str
    source: Literal["wiki", "agit", "gdocs", "slack", "confluence", "notion"]
    source_url: str
    owner_id: str
    owner_org: str
    status: Literal["draft", "published", "archived"] = "draft"
    security_level: Literal["public", "internal", "confidential"] = "internal"
    current_version_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentVersion(BaseModel):
    """Document version entity."""

    version_id: UUID
    doc_uuid: UUID
    version_no: int
    content_hash: str
    effective_from: datetime | None = None
    approved_by: str | None = None
    created_at: datetime | None = None


class Chunk(BaseModel):
    """Document chunk entity."""

    chunk_uuid: UUID
    doc_uuid: UUID
    version_id: UUID
    chunk_no: int
    section_path: str | None = None
    chunk_text: str | None = None
    milvus_id: str | None = None
    neo4j_node_id: str | None = None
    created_at: datetime | None = None


class AclEntry(BaseModel):
    """ACL entry entity."""

    id: UUID | None = None
    doc_uuid: UUID
    principal_type: Literal["user", "group", "org"]
    principal_id: str
    permission: Literal["read", "write", "admin"]
    created_at: datetime | None = None


class AuditLog(BaseModel):
    """Audit log entity."""

    log_id: UUID | None = None
    user_id: str
    action: Literal["search", "view", "create", "update", "delete"]
    doc_uuid: UUID | None = None
    query_text: str | None = None
    retrieved_docs: list[UUID] | None = None
    metadata: dict | None = None
    timestamp: datetime | None = None
```

**완료 기준:**
- [ ] Document 모델 정의
- [ ] DocumentVersion 모델 정의
- [ ] Chunk 모델 정의
- [ ] AclEntry 모델 정의
- [ ] AuditLog 모델 정의

---

### Step 2: Document CRUD 구현 (1.5h)

**작업 내용:**
1. create_document
2. get_document
3. update_document
4. delete_document

**src/repositories/postgres/repository.py:**
```python
"""PostgreSQL repository for data access."""
from typing import Any
from uuid import UUID

from src.domain.document import Document, DocumentVersion, Chunk, AclEntry, AuditLog
from src.infrastructure.database.postgres import PostgresClient


class PostgresRepository:
    """PostgreSQL data access layer."""

    def __init__(self, client: PostgresClient) -> None:
        """Initialize repository.

        Args:
            client: PostgreSQL client
        """
        self._client = client

    # ==================
    # Document CRUD
    # ==================

    async def create_document(self, doc: Document) -> Document:
        """Create a new document.

        Args:
            doc: Document to create

        Returns:
            Created document with generated UUID
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
        query = """
            SELECT * FROM documents WHERE doc_uuid = $1
        """
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
            updates: Fields to update

        Returns:
            Updated document or None if not found
        """
        if not updates:
            return await self.get_document(doc_uuid)

        # Build SET clause dynamically
        set_clauses = []
        values = []
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
        query = """
            DELETE FROM documents WHERE doc_uuid = $1
            RETURNING doc_uuid
        """
        row = await self._client.fetchrow(query, str(doc_uuid))
        return row is not None

    async def list_documents(
        self,
        limit: int = 100,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Document]:
        """List documents with pagination.

        Args:
            limit: Max results
            offset: Skip count
            status: Filter by status

        Returns:
            List of documents
        """
        if status:
            query = """
                SELECT * FROM documents
                WHERE status = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """
            rows = await self._client.fetch(query, status, limit, offset)
        else:
            query = """
                SELECT * FROM documents
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
            """
            rows = await self._client.fetch(query, limit, offset)

        return [Document(**dict(row)) for row in rows]
```

**완료 기준:**
- [ ] create_document 구현
- [ ] get_document 구현
- [ ] update_document 구현
- [ ] delete_document 구현
- [ ] list_documents 구현

---

### Step 3: Chunk 및 Version CRUD 구현 (1h)

**작업 내용:**
1. Version 생성
2. Chunk CRUD

**src/repositories/postgres/repository.py (계속):**
```python
    # ==================
    # Version CRUD
    # ==================

    async def create_version(self, version: DocumentVersion) -> DocumentVersion:
        """Create a new document version.

        Args:
            version: Version to create

        Returns:
            Created version
        """
        query = """
            INSERT INTO document_versions (
                doc_uuid, version_no, content_hash, effective_from, approved_by
            ) VALUES ($1, $2, $3, $4, $5)
            RETURNING version_id, created_at
        """
        row = await self._client.fetchrow(
            query,
            str(version.doc_uuid),
            version.version_no,
            version.content_hash,
            version.effective_from,
            version.approved_by,
        )

        return DocumentVersion(
            version_id=row["version_id"],
            doc_uuid=version.doc_uuid,
            version_no=version.version_no,
            content_hash=version.content_hash,
            effective_from=version.effective_from,
            approved_by=version.approved_by,
            created_at=row["created_at"],
        )

    async def get_latest_version(self, doc_uuid: UUID | str) -> DocumentVersion | None:
        """Get latest version of document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Latest version or None
        """
        query = """
            SELECT * FROM document_versions
            WHERE doc_uuid = $1
            ORDER BY version_no DESC
            LIMIT 1
        """
        row = await self._client.fetchrow(query, str(doc_uuid))
        return DocumentVersion(**dict(row)) if row else None

    # ==================
    # Chunk CRUD
    # ==================

    async def create_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """Create multiple chunks.

        Args:
            chunks: Chunks to create

        Returns:
            Created chunks with UUIDs
        """
        if not chunks:
            return []

        query = """
            INSERT INTO document_chunks (
                doc_uuid, version_id, chunk_no, section_path, chunk_text,
                milvus_id, neo4j_node_id
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
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
                    chunk.milvus_id,
                    chunk.neo4j_node_id,
                )
                results.append(Chunk(
                    chunk_uuid=row["chunk_uuid"],
                    doc_uuid=chunk.doc_uuid,
                    version_id=chunk.version_id,
                    chunk_no=chunk.chunk_no,
                    section_path=chunk.section_path,
                    chunk_text=chunk.chunk_text,
                    milvus_id=chunk.milvus_id,
                    neo4j_node_id=chunk.neo4j_node_id,
                    created_at=row["created_at"],
                ))

        return results

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

    async def delete_chunks_by_doc(self, doc_uuid: UUID | str) -> int:
        """Delete all chunks for a document.

        Args:
            doc_uuid: Document UUID

        Returns:
            Number of deleted chunks
        """
        query = """
            DELETE FROM document_chunks
            WHERE doc_uuid = $1
        """
        result = await self._client.execute(query, str(doc_uuid))
        # Extract count from "DELETE X"
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
            milvus_id: Milvus entity ID
            neo4j_node_id: Neo4j node ID
        """
        updates = []
        values = []
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
```

**완료 기준:**
- [ ] create_version 구현
- [ ] get_latest_version 구현
- [ ] create_chunks 구현
- [ ] get_chunks_by_doc 구현
- [ ] delete_chunks_by_doc 구현
- [ ] update_chunk_ids 구현

---

### Step 4: ACL 메서드 구현 (1h)

**작업 내용:**
1. ACL 생성
2. 접근 가능 문서 조회
3. 권한 확인

**src/repositories/postgres/repository.py (계속):**
```python
    # ==================
    # ACL Methods
    # ==================

    async def create_acl_entries(self, entries: list[AclEntry]) -> None:
        """Create ACL entries.

        Args:
            entries: ACL entries to create
        """
        if not entries:
            return

        query = """
            INSERT INTO acl_entries (doc_uuid, principal_type, principal_id, permission)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (doc_uuid, principal_type, principal_id)
            DO UPDATE SET permission = EXCLUDED.permission
        """

        async with self._client.transaction() as conn:
            for entry in entries:
                await conn.execute(
                    query,
                    str(entry.doc_uuid),
                    entry.principal_type,
                    entry.principal_id,
                    entry.permission,
                )

    async def get_accessible_doc_uuids(
        self,
        user_id: str,
        user_groups: list[str],
    ) -> list[str]:
        """Get document UUIDs accessible by user.

        Access is granted if:
        1. principal_type='user' AND principal_id=user_id
        2. principal_type='group' AND principal_id IN user_groups
        3. principal_type='org' AND principal_id='ALL'

        Args:
            user_id: User ID
            user_groups: User's group IDs

        Returns:
            List of accessible document UUIDs
        """
        query = """
            SELECT DISTINCT doc_uuid FROM acl_entries
            WHERE (
                (principal_type = 'user' AND principal_id = $1)
                OR (principal_type = 'group' AND principal_id = ANY($2))
                OR (principal_type = 'org' AND principal_id = 'ALL')
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
    ) -> bool:
        """Check if user has permission on document.

        Args:
            user_id: User ID
            user_groups: User's group IDs
            doc_uuid: Document UUID
            permission: Required permission level

        Returns:
            True if user has access
        """
        # Permission hierarchy: admin > write > read
        permissions = ["read"]
        if permission == "write":
            permissions = ["write", "admin"]
        elif permission == "admin":
            permissions = ["admin"]

        query = """
            SELECT 1 FROM acl_entries
            WHERE doc_uuid = $1
            AND permission = ANY($2)
            AND (
                (principal_type = 'user' AND principal_id = $3)
                OR (principal_type = 'group' AND principal_id = ANY($4))
                OR (principal_type = 'org' AND principal_id = 'ALL')
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
```

**완료 기준:**
- [ ] create_acl_entries 구현
- [ ] get_accessible_doc_uuids 구현
- [ ] check_access 구현
- [ ] delete_acl_entries 구현

---

### Step 5: Audit Log 및 테스트 (1.5h)

**작업 내용:**
1. Audit log 생성
2. 테스트 작성

**src/repositories/postgres/repository.py (계속):**
```python
    # ==================
    # Audit Log
    # ==================

    async def create_audit_log(self, log: AuditLog) -> None:
        """Create audit log entry.

        Args:
            log: Audit log entry
        """
        query = """
            INSERT INTO audit_logs (
                user_id, action, doc_uuid, query_text, retrieved_docs, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6)
        """

        # Convert UUID list to strings
        retrieved_docs = None
        if log.retrieved_docs:
            retrieved_docs = [str(uuid) for uuid in log.retrieved_docs]

        await self._client.execute(
            query,
            log.user_id,
            log.action,
            str(log.doc_uuid) if log.doc_uuid else None,
            log.query_text,
            retrieved_docs,
            log.metadata,
        )

    async def get_audit_logs(
        self,
        user_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Get audit logs with filters.

        Args:
            user_id: Filter by user
            action: Filter by action
            limit: Max results

        Returns:
            List of audit logs
        """
        conditions = []
        values = []
        param_idx = 1

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            values.append(user_id)
            param_idx += 1

        if action:
            conditions.append(f"action = ${param_idx}")
            values.append(action)
            param_idx += 1

        values.append(limit)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT * FROM audit_logs
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx}
        """

        rows = await self._client.fetch(query, *values)
        return [AuditLog(**dict(row)) for row in rows]
```

**tests/unit/test_repositories/test_postgres_repository.py:**
```python
"""Tests for PostgreSQL repository."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.repositories.postgres.repository import PostgresRepository
from src.domain.document import Document, Chunk, AclEntry, AuditLog


@pytest.fixture
def mock_client() -> MagicMock:
    """Create mock PostgreSQL client."""
    client = MagicMock()
    client.fetchrow = AsyncMock()
    client.fetch = AsyncMock()
    client.execute = AsyncMock()
    client.transaction = MagicMock()
    return client


@pytest.fixture
def repo(mock_client: MagicMock) -> PostgresRepository:
    """Create repository with mock client."""
    return PostgresRepository(mock_client)


class TestDocumentCRUD:
    """Tests for Document CRUD operations."""

    async def test_create_document(self, repo: PostgresRepository, mock_client: MagicMock) -> None:
        """Test document creation."""
        doc = Document(
            doc_uuid=uuid4(),
            title="Test Doc",
            source="wiki",
            source_url="http://example.com",
            owner_id="user1",
            owner_org="org1",
        )

        mock_client.fetchrow.return_value = {
            "doc_uuid": doc.doc_uuid,
            "created_at": None,
            "updated_at": None,
        }

        result = await repo.create_document(doc)

        assert result.title == doc.title
        mock_client.fetchrow.assert_called_once()

    async def test_get_document_found(self, repo: PostgresRepository, mock_client: MagicMock) -> None:
        """Test getting existing document."""
        doc_uuid = uuid4()
        mock_client.fetchrow.return_value = {
            "doc_uuid": doc_uuid,
            "title": "Test",
            "source": "wiki",
            "source_url": "http://test.com",
            "owner_id": "user1",
            "owner_org": "org1",
            "status": "draft",
            "security_level": "internal",
            "current_version_id": None,
            "created_at": None,
            "updated_at": None,
        }

        result = await repo.get_document(doc_uuid)

        assert result is not None
        assert result.doc_uuid == doc_uuid

    async def test_get_document_not_found(self, repo: PostgresRepository, mock_client: MagicMock) -> None:
        """Test getting non-existent document."""
        mock_client.fetchrow.return_value = None

        result = await repo.get_document(uuid4())

        assert result is None


class TestACL:
    """Tests for ACL operations."""

    async def test_get_accessible_doc_uuids(self, repo: PostgresRepository, mock_client: MagicMock) -> None:
        """Test getting accessible documents."""
        doc_uuid = uuid4()
        mock_client.fetch.return_value = [{"doc_uuid": doc_uuid}]

        result = await repo.get_accessible_doc_uuids("user1", ["group1", "group2"])

        assert len(result) == 1
        assert result[0] == str(doc_uuid)

    async def test_check_access_granted(self, repo: PostgresRepository, mock_client: MagicMock) -> None:
        """Test access check when granted."""
        mock_client.fetchrow.return_value = {"1": 1}

        result = await repo.check_access("user1", ["group1"], uuid4(), "read")

        assert result is True

    async def test_check_access_denied(self, repo: PostgresRepository, mock_client: MagicMock) -> None:
        """Test access check when denied."""
        mock_client.fetchrow.return_value = None

        result = await repo.check_access("user1", [], uuid4(), "read")

        assert result is False
```

**완료 기준:**
- [ ] create_audit_log 구현
- [ ] get_audit_logs 구현
- [ ] 테스트 작성 및 통과

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_document` | 문서 생성 | UUID 반환 |
| `test_get_document_found` | 문서 조회 (존재) | Document 반환 |
| `test_get_document_not_found` | 문서 조회 (미존재) | None |
| `test_get_accessible_doc_uuids` | 접근 가능 문서 | UUID 리스트 |
| `test_check_access_granted` | 권한 있음 | True |
| `test_check_access_denied` | 권한 없음 | False |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_document_lifecycle` | CRUD 전체 | 성공 |
| `test_acl_filtering` | ACL 필터링 | 정확한 결과 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| SQL Injection | High | Low | 파라미터화된 쿼리 사용 |
| 트랜잭션 누수 | High | Low | context manager 사용 |
| N+1 쿼리 | Medium | Medium | 배치 처리 구현 |

---

## 6. Definition of Done

- [ ] `src/repositories/postgres/repository.py` 구현
- [ ] `src/domain/document.py` 모델 정의
- [ ] Document CRUD 구현
- [ ] Chunk CRUD 구현
- [ ] ACL 메서드 구현
- [ ] Audit Log 메서드 구현
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Domain Models | 1h | - |
| Step 2: Document CRUD | 1.5h | - |
| Step 3: Chunk/Version CRUD | 1h | - |
| Step 4: ACL 메서드 | 1h | - |
| Step 5: Audit 및 테스트 | 1.5h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
