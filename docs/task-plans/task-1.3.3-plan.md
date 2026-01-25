# Task Execution Plan: 1.3.3 - Neo4j 온톨로지 구축

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.3.3 |
| **Task Name** | Neo4j 온톨로지 구축 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.2.2 |

### Description
Architecture 문서의 Neo4j 스키마(제약조건, 인덱스)를 생성합니다.

### Acceptance Criteria
- [ ] `scripts/init_neo4j.py` 생성
- [ ] Unique Constraints 생성 (doc_uuid, chunk_uuid, emp_id, org_id)
- [ ] 검색용 인덱스 생성 (title, text_preview, name)
- [ ] 제약조건/인덱스 생성 확인

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 6.3 Neo4j Graph Schema

### 2.2 Node Labels
| Label | Purpose | Key Properties |
|-------|---------|----------------|
| Document | 문서 노드 | doc_uuid, title, source, security_level |
| Chunk | 청크 노드 | chunk_uuid, sequence, text_preview, section_path |
| Person | 사람 노드 | emp_id, name, department, role, email |
| Organization | 조직 노드 | org_id, name, parent_org_id |
| Project | 프로젝트 노드 | project_id, name, status |
| Policy | 정책 노드 | policy_id, name, effective_from |

### 2.3 Relationship Types
| Type | From | To | Properties |
|------|------|----|-----------|
| WROTE | Person | Document | created_at |
| CONTAINS | Document | Chunk | sequence |
| MENTIONS | Chunk | Entity | confidence |
| MANAGES | Person | Project | role |
| BELONGS_TO | Person | Organization | joined_at |
| HAS_POLICY | Organization | Policy | - |

### 2.4 Constraints & Indexes
**Unique Constraints:**
```cypher
(:Document {doc_uuid})
(:Chunk {chunk_uuid})
(:Person {emp_id})
(:Organization {org_id})
(:Project {project_id})
(:Policy {policy_id})
```

**Search Indexes:**
```cypher
(:Document {title})
(:Chunk {text_preview})
(:Person {name})
(:Organization {name})
```

---

## 3. Implementation Steps

### Step 1: Cypher 스키마 정의 (1h)

**작업 내용:**
1. Constraint 생성 Cypher 문
2. Index 생성 Cypher 문
3. 초기 데이터 검증 쿼리

**scripts/cypher/001_constraints.cypher:**
```cypher
// =====================
// Unique Constraints
// =====================

// Document - doc_uuid must be unique
CREATE CONSTRAINT doc_uuid_unique IF NOT EXISTS
FOR (d:Document) REQUIRE d.doc_uuid IS UNIQUE;

// Chunk - chunk_uuid must be unique
CREATE CONSTRAINT chunk_uuid_unique IF NOT EXISTS
FOR (c:Chunk) REQUIRE c.chunk_uuid IS UNIQUE;

// Person - emp_id must be unique
CREATE CONSTRAINT person_emp_id_unique IF NOT EXISTS
FOR (p:Person) REQUIRE p.emp_id IS UNIQUE;

// Organization - org_id must be unique
CREATE CONSTRAINT org_id_unique IF NOT EXISTS
FOR (o:Organization) REQUIRE o.org_id IS UNIQUE;

// Project - project_id must be unique
CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (proj:Project) REQUIRE proj.project_id IS UNIQUE;

// Policy - policy_id must be unique
CREATE CONSTRAINT policy_id_unique IF NOT EXISTS
FOR (pol:Policy) REQUIRE pol.policy_id IS UNIQUE;
```

**scripts/cypher/002_indexes.cypher:**
```cypher
// =====================
// Search Indexes
// =====================

// Document title index for text search
CREATE INDEX doc_title_idx IF NOT EXISTS
FOR (d:Document) ON (d.title);

// Document source index for filtering
CREATE INDEX doc_source_idx IF NOT EXISTS
FOR (d:Document) ON (d.source);

// Document security level index
CREATE INDEX doc_security_idx IF NOT EXISTS
FOR (d:Document) ON (d.security_level);

// Chunk text preview index
CREATE INDEX chunk_text_idx IF NOT EXISTS
FOR (c:Chunk) ON (c.text_preview);

// Chunk sequence index for ordering
CREATE INDEX chunk_sequence_idx IF NOT EXISTS
FOR (c:Chunk) ON (c.sequence);

// Person name index for search
CREATE INDEX person_name_idx IF NOT EXISTS
FOR (p:Person) ON (p.name);

// Person department index for filtering
CREATE INDEX person_dept_idx IF NOT EXISTS
FOR (p:Person) ON (p.department);

// Organization name index
CREATE INDEX org_name_idx IF NOT EXISTS
FOR (o:Organization) ON (o.name);

// Project name index
CREATE INDEX project_name_idx IF NOT EXISTS
FOR (proj:Project) ON (proj.name);

// Policy name index
CREATE INDEX policy_name_idx IF NOT EXISTS
FOR (pol:Policy) ON (pol.name);
```

**완료 기준:**
- [ ] 6개 Unique Constraint 정의
- [ ] 10개 Search Index 정의

---

### Step 2: Python 초기화 스크립트 (1.5h)

**작업 내용:**
1. Neo4j 연결 함수
2. Cypher 파일 실행 함수
3. 검증 함수

**scripts/init_neo4j.py:**
```python
#!/usr/bin/env python3
"""Initialize Neo4j schema (constraints and indexes)."""
import asyncio
import os
import sys
from pathlib import Path

from neo4j import AsyncGraphDatabase

# Load .env if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def get_driver():
    """Get Neo4j async driver."""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")

    return AsyncGraphDatabase.driver(uri, auth=(user, password))


async def execute_cypher_file(driver, filepath: Path) -> None:
    """Execute Cypher file."""
    print(f"📄 Executing: {filepath.name}")

    # Read and split Cypher statements
    content = filepath.read_text()

    # Remove comments and split by semicolon
    statements = []
    for line in content.split('\n'):
        line = line.strip()
        if line and not line.startswith('//'):
            statements.append(line)

    cypher_text = ' '.join(statements)
    cypher_statements = [s.strip() for s in cypher_text.split(';') if s.strip()]

    async with driver.session() as session:
        for statement in cypher_statements:
            if statement:
                try:
                    await session.run(statement)
                    print(f"   ✅ Executed: {statement[:60]}...")
                except Exception as e:
                    if "already exists" in str(e).lower():
                        print(f"   ℹ️  Already exists: {statement[:60]}...")
                    else:
                        print(f"   ❌ Error: {e}")
                        raise


async def verify_constraints(driver) -> int:
    """Verify constraints exist."""
    print("\n📊 Constraints:")

    async with driver.session() as session:
        result = await session.run("SHOW CONSTRAINTS")
        records = [record async for record in result]

        for record in records:
            name = record.get("name", "unnamed")
            entity = record.get("labelsOrTypes", [])
            properties = record.get("properties", [])
            print(f"   • {name}: {entity} {properties}")

        return len(records)


async def verify_indexes(driver) -> int:
    """Verify indexes exist."""
    print("\n📊 Indexes:")

    async with driver.session() as session:
        result = await session.run("SHOW INDEXES")
        records = [record async for record in result]

        # Filter out constraint-backed indexes
        search_indexes = [r for r in records if r.get("type") != "RANGE"]

        for record in records:
            name = record.get("name", "unnamed")
            idx_type = record.get("type", "unknown")
            entity = record.get("labelsOrTypes", [])
            properties = record.get("properties", [])
            print(f"   • {name}: {idx_type} on {entity} {properties}")

        return len(records)


async def reset_schema(driver) -> None:
    """Drop all constraints and indexes."""
    print("🗑️  Dropping existing constraints and indexes...")

    async with driver.session() as session:
        # Drop constraints
        result = await session.run("SHOW CONSTRAINTS")
        constraints = [record async for record in result]
        for constraint in constraints:
            name = constraint.get("name")
            if name:
                await session.run(f"DROP CONSTRAINT {name} IF EXISTS")
                print(f"   Dropped constraint: {name}")

        # Drop indexes (non-constraint)
        result = await session.run("SHOW INDEXES")
        indexes = [record async for record in result]
        for index in indexes:
            name = index.get("name")
            unique_type = index.get("uniqueness")
            if name and unique_type != "UNIQUE":
                try:
                    await session.run(f"DROP INDEX {name} IF EXISTS")
                    print(f"   Dropped index: {name}")
                except Exception:
                    pass  # Some indexes can't be dropped

        # Clear all nodes (optional, for full reset)
        await session.run("MATCH (n) DETACH DELETE n")
        print("   Cleared all nodes")

    print("   ✅ Reset complete")


async def simple_test(driver) -> bool:
    """Run simple create/query/delete test."""
    print("\n🧪 Running simple test...")

    async with driver.session() as session:
        # Create test document
        await session.run("""
            CREATE (d:Document {
                doc_uuid: 'test-doc-001',
                title: 'Test Document',
                source: 'wiki',
                security_level: 'internal',
                created_at: datetime()
            })
        """)
        print("   ✅ Created test document")

        # Query
        result = await session.run("""
            MATCH (d:Document {doc_uuid: 'test-doc-001'})
            RETURN d.title as title
        """)
        record = await result.single()
        if record and record["title"] == "Test Document":
            print("   ✅ Query successful")

        # Delete
        await session.run("""
            MATCH (d:Document {doc_uuid: 'test-doc-001'})
            DELETE d
        """)
        print("   ✅ Deleted test document")

    return True


async def main(reset: bool = False) -> int:
    """Main function."""
    print("\n=== Neo4j Schema Initialization ===\n")

    try:
        driver = await get_driver()
        await driver.verify_connectivity()
        print("✅ Connected to Neo4j\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1

    try:
        # Reset if requested
        if reset:
            await reset_schema(driver)

        # Execute Cypher files
        cypher_dir = Path(__file__).parent / "cypher"
        cypher_files = sorted(cypher_dir.glob("*.cypher"))

        if not cypher_files:
            print("❌ No Cypher files found in scripts/cypher/")
            return 1

        for cypher_file in cypher_files:
            await execute_cypher_file(driver, cypher_file)

        # Verify
        constraint_count = await verify_constraints(driver)
        index_count = await verify_indexes(driver)

        print(f"\n📈 Summary:")
        print(f"   Constraints: {constraint_count}")
        print(f"   Indexes: {index_count}")

        # Simple test
        await simple_test(driver)

        print("\n✅ Neo4j initialization complete!")
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await driver.close()


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    exit_code = asyncio.run(main(reset=reset_flag))
    sys.exit(exit_code)
```

**완료 기준:**
- [ ] Neo4j 연결 함수 구현
- [ ] Cypher 파일 실행 함수 구현
- [ ] 검증 함수 구현

---

### Step 3: 디렉토리 구조 생성 및 실행 (0.5h)

**작업 내용:**
1. `scripts/cypher/` 디렉토리 생성
2. Cypher 파일 저장
3. 스크립트 실행

**명령어:**
```bash
# 디렉토리 생성
mkdir -p scripts/cypher

# 스크립트 실행
python scripts/init_neo4j.py

# 재초기화
python scripts/init_neo4j.py --reset
```

**완료 기준:**
- [ ] Cypher 파일 생성
- [ ] 스크립트 실행 성공

---

### Step 4: 검증 및 테스트 (1h)

**작업 내용:**
1. Neo4j Browser에서 확인
2. Constraint 확인
3. Index 확인
4. 간단한 쿼리 테스트

**검증 쿼리:**
```cypher
// Constraint 확인
SHOW CONSTRAINTS;

// Index 확인
SHOW INDEXES;

// 테스트 노드 생성
CREATE (d:Document {doc_uuid: 'test-001', title: 'Test'})
RETURN d;

// 조회
MATCH (d:Document {doc_uuid: 'test-001'}) RETURN d;

// 삭제
MATCH (d:Document {doc_uuid: 'test-001'}) DELETE d;

// Constraint 위반 테스트 (중복 생성 시 에러)
CREATE (d1:Document {doc_uuid: 'dup-001', title: 'First'});
CREATE (d2:Document {doc_uuid: 'dup-001', title: 'Second'});
// Expected: ConstraintValidationFailed
```

**완료 기준:**
- [ ] 6개 Constraint 생성 확인
- [ ] 10개 Index 생성 확인
- [ ] CRUD 테스트 통과

---

## 4. Testing Plan

### 4.1 Schema Verification
| Check | Query | Expected |
|-------|-------|----------|
| Constraints | `SHOW CONSTRAINTS` | 6개 |
| Indexes | `SHOW INDEXES` | 10개+ |

### 4.2 Functional Tests
| Test | Description | Expected |
|------|-------------|----------|
| Create | 노드 생성 | Success |
| Query | doc_uuid로 조회 | 결과 반환 |
| Constraint | 중복 doc_uuid | Error |
| Delete | 노드 삭제 | Success |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| APOC 미설치 | Medium | Low | Community 기본 기능만 사용 |
| Cypher 문법 오류 | Medium | Low | IF NOT EXISTS 사용 |
| 기존 데이터 영향 | High | Low | `--reset` 옵션 신중히 사용 |

---

## 6. Definition of Done

- [ ] `scripts/cypher/001_constraints.cypher` 생성
- [ ] `scripts/cypher/002_indexes.cypher` 생성
- [ ] `scripts/init_neo4j.py` 생성
- [ ] 6개 Unique Constraint 생성
- [ ] 10개 Search Index 생성
- [ ] 간단한 CRUD 테스트 통과
- [ ] `--reset` 옵션 작동

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Cypher 스키마 정의 | 1h | - |
| Step 2: Python 스크립트 | 1.5h | - |
| Step 3: 디렉토리 및 실행 | 0.5h | - |
| Step 4: 검증 및 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
