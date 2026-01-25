# Task Execution Plan: 1.3.2 - Milvus Collection 생성

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.3.2 |
| **Task Name** | Milvus Collection 생성 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.2.2 |

### Description
Architecture 문서의 Milvus Collection 스키마를 생성합니다.

### Acceptance Criteria
- [ ] `scripts/init_milvus.py` 생성
- [ ] `knowledge_chunks` Collection 생성
- [ ] 필드 정의 (chunk_uuid, doc_uuid, dense_embedding, sparse_embedding, ...)
- [ ] HNSW 인덱스 생성 (dense_embedding)
- [ ] SPARSE_INVERTED_INDEX 생성 (sparse_embedding)
- [ ] Collection 로드 확인

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 6.2 Milvus Collection Schema
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 2.2 Vector DB

### 2.2 Collection 스키마
```
knowledge_chunks
├── chunk_uuid (VARCHAR, PK) - 청크 고유 ID
├── doc_uuid (VARCHAR) - 문서 ID
├── dense_embedding (FLOAT_VECTOR[1024]) - BGE-M3 Dense
├── sparse_embedding (SPARSE_FLOAT_VECTOR) - BGE-M3 Sparse
├── chunk_text (VARCHAR) - 청크 텍스트
├── section_path (VARCHAR) - 섹션 경로
├── security_level (VARCHAR) - 보안 레벨
├── allowed_groups (ARRAY<VARCHAR>) - 허용 그룹
└── created_at (INT64) - 생성 시간 (Unix timestamp)
```

### 2.3 인덱스 설정
| Field | Index Type | Metric | Parameters |
|-------|------------|--------|------------|
| dense_embedding | HNSW | COSINE | M=16, efConstruction=256 |
| sparse_embedding | SPARSE_INVERTED_INDEX | IP | - |

### 2.4 설계 결정
1. **Primary Key**: `chunk_uuid` (VARCHAR, auto_id=False)
2. **Dense Vector**: 1024 차원 (BGE-M3)
3. **Sparse Vector**: BM25 기반 lexical weights
4. **Partition**: 없음 (PoC 규모)

---

## 3. Implementation Steps

### Step 1: Collection 스키마 정의 (1h)

**작업 내용:**
1. FieldSchema 정의
2. CollectionSchema 정의
3. 유틸리티 함수 작성

**scripts/init_milvus.py (Part 1):**
```python
#!/usr/bin/env python3
"""Initialize Milvus collection."""
import os
import sys
import time

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

# Load .env if exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuration
COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "knowledge_chunks")
DENSE_DIM = 1024  # BGE-M3 dense embedding dimension


def get_collection_schema() -> CollectionSchema:
    """Define collection schema."""
    fields = [
        # Primary Key
        FieldSchema(
            name="chunk_uuid",
            dtype=DataType.VARCHAR,
            max_length=36,
            is_primary=True,
            auto_id=False,
            description="Chunk unique identifier (UUID)",
        ),
        # Document reference
        FieldSchema(
            name="doc_uuid",
            dtype=DataType.VARCHAR,
            max_length=36,
            description="Document unique identifier",
        ),
        # Dense embedding (BGE-M3)
        FieldSchema(
            name="dense_embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=DENSE_DIM,
            description="BGE-M3 dense embedding (1024d)",
        ),
        # Sparse embedding (BM25)
        FieldSchema(
            name="sparse_embedding",
            dtype=DataType.SPARSE_FLOAT_VECTOR,
            description="BGE-M3 sparse embedding (BM25)",
        ),
        # Chunk text
        FieldSchema(
            name="chunk_text",
            dtype=DataType.VARCHAR,
            max_length=8000,
            description="Chunk text content",
        ),
        # Section path
        FieldSchema(
            name="section_path",
            dtype=DataType.VARCHAR,
            max_length=500,
            description="Section path in document",
        ),
        # Security level
        FieldSchema(
            name="security_level",
            dtype=DataType.VARCHAR,
            max_length=20,
            description="Security level (public/internal/confidential)",
        ),
        # Allowed groups (for ACL filtering)
        FieldSchema(
            name="allowed_groups",
            dtype=DataType.ARRAY,
            element_type=DataType.VARCHAR,
            max_length=100,
            max_capacity=50,
            description="List of allowed groups",
        ),
        # Created timestamp
        FieldSchema(
            name="created_at",
            dtype=DataType.INT64,
            description="Creation timestamp (Unix)",
        ),
    ]

    schema = CollectionSchema(
        fields=fields,
        description="Knowledge Store Chunks - Hybrid Search Collection",
        enable_dynamic_field=False,
    )

    return schema
```

**완료 기준:**
- [ ] 9개 필드 정의 완료
- [ ] CollectionSchema 생성

---

### Step 2: 인덱스 정의 및 생성 함수 (1h)

**작업 내용:**
1. HNSW 인덱스 파라미터 정의
2. Sparse 인덱스 파라미터 정의
3. 인덱스 생성 함수

**scripts/init_milvus.py (Part 2):**
```python
def create_indexes(collection: Collection) -> None:
    """Create indexes for the collection."""

    # Dense embedding index (HNSW)
    print("📊 Creating HNSW index for dense_embedding...")
    dense_index_params = {
        "index_type": "HNSW",
        "metric_type": "COSINE",
        "params": {
            "M": 16,  # Max edges per node
            "efConstruction": 256,  # Construction time accuracy
        },
    }
    collection.create_index(
        field_name="dense_embedding",
        index_params=dense_index_params,
        index_name="idx_dense_hnsw",
    )
    print("   ✅ HNSW index created")

    # Sparse embedding index
    print("📊 Creating SPARSE_INVERTED_INDEX for sparse_embedding...")
    sparse_index_params = {
        "index_type": "SPARSE_INVERTED_INDEX",
        "metric_type": "IP",  # Inner Product for sparse
        "params": {
            "drop_ratio_build": 0.2,  # Drop low-value terms during build
        },
    }
    collection.create_index(
        field_name="sparse_embedding",
        index_params=sparse_index_params,
        index_name="idx_sparse_inverted",
    )
    print("   ✅ Sparse index created")

    # Scalar indexes for filtering
    print("📊 Creating scalar indexes...")
    collection.create_index(
        field_name="doc_uuid",
        index_name="idx_doc_uuid",
    )
    collection.create_index(
        field_name="security_level",
        index_name="idx_security_level",
    )
    print("   ✅ Scalar indexes created")
```

**완료 기준:**
- [ ] HNSW 인덱스 파라미터 정의
- [ ] Sparse 인덱스 파라미터 정의
- [ ] 스칼라 인덱스 정의

---

### Step 3: 메인 함수 및 검증 로직 (1h)

**작업 내용:**
1. Collection 생성 함수
2. 검증 함수
3. 메인 실행 로직

**scripts/init_milvus.py (Part 3):**
```python
def connect_milvus() -> None:
    """Connect to Milvus server."""
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")

    print(f"🔗 Connecting to Milvus ({host}:{port})...")
    connections.connect(
        alias="default",
        host=host,
        port=port,
    )
    print("   ✅ Connected")


def create_collection(reset: bool = False) -> Collection:
    """Create or get collection."""

    # Check if collection exists
    if utility.has_collection(COLLECTION_NAME):
        if reset:
            print(f"🗑️  Dropping existing collection: {COLLECTION_NAME}")
            utility.drop_collection(COLLECTION_NAME)
            print("   ✅ Collection dropped")
        else:
            print(f"📦 Collection exists: {COLLECTION_NAME}")
            return Collection(COLLECTION_NAME)

    # Create new collection
    print(f"📦 Creating collection: {COLLECTION_NAME}")
    schema = get_collection_schema()
    collection = Collection(
        name=COLLECTION_NAME,
        schema=schema,
        using="default",
    )
    print("   ✅ Collection created")

    return collection


def verify_collection(collection: Collection) -> bool:
    """Verify collection setup."""
    print("\n📊 Collection Verification:")

    # Check schema
    schema = collection.schema
    print(f"   Fields: {len(schema.fields)}")
    for field in schema.fields:
        pk_marker = " (PK)" if field.is_primary else ""
        print(f"      • {field.name}: {field.dtype.name}{pk_marker}")

    # Check indexes
    indexes = collection.indexes
    print(f"   Indexes: {len(indexes)}")
    for idx in indexes:
        print(f"      • {idx.field_name}: {idx.params.get('index_type', 'SCALAR')}")

    # Load collection
    print("\n📥 Loading collection into memory...")
    collection.load()
    print("   ✅ Collection loaded")

    # Get stats
    stats = collection.num_entities
    print(f"   Entities: {stats}")

    return True


def simple_insert_test(collection: Collection) -> bool:
    """Test simple insert and delete."""
    import uuid

    print("\n🧪 Running simple insert test...")

    test_uuid = str(uuid.uuid4())
    test_data = {
        "chunk_uuid": [test_uuid],
        "doc_uuid": ["test-doc-001"],
        "dense_embedding": [[0.1] * DENSE_DIM],
        "sparse_embedding": [{"hello": 0.5, "world": 0.3}],
        "chunk_text": ["This is a test chunk."],
        "section_path": ["/test/section"],
        "security_level": ["internal"],
        "allowed_groups": [["group1", "group2"]],
        "created_at": [int(time.time())],
    }

    # Insert
    collection.insert(test_data)
    collection.flush()
    print(f"   ✅ Inserted test entity: {test_uuid}")

    # Simple search
    search_params = {
        "metric_type": "COSINE",
        "params": {"ef": 64},
    }
    results = collection.search(
        data=[[0.1] * DENSE_DIM],
        anns_field="dense_embedding",
        param=search_params,
        limit=1,
        output_fields=["chunk_uuid", "chunk_text"],
    )
    print(f"   ✅ Search returned {len(results[0])} result(s)")

    # Delete
    collection.delete(f'chunk_uuid == "{test_uuid}"')
    collection.flush()
    print(f"   ✅ Deleted test entity")

    return True


def main(reset: bool = False) -> int:
    """Main function."""
    print("\n=== Milvus Collection Initialization ===\n")

    try:
        connect_milvus()
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1

    try:
        # Create/get collection
        collection = create_collection(reset=reset)

        # Create indexes if new collection
        if not collection.indexes or reset:
            create_indexes(collection)

        # Verify
        verify_collection(collection)

        # Simple test
        simple_insert_test(collection)

        print("\n✅ Milvus initialization complete!")
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        connections.disconnect("default")


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv
    exit_code = main(reset=reset_flag)
    sys.exit(exit_code)
```

**완료 기준:**
- [ ] Collection 생성/조회 함수
- [ ] 검증 로직 구현
- [ ] 간단한 삽입/검색/삭제 테스트

---

### Step 4: 실행 및 검증 (1h)

**작업 내용:**
1. 스크립트 실행
2. Collection 확인
3. 인덱스 상태 확인

**검증 명령어:**
```bash
# Collection 초기화
python scripts/init_milvus.py

# 재초기화
python scripts/init_milvus.py --reset

# Milvus 상태 확인 (HTTP API)
curl http://localhost:9091/healthz

# Attu Web UI (설치된 경우)
open http://localhost:3000
```

**완료 기준:**
- [ ] Collection 생성 확인
- [ ] 인덱스 상태 확인
- [ ] 삽입/검색 테스트 통과

---

## 4. Testing Plan

### 4.1 Collection Verification
| Check | Method | Expected |
|-------|--------|----------|
| Collection 존재 | `utility.has_collection()` | True |
| 필드 수 | `len(schema.fields)` | 9 |
| 인덱스 수 | `len(indexes)` | 4 |

### 4.2 Functional Tests
| Test | Description | Expected |
|------|-------------|----------|
| Insert | 테스트 데이터 삽입 | Success |
| Search | Dense 벡터 검색 | 결과 반환 |
| Delete | 테스트 데이터 삭제 | Success |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Sparse Vector 지원 미비 | High | Low | Milvus 2.5+ 버전 확인 |
| 메모리 부족 | Medium | Medium | Collection load 전 확인 |
| 인덱스 빌드 시간 | Low | Low | PoC 규모에서는 문제 없음 |

---

## 6. Definition of Done

- [ ] `scripts/init_milvus.py` 생성
- [ ] 9개 필드 정의 완료
- [ ] HNSW 인덱스 생성 완료
- [ ] SPARSE_INVERTED_INDEX 생성 완료
- [ ] Collection 로드 성공
- [ ] 삽입/검색/삭제 테스트 통과
- [ ] `--reset` 옵션 작동

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 스키마 정의 | 1h | - |
| Step 2: 인덱스 정의 | 1h | - |
| Step 3: 메인 함수 | 1h | - |
| Step 4: 실행 및 검증 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
