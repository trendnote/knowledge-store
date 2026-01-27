# Task 1.3.1 Implementation Log

## Task Information

| Item | Value |
|------|-------|
| **Task ID** | 1.3.1 |
| **Task Name** | PostgreSQL 스키마 마이그레이션 |
| **GitHub Issue** | [#6](https://github.com/trendnote/knowledge-store/issues/6) |
| **Task Plan** | [task-1.3.1-plan.md](../docs/task-plans/task-1.3.1-plan.md) |
| **Date** | 2026-01-28 |
| **Status** | Completed |

---

## Summary

Knowledge Store Layer의 PostgreSQL 스키마를 생성했습니다. 5개 테이블, 27개 인덱스, 5개 FK 제약조건, 2개 트리거가 성공적으로 생성되었습니다.

---

## Implementation Details

### Step 1: SQL 스키마 파일 작성

**scripts/sql/001_create_tables.sql:**

| Table | Columns | Indexes | Purpose |
|-------|---------|---------|---------|
| documents | 11 | 7 | 정본 문서 메타데이터 |
| document_versions | 11 | 4 | 버전 관리 |
| document_chunks | 13 | 5 | 청크 ID 매핑 |
| acl_entries | 8 | 4 | 권한 관리 |
| audit_logs | 14 | 7 | 감사 로그 |

**주요 기능:**
- CHECK 제약조건 (source, status, security_level 등)
- UNIQUE 제약조건 (doc_uuid + version_no, 등)
- 자동 updated_at 트리거
- 버전 번호 순차 검증 트리거

### Step 2: Python 초기화 스크립트 작성

**scripts/init_postgres.py:**
- `--reset`: 기존 테이블 삭제 후 재생성
- `--verify`: 스키마 검증만 수행
- 환경 변수 기반 연결 설정
- 상세 검증 결과 출력

### Step 3: 스키마 검증

```
Tables:
  documents: 0 rows, 7 indexes
  document_versions: 0 rows, 4 indexes
  document_chunks: 0 rows, 5 indexes
  acl_entries: 0 rows, 4 indexes
  audit_logs: 0 rows, 7 indexes

Indexes: 27/27 expected
Foreign Keys: 5 (all correct)
Triggers: 2 (update_documents_updated_at, validate_version_number_trigger)
```

---

## Output Files

### Created Files

1. **scripts/sql/001_create_tables.sql**
   - 5개 테이블 DDL
   - 27개 인덱스 정의
   - FK 제약조건
   - 트리거 함수

2. **scripts/init_postgres.py**
   - SQL 파일 실행
   - 스키마 검증
   - --reset, --verify 옵션

---

## Schema Details

### 1. documents Table
```sql
doc_uuid        UUID PRIMARY KEY
title           VARCHAR(500) NOT NULL
source          VARCHAR(50) CHECK (wiki, agit, gdocs, slack, confluence, notion, file)
source_url      VARCHAR(2000) NOT NULL
owner_id        VARCHAR(100) NOT NULL
owner_org       VARCHAR(100) NOT NULL
status          VARCHAR(20) DEFAULT 'draft' CHECK (draft, published, archived)
security_level  VARCHAR(20) DEFAULT 'internal' CHECK (public, internal, confidential)
current_version_id UUID FK -> document_versions
created_at      TIMESTAMP WITH TIME ZONE
updated_at      TIMESTAMP WITH TIME ZONE
```

### 2. document_versions Table
```sql
version_id      UUID PRIMARY KEY
doc_uuid        UUID FK -> documents (CASCADE)
version_no      INTEGER NOT NULL
content_hash    VARCHAR(64) NOT NULL
effective_from  TIMESTAMP WITH TIME ZONE
approved_by     VARCHAR(100)
UNIQUE(doc_uuid, version_no)
```

### 3. document_chunks Table
```sql
chunk_uuid      UUID PRIMARY KEY
doc_uuid        UUID FK -> documents (CASCADE)
version_id      UUID FK -> document_versions (CASCADE)
chunk_no        INTEGER NOT NULL
section_path    VARCHAR(500)
chunk_text      TEXT
milvus_id       VARCHAR(100)
neo4j_node_id   VARCHAR(100)
UNIQUE(version_id, chunk_no)
```

### 4. acl_entries Table
```sql
id              UUID PRIMARY KEY
doc_uuid        UUID FK -> documents (CASCADE)
principal_type  VARCHAR(20) CHECK (user, group, org, role)
principal_id    VARCHAR(100) NOT NULL
permission      VARCHAR(20) CHECK (read, write, admin, delete)
UNIQUE(doc_uuid, principal_type, principal_id, permission)
```

### 5. audit_logs Table
```sql
log_id          UUID PRIMARY KEY
user_id         VARCHAR(100) NOT NULL
action          VARCHAR(50) CHECK (search, view, create, update, delete, export, share, permission_change)
resource_type   VARCHAR(50) DEFAULT 'document'
doc_uuid        UUID
query_text      TEXT
retrieved_docs  UUID[]
metadata        JSONB DEFAULT '{}'
timestamp       TIMESTAMP WITH TIME ZONE
```

---

## Acceptance Criteria Checklist

- [x] `scripts/init_postgres.py` 생성
- [x] `documents` 테이블 생성
- [x] `document_versions` 테이블 생성
- [x] `document_chunks` 테이블 생성
- [x] `acl_entries` 테이블 생성
- [x] `audit_logs` 테이블 생성
- [x] 모든 인덱스 생성 (27개)
- [x] FK 제약조건 설정 (5개)

---

## Definition of Done

- [x] `scripts/sql/001_create_tables.sql` 생성
- [x] `scripts/init_postgres.py` 생성
- [x] 5개 테이블 생성 완료
- [x] 모든 인덱스 생성 완료
- [x] FK 제약조건 설정 완료
- [x] `--reset` 옵션 작동
- [x] 중복 실행 시 에러 없음 (IF NOT EXISTS)
- [x] 코드 품질 검증 (ruff, mypy)

---

## Usage

```bash
# 스키마 초기화
python scripts/init_postgres.py

# 스키마 재초기화 (데이터 삭제)
python scripts/init_postgres.py --reset

# 스키마 검증만
python scripts/init_postgres.py --verify

# psql로 직접 확인
docker exec -it knowledge-store-postgres psql -U ks_user -d knowledge_store
\dt  # 테이블 목록
\di  # 인덱스 목록
\d documents  # 테이블 상세
```

---

## Next Steps

- **Task 1.3.2**: Milvus 컬렉션 생성
  - Dense vector 컬렉션 설정
  - Sparse vector 컬렉션 설정
  - 인덱스 생성

---

## Notes

- FK 순환 참조 해결: documents.current_version_id는 ALTER TABLE로 나중에 추가
- 버전 번호 순차 검증: 트리거로 version_no가 순차적으로 증가하도록 보장
- 감사 로그는 파티셔닝 고려 필요 (대용량 시)
