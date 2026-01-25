# Task Execution Plan: 2.1.3 - Neo4j Client 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.1.3 |
| **Task Name** | Neo4j Client 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.3.3 |

### Description
neo4j-driver 기반 Neo4j 연결 및 기본 연산을 관리하는 클라이언트를 구현합니다.

### Acceptance Criteria
- [ ] `src/infrastructure/database/neo4j.py` 생성
- [ ] 비동기 드라이버 생성/종료
- [ ] 세션 컨텍스트 매니저
- [ ] Cypher 쿼리 실행 메서드
- [ ] 연결 상태 확인 (ping)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.4 Infrastructure Layer
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 2.2 Graph DB

### 2.2 neo4j-driver 주요 기능
```python
from neo4j import AsyncGraphDatabase

# Driver
driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
await driver.verify_connectivity()

# Session & Query
async with driver.session() as session:
    result = await session.run("MATCH (n) RETURN n LIMIT 10")
    records = [record async for record in result]
```

### 2.3 설계 결정
1. **Async Driver**: neo4j 공식 async driver 사용
2. **Session Pool**: 내장 connection pool 활용
3. **Transaction 지원**: 읽기/쓰기 트랜잭션 구분
4. **Result 처리**: async iterator로 결과 스트리밍

### 2.4 클래스 구조
```
Neo4jClient
├── __init__(settings: Neo4jSettings)
├── connect() -> None (드라이버 생성)
├── close() -> None
├── ping() -> bool
├── session() -> AsyncSession (context manager)
├── execute_read(query, params) -> list[dict]
├── execute_write(query, params) -> list[dict]
└── execute_query(query, params) -> list[dict]
```

---

## 3. Implementation Steps

### Step 1: 기본 클래스 및 연결 관리 (1h)

**작업 내용:**
1. Neo4jClient 클래스 정의
2. connect/close 메서드
3. ping 메서드

**src/infrastructure/database/neo4j.py:**
```python
"""Neo4j async graph database client."""
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession
from neo4j.exceptions import ServiceUnavailable

from src.config import Neo4jSettings


class Neo4jClient:
    """Async Neo4j client for graph operations."""

    def __init__(self, settings: Neo4jSettings) -> None:
        """Initialize Neo4j client.

        Args:
            settings: Neo4j connection settings
        """
        self._settings = settings
        self._driver: AsyncDriver | None = None

    @property
    def driver(self) -> AsyncDriver:
        """Get driver (raises if not connected)."""
        if self._driver is None:
            raise RuntimeError("Neo4jClient is not connected. Call connect() first.")
        return self._driver

    async def connect(self) -> None:
        """Create driver and verify connectivity."""
        if self._driver is not None:
            return

        self._driver = AsyncGraphDatabase.driver(
            self._settings.uri,
            auth=(self._settings.user, self._settings.password),
            max_connection_lifetime=3600,
            max_connection_pool_size=50,
            connection_acquisition_timeout=60,
        )

        # Verify connectivity
        await self._driver.verify_connectivity()

    async def close(self) -> None:
        """Close driver."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def ping(self) -> bool:
        """Check if Neo4j is reachable."""
        try:
            await self.driver.verify_connectivity()
            return True
        except (ServiceUnavailable, RuntimeError):
            return False
```

**완료 기준:**
- [ ] 클래스 기본 구조 완성
- [ ] connect/close 구현
- [ ] ping 구현

---

### Step 2: Session 및 Transaction 메서드 (1.5h)

**작업 내용:**
1. session context manager
2. execute_read 메서드
3. execute_write 메서드
4. execute_query 범용 메서드

**src/infrastructure/database/neo4j.py (계속):**
```python
    @asynccontextmanager
    async def session(self, database: str | None = None):
        """Create a session context.

        Args:
            database: Database name (default: neo4j)

        Usage:
            async with client.session() as session:
                result = await session.run(...)
        """
        async with self.driver.session(database=database or "neo4j") as session:
            yield session

    async def execute_read(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a read query.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            List of record dictionaries
        """
        async def _read_tx(tx) -> list[dict[str, Any]]:
            result = await tx.run(query, parameters or {})
            records = [record.data() async for record in result]
            return records

        async with self.session(database) as session:
            return await session.execute_read(_read_tx)

    async def execute_write(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a write query.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            List of record dictionaries
        """
        async def _write_tx(tx) -> list[dict[str, Any]]:
            result = await tx.run(query, parameters or {})
            records = [record.data() async for record in result]
            return records

        async with self.session(database) as session:
            return await session.execute_write(_write_tx)

    async def execute_query(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a query (auto-detect read/write).

        For simple queries. Use execute_read/execute_write for
        explicit transaction control.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            List of record dictionaries
        """
        async with self.session(database) as session:
            result = await session.run(query, parameters or {})
            records = [record.data() async for record in result]
            return records
```

**완료 기준:**
- [ ] session context manager 구현
- [ ] execute_read 구현
- [ ] execute_write 구현
- [ ] execute_query 구현

---

### Step 3: 편의 메서드 추가 (0.5h)

**작업 내용:**
1. 단일 레코드 조회
2. 단일 값 조회
3. 노드 생성/삭제 헬퍼

**src/infrastructure/database/neo4j.py (계속):**
```python
    async def execute_query_single(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
    ) -> dict[str, Any] | None:
        """Execute query and return single record.

        Args:
            query: Cypher query
            parameters: Query parameters
            database: Database name

        Returns:
            Single record dict or None
        """
        records = await self.execute_query(query, parameters, database)
        return records[0] if records else None

    async def execute_query_value(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        database: str | None = None,
        key: str = "value",
    ) -> Any:
        """Execute query and return single value.

        Args:
            query: Cypher query returning {key: value}
            parameters: Query parameters
            database: Database name
            key: Key to extract from result

        Returns:
            Single value or None
        """
        record = await self.execute_query_single(query, parameters, database)
        return record.get(key) if record else None

    async def count_nodes(self, label: str) -> int:
        """Count nodes with given label.

        Args:
            label: Node label

        Returns:
            Node count
        """
        result = await self.execute_query_value(
            f"MATCH (n:{label}) RETURN count(n) as value"
        )
        return result or 0

    async def node_exists(self, label: str, property_name: str, property_value: Any) -> bool:
        """Check if node exists.

        Args:
            label: Node label
            property_name: Property to check
            property_value: Property value

        Returns:
            True if node exists
        """
        result = await self.execute_query_value(
            f"MATCH (n:{label} {{{property_name}: $value}}) RETURN count(n) > 0 as value",
            {"value": property_value}
        )
        return result or False
```

**완료 기준:**
- [ ] execute_query_single 구현
- [ ] execute_query_value 구현
- [ ] count_nodes 구현
- [ ] node_exists 구현

---

### Step 4: Factory 및 테스트 (1h)

**작업 내용:**
1. Singleton factory 함수
2. __init__.py 업데이트
3. 테스트 작성

**src/infrastructure/database/neo4j.py (추가):**
```python
# Singleton instance
_client: Neo4jClient | None = None


def get_neo4j_client(settings: Neo4jSettings | None = None) -> Neo4jClient:
    """Get or create Neo4j client singleton."""
    global _client
    if _client is None:
        if settings is None:
            from src.config import get_settings
            settings = get_settings().neo4j
        _client = Neo4jClient(settings)
    return _client


async def close_neo4j_client() -> None:
    """Close the Neo4j client singleton."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
```

**tests/unit/test_infrastructure/test_neo4j_client.py:**
```python
"""Tests for Neo4j client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.database.neo4j import Neo4jClient
from src.config import Neo4jSettings


@pytest.fixture
def settings() -> Neo4jSettings:
    """Create test settings."""
    return Neo4jSettings(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="test_password",
    )


@pytest.fixture
def client(settings: Neo4jSettings) -> Neo4jClient:
    """Create test client."""
    return Neo4jClient(settings)


class TestNeo4jClient:
    """Tests for Neo4jClient."""

    async def test_connect_creates_driver(self, client: Neo4jClient) -> None:
        """Test that connect creates a driver."""
        mock_driver = AsyncMock()

        with patch.object(
            Neo4jClient,
            "_driver",
            None,
        ), patch(
            "neo4j.AsyncGraphDatabase.driver",
            return_value=mock_driver
        ):
            await client.connect()
            mock_driver.verify_connectivity.assert_called_once()

    async def test_close_closes_driver(self, client: Neo4jClient) -> None:
        """Test that close closes the driver."""
        mock_driver = AsyncMock()
        client._driver = mock_driver

        await client.close()

        mock_driver.close.assert_called_once()
        assert client._driver is None

    async def test_driver_not_connected_raises(self, client: Neo4jClient) -> None:
        """Test accessing driver before connect."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.driver

    async def test_ping_success(self, client: Neo4jClient) -> None:
        """Test ping returns True when connected."""
        mock_driver = AsyncMock()
        client._driver = mock_driver

        result = await client.ping()
        assert result is True
        mock_driver.verify_connectivity.assert_called_once()

    async def test_execute_query(self, client: Neo4jClient) -> None:
        """Test execute_query returns records."""
        mock_driver = AsyncMock()
        mock_session = AsyncMock()
        mock_result = AsyncMock()

        # Mock async iteration
        mock_record = MagicMock()
        mock_record.data.return_value = {"name": "test"}

        async def mock_iter():
            yield mock_record

        mock_result.__aiter__ = lambda self: mock_iter()
        mock_session.run = AsyncMock(return_value=mock_result)
        mock_driver.session.return_value.__aenter__.return_value = mock_session

        client._driver = mock_driver

        records = await client.execute_query("MATCH (n) RETURN n")
        assert len(records) == 1
        assert records[0]["name"] == "test"
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
| `test_connect_creates_driver` | connect 시 드라이버 생성 | verify_connectivity called |
| `test_close_closes_driver` | close 시 드라이버 종료 | driver.close() called |
| `test_driver_not_connected` | 미연결 시 드라이버 접근 | RuntimeError |
| `test_ping_success` | 연결 상태 ping | True |
| `test_execute_query` | 쿼리 실행 | 레코드 리스트 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_create_node` | 노드 생성 | 성공 |
| `test_create_relationship` | 관계 생성 | 성공 |
| `test_read_transaction` | 읽기 트랜잭션 | 결과 반환 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Connection timeout | Medium | Low | timeout 설정, 재시도 로직 |
| Transaction 충돌 | Medium | Low | execute_read/write 명확히 구분 |
| Memory leak (driver) | High | Low | close() 호출 보장 |

---

## 6. Definition of Done

- [ ] `src/infrastructure/database/neo4j.py` 구현
- [ ] connect/close/ping 구현
- [ ] session context manager 구현
- [ ] execute_read/write/query 구현
- [ ] 편의 메서드 구현
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 기본 구조 및 연결 | 1h | - |
| Step 2: Session 및 Transaction | 1.5h | - |
| Step 3: 편의 메서드 | 0.5h | - |
| Step 4: Factory 및 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
