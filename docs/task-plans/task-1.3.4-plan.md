# Task Execution Plan: 1.3.4 - 스키마 초기화 통합 스크립트

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.3.4 |
| **Task Name** | 스키마 초기화 통합 스크립트 |
| **Estimate** | 2h |
| **Priority** | P1 |
| **Dependencies** | Task 1.3.1, 1.3.2, 1.3.3 |

### Description
모든 데이터베이스 스키마를 한 번에 초기화하는 통합 스크립트를 작성합니다.

### Acceptance Criteria
- [ ] `scripts/init_all.py` 생성
- [ ] PostgreSQL, Milvus, Neo4j 순서대로 초기화
- [ ] 이미 존재하는 경우 스킵 또는 재생성 옵션
- [ ] 초기화 결과 출력

---

## 2. Research & Design

### 2.1 참조 문서
- **Task 1.3.1**: `scripts/init_postgres.py`
- **Task 1.3.2**: `scripts/init_milvus.py`
- **Task 1.3.3**: `scripts/init_neo4j.py`

### 2.2 초기화 순서
```
1. PostgreSQL (메타데이터 저장소 - 정본)
   └── documents, document_versions, document_chunks, acl_entries, audit_logs

2. Milvus (벡터 저장소)
   └── knowledge_chunks collection

3. Neo4j (그래프 저장소)
   └── Constraints, Indexes
```

### 2.3 설계 결정
1. **순차 실행**: 의존성 순서 (PostgreSQL → Milvus → Neo4j)
2. **개별 결과 수집**: 각 저장소 초기화 결과 추적
3. **옵션**: `--reset`, `--postgres-only`, `--milvus-only`, `--neo4j-only`
4. **출력 형식**: 컬러 이모지 + 요약 테이블

---

## 3. Implementation Steps

### Step 1: 스크립트 기본 구조 (0.5h)

**작업 내용:**
1. 인자 파싱 (argparse)
2. 결과 추적 클래스
3. 메인 함수 구조

**scripts/init_all.py (Part 1):**
```python
#!/usr/bin/env python3
"""Initialize all database schemas."""
import argparse
import asyncio
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class Status(Enum):
    """Initialization status."""
    SUCCESS = "✅"
    SKIPPED = "⏭️"
    FAILED = "❌"
    PENDING = "⏳"


@dataclass
class InitResult:
    """Result of initialization."""
    name: str
    status: Status
    message: str
    duration_seconds: float = 0.0


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Initialize all Knowledge Store schemas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/init_all.py              # Initialize all (skip existing)
  python scripts/init_all.py --reset      # Reset and reinitialize all
  python scripts/init_all.py --postgres-only  # PostgreSQL only
  python scripts/init_all.py --check      # Check status only
        """,
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop existing schemas and recreate",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check connection status only (no changes)",
    )
    parser.add_argument(
        "--postgres-only",
        action="store_true",
        help="Initialize PostgreSQL only",
    )
    parser.add_argument(
        "--milvus-only",
        action="store_true",
        help="Initialize Milvus only",
    )
    parser.add_argument(
        "--neo4j-only",
        action="store_true",
        help="Initialize Neo4j only",
    )

    return parser.parse_args()
```

**완료 기준:**
- [ ] argparse 설정 완료
- [ ] 결과 클래스 정의

---

### Step 2: 개별 초기화 함수 (1h)

**작업 내용:**
1. PostgreSQL 초기화 함수
2. Milvus 초기화 함수
3. Neo4j 초기화 함수

**scripts/init_all.py (Part 2):**
```python
import time
import os

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def init_postgres(reset: bool = False) -> InitResult:
    """Initialize PostgreSQL schema."""
    start_time = time.time()
    name = "PostgreSQL"

    try:
        # Import and run init_postgres functions
        from scripts.init_postgres import main as postgres_main

        exit_code = await postgres_main(reset=reset)

        duration = time.time() - start_time
        if exit_code == 0:
            return InitResult(name, Status.SUCCESS, "Schema initialized", duration)
        else:
            return InitResult(name, Status.FAILED, "Initialization failed", duration)

    except ImportError:
        # Fallback to subprocess
        script_path = Path(__file__).parent / "init_postgres.py"
        cmd = [sys.executable, str(script_path)]
        if reset:
            cmd.append("--reset")

        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = time.time() - start_time

        if result.returncode == 0:
            return InitResult(name, Status.SUCCESS, "Schema initialized", duration)
        else:
            return InitResult(name, Status.FAILED, result.stderr[:200], duration)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e), duration)


def init_milvus(reset: bool = False) -> InitResult:
    """Initialize Milvus collection."""
    start_time = time.time()
    name = "Milvus"

    try:
        script_path = Path(__file__).parent / "init_milvus.py"
        cmd = [sys.executable, str(script_path)]
        if reset:
            cmd.append("--reset")

        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = time.time() - start_time

        if result.returncode == 0:
            return InitResult(name, Status.SUCCESS, "Collection initialized", duration)
        else:
            error_msg = result.stderr[:200] if result.stderr else "Unknown error"
            return InitResult(name, Status.FAILED, error_msg, duration)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e), duration)


async def init_neo4j(reset: bool = False) -> InitResult:
    """Initialize Neo4j schema."""
    start_time = time.time()
    name = "Neo4j"

    try:
        script_path = Path(__file__).parent / "init_neo4j.py"
        cmd = [sys.executable, str(script_path)]
        if reset:
            cmd.append("--reset")

        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = time.time() - start_time

        if result.returncode == 0:
            return InitResult(name, Status.SUCCESS, "Constraints/Indexes created", duration)
        else:
            error_msg = result.stderr[:200] if result.stderr else "Unknown error"
            return InitResult(name, Status.FAILED, error_msg, duration)
    except Exception as e:
        duration = time.time() - start_time
        return InitResult(name, Status.FAILED, str(e), duration)


async def check_connections() -> list[InitResult]:
    """Check all connections without making changes."""
    results = []

    # PostgreSQL
    try:
        import asyncpg
        conn = await asyncpg.connect(
            host=os.getenv("POSTGRES_HOST", "localhost"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DB", "knowledge_store"),
            user=os.getenv("POSTGRES_USER", "ks_user"),
            password=os.getenv("POSTGRES_PASSWORD", "ks_password"),
            timeout=5,
        )
        await conn.close()
        results.append(InitResult("PostgreSQL", Status.SUCCESS, "Connected"))
    except Exception as e:
        results.append(InitResult("PostgreSQL", Status.FAILED, str(e)[:100]))

    # Milvus
    try:
        from pymilvus import connections
        connections.connect(
            alias="check",
            host=os.getenv("MILVUS_HOST", "localhost"),
            port=os.getenv("MILVUS_PORT", "19530"),
            timeout=5,
        )
        connections.disconnect("check")
        results.append(InitResult("Milvus", Status.SUCCESS, "Connected"))
    except Exception as e:
        results.append(InitResult("Milvus", Status.FAILED, str(e)[:100]))

    # Neo4j
    try:
        from neo4j import AsyncGraphDatabase
        driver = AsyncGraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(
                os.getenv("NEO4J_USER", "neo4j"),
                os.getenv("NEO4J_PASSWORD", "neo4j_password"),
            ),
        )
        await driver.verify_connectivity()
        await driver.close()
        results.append(InitResult("Neo4j", Status.SUCCESS, "Connected"))
    except Exception as e:
        results.append(InitResult("Neo4j", Status.FAILED, str(e)[:100]))

    return results
```

**완료 기준:**
- [ ] PostgreSQL 초기화 함수
- [ ] Milvus 초기화 함수
- [ ] Neo4j 초기화 함수
- [ ] 연결 확인 함수

---

### Step 3: 메인 함수 및 출력 (0.5h)

**작업 내용:**
1. 결과 요약 출력
2. 종합 exit code 반환
3. 실행 로직

**scripts/init_all.py (Part 3):**
```python
def print_results(results: list[InitResult]) -> None:
    """Print results summary."""
    print("\n" + "=" * 60)
    print("                 INITIALIZATION SUMMARY")
    print("=" * 60 + "\n")

    # Table header
    print(f"{'Component':<15} {'Status':<10} {'Duration':<12} {'Message'}")
    print("-" * 60)

    # Table rows
    for r in results:
        duration_str = f"{r.duration_seconds:.1f}s" if r.duration_seconds > 0 else "-"
        status_str = r.status.value
        message = r.message[:35] + "..." if len(r.message) > 35 else r.message
        print(f"{r.name:<15} {status_str:<10} {duration_str:<12} {message}")

    print("-" * 60)

    # Summary
    success_count = sum(1 for r in results if r.status == Status.SUCCESS)
    failed_count = sum(1 for r in results if r.status == Status.FAILED)
    total_time = sum(r.duration_seconds for r in results)

    print(f"\nTotal: {success_count} succeeded, {failed_count} failed")
    print(f"Time: {total_time:.1f}s")

    if failed_count == 0:
        print("\n✅ All initializations completed successfully!")
    else:
        print(f"\n❌ {failed_count} initialization(s) failed")


async def main() -> int:
    """Main function."""
    args = parse_args()

    print("\n" + "=" * 60)
    print("       KNOWLEDGE STORE - SCHEMA INITIALIZATION")
    print("=" * 60 + "\n")

    # Check mode
    if args.check:
        print("🔍 Checking connections...\n")
        results = await check_connections()
        print_results(results)
        failed = any(r.status == Status.FAILED for r in results)
        return 1 if failed else 0

    # Determine which to initialize
    init_postgres_flag = not (args.milvus_only or args.neo4j_only)
    init_milvus_flag = not (args.postgres_only or args.neo4j_only)
    init_neo4j_flag = not (args.postgres_only or args.milvus_only)

    if args.reset:
        print("⚠️  RESET MODE: Existing schemas will be dropped!\n")

    results: list[InitResult] = []

    # Initialize in order
    if init_postgres_flag:
        print("📦 [1/3] Initializing PostgreSQL...")
        result = await init_postgres(reset=args.reset)
        results.append(result)
        print(f"   {result.status.value} {result.message}\n")

    if init_milvus_flag:
        print("📦 [2/3] Initializing Milvus...")
        result = init_milvus(reset=args.reset)
        results.append(result)
        print(f"   {result.status.value} {result.message}\n")

    if init_neo4j_flag:
        print("📦 [3/3] Initializing Neo4j...")
        result = await init_neo4j(reset=args.reset)
        results.append(result)
        print(f"   {result.status.value} {result.message}\n")

    # Print summary
    print_results(results)

    # Return exit code
    failed = any(r.status == Status.FAILED for r in results)
    return 1 if failed else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
```

**완료 기준:**
- [ ] 결과 요약 출력 구현
- [ ] exit code 반환
- [ ] CLI 옵션 처리

---

## 4. Testing Plan

### 4.1 CLI Tests
| Command | Expected |
|---------|----------|
| `python scripts/init_all.py --check` | 연결 상태 확인 |
| `python scripts/init_all.py` | 전체 초기화 |
| `python scripts/init_all.py --reset` | 전체 재초기화 |
| `python scripts/init_all.py --postgres-only` | PostgreSQL만 |
| `python scripts/init_all.py --milvus-only` | Milvus만 |
| `python scripts/init_all.py --neo4j-only` | Neo4j만 |

### 4.2 Result Verification
| Check | Expected |
|-------|----------|
| 성공 시 exit code | 0 |
| 실패 시 exit code | 1 |
| 결과 테이블 | 3개 컴포넌트 표시 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 개별 스크립트 미존재 | High | Low | 의존성 체크 및 에러 메시지 |
| 부분 실패 | Medium | Medium | 개별 결과 추적 및 계속 진행 |
| 순서 의존성 | Low | Low | 독립적 초기화 (FK 제외) |

---

## 6. Definition of Done

- [ ] `scripts/init_all.py` 생성
- [ ] `--reset` 옵션 작동
- [ ] `--check` 옵션 작동
- [ ] `--postgres-only`, `--milvus-only`, `--neo4j-only` 옵션 작동
- [ ] 결과 요약 테이블 출력
- [ ] 중복 실행 시 에러 없음
- [ ] 부분 실패 시 나머지 계속 진행

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 기본 구조 | 0.5h | - |
| Step 2: 개별 초기화 함수 | 1h | - |
| Step 3: 메인 함수 및 출력 | 0.5h | - |
| **Total** | **2h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
