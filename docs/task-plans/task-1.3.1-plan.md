# Task Execution Plan: 1.3.1 - PostgreSQL 스키마 마이그레이션

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.3.1 |
| **Task Name** | PostgreSQL 스키마 마이그레이션 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.2.2 |

### Description
Architecture 문서의 PostgreSQL 스키마를 생성합니다.

### Acceptance Criteria
- [ ] `scripts/init_postgres.py` 생성
- [ ] `documents` 테이블 생성
- [ ] `document_versions` 테이블 생성
- [ ] `document_chunks` 테이블 생성
- [ ] `acl_entries` 테이블 생성
- [ ] `audit_logs` 테이블 생성
- [ ] 모든 인덱스 생성
- [ ] FK 제약조건 설정

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 6.1 PostgreSQL Schema

### 2.2 테이블 구조
```
documents (정본 관리)
├── doc_uuid (PK)
├── title
├── source
├── source_url
├── owner_id
├── owner_org
├── status
├── security_level
├── current_version_id (FK)
├── created_at
└── updated_at

document_versions (버전 관리)
├── version_id (PK)
├── doc_uuid (FK → documents)
├── version_no
├── content_hash
├── effective_from
├── approved_by
└── created_at

document_chunks (청크 ID 매핑)
├── chunk_uuid (PK)
├── doc_uuid (FK → documents)
├── version_id (FK → document_versions)
├── chunk_no
├── section_path
├── milvus_id
├── neo4j_node_id
└── created_at

acl_entries (권한 관리)
├── id (PK)
├── doc_uuid (FK → documents)
├── principal_type
├── principal_id
├── permission
└── created_at

audit_logs (감사 로그)
├── log_id (PK)
├── user_id
├── action
├── doc_uuid
├── query_text
├── retrieved_docs
├── metadata
└── timestamp
```

### 2.3 인덱스 전략
| Table | Index | Columns | Purpose |
|-------|-------|---------|---------|
| documents | idx_documents_owner | owner_id | 소유자 조회 |
| documents | idx_documents_status | status | 상태별 필터 |
| documents | idx_documents_security | security_level | 보안 레벨 필터 |
| document_versions | idx_versions_doc | doc_uuid | 문서별 버전 조회 |
| document_chunks | idx_chunks_doc | doc_uuid | 문서별 청크 조회 |
| document_chunks | idx_chunks_milvus | milvus_id | Milvus ID 조회 |
| acl_entries | idx_acl_principal | principal_type, principal_id | ACL 조회 |
| audit_logs | idx_audit_user | user_id | 사용자별 로그 |
| audit_logs | idx_audit_timestamp | timestamp | 시간순 조회 |

---

## 3. Implementation Steps

### Step 1: SQL 스키마 파일 작성 (1.5h)

**작업 내용:**
1. `scripts/sql/001_create_tables.sql` 작성
2. 모든 테이블 정의
3. 인덱스 및 제약조건 정의

**scripts/sql/001_create_tables.sql:**
```sql
-- Knowledge Store PostgreSQL Schema
-- Version: 1.0.0
-- Date: 2026-01-25

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =====================
-- 1. Documents Table
-- =====================
CREATE TABLE IF NOT EXISTS documents (
    doc_uuid        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR(500) NOT NULL,
    source          VARCHAR(50) NOT NULL CHECK (source IN ('wiki', 'agit', 'gdocs', 'slack', 'confluence', 'notion')),
    source_url      VARCHAR(2000) NOT NULL,
    owner_id        VARCHAR(100) NOT NULL,
    owner_org       VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
    security_level  VARCHAR(20) NOT NULL DEFAULT 'internal' CHECK (security_level IN ('public', 'internal', 'confidential')),
    current_version_id UUID,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Documents Indexes
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_security ON documents(security_level);
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);

-- =====================
-- 2. Document Versions Table
-- =====================
CREATE TABLE IF NOT EXISTS document_versions (
    version_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    content_hash    VARCHAR(64) NOT NULL,
    effective_from  TIMESTAMP WITH TIME ZONE,
    approved_by     VARCHAR(100),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doc_uuid, version_no)
);

-- Versions Indexes
CREATE INDEX IF NOT EXISTS idx_versions_doc ON document_versions(doc_uuid);
CREATE INDEX IF NOT EXISTS idx_versions_effective ON document_versions(effective_from);

-- =====================
-- 3. Document Chunks Table
-- =====================
CREATE TABLE IF NOT EXISTS document_chunks (
    chunk_uuid      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    version_id      UUID NOT NULL REFERENCES document_versions(version_id) ON DELETE CASCADE,
    chunk_no        INTEGER NOT NULL,
    section_path    VARCHAR(500),
    chunk_text      TEXT,
    milvus_id       VARCHAR(100),
    neo4j_node_id   VARCHAR(100),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chunks Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(doc_uuid);
CREATE INDEX IF NOT EXISTS idx_chunks_version ON document_chunks(version_id);
CREATE INDEX IF NOT EXISTS idx_chunks_milvus ON document_chunks(milvus_id);
CREATE INDEX IF NOT EXISTS idx_chunks_neo4j ON document_chunks(neo4j_node_id);

-- =====================
-- 4. ACL Entries Table
-- =====================
CREATE TABLE IF NOT EXISTS acl_entries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_uuid        UUID NOT NULL REFERENCES documents(doc_uuid) ON DELETE CASCADE,
    principal_type  VARCHAR(20) NOT NULL CHECK (principal_type IN ('user', 'group', 'org')),
    principal_id    VARCHAR(100) NOT NULL,
    permission      VARCHAR(20) NOT NULL CHECK (permission IN ('read', 'write', 'admin')),
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(doc_uuid, principal_type, principal_id)
);

-- ACL Indexes
CREATE INDEX IF NOT EXISTS idx_acl_doc ON acl_entries(doc_uuid);
CREATE INDEX IF NOT EXISTS idx_acl_principal ON acl_entries(principal_type, principal_id);

-- =====================
-- 5. Audit Logs Table
-- =====================
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         VARCHAR(100) NOT NULL,
    action          VARCHAR(50) NOT NULL CHECK (action IN ('search', 'view', 'create', 'update', 'delete')),
    doc_uuid        UUID,
    query_text      TEXT,
    retrieved_docs  UUID[],
    metadata        JSONB DEFAULT '{}',
    timestamp       TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Audit Indexes
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_doc ON audit_logs(doc_uuid) WHERE doc_uuid IS NOT NULL;

-- =====================
-- 6. Add FK for current_version_id
-- =====================
ALTER TABLE documents
    ADD CONSTRAINT fk_current_version
    FOREIGN KEY (current_version_id)
    REFERENCES document_versions(version_id)
    ON DELETE SET NULL;

-- =====================
-- 7. Updated_at Trigger Function
-- =====================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Apply trigger to documents table
DROP TRIGGER IF EXISTS update_documents_updated_at ON documents;
CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

**완료 기준:**
- [ ] 5개 테이블 DDL 완성
- [ ] 모든 인덱스 정의
- [ ] FK 제약조건 정의

---

### Step 2: Python 초기화 스크립트 작성 (1.5h)

**작업 내용:**
1. `scripts/init_postgres.py` 작성
2. SQL 파일 실행 로직
3. 결과 확인 로직

**scripts/init_postgres.py:**
```python
#!/usr/bin/env python3
"""Initialize PostgreSQL schema."""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

# Load .env if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def get_connection() -> asyncpg.Connection:
    """Get PostgreSQL connection."""
    return await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "knowledge_store"),
        user=os.getenv("POSTGRES_USER", "ks_user"),
        password=os.getenv("POSTGRES_PASSWORD", "ks_password"),
    )


async def execute_sql_file(conn: asyncpg.Connection, filepath: Path) -> None:
    """Execute SQL file."""
    print(f"📄 Executing: {filepath.name}")
    sql = filepath.read_text()
    await conn.execute(sql)
    print(f"   ✅ Done")


async def verify_tables(conn: asyncpg.Connection) -> bool:
    """Verify all tables exist."""
    expected_tables = [
        "documents",
        "document_versions",
        "document_chunks",
        "acl_entries",
        "audit_logs",
    ]

    query = """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        AND table_name = ANY($1)
    """
    rows = await conn.fetch(query, expected_tables)
    found_tables = {row["table_name"] for row in rows}

    print("\n📊 Table Verification:")
    all_ok = True
    for table in expected_tables:
        if table in found_tables:
            print(f"   ✅ {table}")
        else:
            print(f"   ❌ {table} (NOT FOUND)")
            all_ok = False

    return all_ok


async def verify_indexes(conn: asyncpg.Connection) -> None:
    """Verify indexes exist."""
    query = """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        AND indexname LIKE 'idx_%'
    """
    rows = await conn.fetch(query)
    print(f"\n📊 Indexes Created: {len(rows)}")
    for row in rows:
        print(f"   • {row['indexname']}")


async def reset_schema(conn: asyncpg.Connection) -> None:
    """Drop all tables and recreate schema."""
    print("🗑️  Dropping existing tables...")
    await conn.execute("""
        DROP TABLE IF EXISTS audit_logs CASCADE;
        DROP TABLE IF EXISTS acl_entries CASCADE;
        DROP TABLE IF EXISTS document_chunks CASCADE;
        DROP TABLE IF EXISTS document_versions CASCADE;
        DROP TABLE IF EXISTS documents CASCADE;
    """)
    print("   ✅ Tables dropped")


async def main(reset: bool = False) -> int:
    """Main function."""
    print("\n=== PostgreSQL Schema Initialization ===\n")

    try:
        conn = await get_connection()
        print("✅ Connected to PostgreSQL\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1

    try:
        # Reset if requested
        if reset:
            await reset_schema(conn)

        # Execute SQL files
        sql_dir = Path(__file__).parent / "sql"
        sql_files = sorted(sql_dir.glob("*.sql"))

        if not sql_files:
            print("❌ No SQL files found in scripts/sql/")
            return 1

        for sql_file in sql_files:
            await execute_sql_file(conn, sql_file)

        # Verify
        tables_ok = await verify_tables(conn)
        await verify_indexes(conn)

        if tables_ok:
            print("\n✅ Schema initialization complete!")
            return 0
        else:
            print("\n❌ Schema initialization incomplete")
            return 1

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1
    finally:
        await conn.close()


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    exit_code = asyncio.run(main(reset=reset_flag))
    sys.exit(exit_code)
```

**완료 기준:**
- [ ] SQL 파일 실행 성공
- [ ] 테이블 검증 로직 구현
- [ ] `--reset` 옵션 구현

---

### Step 3: 검증 및 테스트 (1h)

**작업 내용:**
1. 스크립트 실행
2. 테이블 존재 확인
3. 인덱스 확인
4. FK 확인

**검증 명령어:**
```bash
# 스키마 초기화
python scripts/init_postgres.py

# 재초기화 (기존 데이터 삭제)
python scripts/init_postgres.py --reset

# psql로 직접 확인
docker exec -it knowledge-store-postgres psql -U ks_user -d knowledge_store

# 테이블 확인
\dt

# 인덱스 확인
\di

# 특정 테이블 구조 확인
\d documents
```

**완료 기준:**
- [ ] 5개 테이블 생성 확인
- [ ] 모든 인덱스 생성 확인
- [ ] FK 제약조건 확인

---

## 4. Testing Plan

### 4.1 Schema Verification
| Check | Method | Expected |
|-------|--------|----------|
| 테이블 수 | `\dt` | 5개 테이블 |
| 인덱스 수 | `\di` | 15개+ 인덱스 |
| FK 제약조건 | `\d documents` | current_version_id FK |

### 4.2 Script Tests
| Test | Command | Expected |
|------|---------|----------|
| 초기 실행 | `python scripts/init_postgres.py` | Success |
| 중복 실행 | `python scripts/init_postgres.py` | Success (IF NOT EXISTS) |
| 리셋 | `python scripts/init_postgres.py --reset` | Success |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| FK 순환 참조 | High | Low | documents.current_version_id는 나중에 ALTER |
| 기존 데이터 손실 | High | Low | `--reset` 플래그로 명시적 삭제 |
| 권한 부족 | Medium | Low | ks_user에 CREATE 권한 확인 |

---

## 6. Definition of Done

- [ ] `scripts/sql/001_create_tables.sql` 생성
- [ ] `scripts/init_postgres.py` 생성
- [ ] 5개 테이블 생성 완료
- [ ] 모든 인덱스 생성 완료
- [ ] FK 제약조건 설정 완료
- [ ] `--reset` 옵션 작동
- [ ] 중복 실행 시 에러 없음

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: SQL 스키마 파일 | 1.5h | - |
| Step 2: Python 스크립트 | 1.5h | - |
| Step 3: 검증 및 테스트 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
