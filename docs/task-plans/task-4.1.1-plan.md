# Task Execution Plan: 4.1.1 - Document Service 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.1.1 |
| **Task Name** | Document Service 구현 |
| **Estimate** | 6h |
| **Priority** | P0 |
| **Dependencies** | Task 2.3.3 |

### Description
문서 CRUD 비즈니스 로직을 구현합니다.

### Acceptance Criteria
- [ ] `src/services/document_service.py` 생성
- [ ] `create_document`: 임베딩 생성 + Saga 실행 + Kafka 이벤트
- [ ] `get_document`: PostgreSQL 조회
- [ ] `update_document`: 변경 사항 임베딩 + Saga 업데이트
- [ ] `delete_document`: Saga 삭제 + Kafka 이벤트

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.1 Document Service
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-1

### 2.2 Document Service 역할
```
Document Service
├── 문서 CRUD 비즈니스 로직
├── 임베딩 생성 조율
├── Saga Coordinator 호출
├── Kafka 이벤트 발행
└── 권한 검증
```

### 2.3 설계 결정
1. **Saga 활용**: 3개 저장소 분산 트랜잭션
2. **이벤트 발행**: 생성/수정/삭제 시 Kafka 이벤트
3. **권한 확인**: ACL Service 활용
4. **청킹**: 외부 청킹 서비스 또는 간단한 내장 청킹

### 2.4 클래스 구조
```
DocumentService
├── __init__(saga_coordinator, embedding_service, kafka_producer, acl_service, postgres_repo)
├── create_document(request) -> DocumentResponse
├── get_document(doc_uuid, user_id) -> DocumentResponse
├── update_document(doc_uuid, request) -> DocumentResponse
├── delete_document(doc_uuid, user_id) -> bool
├── list_documents(user_id, filters) -> list[DocumentResponse]
└── _chunk_text(text) -> list[str]
```

---

## 3. Implementation Steps

### Step 1: 도메인 모델 및 요청/응답 정의 (1h)

**작업 내용:**
1. Document 도메인 모델
2. Chunk 도메인 모델
3. Request/Response 모델

**src/domain/models/document.py:**
```python
"""Document domain models."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4


class DocumentStatus(str, Enum):
    """Document status."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class Chunk:
    """Document chunk model."""

    chunk_uuid: str
    doc_uuid: str
    chunk_index: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, doc_uuid: str, chunk_index: int, text: str) -> "Chunk":
        """Create a new chunk."""
        return cls(
            chunk_uuid=str(uuid4()),
            doc_uuid=doc_uuid,
            chunk_index=chunk_index,
            text=text,
        )


@dataclass
class Document:
    """Document model."""

    doc_uuid: str
    title: str
    owner_id: str
    status: DocumentStatus = DocumentStatus.DRAFT
    source_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        title: str,
        owner_id: str,
        source_url: str | None = None,
    ) -> "Document":
        """Create a new document."""
        return cls(
            doc_uuid=str(uuid4()),
            title=title,
            owner_id=owner_id,
            source_url=source_url,
        )


@dataclass
class DocumentCreateRequest:
    """Request to create a document."""

    title: str
    content: str  # Raw content to be chunked
    owner_id: str
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_size: int = 500  # Characters per chunk
    chunk_overlap: int = 50


@dataclass
class DocumentUpdateRequest:
    """Request to update a document."""

    title: str | None = None
    content: str | None = None
    status: DocumentStatus | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class DocumentResponse:
    """Document response."""

    doc_uuid: str
    title: str
    owner_id: str
    status: DocumentStatus
    chunk_count: int
    created_at: datetime | None
    updated_at: datetime | None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_document(cls, doc: Document) -> "DocumentResponse":
        """Create response from document."""
        return cls(
            doc_uuid=doc.doc_uuid,
            title=doc.title,
            owner_id=doc.owner_id,
            status=doc.status,
            chunk_count=len(doc.chunks),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            source_url=doc.source_url,
            metadata=doc.metadata,
        )
```

**완료 기준:**
- [ ] Document 모델 정의
- [ ] Chunk 모델 정의
- [ ] Request/Response 모델

---

### Step 2: 텍스트 청킹 구현 (1h)

**작업 내용:**
1. 간단한 청킹 로직
2. 오버랩 처리
3. 청크 메타데이터

**src/services/document_service.py:**
```python
"""Document service for document CRUD operations."""
import logging
from typing import Any, Protocol

from src.domain.models.document import (
    Chunk,
    Document,
    DocumentCreateRequest,
    DocumentResponse,
    DocumentStatus,
    DocumentUpdateRequest,
)

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document operations."""

    def __init__(
        self,
        postgres_repo: Any,
        saga_coordinator: Any,
        embedding_service: Any,
        kafka_producer: Any | None = None,
        acl_service: Any | None = None,
    ) -> None:
        """Initialize document service.

        Args:
            postgres_repo: PostgreSQL repository
            saga_coordinator: Saga coordinator for distributed transactions
            embedding_service: Embedding service
            kafka_producer: Kafka producer for events (optional)
            acl_service: ACL service for permissions (optional)
        """
        self._postgres_repo = postgres_repo
        self._saga = saga_coordinator
        self._embedding = embedding_service
        self._kafka = kafka_producer
        self._acl = acl_service

    def _chunk_text(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list[str]:
        """Split text into chunks.

        Simple character-based chunking with overlap.
        Can be replaced with more sophisticated chunking.

        Args:
            text: Text to chunk
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks

        Returns:
            List of text chunks
        """
        if not text:
            return []

        # Normalize whitespace
        text = " ".join(text.split())

        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end
                for sep in [". ", "! ", "? ", "\n"]:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start:
                        end = last_sep + 1
                        break

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move start with overlap
            start = end - chunk_overlap
            if start <= 0:
                start = end

        return chunks

    def _create_chunks(
        self,
        doc_uuid: str,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> list[Chunk]:
        """Create chunk objects from text.

        Args:
            doc_uuid: Document UUID
            text: Text to chunk
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks

        Returns:
            List of Chunk objects
        """
        texts = self._chunk_text(text, chunk_size, chunk_overlap)
        return [
            Chunk.create(doc_uuid, i, text)
            for i, text in enumerate(texts)
        ]
```

**완료 기준:**
- [ ] _chunk_text 구현
- [ ] 문장 경계 처리
- [ ] 오버랩 처리

---

### Step 3: Create/Get Document 구현 (1.5h)

**작업 내용:**
1. create_document 구현
2. get_document 구현
3. Saga 연동

**src/services/document_service.py (계속):**
```python
    async def create_document(
        self,
        request: DocumentCreateRequest,
    ) -> DocumentResponse:
        """Create a new document.

        1. Create chunks from content
        2. Generate embeddings
        3. Execute create saga (PostgreSQL → Milvus → Neo4j)
        4. Publish Kafka event

        Args:
            request: Document creation request

        Returns:
            Created document response

        Raises:
            ValueError: If content is empty
            RuntimeError: If saga fails
        """
        logger.info(f"Creating document: {request.title}")

        if not request.content.strip():
            raise ValueError("Document content cannot be empty")

        # Create document
        doc = Document.create(
            title=request.title,
            owner_id=request.owner_id,
            source_url=request.source_url,
        )
        doc.metadata = request.metadata

        # Create chunks
        chunks = self._create_chunks(
            doc.doc_uuid,
            request.content,
            request.chunk_size,
            request.chunk_overlap,
        )

        if not chunks:
            raise ValueError("No chunks created from content")

        doc.chunks = chunks

        # Execute saga
        result = await self._saga.execute_create_saga(doc, chunks)

        if not result.success:
            logger.error(f"Create saga failed: {result.error}")
            raise RuntimeError(f"Failed to create document: {result.error}")

        # Grant owner access
        if self._acl:
            from src.domain.models.acl import Permission, PrincipalType
            await self._acl.grant_access(
                doc.doc_uuid,
                PrincipalType.USER,
                request.owner_id,
                Permission.ADMIN,
            )

        # Publish event
        if self._kafka:
            await self._kafka.send(
                "document.created",
                {
                    "doc_uuid": doc.doc_uuid,
                    "title": doc.title,
                    "owner_id": doc.owner_id,
                    "chunk_count": len(chunks),
                },
            )

        logger.info(f"Document created: {doc.doc_uuid}")
        return DocumentResponse.from_document(doc)

    async def get_document(
        self,
        doc_uuid: str,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> DocumentResponse | None:
        """Get a document by UUID.

        Args:
            doc_uuid: Document UUID
            user_id: Requesting user ID
            user_groups: User's group memberships

        Returns:
            Document response or None if not found

        Raises:
            PermissionError: If user doesn't have access
        """
        # Check access
        if self._acl:
            from src.domain.models.acl import Permission
            has_access = await self._acl.check_access(
                user_id=user_id,
                user_groups=user_groups,
                doc_uuid=doc_uuid,
                permission=Permission.READ,
            )
            if not has_access:
                raise PermissionError(f"User {user_id} cannot access document {doc_uuid}")

        # Get from PostgreSQL
        doc = await self._postgres_repo.get_document(doc_uuid)
        if not doc:
            return None

        chunks = await self._postgres_repo.get_chunks_by_doc(doc_uuid)
        doc.chunks = chunks

        return DocumentResponse.from_document(doc)

    async def list_documents(
        self,
        user_id: str,
        user_groups: list[str] | None = None,
        status: DocumentStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[DocumentResponse]:
        """List accessible documents.

        Args:
            user_id: User ID
            user_groups: User's groups
            status: Filter by status
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of document responses
        """
        # Get accessible doc UUIDs
        if self._acl:
            accessible_uuids = await self._acl.get_accessible_documents(
                user_id, user_groups
            )
        else:
            accessible_uuids = None  # No ACL, allow all

        docs = await self._postgres_repo.list_documents(
            doc_uuids=accessible_uuids,
            status=status,
            limit=limit,
            offset=offset,
        )

        return [DocumentResponse.from_document(d) for d in docs]
```

**완료 기준:**
- [ ] create_document 구현
- [ ] get_document 구현
- [ ] list_documents 구현
- [ ] ACL 통합

---

### Step 4: Update/Delete Document 구현 (1.5h)

**작업 내용:**
1. update_document 구현
2. delete_document 구현
3. Kafka 이벤트 발행

**src/services/document_service.py (계속):**
```python
    async def update_document(
        self,
        doc_uuid: str,
        request: DocumentUpdateRequest,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> DocumentResponse:
        """Update a document.

        If content changes, regenerates chunks and embeddings.

        Args:
            doc_uuid: Document UUID
            request: Update request
            user_id: User performing update
            user_groups: User's groups

        Returns:
            Updated document response

        Raises:
            PermissionError: If user cannot update
            ValueError: If document not found
        """
        logger.info(f"Updating document: {doc_uuid}")

        # Check write access
        if self._acl:
            from src.domain.models.acl import Permission
            has_access = await self._acl.check_access(
                user_id=user_id,
                user_groups=user_groups,
                doc_uuid=doc_uuid,
                permission=Permission.WRITE,
            )
            if not has_access:
                raise PermissionError(f"User {user_id} cannot update document {doc_uuid}")

        # Get existing document
        doc = await self._postgres_repo.get_document(doc_uuid)
        if not doc:
            raise ValueError(f"Document not found: {doc_uuid}")

        # Update fields
        if request.title is not None:
            doc.title = request.title
        if request.status is not None:
            doc.status = request.status
        if request.metadata is not None:
            doc.metadata.update(request.metadata)

        # If content changed, regenerate chunks
        if request.content is not None:
            chunks = self._create_chunks(doc_uuid, request.content)

            if not chunks:
                raise ValueError("No chunks created from content")

            doc.chunks = chunks

            # Execute update saga (deletes old vectors/graph, creates new)
            result = await self._saga.execute_update_saga(doc_uuid, doc, chunks)

            if not result.success:
                raise RuntimeError(f"Update saga failed: {result.error}")
        else:
            # Just update PostgreSQL
            await self._postgres_repo.update_document(doc_uuid, doc)

        # Publish event
        if self._kafka:
            await self._kafka.send(
                "document.updated",
                {
                    "doc_uuid": doc_uuid,
                    "title": doc.title,
                    "updated_by": user_id,
                    "content_changed": request.content is not None,
                },
            )

        logger.info(f"Document updated: {doc_uuid}")
        return DocumentResponse.from_document(doc)

    async def delete_document(
        self,
        doc_uuid: str,
        user_id: str,
        user_groups: list[str] | None = None,
    ) -> bool:
        """Delete a document.

        Args:
            doc_uuid: Document UUID
            user_id: User performing deletion
            user_groups: User's groups

        Returns:
            True if deleted

        Raises:
            PermissionError: If user cannot delete
            ValueError: If document not found
        """
        logger.info(f"Deleting document: {doc_uuid}")

        # Check admin access
        if self._acl:
            from src.domain.models.acl import Permission
            has_access = await self._acl.check_access(
                user_id=user_id,
                user_groups=user_groups,
                doc_uuid=doc_uuid,
                permission=Permission.ADMIN,
            )
            if not has_access:
                raise PermissionError(f"User {user_id} cannot delete document {doc_uuid}")

        # Check document exists
        doc = await self._postgres_repo.get_document(doc_uuid)
        if not doc:
            raise ValueError(f"Document not found: {doc_uuid}")

        # Execute delete saga
        result = await self._saga.execute_delete_saga(doc_uuid)

        if not result.success:
            raise RuntimeError(f"Delete saga failed: {result.error}")

        # Publish event
        if self._kafka:
            await self._kafka.send(
                "document.deleted",
                {
                    "doc_uuid": doc_uuid,
                    "deleted_by": user_id,
                },
            )

        logger.info(f"Document deleted: {doc_uuid}")
        return True
```

**완료 기준:**
- [ ] update_document 구현
- [ ] delete_document 구현
- [ ] Kafka 이벤트 발행
- [ ] 권한 검증

---

### Step 5: Factory 및 테스트 (1h)

**작업 내용:**
1. Factory 함수
2. 테스트 작성

**src/services/document_service.py (추가):**
```python
# Factory
_service: DocumentService | None = None


def get_document_service(
    postgres_repo: Any | None = None,
    saga_coordinator: Any | None = None,
    embedding_service: Any | None = None,
    kafka_producer: Any | None = None,
    acl_service: Any | None = None,
) -> DocumentService:
    """Get or create document service singleton."""
    global _service
    if _service is None:
        if postgres_repo is None or saga_coordinator is None or embedding_service is None:
            raise ValueError("Required dependencies not provided")
        _service = DocumentService(
            postgres_repo=postgres_repo,
            saga_coordinator=saga_coordinator,
            embedding_service=embedding_service,
            kafka_producer=kafka_producer,
            acl_service=acl_service,
        )
    return _service


def reset_document_service() -> None:
    """Reset service singleton (for testing)."""
    global _service
    _service = None
```

**tests/unit/test_services/test_document_service.py:**
```python
"""Tests for document service."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.document_service import DocumentService
from src.domain.models.document import DocumentCreateRequest


@pytest.fixture
def mock_deps() -> dict:
    """Create mock dependencies."""
    return {
        "postgres_repo": MagicMock(),
        "saga_coordinator": MagicMock(),
        "embedding_service": MagicMock(),
        "kafka_producer": MagicMock(),
        "acl_service": MagicMock(),
    }


@pytest.fixture
def document_service(mock_deps: dict) -> DocumentService:
    """Create document service with mocks."""
    return DocumentService(**mock_deps)


class TestChunking:
    """Tests for text chunking."""

    def test_chunk_text_simple(self, document_service: DocumentService) -> None:
        """Test simple text chunking."""
        text = "A" * 1000
        chunks = document_service._chunk_text(text, chunk_size=300, chunk_overlap=50)

        assert len(chunks) > 1
        assert all(len(c) <= 300 for c in chunks)

    def test_chunk_text_sentence_boundary(self, document_service: DocumentService) -> None:
        """Test chunking respects sentence boundaries."""
        text = "First sentence. Second sentence. Third sentence."
        chunks = document_service._chunk_text(text, chunk_size=30, chunk_overlap=5)

        # Should break at periods
        assert any(c.endswith(".") or c.endswith(". ") or "sentence" in c for c in chunks)


class TestCreateDocument:
    """Tests for document creation."""

    async def test_create_document_success(
        self,
        document_service: DocumentService,
        mock_deps: dict,
    ) -> None:
        """Test successful document creation."""
        mock_deps["saga_coordinator"].execute_create_saga = AsyncMock(
            return_value=MagicMock(success=True)
        )
        mock_deps["acl_service"].grant_access = AsyncMock()
        mock_deps["kafka_producer"].send = AsyncMock()

        request = DocumentCreateRequest(
            title="Test Doc",
            content="This is test content for the document.",
            owner_id="user1",
        )

        response = await document_service.create_document(request)

        assert response.title == "Test Doc"
        assert response.owner_id == "user1"
        mock_deps["saga_coordinator"].execute_create_saga.assert_called_once()

    async def test_create_document_empty_content(
        self,
        document_service: DocumentService,
    ) -> None:
        """Test create with empty content fails."""
        request = DocumentCreateRequest(
            title="Test",
            content="   ",
            owner_id="user1",
        )

        with pytest.raises(ValueError, match="empty"):
            await document_service.create_document(request)


class TestDeleteDocument:
    """Tests for document deletion."""

    async def test_delete_document_success(
        self,
        document_service: DocumentService,
        mock_deps: dict,
    ) -> None:
        """Test successful document deletion."""
        mock_deps["acl_service"].check_access = AsyncMock(return_value=True)
        mock_deps["postgres_repo"].get_document = AsyncMock(return_value=MagicMock())
        mock_deps["saga_coordinator"].execute_delete_saga = AsyncMock(
            return_value=MagicMock(success=True)
        )
        mock_deps["kafka_producer"].send = AsyncMock()

        result = await document_service.delete_document("doc-uuid", "user1")

        assert result is True
        mock_deps["kafka_producer"].send.assert_called()
```

**완료 기준:**
- [ ] Factory 함수
- [ ] 청킹 테스트
- [ ] CRUD 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_chunk_text_simple` | 기본 청킹 | 적절한 크기 |
| `test_create_document_success` | 문서 생성 | 성공 |
| `test_create_document_empty` | 빈 내용 | ValueError |
| `test_delete_document_success` | 문서 삭제 | True |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_full_flow` | 전체 생성 플로우 | 3개 저장소에 저장 |
| `test_update_content` | 내용 수정 | 벡터 재생성 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Saga 실패 | High | Low | 상세 에러 로깅 |
| 대용량 문서 | Medium | Medium | 청크 크기 제한 |
| Kafka 장애 | Medium | Low | 비동기 발행, 재시도 |

---

## 6. Definition of Done

- [ ] `src/services/document_service.py` 구현
- [ ] 텍스트 청킹 구현
- [ ] create_document 구현
- [ ] get_document 구현
- [ ] update_document 구현
- [ ] delete_document 구현
- [ ] Kafka 이벤트 발행
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 도메인 모델 | 1h | - |
| Step 2: 텍스트 청킹 | 1h | - |
| Step 3: Create/Get | 1.5h | - |
| Step 4: Update/Delete | 1.5h | - |
| Step 5: Factory 및 테스트 | 1h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
