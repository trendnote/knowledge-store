# Task Execution Plan: 4.1.2 - Document Router 및 Schemas 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 4.1.2 |
| **Task Name** | Document Router 및 Schemas 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 4.1.1 |

### Description
Document API 엔드포인트와 Request/Response 스키마를 구현합니다.

### Acceptance Criteria
- [ ] `src/api/routers/documents.py` 생성
- [ ] `src/api/schemas/documents.py` 생성
- [ ] `POST /api/v1/documents` (Create)
- [ ] `GET /api/v1/documents/{doc_uuid}` (Read)
- [ ] `PUT /api/v1/documents/{doc_uuid}` (Update)
- [ ] `DELETE /api/v1/documents/{doc_uuid}` (Delete)
- [ ] 에러 핸들링

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.1 API Layer
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-1

### 2.2 API 설계
```
POST   /api/v1/documents          - Create document
GET    /api/v1/documents          - List documents
GET    /api/v1/documents/{uuid}   - Get document
PUT    /api/v1/documents/{uuid}   - Update document
DELETE /api/v1/documents/{uuid}   - Delete document
```

### 2.3 요청/응답 형식
```json
// POST /api/v1/documents
Request:
{
    "title": "문서 제목",
    "content": "문서 내용...",
    "source_url": "https://...",
    "metadata": {}
}

Response:
{
    "doc_uuid": "...",
    "title": "문서 제목",
    "owner_id": "user1",
    "status": "draft",
    "chunk_count": 5,
    "created_at": "2026-01-26T10:00:00Z"
}
```

---

## 3. Implementation Steps

### Step 1: Pydantic 스키마 정의 (1h)

**작업 내용:**
1. DocumentCreateSchema
2. DocumentUpdateSchema
3. DocumentResponseSchema

**src/api/schemas/documents.py:**
```python
"""Document API schemas."""
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class DocumentStatusEnum(str, Enum):
    """Document status enum."""

    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DocumentCreateSchema(BaseModel):
    """Schema for creating a document."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Document title",
        examples=["인공지능 기술 개요"],
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Document content to be chunked",
    )
    source_url: str | None = Field(
        None,
        description="Source URL of the document",
        examples=["https://example.com/doc.pdf"],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )
    chunk_size: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="Characters per chunk",
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=200,
        description="Overlap between chunks",
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate and clean title."""
        return v.strip()

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate content is not just whitespace."""
        if not v.strip():
            raise ValueError("Content cannot be empty or whitespace only")
        return v


class DocumentUpdateSchema(BaseModel):
    """Schema for updating a document."""

    title: str | None = Field(
        None,
        min_length=1,
        max_length=500,
        description="New title",
    )
    content: str | None = Field(
        None,
        min_length=1,
        description="New content (triggers re-chunking)",
    )
    status: DocumentStatusEnum | None = Field(
        None,
        description="New status",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Metadata to merge",
    )


class DocumentResponseSchema(BaseModel):
    """Document response schema."""

    doc_uuid: str = Field(..., description="Document UUID")
    title: str = Field(..., description="Document title")
    owner_id: str = Field(..., description="Owner user ID")
    status: DocumentStatusEnum = Field(..., description="Document status")
    chunk_count: int = Field(..., description="Number of chunks")
    source_url: str | None = Field(None, description="Source URL")
    created_at: datetime | None = Field(None, description="Creation time")
    updated_at: datetime | None = Field(None, description="Last update time")
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "doc_uuid": "550e8400-e29b-41d4-a716-446655440000",
                    "title": "인공지능 기술 개요",
                    "owner_id": "user123",
                    "status": "published",
                    "chunk_count": 5,
                    "source_url": "https://example.com/ai.pdf",
                    "created_at": "2026-01-26T10:00:00Z",
                    "updated_at": "2026-01-26T11:00:00Z",
                }
            ]
        }
    }


class DocumentListResponseSchema(BaseModel):
    """List of documents response."""

    documents: list[DocumentResponseSchema]
    total: int
    limit: int
    offset: int


class DocumentListQuerySchema(BaseModel):
    """Query parameters for listing documents."""

    status: DocumentStatusEnum | None = None
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
```

**완료 기준:**
- [ ] Create 스키마
- [ ] Update 스키마
- [ ] Response 스키마
- [ ] List 스키마

---

### Step 2: Document Router 구현 (1.5h)

**작업 내용:**
1. Router 정의
2. CRUD 엔드포인트
3. 인증 헤더 처리

**src/api/routers/documents.py:**
```python
"""Document API router."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from src.api.schemas.documents import (
    DocumentCreateSchema,
    DocumentListQuerySchema,
    DocumentListResponseSchema,
    DocumentResponseSchema,
    DocumentStatusEnum,
    DocumentUpdateSchema,
)
from src.domain.models.document import (
    DocumentCreateRequest,
    DocumentStatus,
    DocumentUpdateRequest,
)
from src.services.document_service import DocumentService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


# Dependency placeholder
async def get_document_service() -> DocumentService:
    """Get document service instance."""
    raise NotImplementedError("Document service not configured")


DocumentServiceDep = Annotated[DocumentService, Depends(get_document_service)]


def _convert_status(status: DocumentStatusEnum | None) -> DocumentStatus | None:
    """Convert API enum to domain enum."""
    if status is None:
        return None
    return DocumentStatus(status.value)


def _convert_to_response_status(status: DocumentStatus) -> DocumentStatusEnum:
    """Convert domain enum to API enum."""
    return DocumentStatusEnum(status.value)


@router.post(
    "",
    response_model=DocumentResponseSchema,
    status_code=status.HTTP_201_CREATED,
    summary="Create Document",
    description="Create a new document with automatic chunking and embedding.",
)
async def create_document(
    request: DocumentCreateSchema,
    service: DocumentServiceDep,
    x_user_id: Annotated[str, Header(description="User ID")],
) -> DocumentResponseSchema:
    """Create a new document."""
    logger.info(f"Create document request: {request.title} by {x_user_id}")

    try:
        domain_request = DocumentCreateRequest(
            title=request.title,
            content=request.content,
            owner_id=x_user_id,
            source_url=request.source_url,
            metadata=request.metadata,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
        )

        response = await service.create_document(domain_request)

        return DocumentResponseSchema(
            doc_uuid=response.doc_uuid,
            title=response.title,
            owner_id=response.owner_id,
            status=_convert_to_response_status(response.status),
            chunk_count=response.chunk_count,
            source_url=response.source_url,
            created_at=response.created_at,
            updated_at=response.updated_at,
            metadata=response.metadata,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Create document failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document",
        )


@router.get(
    "",
    response_model=DocumentListResponseSchema,
    summary="List Documents",
    description="List accessible documents with pagination.",
)
async def list_documents(
    service: DocumentServiceDep,
    x_user_id: Annotated[str, Header(description="User ID")],
    x_user_groups: Annotated[str | None, Header(description="Comma-separated groups")] = None,
    status_filter: Annotated[DocumentStatusEnum | None, Query(alias="status")] = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DocumentListResponseSchema:
    """List accessible documents."""
    groups = x_user_groups.split(",") if x_user_groups else []

    docs = await service.list_documents(
        user_id=x_user_id,
        user_groups=groups,
        status=_convert_status(status_filter),
        limit=limit,
        offset=offset,
    )

    return DocumentListResponseSchema(
        documents=[
            DocumentResponseSchema(
                doc_uuid=d.doc_uuid,
                title=d.title,
                owner_id=d.owner_id,
                status=_convert_to_response_status(d.status),
                chunk_count=d.chunk_count,
                source_url=d.source_url,
                created_at=d.created_at,
                updated_at=d.updated_at,
                metadata=d.metadata,
            )
            for d in docs
        ],
        total=len(docs),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{doc_uuid}",
    response_model=DocumentResponseSchema,
    summary="Get Document",
    description="Get a document by UUID.",
)
async def get_document(
    doc_uuid: str,
    service: DocumentServiceDep,
    x_user_id: Annotated[str, Header(description="User ID")],
    x_user_groups: Annotated[str | None, Header(description="Comma-separated groups")] = None,
) -> DocumentResponseSchema:
    """Get a document by UUID."""
    groups = x_user_groups.split(",") if x_user_groups else []

    try:
        response = await service.get_document(
            doc_uuid=doc_uuid,
            user_id=x_user_id,
            user_groups=groups,
        )

        if not response:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document not found: {doc_uuid}",
            )

        return DocumentResponseSchema(
            doc_uuid=response.doc_uuid,
            title=response.title,
            owner_id=response.owner_id,
            status=_convert_to_response_status(response.status),
            chunk_count=response.chunk_count,
            source_url=response.source_url,
            created_at=response.created_at,
            updated_at=response.updated_at,
            metadata=response.metadata,
        )

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )


@router.put(
    "/{doc_uuid}",
    response_model=DocumentResponseSchema,
    summary="Update Document",
    description="Update a document. Content changes trigger re-chunking.",
)
async def update_document(
    doc_uuid: str,
    request: DocumentUpdateSchema,
    service: DocumentServiceDep,
    x_user_id: Annotated[str, Header(description="User ID")],
    x_user_groups: Annotated[str | None, Header(description="Comma-separated groups")] = None,
) -> DocumentResponseSchema:
    """Update a document."""
    groups = x_user_groups.split(",") if x_user_groups else []

    try:
        domain_request = DocumentUpdateRequest(
            title=request.title,
            content=request.content,
            status=_convert_status(request.status),
            metadata=request.metadata,
        )

        response = await service.update_document(
            doc_uuid=doc_uuid,
            request=domain_request,
            user_id=x_user_id,
            user_groups=groups,
        )

        return DocumentResponseSchema(
            doc_uuid=response.doc_uuid,
            title=response.title,
            owner_id=response.owner_id,
            status=_convert_to_response_status(response.status),
            chunk_count=response.chunk_count,
            source_url=response.source_url,
            created_at=response.created_at,
            updated_at=response.updated_at,
            metadata=response.metadata,
        )

    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete(
    "/{doc_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Document",
    description="Delete a document and all associated data.",
)
async def delete_document(
    doc_uuid: str,
    service: DocumentServiceDep,
    x_user_id: Annotated[str, Header(description="User ID")],
    x_user_groups: Annotated[str | None, Header(description="Comma-separated groups")] = None,
) -> None:
    """Delete a document."""
    groups = x_user_groups.split(",") if x_user_groups else []

    try:
        await service.delete_document(
            doc_uuid=doc_uuid,
            user_id=x_user_id,
            user_groups=groups,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
```

**완료 기준:**
- [ ] POST /documents
- [ ] GET /documents
- [ ] GET /documents/{uuid}
- [ ] PUT /documents/{uuid}
- [ ] DELETE /documents/{uuid}

---

### Step 3: 인증 및 의존성 설정 (1h)

**작업 내용:**
1. 인증 헤더 처리
2. 의존성 주입
3. Router 등록

**src/api/dependencies.py (업데이트):**
```python
"""API dependencies."""
from src.services.document_service import DocumentService
from src.services.search_service import SearchService

# Service instances
_document_service: DocumentService | None = None
_search_service: SearchService | None = None


def set_document_service(service: DocumentService) -> None:
    """Set document service instance."""
    global _document_service
    _document_service = service


async def get_document_service() -> DocumentService:
    """Get document service instance."""
    if _document_service is None:
        raise RuntimeError("Document service not initialized")
    return _document_service


def set_search_service(service: SearchService) -> None:
    """Set search service instance."""
    global _search_service
    _search_service = service


async def get_search_service() -> SearchService:
    """Get search service instance."""
    if _search_service is None:
        raise RuntimeError("Search service not initialized")
    return _search_service
```

**src/api/routers/__init__.py (업데이트):**
```python
"""API routers."""
from src.api.routers.documents import router as documents_router
from src.api.routers.search import router as search_router

__all__ = ["documents_router", "search_router"]
```

**완료 기준:**
- [ ] 인증 헤더 처리
- [ ] 의존성 설정
- [ ] Router 등록

---

### Step 4: 테스트 작성 (0.5h)

**작업 내용:**
1. 스키마 테스트
2. 엔드포인트 테스트

**tests/unit/test_api/test_documents_router.py:**
```python
"""Tests for documents router."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.documents import router
from src.api.schemas.documents import DocumentCreateSchema
from src.domain.models.document import DocumentResponse, DocumentStatus


@pytest.fixture
def mock_document_service() -> MagicMock:
    """Create mock document service."""
    mock = MagicMock()
    mock.create_document = AsyncMock(
        return_value=DocumentResponse(
            doc_uuid="doc-123",
            title="Test Doc",
            owner_id="user1",
            status=DocumentStatus.DRAFT,
            chunk_count=3,
            created_at=None,
            updated_at=None,
        )
    )
    mock.get_document = AsyncMock(return_value=None)
    mock.delete_document = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def client(mock_document_service: MagicMock) -> TestClient:
    """Create test client."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    async def get_mock_service():
        return mock_document_service

    from src.api.routers import documents
    app.dependency_overrides[documents.get_document_service] = get_mock_service

    return TestClient(app)


class TestDocumentSchemas:
    """Tests for document schemas."""

    def test_create_schema_valid(self) -> None:
        """Test valid create schema."""
        schema = DocumentCreateSchema(
            title="Test",
            content="Content here",
        )
        assert schema.title == "Test"

    def test_create_schema_empty_content(self) -> None:
        """Test empty content validation."""
        with pytest.raises(ValueError):
            DocumentCreateSchema(title="Test", content="   ")


class TestDocumentEndpoints:
    """Tests for document endpoints."""

    def test_create_document(
        self,
        client: TestClient,
    ) -> None:
        """Test create document endpoint."""
        response = client.post(
            "/api/v1/documents",
            json={"title": "Test", "content": "Content"},
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 201
        assert response.json()["doc_uuid"] == "doc-123"

    def test_create_document_missing_user(
        self,
        client: TestClient,
    ) -> None:
        """Test create without user header."""
        response = client.post(
            "/api/v1/documents",
            json={"title": "Test", "content": "Content"},
        )

        assert response.status_code == 422

    def test_delete_document(
        self,
        client: TestClient,
    ) -> None:
        """Test delete document endpoint."""
        response = client.delete(
            "/api/v1/documents/doc-123",
            headers={"x-user-id": "user1"},
        )

        assert response.status_code == 204
```

**완료 기준:**
- [ ] 스키마 검증 테스트
- [ ] CRUD 엔드포인트 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_schema_valid` | 유효한 스키마 | 성공 |
| `test_create_document` | 문서 생성 | 201 |
| `test_delete_document` | 문서 삭제 | 204 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_crud_flow` | 전체 CRUD | 정상 동작 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 인증 누락 | High | Low | 헤더 필수 검증 |
| 대용량 content | Medium | Medium | 크기 제한 |

---

## 6. Definition of Done

- [ ] `src/api/schemas/documents.py` 생성
- [ ] `src/api/routers/documents.py` 생성
- [ ] POST/GET/PUT/DELETE 엔드포인트
- [ ] 에러 핸들링
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Pydantic 스키마 | 1h | - |
| Step 2: Document Router | 1.5h | - |
| Step 3: 의존성 설정 | 1h | - |
| Step 4: 테스트 | 0.5h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
