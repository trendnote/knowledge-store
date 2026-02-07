# Task 3.1.2: Sparse Search 구현

## 작업 정보
- **Task ID**: 3.1.2
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 09:15:42
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/21
- **Task Plan**: docs/task-plans/task-3.1.2-plan.md

## 작업 개요
Milvus Sparse Vector (BM25) 키워드 검색을 구현합니다.

## 생성/수정된 파일

### 1. Search Service 확장
**파일**: `src/services/search_service.py`

#### 신규 Private Methods
```python
def _preprocess_query(self, query: str) -> str:
    """Preprocess query for better search.

    - BGE-M3 handles Korean tokenization internally
    - Strips whitespace
    """
    return query.strip()

def _is_valid_sparse_vector(self, sparse_vector: Any) -> bool:
    """Check if sparse vector is valid (non-empty).

    Handles:
    - dict-like sparse vectors (len check)
    - scipy sparse arrays (nnz check)
    - None validation
    """
```

#### sparse_search 개선
- 쿼리 전처리 (`_preprocess_query`) 적용
- 빈 sparse 벡터 검증 (`_is_valid_sparse_vector`) 추가
- 빈 쿼리 처리 추가
- 한국어 쿼리 지원 (BGE-M3 내장 토크나이저)
- 상세 docstring 추가

#### sparse_search_with_response (신규)
```python
async def sparse_search_with_response(
    self,
    query: str,
    user_id: str,
    user_groups: list[str] | None = None,
    top_k: int = 10,
    min_score: float = 0.0,
    security_level: str | None = None,
) -> SearchResponse:
    """Execute sparse search and return SearchResponse."""
```

### 2. Unit Tests 확장
**파일**: `tests/unit/test_services/test_search_service.py`

#### 신규 테스트 클래스
- `TestSparseSearch`: 10개 테스트
  - 성공 케이스
  - 한국어 쿼리
  - min_score 필터
  - 빈 sparse 임베딩
  - 빈 sparse 벡터
  - ACL 필터 적용
  - security_level 적용
  - 예외 전파
  - 빈 쿼리 처리
- `TestSparseSearchWithResponse`: 2개 테스트
- `TestPreprocessQuery`: 3개 테스트
- `TestSparseVectorValidation`: 3개 테스트

#### Mock Fixture 개선
```python
@pytest.fixture
def mock_embedding_service() -> MagicMock:
    # Use a dict with content for sparse vector to pass validation
    sparse_vector = {123: 0.5, 456: 0.8, 789: 0.3}
    service.encode.return_value = MagicMock(
        dense=[[0.1] * 1024],
        sparse=[sparse_vector],
    )
```

**총 38개 테스트, 100% PASSED**

## 기술적 특징

### 1. Inner Product 메트릭
```python
# Sparse search uses Inner Product for BM25-style matching
# Dense search uses Cosine similarity
```

### 2. 한국어 지원
```python
# BGE-M3 handles Korean tokenization internally
# Just trim whitespace for now
processed_query = self._preprocess_query(query)
```

### 3. Sparse Vector 검증
```python
def _is_valid_sparse_vector(self, sparse_vector: Any) -> bool:
    if sparse_vector is None:
        return False
    # Handle dict-like sparse vectors
    if hasattr(sparse_vector, "__len__"):
        return len(sparse_vector) > 0
    # Handle scipy sparse arrays
    if hasattr(sparse_vector, "nnz"):
        return sparse_vector.nnz > 0
    return True
```

### 4. Dense vs Sparse 비교
| 특성 | Dense | Sparse |
|------|-------|--------|
| 벡터 형태 | Float[1024] | Dict[int, float] |
| 메트릭 | COSINE | IP (Inner Product) |
| 강점 | 의미적 유사성 | 키워드 정확 매칭 |
| 약점 | 키워드 누락 | 의미 파악 한계 |

## 테스트 결과

```
============================== test session starts ==============================
38 passed in 0.45s

Coverage:
- src/services/search_service.py: 89%
- src/domain/search.py: 100%
```

## 검색 흐름

```
1. 쿼리 전처리: _preprocess_query() - whitespace 제거
2. ACL 서비스: 접근 가능한 doc_uuids 조회
3. 임베딩 서비스: 쿼리 텍스트 → Sparse Vector
4. 벡터 검증: _is_valid_sparse_vector() - 빈 벡터 확인
5. Milvus: Inner Product 검색 (doc_uuids 필터 적용)
6. 후처리: min_score 필터링
7. 반환: list[SearchHit] 또는 SearchResponse
```

## 다음 단계
- Task 3.1.3: Hybrid Search 구현 (RRF 융합)
- Task 3.1.4: Graph Search 구현 (Neo4j 그래프 탐색)
