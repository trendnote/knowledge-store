# Task Execution Plan: 2.1.2 - Milvus Client 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.1.2 |
| **Task Name** | Milvus Client 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.3.2 |

### Description
pymilvus 기반 Milvus 연결 및 기본 연산을 관리하는 클라이언트를 구현합니다.

### Acceptance Criteria
- [ ] `src/infrastructure/database/milvus.py` 생성
- [ ] 연결/종료 메서드
- [ ] Collection 로드/릴리스
- [ ] Insert, Delete, Search 기본 메서드
- [ ] 연결 상태 확인 (ping)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.4 Infrastructure Layer
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 2.2 Vector DB

### 2.2 pymilvus 주요 기능
```python
from pymilvus import connections, Collection, utility

# Connection
connections.connect(alias="default", host="localhost", port=19530)

# Collection
collection = Collection("knowledge_chunks")
collection.load()

# Search
results = collection.search(
    data=[query_vector],
    anns_field="dense_embedding",
    param={"metric_type": "COSINE", "params": {"ef": 64}},
    limit=10,
    expr="doc_uuid in ['doc1', 'doc2']",
    output_fields=["chunk_uuid", "chunk_text"]
)
```

### 2.3 설계 결정
1. **Sync SDK**: pymilvus는 동기 SDK (run_in_executor로 async 래핑)
2. **Connection Alias**: "default" alias 사용
3. **Auto-Load**: 연결 시 Collection 자동 로드
4. **Retry**: 일시적 실패 시 재시도 로직

### 2.4 클래스 구조
```
MilvusClient
├── __init__(settings: MilvusSettings)
├── connect() -> None
├── disconnect() -> None
├── ping() -> bool
├── get_collection() -> Collection
├── insert(data: dict) -> list[str]
├── delete(expr: str) -> int
├── search(vector, params, limit, expr, output_fields) -> list
├── hybrid_search(dense, sparse, params, limit, expr) -> list
└── flush() -> None
```

---

## 3. Implementation Steps

### Step 1: 기본 클래스 및 연결 관리 (1h)

**작업 내용:**
1. MilvusClient 클래스 정의
2. connect/disconnect 메서드
3. ping 메서드

**src/infrastructure/database/milvus.py:**
```python
"""Milvus vector database client."""
import asyncio
from typing import Any

from pymilvus import Collection, connections, utility

from src.config import MilvusSettings


class MilvusClient:
    """Milvus client for vector operations."""

    def __init__(self, settings: MilvusSettings) -> None:
        """Initialize Milvus client.

        Args:
            settings: Milvus connection settings
        """
        self._settings = settings
        self._collection: Collection | None = None
        self._connected = False

    @property
    def collection(self) -> Collection:
        """Get collection (raises if not connected)."""
        if self._collection is None:
            raise RuntimeError("MilvusClient is not connected. Call connect() first.")
        return self._collection

    def connect(self) -> None:
        """Connect to Milvus and load collection."""
        if self._connected:
            return

        connections.connect(
            alias="default",
            host=self._settings.host,
            port=self._settings.port,
            timeout=30,
        )

        # Check if collection exists
        if not utility.has_collection(self._settings.collection):
            raise RuntimeError(
                f"Collection '{self._settings.collection}' does not exist. "
                "Run init_milvus.py first."
            )

        # Load collection
        self._collection = Collection(self._settings.collection)
        self._collection.load()
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect from Milvus."""
        if self._connected:
            if self._collection is not None:
                self._collection.release()
                self._collection = None
            connections.disconnect("default")
            self._connected = False

    def ping(self) -> bool:
        """Check if Milvus is reachable."""
        try:
            if not self._connected:
                return False
            utility.list_collections()
            return True
        except Exception:
            return False

    async def ping_async(self) -> bool:
        """Async wrapper for ping."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.ping)
```

**완료 기준:**
- [ ] 클래스 기본 구조 완성
- [ ] connect/disconnect 구현
- [ ] ping 구현

---

### Step 2: Insert/Delete/Flush 메서드 (1h)

**작업 내용:**
1. insert 메서드
2. delete 메서드
3. flush 메서드

**src/infrastructure/database/milvus.py (계속):**
```python
    def insert(self, data: dict[str, list[Any]]) -> list[str]:
        """Insert data into collection.

        Args:
            data: Dictionary with field names as keys and lists of values

        Returns:
            List of inserted primary keys (chunk_uuids)

        Example:
            data = {
                "chunk_uuid": ["uuid1", "uuid2"],
                "doc_uuid": ["doc1", "doc1"],
                "dense_embedding": [[0.1, ...], [0.2, ...]],
                ...
            }
        """
        result = self.collection.insert(data)
        return result.primary_keys

    async def insert_async(self, data: dict[str, list[Any]]) -> list[str]:
        """Async wrapper for insert."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.insert, data)

    def delete(self, expr: str) -> int:
        """Delete entities matching expression.

        Args:
            expr: Boolean expression (e.g., "chunk_uuid in ['uuid1', 'uuid2']")

        Returns:
            Number of deleted entities
        """
        result = self.collection.delete(expr)
        return result.delete_count

    async def delete_async(self, expr: str) -> int:
        """Async wrapper for delete."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.delete, expr)

    def flush(self) -> None:
        """Flush data to disk."""
        self.collection.flush()

    async def flush_async(self) -> None:
        """Async wrapper for flush."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.flush)
```

**완료 기준:**
- [ ] insert 메서드 구현
- [ ] delete 메서드 구현
- [ ] flush 메서드 구현
- [ ] 모든 async 래퍼 구현

---

### Step 3: Search 메서드 (1h)

**작업 내용:**
1. dense_search 메서드
2. sparse_search 메서드
3. hybrid_search 메서드

**src/infrastructure/database/milvus.py (계속):**
```python
    def dense_search(
        self,
        query_vector: list[float],
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search by dense vector (cosine similarity).

        Args:
            query_vector: Query embedding (1024 dim)
            limit: Max results
            expr: Filter expression
            output_fields: Fields to return

        Returns:
            List of search results
        """
        search_params = {
            "metric_type": "COSINE",
            "params": {"ef": 64},
        }

        if output_fields is None:
            output_fields = ["chunk_uuid", "doc_uuid", "chunk_text", "section_path"]

        results = self.collection.search(
            data=[query_vector],
            anns_field="dense_embedding",
            param=search_params,
            limit=limit,
            expr=expr,
            output_fields=output_fields,
        )

        return self._format_search_results(results[0])

    def sparse_search(
        self,
        query_sparse: dict[str, float],
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search by sparse vector (BM25-like).

        Args:
            query_sparse: Sparse vector as dict {term: weight}
            limit: Max results
            expr: Filter expression
            output_fields: Fields to return

        Returns:
            List of search results
        """
        search_params = {
            "metric_type": "IP",
            "params": {},
        }

        if output_fields is None:
            output_fields = ["chunk_uuid", "doc_uuid", "chunk_text", "section_path"]

        results = self.collection.search(
            data=[query_sparse],
            anns_field="sparse_embedding",
            param=search_params,
            limit=limit,
            expr=expr,
            output_fields=output_fields,
        )

        return self._format_search_results(results[0])

    def hybrid_search(
        self,
        query_dense: list[float],
        query_sparse: dict[str, float],
        limit: int = 10,
        expr: str | None = None,
        output_fields: list[str] | None = None,
        dense_weight: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining dense and sparse.

        Args:
            query_dense: Dense embedding
            query_sparse: Sparse weights
            limit: Max results
            expr: Filter expression
            output_fields: Fields to return
            dense_weight: Weight for dense results (0-1)

        Returns:
            List of merged search results
        """
        from pymilvus import AnnSearchRequest, RRFRanker

        if output_fields is None:
            output_fields = ["chunk_uuid", "doc_uuid", "chunk_text", "section_path"]

        # Dense search request
        dense_req = AnnSearchRequest(
            data=[query_dense],
            anns_field="dense_embedding",
            param={"metric_type": "COSINE", "params": {"ef": 64}},
            limit=limit,
            expr=expr,
        )

        # Sparse search request
        sparse_req = AnnSearchRequest(
            data=[query_sparse],
            anns_field="sparse_embedding",
            param={"metric_type": "IP"},
            limit=limit,
            expr=expr,
        )

        # RRF (Reciprocal Rank Fusion) ranker
        ranker = RRFRanker()

        results = self.collection.hybrid_search(
            reqs=[dense_req, sparse_req],
            ranker=ranker,
            limit=limit,
            output_fields=output_fields,
        )

        return self._format_search_results(results[0])

    def _format_search_results(self, hits) -> list[dict[str, Any]]:
        """Format Milvus search hits to dict list."""
        results = []
        for hit in hits:
            result = {
                "id": hit.id,
                "score": hit.score,
                "distance": hit.distance,
            }
            # Add output fields
            for field in hit.fields:
                result[field] = hit.fields[field]
            results.append(result)
        return results

    # Async wrappers
    async def dense_search_async(self, *args, **kwargs) -> list[dict[str, Any]]:
        """Async wrapper for dense_search."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.dense_search(*args, **kwargs))

    async def sparse_search_async(self, *args, **kwargs) -> list[dict[str, Any]]:
        """Async wrapper for sparse_search."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.sparse_search(*args, **kwargs))

    async def hybrid_search_async(self, *args, **kwargs) -> list[dict[str, Any]]:
        """Async wrapper for hybrid_search."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.hybrid_search(*args, **kwargs))
```

**완료 기준:**
- [ ] dense_search 구현
- [ ] sparse_search 구현
- [ ] hybrid_search 구현
- [ ] 결과 포맷팅 함수 구현

---

### Step 4: Factory 및 테스트 (1h)

**작업 내용:**
1. Singleton factory 함수
2. __init__.py 업데이트
3. 테스트 작성

**src/infrastructure/database/milvus.py (추가):**
```python
# Singleton instance
_client: MilvusClient | None = None


def get_milvus_client(settings: MilvusSettings | None = None) -> MilvusClient:
    """Get or create Milvus client singleton."""
    global _client
    if _client is None:
        if settings is None:
            from src.config import get_settings
            settings = get_settings().milvus
        _client = MilvusClient(settings)
    return _client


def close_milvus_client() -> None:
    """Close the Milvus client singleton."""
    global _client
    if _client is not None:
        _client.disconnect()
        _client = None
```

**tests/unit/test_infrastructure/test_milvus_client.py:**
```python
"""Tests for Milvus client."""
import pytest
from unittest.mock import MagicMock, patch

from src.infrastructure.database.milvus import MilvusClient
from src.config import MilvusSettings


@pytest.fixture
def settings() -> MilvusSettings:
    """Create test settings."""
    return MilvusSettings(
        host="localhost",
        port=19530,
        collection="test_collection",
    )


@pytest.fixture
def client(settings: MilvusSettings) -> MilvusClient:
    """Create test client."""
    return MilvusClient(settings)


class TestMilvusClient:
    """Tests for MilvusClient."""

    def test_connect_success(self, client: MilvusClient) -> None:
        """Test successful connection."""
        with patch("pymilvus.connections.connect") as mock_connect, \
             patch("pymilvus.utility.has_collection", return_value=True), \
             patch("pymilvus.Collection") as mock_collection:

            mock_coll = MagicMock()
            mock_collection.return_value = mock_coll

            client.connect()

            mock_connect.assert_called_once()
            mock_coll.load.assert_called_once()
            assert client._connected is True

    def test_disconnect(self, client: MilvusClient) -> None:
        """Test disconnect."""
        client._connected = True
        mock_coll = MagicMock()
        client._collection = mock_coll

        with patch("pymilvus.connections.disconnect"):
            client.disconnect()

        mock_coll.release.assert_called_once()
        assert client._connected is False
        assert client._collection is None

    def test_collection_not_connected_raises(self, client: MilvusClient) -> None:
        """Test accessing collection before connect."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.collection

    def test_ping_when_connected(self, client: MilvusClient) -> None:
        """Test ping returns True when connected."""
        client._connected = True
        with patch("pymilvus.utility.list_collections"):
            assert client.ping() is True

    def test_ping_when_disconnected(self, client: MilvusClient) -> None:
        """Test ping returns False when disconnected."""
        client._connected = False
        assert client.ping() is False
```

**완료 기준:**
- [ ] Factory 함수 구현
- [ ] __init__.py 업데이트
- [ ] 테스트 작성

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_connect_success` | 정상 연결 | _connected=True |
| `test_disconnect` | 연결 종료 | release, disconnect called |
| `test_collection_not_connected` | 미연결 시 접근 | RuntimeError |
| `test_ping_connected` | 연결 상태 ping | True |
| `test_ping_disconnected` | 미연결 상태 ping | False |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_insert_and_search` | 삽입 후 검색 | 결과 반환 |
| `test_hybrid_search` | 하이브리드 검색 | RRF 결과 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 동기 SDK 블로킹 | High | Medium | run_in_executor로 async 래핑 |
| Collection 미존재 | High | Low | 연결 시 존재 확인 |
| Memory 부족 (로드 시) | Medium | Low | 에러 메시지로 안내 |

---

## 6. Definition of Done

- [ ] `src/infrastructure/database/milvus.py` 구현
- [ ] connect/disconnect/ping 구현
- [ ] insert/delete/flush 구현
- [ ] dense_search/sparse_search/hybrid_search 구현
- [ ] 모든 async 래퍼 구현
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 기본 구조 및 연결 | 1h | - |
| Step 2: Insert/Delete/Flush | 1h | - |
| Step 3: Search 메서드 | 1h | - |
| Step 4: Factory 및 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
