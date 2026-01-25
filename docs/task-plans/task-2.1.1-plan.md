# Task Execution Plan: 2.1.1 - PostgreSQL Client 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 2.1.1 |
| **Task Name** | PostgreSQL Client 구현 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.3.1 |

### Description
asyncpg 기반 PostgreSQL 연결 및 Connection Pool을 관리하는 클라이언트를 구현합니다.

### Acceptance Criteria
- [ ] `src/infrastructure/database/postgres.py` 생성
- [ ] Connection Pool 생성/종료 메서드
- [ ] 트랜잭션 컨텍스트 매니저
- [ ] 연결 상태 확인 (ping)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 4.4 Infrastructure Layer
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 3.1 Core Dependencies

### 2.2 asyncpg 주요 기능
```python
# Connection Pool
pool = await asyncpg.create_pool(
    dsn=dsn,
    min_size=5,
    max_size=20,
    command_timeout=60.0
)

# Transaction
async with pool.acquire() as conn:
    async with conn.transaction():
        await conn.execute(...)
```

### 2.3 설계 결정
1. **Async-First**: asyncpg 사용 (동기 psycopg2 대신)
2. **Connection Pool**: 재사용으로 연결 오버헤드 감소
3. **Context Manager**: 트랜잭션 자동 관리
4. **Type Hints**: 완전한 타입 힌트 적용

### 2.4 클래스 구조
```
PostgresClient
├── __init__(settings: PostgresSettings)
├── connect() -> None
├── disconnect() -> None
├── ping() -> bool
├── acquire() -> Connection (context manager)
├── transaction() -> Transaction (context manager)
├── execute(query, *args) -> str
├── fetch(query, *args) -> list[Record]
├── fetchrow(query, *args) -> Record | None
└── fetchval(query, *args) -> Any
```

---

## 3. Implementation Steps

### Step 1: 기본 클래스 구조 및 연결 관리 (1h)

**작업 내용:**
1. PostgresClient 클래스 정의
2. connect/disconnect 메서드
3. ping 메서드

**src/infrastructure/database/postgres.py:**
```python
"""PostgreSQL async client with connection pooling."""
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from asyncpg import Pool, Connection, Record

from src.config import PostgresSettings


class PostgresClient:
    """Async PostgreSQL client with connection pool management."""

    def __init__(self, settings: PostgresSettings) -> None:
        """Initialize PostgreSQL client.

        Args:
            settings: PostgreSQL connection settings
        """
        self._settings = settings
        self._pool: Pool | None = None

    @property
    def pool(self) -> Pool:
        """Get connection pool (raises if not connected)."""
        if self._pool is None:
            raise RuntimeError("PostgresClient is not connected. Call connect() first.")
        return self._pool

    async def connect(self) -> None:
        """Create connection pool."""
        if self._pool is not None:
            return

        self._pool = await asyncpg.create_pool(
            dsn=self._settings.dsn,
            min_size=5,
            max_size=self._settings.pool_size,
            command_timeout=60.0,
            statement_cache_size=100,
        )

    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        """Check if database is reachable."""
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False
```

**완료 기준:**
- [ ] 클래스 기본 구조 완성
- [ ] connect/disconnect 구현
- [ ] ping 구현

---

### Step 2: Context Manager 및 쿼리 메서드 (1.5h)

**작업 내용:**
1. acquire context manager
2. transaction context manager
3. execute, fetch, fetchrow, fetchval 메서드

**src/infrastructure/database/postgres.py (계속):**
```python
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool.

        Usage:
            async with client.acquire() as conn:
                await conn.execute(...)
        """
        async with self.pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self):
        """Create a transaction context.

        Usage:
            async with client.transaction() as conn:
                await conn.execute(...)  # Auto commit on success
                # Auto rollback on exception
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query and return status.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Command status string (e.g., 'INSERT 0 1')
        """
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[Record]:
        """Execute a query and return all rows.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            List of Record objects
        """
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Record | None:
        """Execute a query and return first row.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single Record or None
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Execute a query and return first column of first row.

        Args:
            query: SQL query
            *args: Query parameters

        Returns:
            Single value
        """
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)
```

**완료 기준:**
- [ ] acquire context manager 구현
- [ ] transaction context manager 구현
- [ ] 쿼리 메서드 4개 구현

---

### Step 3: Factory 함수 및 __init__.py (0.5h)

**작업 내용:**
1. get_postgres_client factory 함수
2. 모듈 export 설정

**src/infrastructure/database/postgres.py (추가):**
```python
# Singleton instance
_client: PostgresClient | None = None


def get_postgres_client(settings: PostgresSettings | None = None) -> PostgresClient:
    """Get or create PostgreSQL client singleton.

    Args:
        settings: PostgreSQL settings (required on first call)

    Returns:
        PostgresClient instance
    """
    global _client
    if _client is None:
        if settings is None:
            from src.config import get_settings
            settings = get_settings().postgres
        _client = PostgresClient(settings)
    return _client


async def close_postgres_client() -> None:
    """Close the PostgreSQL client singleton."""
    global _client
    if _client is not None:
        await _client.disconnect()
        _client = None
```

**src/infrastructure/database/__init__.py:**
```python
"""Database infrastructure clients."""
from src.infrastructure.database.postgres import (
    PostgresClient,
    get_postgres_client,
    close_postgres_client,
)

__all__ = [
    "PostgresClient",
    "get_postgres_client",
    "close_postgres_client",
]
```

**완료 기준:**
- [ ] Factory 함수 구현
- [ ] __init__.py export 설정

---

### Step 4: 테스트 작성 (1h)

**작업 내용:**
1. 연결/종료 테스트
2. 트랜잭션 커밋/롤백 테스트
3. 쿼리 메서드 테스트

**tests/unit/test_infrastructure/test_postgres_client.py:**
```python
"""Tests for PostgreSQL client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.database.postgres import PostgresClient
from src.config import PostgresSettings


@pytest.fixture
def settings() -> PostgresSettings:
    """Create test settings."""
    return PostgresSettings(
        host="localhost",
        port=5432,
        db="test_db",
        user="test_user",
        password="test_pass",
    )


@pytest.fixture
def client(settings: PostgresSettings) -> PostgresClient:
    """Create test client."""
    return PostgresClient(settings)


class TestPostgresClient:
    """Tests for PostgresClient."""

    async def test_connect_creates_pool(self, client: PostgresClient) -> None:
        """Test that connect creates a connection pool."""
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as mock_pool:
            mock_pool.return_value = MagicMock()
            await client.connect()
            mock_pool.assert_called_once()
            assert client._pool is not None

    async def test_disconnect_closes_pool(self, client: PostgresClient) -> None:
        """Test that disconnect closes the pool."""
        mock_pool = AsyncMock()
        client._pool = mock_pool
        await client.disconnect()
        mock_pool.close.assert_called_once()
        assert client._pool is None

    async def test_ping_success(self, client: PostgresClient) -> None:
        """Test ping returns True when connected."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        client._pool = mock_pool

        result = await client.ping()
        assert result is True

    async def test_ping_failure(self, client: PostgresClient) -> None:
        """Test ping returns False when disconnected."""
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.side_effect = Exception("Connection failed")
        client._pool = mock_pool

        result = await client.ping()
        assert result is False

    async def test_pool_not_connected_raises(self, client: PostgresClient) -> None:
        """Test accessing pool before connect raises error."""
        with pytest.raises(RuntimeError, match="not connected"):
            _ = client.pool

    async def test_transaction_commits_on_success(self, client: PostgresClient) -> None:
        """Test transaction commits when no exception."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_txn = AsyncMock()
        mock_conn.transaction.return_value.__aenter__.return_value = mock_txn
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        client._pool = mock_pool

        async with client.transaction() as conn:
            await conn.execute("INSERT INTO test VALUES (1)")

        # Transaction context manager handles commit automatically

    async def test_fetch_returns_records(self, client: PostgresClient) -> None:
        """Test fetch returns list of records."""
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[{"id": 1}, {"id": 2}])
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        client._pool = mock_pool

        result = await client.fetch("SELECT * FROM test")
        assert len(result) == 2
```

**완료 기준:**
- [ ] 연결/종료 테스트 작성
- [ ] ping 테스트 작성
- [ ] 트랜잭션 테스트 작성
- [ ] 쿼리 메서드 테스트 작성

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_connect_creates_pool` | connect 호출 시 pool 생성 | pool != None |
| `test_disconnect_closes_pool` | disconnect 호출 시 pool 종료 | pool.close() called |
| `test_ping_success` | 연결 성공 시 | True |
| `test_ping_failure` | 연결 실패 시 | False |
| `test_pool_not_connected_raises` | 미연결 시 pool 접근 | RuntimeError |
| `test_transaction_commits` | 정상 트랜잭션 | 커밋 |
| `test_transaction_rollback` | 예외 시 트랜잭션 | 롤백 |

### 4.2 Integration Tests (with real DB)
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_real_connection` | 실제 DB 연결 | Success |
| `test_real_transaction` | 실제 트랜잭션 | Commit/Rollback |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Connection Pool 고갈 | High | Low | max_size 설정, 타임아웃 설정 |
| 비동기 컨텍스트 누수 | Medium | Low | asynccontextmanager 사용 |
| 타입 힌트 누락 | Low | Low | mypy strict 모드 사용 |

---

## 6. Definition of Done

- [ ] `src/infrastructure/database/postgres.py` 구현
- [ ] `src/infrastructure/database/__init__.py` 설정
- [ ] Connection Pool 관리 (connect/disconnect)
- [ ] 트랜잭션 컨텍스트 매니저
- [ ] ping 메서드
- [ ] 쿼리 메서드 (execute, fetch, fetchrow, fetchval)
- [ ] 모든 단위 테스트 통과
- [ ] mypy 타입 체크 통과
- [ ] ruff 린트 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 기본 구조 및 연결 | 1h | - |
| Step 2: Context Manager 및 쿼리 | 1.5h | - |
| Step 3: Factory 및 export | 0.5h | - |
| Step 4: 테스트 작성 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
