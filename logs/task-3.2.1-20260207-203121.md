# Task 3.2.1: Search Router 및 Schemas 구현

## 작업 정보
- **Task ID**: 3.2.1
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 20:31:21
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/24
- **Task Plan**: docs/task-plans/task-3.2.1-plan.md

## 작업 개요
Search API 엔드포인트와 Request/Response Pydantic 스키마를 구현합니다.

## 생성/수정된 파일

### 1. Pydantic Schemas
**파일**: `src/api/schemas/search.py`

#### SearchTypeEnum
```python
class SearchTypeEnum(str, Enum):
    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    HYBRID = "hybrid"
```

#### SearchRequestSchema
```python
class SearchRequestSchema(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    user_id: str = Field(..., min_length=1)
    user_groups: list[str] = Field(default_factory=list)
    top_k: int = Field(default=10, ge=1, le=100)
    search_types: list[SearchTypeEnum] | None = Field(default=None)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("query")
    def validate_query(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Query cannot be empty")
        return stripped
```

#### SearchResultSchema
```python
class SearchResultSchema(BaseModel):
    chunk_uuid: str
    doc_uuid: str
    score: float = Field(..., ge=0.0)
    search_type: str
    text_preview: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

#### SearchResponseSchema
```python
class SearchResponseSchema(BaseModel):
    results: list[SearchResultSchema]
    total: int = Field(..., ge=0)
    search_time_ms: float = Field(..., ge=0.0)
    search_types_used: list[str] = Field(default_factory=list)
```

### 2. Search Router
**파일**: `src/api/routers/search.py`

#### POST /search 엔드포인트
```python
@router.post(
    "",
    response_model=SearchResponseSchema,
    summary="Hybrid Search",
)
async def search(
    request: SearchRequestSchema,
    search_service: Any = Depends(get_search_service),
) -> SearchResponseSchema:
    """Execute hybrid search."""
```

#### 주요 기능
- 도메인 타입 변환 (`_convert_api_to_domain_types`)
- SearchService.unified_search() 호출
- 에러 핸들링 (400, 403, 500)
- 로깅

### 3. 의존성 주입
**파일**: `src/api/dependencies.py`

```python
def set_search_service(service: SearchService) -> None:
    """Set search service instance."""
    global _search_service
    _search_service = service

async def get_search_service() -> SearchService:
    """Get search service instance."""
    if _search_service is None:
        raise RuntimeError("Search service not initialized")
    return _search_service

def reset_dependencies() -> None:
    """Reset all dependency instances (for testing)."""
```

### 4. 패키지 초기화
- `src/api/__init__.py`: search_router export
- `src/api/routers/__init__.py`: search_router export
- `src/api/schemas/__init__.py`: 스키마 클래스들 export

### 5. Unit Tests
**파일**: `tests/unit/test_api/`

#### test_search_schemas.py (23개 테스트)
- `TestSearchTypeEnum`: 2개
- `TestSearchRequestSchema`: 11개
  - 유효 요청 검증
  - 쿼리 검증 (빈 값, 공백, 최대 길이)
  - user_id 검증
  - top_k 범위 검증
  - min_score 범위 검증
- `TestSearchResultSchema`: 3개
- `TestSearchResponseSchema`: 4개
- `TestSearchErrorSchema`: 2개

#### test_search_router.py (18개 테스트)
- `TestTypeConversion`: 4개
- `TestSearchEndpoint`: 10개
  - 성공 케이스
  - 검증 에러 (422)
  - ValueError → 400
  - PermissionError → 403
  - Exception → 500
- `TestEmptyResults`: 1개
- `TestKoreanQuery`: 2개

#### test_dependencies.py (4개 테스트)
- 초기화 안됨 → RuntimeError
- set/get 동작
- reset 동작
- replace 동작

**총 45개 테스트, 100% PASSED**

## 기술적 특징

### 1. Pydantic v2 검증
```python
@field_validator("query")
@classmethod
def validate_query(cls, v: str) -> str:
    stripped = v.strip()
    if not stripped:
        raise ValueError("Query cannot be empty")
    return stripped
```

### 2. 의존성 주입 패턴
```python
# 앱 시작 시
set_search_service(service_instance)

# 라우터에서
async def search(
    search_service: Any = Depends(get_search_service),
):
```

### 3. 타입 변환
```python
def _convert_api_to_domain_types(
    types: list[SearchTypeEnum] | None,
) -> list[SearchType] | None:
    mapping = {
        SearchTypeEnum.DENSE: SearchType.DENSE,
        SearchTypeEnum.SPARSE: SearchType.SPARSE,
        ...
    }
```

### 4. 에러 핸들링
| Exception | HTTP Status | Response |
|-----------|-------------|----------|
| ValueError | 400 | 에러 메시지 |
| PermissionError | 403 | "Access denied" |
| Exception | 500 | "Search failed" |

## 테스트 결과

```
============================== test session starts ==============================
45 passed in 0.34s

Coverage:
- src/api/schemas/search.py: 100%
- src/api/routers/search.py: 100%
- src/api/dependencies.py: 100%
```

## API 사용 예시

### Request
```json
POST /api/v1/search
{
    "query": "인공지능 기술 문서",
    "user_id": "user123",
    "user_groups": ["engineering", "ml-team"],
    "top_k": 10,
    "search_types": ["dense", "sparse"],
    "min_score": 0.5
}
```

### Response
```json
{
    "results": [
        {
            "chunk_uuid": "chunk-123",
            "doc_uuid": "doc-456",
            "score": 0.95,
            "search_type": "hybrid",
            "text_preview": "AI 기술에 관한 문서...",
            "title": "인공지능 개요",
            "metadata": {
                "sources": {
                    "dense": {"score": 0.92, "rank": 1},
                    "sparse": {"score": 0.88, "rank": 2}
                }
            }
        }
    ],
    "total": 1,
    "search_time_ms": 45.2,
    "search_types_used": ["dense", "sparse"]
}
```

## 다음 단계
- Task 3.2.2: API 통합 및 OpenAPI 문서화
- Task 3.3: Search 성능 최적화
