# Task 1.3.2 Implementation Log

## Task Information

| Item | Value |
|------|-------|
| **Task ID** | 1.3.2 |
| **Task Name** | Milvus Collection 생성 |
| **GitHub Issue** | [#7](https://github.com/trendnote/knowledge-store/issues/7) |
| **Task Plan** | [task-1.3.2-plan.md](../docs/task-plans/task-1.3.2-plan.md) |
| **Date** | 2026-01-28 |
| **Status** | Completed |

---

## Summary

Knowledge Store Layer의 Milvus Collection을 생성했습니다. BGE-M3 기반의 Dense/Sparse 하이브리드 검색을 지원하는 `knowledge_chunks` Collection이 성공적으로 생성되었습니다.

---

## Implementation Details

### Step 1: Collection 스키마 정의

**12개 필드 정의:**

| Field | Type | Description |
|-------|------|-------------|
| chunk_uuid | VARCHAR(36) | Primary Key |
| doc_uuid | VARCHAR(36) | 문서 ID |
| version_id | VARCHAR(36) | 버전 ID |
| dense_embedding | FLOAT_VECTOR[1024] | BGE-M3 Dense |
| sparse_embedding | SPARSE_FLOAT_VECTOR | BGE-M3 Sparse |
| chunk_text | VARCHAR(16000) | 청크 텍스트 |
| section_path | VARCHAR(500) | 섹션 경로 |
| chunk_no | INT64 | 청크 번호 |
| security_level | VARCHAR(20) | 보안 레벨 |
| owner_org | VARCHAR(100) | 소유 조직 |
| allowed_groups | ARRAY<VARCHAR> | 허용 그룹 |
| created_at | INT64 | 생성 시간 |

### Step 2: 인덱스 생성

| Index | Field | Type | Parameters |
|-------|-------|------|------------|
| idx_dense_hnsw | dense_embedding | HNSW | M=16, efConstruction=256, COSINE |
| idx_sparse_inverted | sparse_embedding | SPARSE_INVERTED_INDEX | IP, drop_ratio=0.2 |
| idx_doc_uuid | doc_uuid | SCALAR | - |
| idx_security_level | security_level | SCALAR | - |
| idx_owner_org | owner_org | SCALAR | - |

### Step 3: 기능 테스트

```
Insert: OK
Dense Search: OK (HNSW COSINE)
Hybrid Search: OK (RRF Reranking)
Delete: OK
```

---

## Output Files

### Created Files

1. **scripts/init_milvus.py**
   - Collection 스키마 정의
   - 인덱스 생성
   - Insert/Search/Delete 테스트
   - --reset, --verify 옵션

---

## Test Results

```
============================================================
  Milvus Collection Initialization
============================================================

  Target: localhost:19531
  Connection: OK
  Mode: Reset (DROP + CREATE)

  Creating collection: knowledge_chunks
  Collection created

  Creating indexes...
    HNSW index for dense_embedding... Done
    SPARSE_INVERTED_INDEX for sparse_embedding... Done
    Scalar indexes... Done

  Verification:
    Fields: 12
    Indexes: 5

  Loading collection into memory...
  Collection loaded
  Entities: 0

  Running functional test...
    Insert: OK (chunk_uuid=447f755d...)
    Dense Search: OK (found 1 result)
    Hybrid Search: OK (found 1 result)
    Delete: OK

  Initialization: SUCCESS
```

---

## Acceptance Criteria Checklist

- [x] `scripts/init_milvus.py` 생성
- [x] `knowledge_chunks` Collection 생성
- [x] 필드 정의 (12개)
- [x] HNSW 인덱스 생성 (dense_embedding)
- [x] SPARSE_INVERTED_INDEX 생성 (sparse_embedding)
- [x] Collection 로드 확인
- [x] Insert/Search/Delete 테스트 통과

---

## Definition of Done

- [x] Collection 스키마 정의 완료
- [x] 5개 인덱스 생성 완료
- [x] Dense 검색 테스트 통과
- [x] Hybrid 검색 테스트 통과 (RRF Reranking)
- [x] `--reset` 옵션 작동
- [x] `--verify` 옵션 작동
- [x] 코드 품질 검증 (ruff, mypy)

---

## Usage

```bash
# Collection 초기화
python scripts/init_milvus.py

# Collection 재초기화 (데이터 삭제)
python scripts/init_milvus.py --reset

# Collection 검증만
python scripts/init_milvus.py --verify
```

---

## Hybrid Search Example

```python
from pymilvus import AnnSearchRequest, RRFRanker, Collection

collection = Collection("knowledge_chunks")
collection.load()

# Dense search request
dense_req = AnnSearchRequest(
    data=[dense_vector],
    anns_field="dense_embedding",
    param={"metric_type": "COSINE", "params": {"ef": 64}},
    limit=10,
)

# Sparse search request
sparse_req = AnnSearchRequest(
    data=[sparse_vector],
    anns_field="sparse_embedding",
    param={"metric_type": "IP"},
    limit=10,
)

# Hybrid search with RRF reranking
results = collection.hybrid_search(
    reqs=[dense_req, sparse_req],
    rerank=RRFRanker(k=60),
    limit=10,
    output_fields=["chunk_uuid", "chunk_text", "doc_uuid"],
)
```

---

## Next Steps

- **Task 1.3.3**: Neo4j 그래프 스키마 생성
  - 노드 레이블 정의
  - 관계 타입 정의
  - 제약조건 생성

---

## Notes

- Sparse vector는 scipy.sparse.csr_array 형식 사용
- BGE-M3 모델은 1024차원 Dense + Sparse 벡터 생성
- Hybrid Search는 RRF(Reciprocal Rank Fusion) 알고리즘 사용
- Collection load 후 메모리에 상주하여 검색 성능 향상
