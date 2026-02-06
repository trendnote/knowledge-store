# Task 2.1.2 Implementation Log

## Task Information

| Item | Value |
|------|-------|
| **Task ID** | 2.1.2 |
| **Task Name** | Milvus Client 구현 |
| **GitHub Issue** | [#11](https://github.com/trendnote/knowledge-store/issues/11) |
| **Task Plan** | [task-2.1.2-plan.md](../docs/task-plans/task-2.1.2-plan.md) |
| **Date** | 2026-02-06 |
| **Status** | Completed |

---

## Summary

pymilvus 기반 Milvus 벡터 데이터베이스 클라이언트를 구현했습니다. Dense/Sparse/Hybrid 검색을 지원하며, 모든 동기 메서드에 대한 비동기 래퍼를 제공합니다.

---

## Implementation Details

### Step 1: MilvusClient 클래스 구현

**핵심 메서드:**

| Method | Description |
|--------|-------------|
| `connect()` | Milvus 연결 및 Collection 로드 |
| `disconnect()` | Collection 해제 및 연결 종료 |
| `ping()` | 연결 상태 확인 |
| `insert()` | 데이터 삽입 |
| `delete()` | 데이터 삭제 |
| `flush()` | 디스크에 flush |
| `count()` | 엔티티 수 조회 |
| `dense_search()` | Dense 벡터 검색 (COSINE) |
| `sparse_search()` | Sparse 벡터 검색 (IP) |
| `hybrid_search()` | RRF 기반 하이브리드 검색 |

### Step 2: 비동기 래퍼

pymilvus는 동기 SDK이므로 `run_in_executor`를 사용한 비동기 래퍼 제공:

```python
async def dense_search_async(
    self,
    query_vector: list[float],
    limit: int = 10,
    expr: str | None = None,
    output_fields: list[str] | None = None,
    ef: int = 64,
) -> list[dict[str, Any]]:
    """Async wrapper for dense_search."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: self.dense_search(query_vector, limit, expr, output_fields, ef),
    )
```

### Step 3: Hybrid Search 구현

RRF (Reciprocal Rank Fusion) 기반 하이브리드 검색:

```python
def hybrid_search(
    self,
    query_dense: list[float],
    query_sparse: csr_array,
    limit: int = 10,
    expr: str | None = None,
    output_fields: list[str] | None = None,
    rrf_k: int = 60,
    ef: int = 64,
) -> list[dict[str, Any]]:
    from pymilvus import AnnSearchRequest, RRFRanker

    dense_req = AnnSearchRequest(
        data=[query_dense],
        anns_field="dense_embedding",
        param={"metric_type": "COSINE", "params": {"ef": ef}},
        limit=limit,
        expr=expr,
    )

    sparse_req = AnnSearchRequest(
        data=[query_sparse],
        anns_field="sparse_embedding",
        param={"metric_type": "IP"},
        limit=limit,
        expr=expr,
    )

    ranker = RRFRanker(k=rrf_k)

    results = self.collection.hybrid_search(
        reqs=[dense_req, sparse_req],
        rerank=ranker,
        limit=limit,
        output_fields=output_fields,
    )
    return self._format_search_results(results[0])
```

### Step 4: Factory 함수

| Function | Description |
|----------|-------------|
| `get_milvus_client()` | Singleton 클라이언트 반환 |
| `close_milvus_client()` | Singleton 클라이언트 종료 |
| `reset_milvus_client()` | Singleton 초기화 (테스트용) |

---

## Output Files

### Created Files

1. **src/infrastructure/database/milvus.py**
   - MilvusClient 클래스
   - Singleton factory 함수

2. **src/infrastructure/database/__init__.py** (Updated)
   - Milvus 모듈 export 추가

3. **tests/unit/test_infrastructure/test_milvus_client.py**
   - 30개 단위 테스트

---

## Test Results

### Unit Tests (30개)

```
TestMilvusClientConnection
  ✅ test_connect_success
  ✅ test_connect_is_idempotent
  ✅ test_connect_collection_not_exists_raises
  ✅ test_disconnect
  ✅ test_disconnect_is_idempotent
  ✅ test_collection_not_connected_raises

TestMilvusClientPing
  ✅ test_ping_when_connected
  ✅ test_ping_when_disconnected
  ✅ test_ping_on_error
  ✅ test_ping_async

TestMilvusClientInsertDelete
  ✅ test_insert
  ✅ test_insert_async
  ✅ test_delete
  ✅ test_delete_async
  ✅ test_flush
  ✅ test_flush_async
  ✅ test_count
  ✅ test_count_async

TestMilvusClientSearch
  ✅ test_dense_search
  ✅ test_dense_search_async
  ✅ test_dense_search_with_filter
  ✅ test_sparse_search
  ✅ test_sparse_search_async
  ✅ test_hybrid_search
  ✅ test_hybrid_search_async

TestMilvusClientSingleton
  ✅ test_get_milvus_client_creates_instance
  ✅ test_get_milvus_client_returns_same_instance
  ✅ test_get_milvus_client_with_auto_settings
  ✅ test_close_milvus_client
  ✅ test_close_milvus_client_when_none

Coverage: 98% (src/infrastructure/database/milvus.py)
```

### Integration Test

```
Connecting to: localhost:19531/knowledge_chunks
Connected: OK
Ping: True
Entity count: 0
Dense search results: 0
Disconnected: OK

Integration test: SUCCESS
```

---

## Acceptance Criteria Checklist

- [x] `src/infrastructure/database/milvus.py` 생성
- [x] 연결 관리 (connect/disconnect)
- [x] Dense 검색 (COSINE similarity)
- [x] Sparse 검색 (Inner Product)
- [x] Hybrid 검색 (RRF reranking)

---

## Definition of Done

- [x] `src/infrastructure/database/milvus.py` 구현
- [x] `src/infrastructure/database/__init__.py` 업데이트
- [x] Connection 관리 (connect/disconnect)
- [x] ping 메서드
- [x] CRUD 메서드 (insert, delete, flush, count)
- [x] 검색 메서드 (dense_search, sparse_search, hybrid_search)
- [x] 모든 메서드에 대한 async 래퍼
- [x] 모든 단위 테스트 통과 (30개)
- [x] 통합 테스트 통과
- [x] ruff 린트 통과

---

## Usage

```python
from src.infrastructure.database import get_milvus_client

# Get client singleton
client = get_milvus_client()

# Connect
client.connect()

# Dense search
results = client.dense_search(
    query_vector=[0.1] * 1024,
    limit=10,
    expr='security_level == "public"',
)

# Sparse search (with scipy.sparse.csr_array)
from scipy.sparse import csr_array
sparse_vector = csr_array(([0.5, 0.3], ([0, 0], [100, 200])), shape=(1, 30000))
results = client.sparse_search(sparse_vector, limit=10)

# Hybrid search
results = client.hybrid_search(
    query_dense=[0.1] * 1024,
    query_sparse=sparse_vector,
    limit=10,
    rrf_k=60,
)

# Async operations
results = await client.dense_search_async(query_vector, limit=10)

# Disconnect
client.disconnect()
```

---

## API Reference

### MilvusClient

```python
class MilvusClient:
    # Properties
    collection: Collection    # Milvus Collection (raises if not connected)
    is_connected: bool        # Connection status

    # Connection Management
    def connect() -> None
    async def connect_async() -> None
    def disconnect() -> None
    def ping() -> bool
    async def ping_async() -> bool

    # CRUD Operations
    def insert(data: list[dict]) -> list[str]
    async def insert_async(data: list[dict]) -> list[str]
    def delete(expr: str) -> int
    async def delete_async(expr: str) -> int
    def flush() -> None
    async def flush_async() -> None
    def count() -> int
    async def count_async() -> int

    # Search Operations
    def dense_search(query_vector, limit=10, expr=None, output_fields=None, ef=64) -> list[dict]
    async def dense_search_async(...) -> list[dict]
    def sparse_search(query_sparse, limit=10, expr=None, output_fields=None) -> list[dict]
    async def sparse_search_async(...) -> list[dict]
    def hybrid_search(query_dense, query_sparse, limit=10, expr=None, output_fields=None, rrf_k=60, ef=64) -> list[dict]
    async def hybrid_search_async(...) -> list[dict]
```

---

## Next Steps

- **Task 2.1.3**: Neo4j Client 구현
  - neo4j-driver 기반 그래프 DB 클라이언트
  - Cypher 쿼리 실행 지원

---

## Notes

- pymilvus는 동기 SDK이므로 `run_in_executor`를 사용하여 비동기 래퍼 제공
- scipy.sparse.csr_array를 사용하여 Sparse 벡터 표현
- Hybrid 검색은 RRF (Reciprocal Rank Fusion) 알고리즘 사용 (k=60 기본값)
- Singleton 패턴으로 애플리케이션 전체에서 하나의 클라이언트 인스턴스 사용
- `reset_milvus_client()`는 테스트 격리를 위해 제공됨
