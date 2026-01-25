# Task Execution Plan: 1.2.3 - 인프라 연결 테스트 스크립트

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.2.3 |
| **Task Name** | 인프라 연결 테스트 스크립트 |
| **Estimate** | 2h |
| **Priority** | P0 |
| **Dependencies** | Task 1.2.2 |

### Description
각 인프라 컴포넌트에 연결 가능한지 확인하는 스크립트를 작성합니다.

### Acceptance Criteria
- [ ] `scripts/check_infrastructure.py` 생성
- [ ] PostgreSQL 연결 테스트
- [ ] Milvus 연결 테스트
- [ ] Neo4j 연결 테스트
- [ ] Kafka 연결 테스트
- [ ] 모든 연결 성공 시 "All connections OK" 출력

---

## 2. Research & Design

### 2.1 참조 문서
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 4.2 Docker Compose Configuration
- **Task Breakdown**: Task 1.2.3 Technical Details

### 2.2 연결 정보
| Component | Host | Port | Library |
|-----------|------|------|---------|
| PostgreSQL | localhost | 5432 | asyncpg |
| Milvus | localhost | 19530 | pymilvus |
| Neo4j | localhost | 7687 | neo4j |
| Kafka | localhost | 9092 | aiokafka |

### 2.3 설계 결정
1. **비동기 연결**: asyncio 기반 병렬 연결 테스트
2. **환경 변수**: `.env` 파일에서 연결 정보 로드
3. **결과 출력**: 컬러 이모지로 상태 표시
4. **Exit Code**: 실패 시 1, 성공 시 0

---

## 3. Implementation Steps

### Step 1: 스크립트 기본 구조 작성 (0.5h)

**작업 내용:**
1. 필요한 라이브러리 import
2. 환경 변수 로드
3. 메인 함수 구조

**scripts/check_infrastructure.py:**
```python
#!/usr/bin/env python3
"""Infrastructure connectivity check script."""
import asyncio
import os
import sys
from typing import NamedTuple

# Load .env if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class ConnectionResult(NamedTuple):
    """Connection test result."""
    name: str
    success: bool
    message: str


def print_result(result: ConnectionResult) -> None:
    """Print connection result with emoji."""
    emoji = "✅" if result.success else "❌"
    print(f"{emoji} {result.name}: {result.message}")


async def main() -> int:
    """Run all connection tests."""
    results: list[ConnectionResult] = []

    # Run all connection tests
    results.append(await check_postgres())
    results.append(await check_milvus())
    results.append(await check_neo4j())
    results.append(await check_kafka())

    # Print results
    print("\n=== Infrastructure Connection Check ===\n")
    for result in results:
        print_result(result)

    # Summary
    failed = [r for r in results if not r.success]
    print()
    if failed:
        print(f"❌ {len(failed)} connection(s) failed")
        return 1
    else:
        print("✅ All connections OK!")
        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

**완료 기준:**
- [ ] 기본 스크립트 구조 완성
- [ ] 환경 변수 로드 설정

---

### Step 2: PostgreSQL 연결 테스트 (0.5h)

**작업 내용:**
1. asyncpg로 연결 테스트
2. 간단한 쿼리 실행
3. 연결 종료

**코드:**
```python
async def check_postgres() -> ConnectionResult:
    """Check PostgreSQL connection."""
    import asyncpg

    host = os.getenv("POSTGRES_HOST", "localhost")
    port = int(os.getenv("POSTGRES_PORT", "5432"))
    database = os.getenv("POSTGRES_DB", "knowledge_store")
    user = os.getenv("POSTGRES_USER", "ks_user")
    password = os.getenv("POSTGRES_PASSWORD", "ks_password")

    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            timeout=10,
        )
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        return ConnectionResult(
            name="PostgreSQL",
            success=True,
            message=f"Connected ({host}:{port})",
        )
    except Exception as e:
        return ConnectionResult(
            name="PostgreSQL",
            success=False,
            message=str(e),
        )
```

**완료 기준:**
- [ ] PostgreSQL 연결 성공
- [ ] 에러 핸들링 완료

---

### Step 3: Milvus 연결 테스트 (0.5h)

**작업 내용:**
1. pymilvus로 연결 테스트
2. 서버 버전 확인
3. 연결 종료

**코드:**
```python
async def check_milvus() -> ConnectionResult:
    """Check Milvus connection."""
    from pymilvus import connections, utility

    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")

    try:
        # Milvus SDK is synchronous, run in executor
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: connections.connect(
                alias="default",
                host=host,
                port=port,
                timeout=10,
            ),
        )

        # Check server version
        version = await loop.run_in_executor(
            None,
            utility.get_server_version,
        )

        # Disconnect
        await loop.run_in_executor(
            None,
            lambda: connections.disconnect("default"),
        )

        return ConnectionResult(
            name="Milvus",
            success=True,
            message=f"Connected ({host}:{port}) - v{version}",
        )
    except Exception as e:
        return ConnectionResult(
            name="Milvus",
            success=False,
            message=str(e),
        )
```

**완료 기준:**
- [ ] Milvus 연결 성공
- [ ] 버전 정보 출력

---

### Step 4: Neo4j 연결 테스트 (0.25h)

**작업 내용:**
1. neo4j 드라이버로 연결 테스트
2. 서버 정보 확인
3. 연결 종료

**코드:**
```python
async def check_neo4j() -> ConnectionResult:
    """Check Neo4j connection."""
    from neo4j import AsyncGraphDatabase

    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")

    try:
        driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        await driver.verify_connectivity()

        # Get server info
        async with driver.session() as session:
            result = await session.run("RETURN 1 as test")
            await result.consume()

        await driver.close()

        return ConnectionResult(
            name="Neo4j",
            success=True,
            message=f"Connected ({uri})",
        )
    except Exception as e:
        return ConnectionResult(
            name="Neo4j",
            success=False,
            message=str(e),
        )
```

**완료 기준:**
- [ ] Neo4j 연결 성공
- [ ] 쿼리 실행 확인

---

### Step 5: Kafka 연결 테스트 (0.25h)

**작업 내용:**
1. aiokafka로 Producer 연결 테스트
2. 브로커 연결 확인
3. 연결 종료

**코드:**
```python
async def check_kafka() -> ConnectionResult:
    """Check Kafka connection."""
    from aiokafka import AIOKafkaProducer

    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

    try:
        producer = AIOKafkaProducer(
            bootstrap_servers=bootstrap_servers,
            request_timeout_ms=10000,
        )
        await producer.start()
        await producer.stop()

        return ConnectionResult(
            name="Kafka",
            success=True,
            message=f"Connected ({bootstrap_servers})",
        )
    except Exception as e:
        return ConnectionResult(
            name="Kafka",
            success=False,
            message=str(e),
        )
```

**완료 기준:**
- [ ] Kafka 연결 성공
- [ ] Producer 시작/종료 정상

---

## 4. Testing Plan

### 4.1 Manual Tests
| Test | Command | Expected |
|------|---------|----------|
| 스크립트 실행 | `python scripts/check_infrastructure.py` | 모든 연결 OK |
| 개별 실패 | 서비스 중지 후 실행 | 해당 서비스 실패 표시 |
| Exit code | `echo $?` | 성공: 0, 실패: 1 |

### 4.2 Connection Tests
| Component | Test Method | Expected |
|-----------|-------------|----------|
| PostgreSQL | asyncpg connect | ✅ Connected |
| Milvus | pymilvus connect | ✅ Connected |
| Neo4j | driver verify_connectivity | ✅ Connected |
| Kafka | producer start/stop | ✅ Connected |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 라이브러리 미설치 | High | Medium | `pip install -e ".[dev]"` 안내 |
| 타임아웃 | Medium | Low | 적절한 timeout 설정 (10s) |
| 동기 SDK (Milvus) | Low | Low | run_in_executor 사용 |

---

## 6. Definition of Done

- [ ] `scripts/check_infrastructure.py` 생성
- [ ] 4개 서비스 연결 테스트 구현
- [ ] 모든 연결 성공 시 "All connections OK" 출력
- [ ] 실패 시 exit code 1 반환
- [ ] 에러 메시지 명확하게 출력

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 기본 구조 | 0.5h | - |
| Step 2: PostgreSQL | 0.5h | - |
| Step 3: Milvus | 0.5h | - |
| Step 4: Neo4j | 0.25h | - |
| Step 5: Kafka | 0.25h | - |
| **Total** | **2h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
