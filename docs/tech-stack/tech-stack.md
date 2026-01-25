# Tech Stack: Knowledge Store Layer

---

## Meta
- **PRD Reference**: [knowledge-store-layer-prd.md](../prd/knowledge-store-layer-prd.md)
- **Status**: Approved
- **Last Updated**: 2026-01-25
- **Decision Makers**: Platform Team

---

## 1. Executive Summary

Knowledge Store Layer는 **Tri-Store Architecture (Vector + Graph + RDB)**를 구현하는 플랫폼 계층으로, Hybrid Search와 ACL 기반 권한 필터링을 제공합니다.

**핵심 기술 선택:**
- **Backend**: Python 3.11 + FastAPI
- **Databases**: Milvus 2.5+ (Vector) + Neo4j 5.x (Graph) + PostgreSQL 15+ (RDB)
- **Message Queue**: Kafka 3.x
- **Embedding**: BGE-M3 (Open Source)
- **Environment**: Docker Compose (Local)

---

## 2. Technology Decisions

### 2.1 Backend

#### Language: Python 3.11+

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **Python 3.11+** | AI/ML 생태계 최고, 모든 DB 공식 SDK | 상대적 느린 속도 | ⭐⭐⭐⭐⭐ |
| TypeScript | 타입 안전성 | Vector DB SDK 부족 | ⭐⭐⭐ |
| Go | 뛰어난 성능 | AI/ML 생태계 약함 | ⭐⭐ |

**선택: Python 3.11+**

**Rationale:**
- Milvus, Neo4j, Kafka 모두 Python 공식 SDK 제공
- BGE-M3 임베딩 모델 HuggingFace Python API
- 100ms P95 목표는 DB 응답이 주요 요인, 언어 속도 영향 미미
- 팀 학습 용이성 및 빠른 개발 속도

---

#### Framework: FastAPI 0.115+

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **FastAPI** | 비동기 네이티브, 자동 OpenAPI, Pydantic 통합 | 상대적으로 새로움 | ⭐⭐⭐⭐⭐ |
| Flask | 간단, 성숙함 | 비동기 제한적 | ⭐⭐⭐ |
| Django | 풀스택 | 무거움, 비동기 제한 | ⭐⭐ |

**선택: FastAPI 0.115+**

**Rationale:**
- 비동기 I/O로 3개 저장소 병렬 검색 최적화
- Pydantic v2 통합으로 데이터 검증 용이
- 자동 OpenAPI 문서 생성 (Orchestration Layer 연동 용이)
- 의존성 주입 패턴 지원

---

### 2.2 Databases

#### Vector DB: Milvus 2.5+

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **Milvus 2.5+** | Native Hybrid Search (Dense+Sparse), 오픈소스 | 운영 복잡도 | ⭐⭐⭐⭐⭐ |
| Pinecone | 관리형 | 유료, Sparse 제한적 | ⭐⭐⭐ |
| Qdrant | 경량 | 커뮤니티 작음 | ⭐⭐⭐⭐ |
| Weaviate | GraphQL API | Sparse Vector 미지원 | ⭐⭐⭐ |

**선택: Milvus 2.5+**

**Rationale:**
- Dense + Sparse Hybrid Search 네이티브 지원 (PRD FR-6 핵심 요구사항)
- 1,000만 청크 목표 충족 (페타바이트급 확장 가능)
- ES 대비 30배 빠른 Sparse 검색 (6ms vs 200ms)
- Lindera 토크나이저 한국어 형태소 분석 지원

**Configuration:**
```yaml
# Milvus Collection Schema
collection_name: knowledge_chunks
fields:
  - chunk_uuid: VARCHAR (PK)
  - doc_uuid: VARCHAR
  - dense_embedding: FLOAT_VECTOR[1024]  # BGE-M3
  - sparse_embedding: SPARSE_FLOAT_VECTOR  # BM25
  - chunk_text: VARCHAR
  - security_level: VARCHAR
  - allowed_groups: ARRAY<VARCHAR>

index:
  dense: HNSW (M=16, efConstruction=256)
  sparse: SPARSE_INVERTED_INDEX
```

---

#### Graph DB: Neo4j 5.x

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **Neo4j 5.x** | Cypher 쿼리, GDS 라이브러리 | Enterprise 라이선스 | ⭐⭐⭐⭐⭐ |
| Amazon Neptune | 관리형 | AWS 종속 | ⭐⭐⭐ |
| ArangoDB | Multi-model | Graph 기능 약함 | ⭐⭐⭐ |

**선택: Neo4j 5.x (Community Edition)**

**Rationale:**
- GraphRAG 구현 최적 (Text-to-Cypher 변환 용이)
- 다중홉 탐색으로 관계 추론 (PRD US-2, FR-6)
- GDS 라이브러리 Leiden 알고리즘 커뮤니티 탐지
- Community Edition으로 PoC 무료 사용

**Ontology:**
```cypher
// Node Labels
(:Person), (:Organization), (:Document), (:Chunk), (:Project), (:Policy)

// Relationships
(Person)-[:WROTE]->(Document)
(Document)-[:CONTAINS]->(Chunk)
(Chunk)-[:MENTIONS]->(Entity)
(Person)-[:MANAGES]->(Project)
(Person)-[:BELONGS_TO]->(Organization)
```

---

#### RDB: PostgreSQL 15+

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **PostgreSQL 15+** | ACID, JSON, 확장성 | - | ⭐⭐⭐⭐⭐ |
| MySQL 8.x | 널리 사용 | JSON 기능 약함 | ⭐⭐⭐⭐ |
| SQLite | 경량 | 동시성 제한 | ⭐⭐ |

**선택: PostgreSQL 15+**

**Rationale:**
- 메타데이터/ACL/감사로그 정본(SoT) 관리 (PRD FR-1, FR-7)
- ACID 트랜잭션으로 Saga 패턴 보상 트랜잭션 구현
- asyncpg로 비동기 지원
- 100만 문서 규모 충분히 지원

**Schema:**
```sql
-- Core Tables
documents (doc_uuid PK, title, source, status, security_level, ...)
document_versions (version_id PK, doc_uuid FK, version_no, ...)
document_chunks (chunk_uuid PK, version_id FK, milvus_id, neo4j_node_id, ...)
acl_entries (id PK, doc_uuid FK, principal_type, principal_id, permission)
audit_logs (log_id PK, user_id, action, doc_uuid, timestamp, ...)
```

---

### 2.3 Message Queue

#### Kafka 3.x

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **Kafka 3.x** | 고성능, 내구성, 이벤트 소싱 | 운영 복잡도 | ⭐⭐⭐⭐⭐ |
| RabbitMQ | 쉬운 운영 | 대용량 처리 약함 | ⭐⭐⭐⭐ |
| Redis Streams | 경량 | 내구성 제한 | ⭐⭐⭐ |

**선택: Kafka 3.x**

**Rationale:**
- 5분 내 동기화 요구사항 충족 (PRD FR-8)
- 향후 Data Ingestion Layer CDC 파이프라인 확장
- 메시지 재처리 가능 (장애 복구)
- PoC에서는 KRaft 모드 단일 브로커

**Topics:**
```
document.created    # 문서 생성 이벤트
document.updated    # 문서 수정 이벤트
document.deleted    # 문서 삭제 이벤트
sync.completed      # 동기화 완료 이벤트
```

---

### 2.4 Embedding Model

#### BGE-M3

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **BGE-M3** | Dense + Sparse 동시 출력, 다국어, 오픈소스 | GPU 권장 | ⭐⭐⭐⭐⭐ |
| OpenAI text-embedding-3 | 고품질 | 유료, Sparse 미지원 | ⭐⭐⭐ |
| Upstage Solar | 한국어 최적화 | Sparse 미지원 | ⭐⭐⭐⭐ |

**선택: BGE-M3**

**Rationale:**
- Dense Vector (1024차원) + Sparse Vector (BM25) 동시 생성
- Hybrid Search PRD 핵심 요구사항 충족
- 오픈소스로 PoC 비용 절감
- 다국어(한국어 포함) 지원

**Configuration:**
```python
from FlagEmbedding import BGEM3FlagModel

model = BGEM3FlagModel('BAAI/bge-m3', use_fp16=True)

# Dense + Sparse 동시 생성
output = model.encode(
    sentences,
    return_dense=True,
    return_sparse=True,
    return_colbert_vecs=False
)

dense_embeddings = output['dense_vecs']  # (N, 1024)
sparse_embeddings = output['lexical_weights']  # Dict[str, float]
```

---

### 2.5 Infrastructure

#### Container: Docker Compose

| 비교 대상 | 장점 | 단점 | PRD 충족도 |
|-----------|------|------|------------|
| **Docker Compose** | 간단, 로컬 개발 최적 | 프로덕션 제한 | ⭐⭐⭐⭐⭐ |
| Kubernetes | 프로덕션 급 | PoC에 과도함 | ⭐⭐⭐ |
| Local Install | 간단 | 환경 일관성 없음 | ⭐⭐ |

**선택: Docker Compose**

**Rationale:**
- PoC 로컬 실행 요구사항 충족
- 모든 인프라 컴포넌트 일관된 환경
- 향후 Kubernetes 마이그레이션 용이

---

## 3. Python Dependencies

### 3.1 Core Dependencies

```toml
[project]
name = "knowledge-store"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Web Framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",

    # Database Clients
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",           # PostgreSQL async
    "pymilvus>=2.4.0",           # Milvus
    "neo4j>=5.0.0",              # Neo4j

    # Message Queue
    "aiokafka>=0.10.0",          # Kafka async

    # Embedding
    "FlagEmbedding>=1.2.0",      # BGE-M3
    "torch>=2.0.0",

    # Utilities
    "httpx>=0.27.0",             # Async HTTP
    "python-json-logger>=2.0.0", # Structured logging
    "prometheus-client>=0.20.0", # Metrics
]
```

### 3.2 Development Dependencies

```toml
[project.optional-dependencies]
dev = [
    # Testing
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",
    "httpx>=0.27.0",             # TestClient

    # Code Quality
    "ruff>=0.3.0",               # Linter + Formatter
    "mypy>=1.8.0",               # Type checking
    "pre-commit>=3.6.0",

    # Database Testing
    "testcontainers>=4.0.0",     # Docker-based tests
]
```

---

## 4. Infrastructure Components

### 4.1 Required Versions

| Component | Version | Port | Purpose |
|-----------|---------|------|---------|
| PostgreSQL | 15+ | 5432 | Metadata, ACL, Audit |
| Milvus | 2.5+ | 19530 | Vector Storage |
| Neo4j | 5.x | 7687 | Graph Storage |
| Kafka | 3.x | 9092 | Event Streaming |
| Zookeeper | 3.x | 2181 | Kafka Coordination (Optional with KRaft) |

### 4.2 Docker Compose Configuration

```yaml
version: '3.8'

services:
  # PostgreSQL
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: knowledge_store
      POSTGRES_USER: ks_user
      POSTGRES_PASSWORD: ks_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ks_user -d knowledge_store"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Milvus Standalone
  milvus:
    image: milvusdb/milvus:v2.5.0
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - etcd
      - minio
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      timeout: 10s
      retries: 5

  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls=http://0.0.0.0:2379 --data-dir /etcd

  minio:
    image: minio/minio:RELEASE.2023-09-04T19-57-37Z
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: minio server /data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"

  # Neo4j
  neo4j:
    image: neo4j:5.15-community
    environment:
      NEO4J_AUTH: neo4j/neo4j_password
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    volumes:
      - neo4j_data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:7474"]
      interval: 10s
      timeout: 5s
      retries: 5

  # Kafka (KRaft mode - no Zookeeper)
  kafka:
    image: bitnami/kafka:3.6
    environment:
      KAFKA_CFG_NODE_ID: 0
      KAFKA_CFG_PROCESS_ROLES: controller,broker
      KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 0@kafka:9093
      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
    ports:
      - "9092:9092"
    volumes:
      - kafka_data:/bitnami/kafka
    healthcheck:
      test: ["CMD-SHELL", "kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 30s
      timeout: 10s
      retries: 5

volumes:
  postgres_data:
  neo4j_data:
  kafka_data:
```

---

## 5. PRD Requirement Mapping

| PRD Requirement | Technology | Coverage |
|-----------------|------------|----------|
| FR-1: PostgreSQL Schema | PostgreSQL 15+ | ✅ Full |
| FR-2: Milvus Collection | Milvus 2.5+ | ✅ Full |
| FR-3: Neo4j Ontology | Neo4j 5.x | ✅ Full |
| FR-4: ID Mapping | PostgreSQL | ✅ Full |
| FR-5: Document Storage API | FastAPI + All DBs | ✅ Full |
| FR-6: Hybrid Search API | Milvus + Neo4j | ✅ Full |
| FR-7: ACL Filtering | PostgreSQL + Milvus | ✅ Full |
| FR-8: Change Sync | Kafka | ✅ Full |

**PRD 충족도: 8/8 (100%)**

---

## 6. Performance Considerations

### 6.1 PRD 목표 vs 기술 스택 역량

| 목표 | PRD 요구사항 | 기술 스택 역량 | 충족 |
|------|-------------|---------------|------|
| 검색 응답 시간 | P95 < 100ms | Milvus 6ms, Neo4j ~50ms | ✅ |
| 저장 응답 시간 | P95 < 500ms | 3개 DB 순차 저장 ~300ms | ✅ |
| 동시 처리량 | 100 RPS | FastAPI async + Connection Pool | ✅ |
| 문서 수 | 100만 건 | PostgreSQL 충분 | ✅ |
| 청크 수 | 1,000만 건 | Milvus 페타바이트급 | ✅ |

### 6.2 최적화 전략

```python
# Connection Pool 설정
POSTGRES_POOL_SIZE = 20
MILVUS_POOL_SIZE = 10
NEO4J_POOL_SIZE = 50

# 병렬 검색 (asyncio.gather)
async def hybrid_search(query: str):
    dense_task = milvus_dense_search(query)
    sparse_task = milvus_sparse_search(query)
    graph_task = neo4j_graph_search(query)

    results = await asyncio.gather(
        dense_task, sparse_task, graph_task
    )
    return merge_results(results)
```

---

## 7. Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| 3개 저장소 트랜잭션 실패 | High | Saga 패턴 + 보상 트랜잭션 |
| Milvus 운영 복잡도 | Medium | Docker Compose로 단순화 |
| BGE-M3 GPU 요구 | Medium | CPU fallback, batch 처리 |
| Kafka 학습 곡선 | Low | aiokafka 간단한 API |

---

## 8. Team Readiness

### 8.1 Required Skills

| Technology | Skill Level | Learning Curve |
|------------|-------------|----------------|
| Python/FastAPI | Intermediate | Low |
| PostgreSQL | Intermediate | Low |
| Milvus | Beginner | Medium |
| Neo4j/Cypher | Beginner | Medium |
| Kafka | Beginner | Medium |

### 8.2 Learning Resources

- **Milvus**: [Official Docs](https://milvus.io/docs), [Bootcamp](https://github.com/milvus-io/bootcamp)
- **Neo4j**: [GraphAcademy](https://graphacademy.neo4j.com/)
- **Kafka**: [Confluent Tutorials](https://developer.confluent.io/tutorials/)
- **BGE-M3**: [FlagEmbedding GitHub](https://github.com/FlagOpen/FlagEmbedding)

---

## 9. Cost Estimation (PoC)

| Component | Type | Monthly Cost |
|-----------|------|--------------|
| PostgreSQL | Docker (Local) | $0 |
| Milvus | Docker (Local) | $0 |
| Neo4j Community | Docker (Local) | $0 |
| Kafka | Docker (Local) | $0 |
| BGE-M3 | HuggingFace (Local) | $0 |

**Total PoC Cost: $0/month** (로컬 Docker 환경)

---

## 10. Decision Log

| Date | Decision | Rationale | Decided By |
|------|----------|-----------|------------|
| 2026-01-25 | Python + FastAPI | AI/ML 생태계, 비동기 지원 | Platform Team |
| 2026-01-25 | Milvus 2.5+ | Native Hybrid Search | Platform Team |
| 2026-01-25 | Neo4j 5.x | GraphRAG 최적 | Platform Team |
| 2026-01-25 | PostgreSQL 15+ | ACID, 메타데이터 관리 | Platform Team |
| 2026-01-25 | Kafka 3.x | 이벤트 동기화 | Platform Team |
| 2026-01-25 | BGE-M3 | Dense + Sparse, 오픈소스 | Platform Team |
| 2026-01-25 | Docker Compose | PoC 로컬 실행 | Platform Team |

---

## 11. Next Steps

1. ✅ Tech Stack 문서 완료
2. ⏭️ 기존 인프라 확인 및 Gap 분석
3. ⏭️ Architecture 설계: `/architecture-design`
4. ⏭️ Phase 1 구현 시작

---

## 12. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial version |
