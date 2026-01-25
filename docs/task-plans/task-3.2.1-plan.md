# Task Execution Plan: 3.2.1 - Search Router 및 Schemas 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 3.2.1 |
| **Task Name** | Search Router 및 Schemas 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 3.1.4 |

### Description
Search API 엔드포인트와 Request/Response 스키마를 구현합니다.

### Acceptance Criteria
- [ ] `src/api/routers/search.py` 생성
- [ ] `src/api/schemas/search.py` 생성
- [ ] `POST /api/v1/search` 엔드포인트
- [ ] SearchRequest 스키마 (query, user_id, user_groups, top_k, search_types)
- [ ] SearchResponse 스키마 (results, total, search_time_ms)
- [ ] 에러 핸들링 (400, 403, 500)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.1 API Layer
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-3

### 2.2 API 설계
```
POST /api/v1/search

Request:
{
    "query": "검색어",
    "user_id": "user123",
    "user_groups": ["group1", "group2"],
    "top_k": 10,
    "search_types": ["dense", "sparse", "graph"],
    "min_score": 0.0
}

Response:
{
    "results": [
        {
            "chunk_uuid": "...",
            "doc_uuid": "...",
            "score": 0.95,
            "search_type": "hybrid",
            "text_preview": "...",
            "title": "..."
        }
    ],
    "total": 10,
    "search_time_ms": 45.2,
    "search_types_used": ["dense", "sparse", "graph"]
}
```

### 2.3 설계 결정
1. **POST 메서드**: 복잡한 검색 파라미터 전달
2. **Pydantic 스키마**: 검증 및 문서화
3. **의존성 주입**: SearchService 주입
4. **에러 핸들링**: HTTPException 활용

---

## 3. Implementation Steps

### Step 1: Pydantic 스키마 정의 (1h)

**작업 내용:**
1. SearchRequestSchema 정의
2. SearchResultSchema 정의
3. SearchResponseSchema 정의

**src/api/schemas/search.py:**
```python
"""Search API schemas."""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SearchTypeEnum(str, Enum):
    """Search type enum for API."""

    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    HYBRID = "hybrid"


class SearchRequestSchema(BaseModel):
    """Search request schema."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Search query text",
        examples=["인공지능 기술 문서"],
    )
    user_id: str = Field(
        ...,
        min_length=1,
        description="User identifier for ACL",
        examples=["user123"],
    )
    user_groups: list[str] = Field(
        default_factory=list,
        description="User's group memberships",
        examples=[["engineering", "ml-team"]],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of results",
    )
    search_types: list[SearchTypeEnum] | None = Field(
        default=None,
        description="Types of search to perform (default: all)",
        examples=[["dense", "sparse"]],
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum score threshold",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and clean query."""
        return v.strip()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "query": "인공지능 기술 문서",
                    "user_id": "user123",
                    "user_groups": ["engineering"],
                    "top_k": 10,
                    "search_types": ["dense", "sparse"],
                    "min_score": 0.5,
                }
            ]
        }
    }


class SearchResultSchema(BaseModel):
    """Single search result schema."""

    chunk_uuid: str = Field(..., description="Chunk UUID")
    doc_uuid: str = Field(..., description="Document UUID")
    score: float = Field(..., description="Relevance score")
    search_type: SearchTypeEnum = Field(..., description="Type of search that found this")
    text_preview: str | None = Field(None, description="Text preview of chunk")
    title: str | None = Field(None, description="Document title")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata",
    )


class SearchResponseSchema(BaseModel):
    """Search response schema."""

    results: list[SearchResultSchema] = Field(
        ...,
        description="Search results",
    )
    total: int = Field(..., description="Total number of results")
    search_time_ms: float = Field(..., description="Search time in milliseconds")
    search_types_used: list[SearchTypeEnum] = Field(
        default_factory=list,
        description="Search types that were used",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "results": [
                        {
                            "chunk_uuid": "chunk-123",
                            "doc_uuid": "doc-456",
                            "score": 0.95,
                            "search_type": "hybrid",
                            "text_preview": "AI 기술에 관한 문서...",
                            "title": "인공지능 개요",
                        }
                    ],
                    "total": 1,
                    "search_time_ms": 45.2,
                    "search_types_used": ["dense", "sparse"],
                }
            ]
        }
    }


class SearchErrorSchema(BaseModel):
    """Search error response schema."""

    detail: str = Field(..., description="Error message")
    error_code: str | None = Field(None, description="Error code")
```

**완료 기준:**
- [ ] SearchRequestSchema 정의
- [ ] SearchResultSchema 정의
- [ ] SearchResponseSchema 정의
- [ ] 필드 검증 추가

---

### Step 2: Search Router 구현 (1.5h)

**작업 내용:**
1. Router 정의
2. 의존성 주입 설정
3. POST /search 엔드포인트

**src/api/routers/search.py:**
```python
"""Search API router."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from src.api.schemas.search import (
    SearchRequestSchema,
    SearchResponseSchema,
    SearchTypeEnum,
)
from src.domain.models.search import SearchRequest, SearchType
from src.services.search_service import SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


# Dependency injection placeholder
async def get_search_service() -> SearchService:
    """Get search service instance.

    This will be overridden in main.py with actual implementation.
    """
    raise NotImplementedError("Search service not configured")


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


def _convert_search_types(
    types: list[SearchTypeEnum] | None,
) -> list[SearchType] | None:
    """Convert API enum to domain enum."""
    if types is None:
        return None

    mapping = {
        SearchTypeEnum.DENSE: SearchType.DENSE,
        SearchTypeEnum.SPARSE: SearchType.SPARSE,
        SearchTypeEnum.GRAPH: SearchType.GRAPH,
        SearchTypeEnum.HYBRID: SearchType.HYBRID,
    }
    return [mapping[t] for t in types]


def _convert_to_response_type(t: SearchType) -> SearchTypeEnum:
    """Convert domain enum to API enum."""
    mapping = {
        SearchType.DENSE: SearchTypeEnum.DENSE,
        SearchType.SPARSE: SearchTypeEnum.SPARSE,
        SearchType.GRAPH: SearchTypeEnum.GRAPH,
        SearchType.HYBRID: SearchTypeEnum.HYBRID,
    }
    return mapping[t]


@router.post(
    "",
    response_model=SearchResponseSchema,
    summary="Hybrid Search",
    description="Execute hybrid search combining dense, sparse, and graph search.",
    responses={
        200: {"description": "Search results"},
        400: {"description": "Invalid request"},
        403: {"description": "Access denied"},
        500: {"description": "Internal server error"},
    },
)
async def search(
    request: SearchRequestSchema,
    search_service: SearchServiceDep,
) -> SearchResponseSchema:
    """Execute hybrid search.

    Combines dense (semantic), sparse (keyword), and graph (relationship)
    search for comprehensive results.
    """
    logger.info(f"Search request: query='{request.query}' user={request.user_id}")

    try:
        # Convert to domain model
        domain_request = SearchRequest(
            query=request.query,
            user_id=request.user_id,
            user_groups=request.user_groups,
            top_k=request.top_k,
            search_types=_convert_search_types(request.search_types),
            min_score=request.min_score,
        )

        # Execute search
        response = await search_service.hybrid_search(domain_request)

        # Convert to API schema
        return SearchResponseSchema(
            results=[
                {
                    "chunk_uuid": r.chunk_uuid,
                    "doc_uuid": r.doc_uuid,
                    "score": r.score,
                    "search_type": _convert_to_response_type(r.search_type),
                    "text_preview": r.text_preview,
                    "title": r.title,
                    "metadata": r.metadata,
                }
                for r in response.results
            ],
            total=response.total,
            search_time_ms=response.search_time_ms,
            search_types_used=[
                _convert_to_response_type(t) for t in response.search_types_used
            ],
        )

    except ValueError as e:
        logger.warning(f"Invalid search request: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except PermissionError as e:
        logger.warning(f"Access denied: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Search failed",
        )
```

**완료 기준:**
- [ ] Router 정의
- [ ] POST /search 엔드포인트
- [ ] 도메인 모델 변환
- [ ] 에러 핸들링

---

### Step 3: 의존성 주입 및 통합 (1h)

**작업 내용:**
1. 의존성 주입 설정
2. Router 등록
3. OpenAPI 문서화

**src/api/dependencies.py:**
```python
"""API dependencies."""
from typing import Any

from src.services.search_service import SearchService

# Service instances (set during app startup)
_search_service: SearchService | None = None


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

**src/api/routers/__init__.py:**
```python
"""API routers."""
from src.api.routers.search import router as search_router

__all__ = ["search_router"]
```

**src/api/__init__.py:**
```python
"""API package."""
from src.api.routers import search_router

__all__ = ["search_router"]
```

**완료 기준:**
- [ ] 의존성 설정
- [ ] Router export
- [ ] API 패키지 구성

---

### Step 4: 테스트 작성 (0.5h)

**작업 내용:**
1. 스키마 검증 테스트
2. 엔드포인트 테스트

**tests/unit/test_api/test_search_router.py:**
```python
"""Tests for search router."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routers.search import router
from src.api.schemas.search import SearchRequestSchema
from src.domain.models.search import SearchResponse, SearchResult, SearchType


@pytest.fixture
def mock_search_service() -> MagicMock:
    """Create mock search service."""
    mock = MagicMock()
    mock.hybrid_search = AsyncMock(
        return_value=SearchResponse(
            results=[
                SearchResult(
                    chunk_uuid="c1",
                    doc_uuid="d1",
                    score=0.95,
                    search_type=SearchType.HYBRID,
                    text_preview="Test text",
                    title="Test Doc",
                )
            ],
            total=1,
            search_time_ms=45.0,
            search_types_used=[SearchType.DENSE, SearchType.SPARSE],
        )
    )
    return mock


@pytest.fixture
def client(mock_search_service: MagicMock) -> TestClient:
    """Create test client with mock service."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    # Override dependency
    async def get_mock_service():
        return mock_search_service

    from src.api.routers import search
    app.dependency_overrides[search.get_search_service] = get_mock_service

    return TestClient(app)


class TestSearchRequestSchema:
    """Tests for SearchRequestSchema."""

    def test_valid_request(self) -> None:
        """Test valid request."""
        schema = SearchRequestSchema(
            query="test query",
            user_id="user1",
        )
        assert schema.query == "test query"
        assert schema.top_k == 10  # Default

    def test_query_validation(self) -> None:
        """Test query validation."""
        with pytest.raises(ValueError):
            SearchRequestSchema(query="", user_id="user1")

    def test_top_k_bounds(self) -> None:
        """Test top_k bounds."""
        with pytest.raises(ValueError):
            SearchRequestSchema(query="test", user_id="user1", top_k=0)

        with pytest.raises(ValueError):
            SearchRequestSchema(query="test", user_id="user1", top_k=101)


class TestSearchEndpoint:
    """Tests for search endpoint."""

    def test_search_success(
        self,
        client: TestClient,
    ) -> None:
        """Test successful search."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test query",
                "user_id": "user1",
                "top_k": 10,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["results"]) == 1
        assert data["search_time_ms"] > 0

    def test_search_empty_query(
        self,
        client: TestClient,
    ) -> None:
        """Test search with empty query."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "",
                "user_id": "user1",
            },
        )

        assert response.status_code == 422  # Validation error

    def test_search_missing_user_id(
        self,
        client: TestClient,
    ) -> None:
        """Test search without user_id."""
        response = client.post(
            "/api/v1/search",
            json={
                "query": "test",
            },
        )

        assert response.status_code == 422
```

**완료 기준:**
- [ ] 스키마 검증 테스트
- [ ] 엔드포인트 성공 테스트
- [ ] 에러 케이스 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_valid_request` | 유효한 요청 | 성공 |
| `test_query_validation` | 빈 쿼리 | 에러 |
| `test_search_success` | 검색 성공 | 200 + 결과 |
| `test_search_empty_query` | 빈 쿼리 | 422 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_search_flow` | 전체 플로우 | 결과 반환 |
| `test_openapi_docs` | OpenAPI 생성 | 문서 포함 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 스키마 불일치 | Medium | Low | 타입 변환 철저 |
| 대용량 응답 | Medium | Medium | 결과 크기 제한 |

---

## 6. Definition of Done

- [ ] `src/api/schemas/search.py` 생성
- [ ] `src/api/routers/search.py` 생성
- [ ] POST /api/v1/search 구현
- [ ] Pydantic 스키마 검증
- [ ] 에러 핸들링
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Pydantic 스키마 | 1h | - |
| Step 2: Search Router | 1.5h | - |
| Step 3: 의존성 주입 | 1h | - |
| Step 4: 테스트 | 0.5h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
