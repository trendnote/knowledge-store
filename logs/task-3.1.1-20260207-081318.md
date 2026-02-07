# Task 3.1.1: Dense Search 구현

## 작업 정보
- **Task ID**: 3.1.1
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 08:13:18
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/20
- **Task Plan**: docs/task-plans/task-3.1.1-plan.md

## 작업 개요
Milvus Dense Vector 코사인 유사도 검색을 구현합니다.

## 생성/수정된 파일

### 1. Search Domain Models 확장
**파일**: `src/domain/search.py`

#### SearchType Enum (신규)
```python
class SearchType(str, Enum):
    DENSE = "dense"
    SPARSE = "sparse"
    GRAPH = "graph"
    HYBRID = "hybrid"
```

#### SearchRequest Dataclass (신규)
```python
@dataclass
class SearchRequest:
    query: str
    user_id: str
    user_groups: list[str] = field(default_factory=list)
    top_k: int = 10
    search_types: list[SearchType]
    min_score: float = 0.0
    include_chunk_text: bool = True
```

#### SearchResponse Dataclass (신규)
```python
@dataclass
class SearchResponse:
    results: list[SearchHit]
    total: int
    search_time_ms: float
    search_types_used: list[SearchType]
```

#### SearchHit 확장
- `to_dict()` 메서드 추가

**exports 업데이트**: `src/domain/__init__.py`

### 2. Search Service
**파일**: `src/services/search_service.py`

#### SearchService 클래스
- **의존성**:
  - MilvusRepositoryProtocol: 벡터 검색
  - EmbeddingServiceProtocol: 쿼리 임베딩 생성
  - AclServiceProtocol: 접근 권한 확인

- **Methods**:
  - `dense_search(query, user_id, user_groups, top_k, min_score, security_level) -> list[SearchHit]`
    - 쿼리 임베딩 생성
    - ACL 기반 문서 필터링
    - Milvus Dense Search 실행
    - min_score 필터링
  - `dense_search_with_response(...) -> SearchResponse`
    - dense_search + 메타데이터 래핑
  - `sparse_search(...)` - 키워드 매칭 검색
  - `hybrid_search(...)` - Dense + Sparse RRF 융합 검색

- **Private Methods**:
  - `_encode_query(query)` - 쿼리 임베딩 생성
  - `_get_accessible_doc_uuids(user_id, user_groups)` - ACL 필터
  - `_filter_by_min_score(results, min_score)` - 점수 필터링

#### Factory Pattern
- `get_search_service(milvus_repo, embedding_service, acl_service) -> SearchService`
- `close_search_service() -> None`
- `reset_search_service() -> None`

**exports 업데이트**: `src/services/__init__.py`

### 3. Unit Tests
**파일**: `tests/unit/test_services/test_search_service.py`

테스트 클래스:
- `TestDenseSearch`: 9개 테스트
  - 성공 케이스
  - min_score 필터
  - 빈 결과
  - ACL 필터 적용
  - 임베딩 생성
  - 임베딩 실패 처리
  - security_level 적용
  - 예외 전파
- `TestDenseSearchWithResponse`: 2개 테스트
- `TestSparseSearch`: 2개 테스트
- `TestHybridSearch`: 2개 테스트
- `TestSearchHit`: 2개 테스트
- `TestSearchType`: 1개 테스트
- `TestSingletonFactory`: 5개 테스트

**총 23개 테스트, 100% PASSED**

## 기술적 특징

### 1. ACL 기반 검색 필터링
```python
# 사용자가 접근 가능한 문서만 검색
doc_uuids = await self._get_accessible_doc_uuids(user_id, groups)

results = await self._milvus_repo.dense_search(
    query_vector=query_vector,
    doc_uuids=doc_uuids,  # ACL 필터
    top_k=top_k,
)
```

### 2. 쿼리 임베딩 자동 생성
```python
embeddings = self._encode_query(query)
query_vector = embeddings.dense[0]  # 1024 dim BGE-M3
```

### 3. 최소 점수 필터링
```python
def _filter_by_min_score(self, results, min_score):
    if min_score <= 0:
        return results
    return [r for r in results if r.score >= min_score]
```

### 4. 검색 시간 추적
```python
start_time = time.time()
# ... 검색 실행 ...
elapsed_ms = (time.time() - start_time) * 1000
logger.info(f"Dense search completed: {len(results)} results in {elapsed_ms:.2f}ms")
```

## 테스트 결과

```
============================== test session starts ==============================
23 passed in 0.26s

Coverage:
- src/domain/search.py: 100%
- src/services/search_service.py: 86%
```

## 검색 흐름

```
1. 사용자 요청: dense_search(query, user_id, groups)
2. ACL 서비스: 접근 가능한 doc_uuids 조회
3. 임베딩 서비스: 쿼리 텍스트 → Dense Vector (1024 dim)
4. Milvus: COSINE 유사도 검색 (doc_uuids 필터 적용)
5. 후처리: min_score 필터링
6. 반환: list[SearchHit]
```

## 다음 단계
- Task 3.1.2: Sparse Search 구현 (BM25 키워드 매칭)
- Task 3.1.3: Hybrid Search 구현 (RRF 융합)
- Task 3.1.4: Graph Search 구현 (Neo4j 그래프 탐색)
