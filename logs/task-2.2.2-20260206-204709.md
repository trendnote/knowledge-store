# Task 2.2.2: Milvus Repository 구현

## 작업 정보
- **Task ID**: 2.2.2
- **작업자**: Claude AI
- **작업일시**: 2026-02-06 20:47:09
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/15
- **Task Plan**: docs/task-plans/task-2.2.2-plan.md

## 작업 개요
Milvus 벡터 데이터베이스를 위한 Repository 레이어를 구현하여 벡터 삽입/삭제 및 Dense/Sparse/Hybrid 검색 기능을 제공합니다.

## 생성된 파일

### 1. Domain Models
**파일**: `src/domain/search.py`

검색 관련 도메인 모델:
- `MilvusChunk`: Milvus 삽입용 청크 데이터
  - chunk_uuid, doc_uuid, dense_embedding, sparse_embedding
  - chunk_text, section_path, security_level, allowed_groups, created_at
- `SearchHit`: 검색 결과
  - chunk_uuid, doc_uuid, score, distance, chunk_text
  - section_path, search_type, metadata
  - `from_milvus_hit()` 클래스 메서드

**exports 업데이트**: `src/domain/__init__.py`

### 2. Milvus Repository
**파일**: `src/repositories/milvus/repository.py`

#### Insert/Delete 메서드
- `insert_chunks(chunks: list[MilvusChunk]) -> list[str]`
  - 청크 벡터 삽입
  - 텍스트 8000자 자동 truncate
- `delete_by_chunk_uuids(chunk_uuids: list[str]) -> int`
- `delete_by_doc_uuid(doc_uuid: str) -> int`
- `get_chunk_count(doc_uuid: str | None) -> int`

#### Search 메서드
- `dense_search(query_vector, doc_uuids, top_k, security_level) -> list[SearchHit]`
  - COSINE similarity with HNSW index
- `sparse_search(query_sparse: csr_array, ...) -> list[SearchHit]`
  - Inner Product with SPARSE_INVERTED_INDEX
- `hybrid_search(query_dense, query_sparse, ..., rrf_k) -> list[SearchHit]`
  - RRF (Reciprocal Rank Fusion) 기반 결합

#### 유틸리티
- `build_filter_expr(doc_uuids, security_level) -> str | None`
  - ACL 기반 doc_uuid 필터링
  - Security level hierarchy: public < internal < confidential
- `get_by_chunk_uuid(chunk_uuid: str) -> SearchHit | None`

#### Factory Pattern
- `get_milvus_repository(client: MilvusClient | None) -> MilvusRepository`
- `reset_milvus_repository() -> None`

**exports**: `src/repositories/milvus/__init__.py`

### 3. Unit Tests
**파일**: `tests/unit/test_repositories/test_milvus_repository.py`

테스트 클래스:
- `TestInsertDelete`: 8개 테스트
- `TestFilterExpression`: 7개 테스트
- `TestDenseSearch`: 3개 테스트
- `TestSparseSearch`: 2개 테스트
- `TestHybridSearch`: 2개 테스트
- `TestGetByChunkUuid`: 2개 테스트
- `TestSearchHit`: 2개 테스트
- `TestSingleton`: 4개 테스트

**총 30개 테스트, 100% PASSED**

## 기술적 특징

### 1. Sparse Vector 지원
```python
# scipy.sparse.csr_array 사용
from scipy.sparse import csr_array
query_sparse = csr_array(([0.5, 0.3], ([0, 0], [100, 200])), shape=(1, 30000))
```

### 2. Security Level Hierarchy
```python
if security_level == "public":
    # public만 접근 가능
    conditions.append('security_level == "public"')
elif security_level == "internal":
    # public, internal 접근 가능
    conditions.append('security_level in ["public", "internal"]')
# confidential은 모든 레벨 접근 가능 (필터 없음)
```

### 3. Empty ACL Handling
```python
if not doc_uuids:
    # 빈 리스트 = 접근 불가
    return 'doc_uuid == "__no_access__"'
```

### 4. RRF (Reciprocal Rank Fusion)
```python
# Hybrid search에서 dense와 sparse 결과 결합
# RRF Score = sum(1 / (k + rank_i))
await self._client.hybrid_search_async(
    query_dense=query_dense,
    query_sparse=query_sparse,
    rrf_k=60,  # 기본값, 높을수록 덜 aggressive
)
```

## 테스트 결과

```
============================== test session starts ==============================
30 passed, 6 warnings in 1.68s

Coverage:
- src/domain/search.py: 100%
- src/repositories/milvus/repository.py: 99%
```

## 해결된 이슈

### 1. Mock Patch 경로 오류
- **문제**: `get_milvus_client` 함수가 함수 내에서 import되어 module level patch 불가
- **해결**: `src.infrastructure.database.get_milvus_client` 경로로 patch

## 다음 단계
- Task 2.2.3: Neo4j Repository 구현
- Task 2.2.4: Kafka Repository 구현
