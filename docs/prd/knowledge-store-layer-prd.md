# PRD: Knowledge Store Layer

---

## Meta
- **Status**: Draft
- **Owner**: Platform Team
- **Stakeholders**: Data Engineering, Backend, Security
- **Last Updated**: 2026-01-25
- **Target Release**: PoC

---

## 1. Executive Summary

엔터프라이즈 환경에서 정보의 사일로화와 파편화로 인해 임직원들의 정보 접근성이 떨어지고 데이터 신뢰도가 낮은 문제를 해결하기 위해, **Tri-Store Architecture (Milvus + Neo4j + PostgreSQL)** 기반의 Knowledge Store Layer를 구축한다.

이 계층은 Vector DB(의미 검색), Graph DB(관계 추론), RDB(메타데이터/거버넌스)를 통합하여 Hybrid Search를 제공하고, ACL 기반 권한 필터링과 3개 저장소 간 데이터 정합성을 보장한다.

**핵심 성과 지표:**
- 3개 저장소 간 ID 매핑 일관성 99.9% 이상
- Hybrid Search로 단일 검색 대비 30% 커버리지 향상
- 검색 API 응답 시간 P95 < 100ms

---

## 2. Problem Statement

### 2.1 현재 상황
- 정보가 Wiki, Agit, Google Docs, Slack 등 다양한 플랫폼에 **파편화**되어 상호 연결성 단절
- 정보 선별 및 탐색에 과도한 시간 소요
- 동일 정보가 여러 곳에서 다르게 관리되어 **데이터 신뢰도 하락**
- 기존 Vector RAG만으로는 복합 추론 질의 해결 실패 (정확도 56%)

### 2.2 해결 방향
- 3개 저장소(Vector + Graph + RDB)를 통합한 **Tri-Store Architecture** 구축
- 문서 간 관계를 구조화하여 **복합 질의 처리** 가능
- 정본(Source of Truth) 관리로 **데이터 신뢰도 확보**
- ACL 기반 **권한 필터링**으로 보안 강화

---

## 3. Goals & Non-Goals

### 3.1 Goals

| 영역 | 목표 | 지표 |
|------|------|------|
| 데이터 정합성 | 3개 저장소 간 ID 매핑 일관성 | 99.9% 이상 |
| 검색 커버리지 | Hybrid Search (Dense + Sparse + Graph) | 단일 검색 대비 30% 향상 |
| 권한 필터링 | ACL 기반 문서 접근 제어 | 100% 적용 |
| 데이터 신선도 | 원본 문서 변경 시 동기화 | 5분 이내 반영 |

### 3.2 Non-Goals

| 제외 항목 | 제외 이유 | 향후 계획 |
|----------|----------|----------|
| LLM 답변 생성 | Orchestration Layer 담당 | Phase 2에서 구현 |
| Chat UI / 사용자 인터페이스 | Experience Layer 담당 | Phase 3에서 구현 |
| 데이터 수집 커넥터 (Wiki, Slack 등) | Data Ingestion Layer 담당 | Phase 2에서 구현 |
| Reranking / RRF Fusion 로직 | Orchestration Layer 담당 | Phase 2에서 구현 |
| 실시간 스트리밍 답변 | Experience Layer 담당 | Phase 3에서 구현 |

> **참고**: 향후 확장을 위해 인터페이스와 API 설계 시 다른 계층과의 연동을 고려하여 설계

---

## 4. Target Users & Use Cases

### 4.1 Target Users

| 사용자 유형 | 설명 | 주요 사용 방식 |
|------------|------|---------------|
| Orchestration Layer | RAG 파이프라인 | API 호출로 검색 결과 조회 |
| 플랫폼 운영자 | 시스템 관리자 | 데이터 적재, 모니터링, 권한 관리 |
| Data Ingestion Layer | 데이터 수집 파이프라인 | 문서/청크 저장 API 호출 |

### 4.2 User Stories

**US-1: 문서 저장**
- **Given**: Data Ingestion Layer가 새 문서를 파싱 완료한 상태
- **When**: 문서 메타데이터, 청크, 임베딩, 엔티티 관계를 저장 요청
- **Then**: PostgreSQL, Milvus, Neo4j에 각각 저장되고 ID 매핑이 생성됨

**US-2: Hybrid Search 검색**
- **Given**: 사용자 쿼리와 권한 정보가 전달된 상태
- **When**: Orchestration Layer가 검색 API 호출
- **Then**: ACL 필터링 후 Dense + Sparse + Graph 검색 결과 반환

**US-3: 문서 업데이트 동기화**
- **Given**: 원본 문서가 수정된 상태
- **When**: 변경 이벤트가 수신됨
- **Then**: 3개 저장소에 5분 이내 동기화 완료

**US-4: 권한 기반 필터링**
- **Given**: 사용자 ID와 소속 그룹 정보가 있는 상태
- **When**: 검색 요청 시
- **Then**: 접근 권한이 있는 문서만 결과에 포함

---

## 5. Functional Requirements (P0)

### FR-1: PostgreSQL 스키마 구축
- **Description**: 메타데이터, 버전 관리, ACL, 감사 로그를 위한 테이블 구축
- **Acceptance Criteria**:
  - [ ] documents 테이블 생성 (doc_uuid PK, 메타데이터 필드)
  - [ ] document_versions 테이블 생성 (버전 관리)
  - [ ] document_chunks 테이블 생성 (청크-저장소 매핑)
  - [ ] acl_entries 테이블 생성 (권한 관리)
  - [ ] audit_logs 테이블 생성 (감사 로그)
  - [ ] 필요한 인덱스 및 FK 설정 완료

### FR-2: Milvus Collection 구축
- **Description**: Dense/Sparse Vector 저장 및 Hybrid Search를 위한 Collection 구축
- **Acceptance Criteria**:
  - [ ] Collection 스키마 정의 (chunk_uuid, dense_embedding, sparse_embedding 등)
  - [ ] Dense Vector 인덱스 생성 (HNSW, 1024 dimensions)
  - [ ] Sparse Vector 인덱스 생성 (BM25)
  - [ ] Hybrid Search 쿼리 동작 확인

### FR-3: Neo4j 온톨로지 구축
- **Description**: 엔티티 및 관계를 저장하기 위한 그래프 스키마 구축
- **Acceptance Criteria**:
  - [ ] Node 라벨 정의 (Person, Document, Chunk, Organization, Project, Policy)
  - [ ] Relationship 타입 정의 (WROTE, CONTAINS, MENTIONS, MANAGES, BELONGS_TO)
  - [ ] 제약조건 설정 (unique constraints)
  - [ ] 인덱스 생성 (검색 성능 최적화)

### FR-4: ID 매핑 관리
- **Description**: 3개 저장소 간 ID 매핑을 일관성 있게 관리
- **Acceptance Criteria**:
  - [ ] doc_uuid, chunk_uuid, milvus_id, neo4j_node_id 간 매핑 생성
  - [ ] 매핑 조회 API 구현
  - [ ] 매핑 삭제 시 연관 데이터 정리
  - [ ] 매핑 정합성 검증 배치 구현

### FR-5: 문서 저장 API
- **Description**: 3개 저장소에 트랜잭션 기반으로 문서 저장
- **Acceptance Criteria**:
  - [ ] POST /api/v1/documents 엔드포인트 구현
  - [ ] PostgreSQL, Milvus, Neo4j 순차 저장
  - [ ] 실패 시 보상 트랜잭션 (Saga 패턴)
  - [ ] 저장 완료 후 ID 매핑 반환

### FR-6: Hybrid Search API
- **Description**: Dense + Sparse + Graph 검색 결과를 통합하여 반환
- **Acceptance Criteria**:
  - [ ] POST /api/v1/search 엔드포인트 구현
  - [ ] Dense Search (Milvus 코사인 유사도)
  - [ ] Sparse Search (Milvus BM25)
  - [ ] Graph Search (Neo4j Cypher)
  - [ ] 3개 검색 결과 통합 반환 (점수 포함)

### FR-7: ACL 필터링
- **Description**: 검색 전 사용자 권한 기반 문서 필터링
- **Acceptance Criteria**:
  - [ ] 사용자 ID로 접근 가능한 doc_uuid 목록 조회
  - [ ] Milvus 검색 시 allowed_groups 필터 적용
  - [ ] 권한 없는 문서는 결과에서 제외
  - [ ] 권한 검증 실패 시 403 응답

### FR-8: 변경 동기화
- **Description**: 문서 수정/삭제 시 3개 저장소 일관성 유지
- **Acceptance Criteria**:
  - [ ] Kafka Consumer로 변경 이벤트 수신
  - [ ] 문서 수정 시 3개 저장소 업데이트
  - [ ] 문서 삭제 시 3개 저장소에서 제거
  - [ ] 동기화 완료까지 5분 이내

---

## 6. Non-Functional Requirements

### 6.1 Performance
| 항목 | 목표 |
|------|------|
| 검색 API 응답 시간 | P95 < 100ms |
| 문서 저장 API 응답 시간 | P95 < 500ms |
| 동시 처리량 | 100 RPS 이상 |

### 6.2 Scalability
| 항목 | 목표 |
|------|------|
| 문서 수 | 100만 건 이상 지원 |
| 청크 수 | 1,000만 건 이상 지원 |

### 6.3 Availability
| 항목 | 목표 |
|------|------|
| 시스템 가용성 | 99.9% Uptime |
| 장애 복구 시간 | RTO < 1시간 |

### 6.4 Security
| 항목 | 목표 |
|------|------|
| 데이터 암호화 | 전송 중(TLS), 저장 시(AES-256) |
| 감사 로그 | 모든 조회/수정 이력 기록 |

### 6.5 Consistency
| 항목 | 목표 |
|------|------|
| 3개 저장소 정합성 | Eventual Consistency (5분 이내) |

---

## 7. Technical Considerations

### 7.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Knowledge Store Layer                     │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   FastAPI   │  │   Services  │  │   Clients   │          │
│  │   Router    │──│  - Document │──│  - Postgres │          │
│  │             │  │  - Search   │  │  - Milvus   │          │
│  │             │  │  - ACL      │  │  - Neo4j    │          │
│  │             │  │  - Sync     │  │  - Kafka    │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │ PostgreSQL  │  │   Milvus    │  │   Neo4j     │          │
│  │ (Metadata)  │  │  (Vector)   │  │  (Graph)    │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Tech Stack

| 구분 | 기술 | 버전 |
|------|------|------|
| Language | Python | 3.11+ |
| Framework | FastAPI | 0.100+ |
| Vector DB | Milvus | 2.5+ |
| Graph DB | Neo4j | 5.x |
| RDB | PostgreSQL | 15+ |
| Message Queue | Kafka | 3.x |
| Embedding Model | BGE-M3 (Open Source) | - |
| Container | Docker Compose | Local |

### 7.3 Data Models

**PostgreSQL (메타데이터/거버넌스)**

```typescript
interface Document {
  doc_uuid: string;          // PK, UUID v4
  title: string;
  source: string;            // 'wiki' | 'agit' | 'gdocs' | 'slack'
  source_url: string;
  owner_id: string;
  owner_org: string;
  status: 'draft' | 'approved' | 'archived';
  security_level: 'public' | 'internal' | 'confidential';
  current_version_id: string;
  created_at: Date;
  updated_at: Date;
}

interface DocumentVersion {
  version_id: string;        // PK
  doc_uuid: string;          // FK -> documents
  version_no: number;
  content_hash: string;
  effective_from: Date;
  approved_by: string;
  created_at: Date;
}

interface DocumentChunk {
  chunk_uuid: string;        // PK, UUID v4
  doc_uuid: string;          // FK -> documents
  version_id: string;        // FK -> document_versions
  chunk_no: number;
  section_path: string;      // 예: "3.2.1"
  milvus_id: string;
  neo4j_node_id: string;
  created_at: Date;
}

interface AclEntry {
  id: string;                // PK
  doc_uuid: string;          // FK -> documents
  principal_type: 'user' | 'group' | 'org';
  principal_id: string;
  permission: 'read' | 'write' | 'admin';
  created_at: Date;
}

interface AuditLog {
  log_id: string;            // PK
  user_id: string;
  action: 'search' | 'read' | 'create' | 'update' | 'delete';
  doc_uuid: string | null;
  query_text: string | null;
  retrieved_docs: string[];
  timestamp: Date;
}
```

**Milvus (벡터 저장소)**

```typescript
interface MilvusChunk {
  chunk_uuid: string;        // PK
  doc_uuid: string;
  dense_embedding: number[]; // 1024 dimensions (BGE-M3)
  sparse_embedding: Record<string, number>;  // BM25 term weights
  chunk_text: string;        // 원본 텍스트
  security_level: string;
  allowed_groups: string[];  // ACL 필터용
  created_at: number;        // Unix timestamp
}
```

**Neo4j (지식 그래프)**

```typescript
// Node Labels
interface PersonNode {
  emp_id: string;            // Unique
  name: string;
  department: string;
  role: string;
  email: string;
}

interface OrganizationNode {
  org_id: string;            // Unique
  name: string;
  parent_org_id: string | null;
}

interface DocumentNode {
  doc_uuid: string;          // Unique
  title: string;
  source: string;
  security_level: string;
  created_at: string;
}

interface ChunkNode {
  chunk_uuid: string;        // Unique
  sequence: number;
  text_preview: string;      // 처음 200자
  section_path: string;
}

interface ProjectNode {
  project_id: string;        // Unique
  name: string;
  status: string;
  start_date: string;
}

interface PolicyNode {
  policy_id: string;         // Unique
  name: string;
  effective_from: string;
}

// Relationship Types
type WROTE = { created_at: string };           // Person -> Document
type CONTAINS = { sequence: number };          // Document -> Chunk
type MENTIONS = { confidence: number };        // Chunk -> Entity
type MANAGES = { role: string };               // Person -> Project
type BELONGS_TO = { joined_at: string };       // Person -> Organization
type HAS_POLICY = {};                          // Organization -> Policy
```

### 7.4 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/v1/documents | 문서 저장 |
| GET | /api/v1/documents/{doc_uuid} | 문서 조회 |
| PUT | /api/v1/documents/{doc_uuid} | 문서 수정 |
| DELETE | /api/v1/documents/{doc_uuid} | 문서 삭제 |
| POST | /api/v1/search | Hybrid Search |
| GET | /api/v1/health | Health Check |
| GET | /api/v1/metrics | Prometheus Metrics |

### 7.5 Dependencies

**Internal:**
- Kafka (메시지 큐, 변경 이벤트)

**External:**
- BGE-M3 모델 (HuggingFace)

---

## 8. Testing Strategy

### 8.1 Unit Tests
| 대상 | 테스트 항목 |
|------|------------|
| PostgreSQL Repository | CRUD 동작, 트랜잭션 롤백 |
| Milvus Client | 벡터 저장/검색, Hybrid Search |
| Neo4j Client | 노드/엣지 생성, Cypher 쿼리 |
| ID Mapping Service | 매핑 생성/조회/삭제 일관성 |
| ACL Service | 권한 필터링 로직 |

### 8.2 Integration Tests
| 시나리오 | 검증 항목 |
|----------|----------|
| 문서 저장 플로우 | 3개 저장소 동시 저장 + ID 매핑 정합성 |
| Hybrid Search 플로우 | Dense + Sparse + Graph 결과 통합 |
| 문서 삭제 플로우 | 3개 저장소 동시 삭제 + 매핑 제거 |
| ACL 필터링 플로우 | 권한 없는 문서 필터링 검증 |

### 8.3 E2E Tests
| 시나리오 | 검증 항목 |
|----------|----------|
| 전체 저장-검색 사이클 | 문서 저장 → 검색 → 결과 반환 |
| 동기화 시나리오 | 문서 수정 → 5분 내 3개 저장소 반영 |
| 보안 시나리오 | 권한 없는 사용자 접근 차단 |

### 8.4 Performance Tests
| 항목 | 목표 |
|------|------|
| 검색 API Latency | P95 < 100ms (1,000 동시 요청) |
| 저장 API Throughput | 100 RPS 이상 |
| 대용량 테스트 | 100만 문서에서 검색 성능 유지 |

---

## 9. Implementation Plan

### Phase 1: 인프라 및 스키마 구축

**Scope**: 기존 인프라 확인, 스키마 설계 및 구축

| 항목 | 산출물 |
|------|--------|
| 기존 인프라 확인 | Docker 컨테이너 현황, 버전 확인 |
| 인프라 Gap 분석 | 필요 버전과 현재 버전 비교, 누락 컴포넌트 식별 |
| PostgreSQL 스키마 | 테이블 생성, 인덱스, FK 설정 |
| Milvus Collection | 스키마 정의, 인덱스 생성 (HNSW + Sparse) |
| Neo4j 온톨로지 | 노드/엣지 라벨, 제약조건, 인덱스 |
| Docker Compose | 누락된 컴포넌트만 추가, 버전 통일 |

**Acceptance Criteria**:
- [ ] 기존 Docker 컨테이너 현황 문서화
- [ ] 모든 인프라 컴포넌트 실행 확인
- [ ] PostgreSQL 스키마 마이그레이션 완료
- [ ] Milvus Collection 생성 및 인덱스 확인
- [ ] Neo4j 제약조건 및 인덱스 생성 완료

### Phase 2: 핵심 서비스 구현

**Scope**: Repository Layer 및 핵심 서비스 구현

| 항목 | 산출물 |
|------|--------|
| Repository Layer | PostgreSQL, Milvus, Neo4j Client |
| ID Mapping Service | 매핑 생성/조회/삭제 API |
| Document Storage Service | 3개 저장소 트랜잭션 저장 |
| ACL Service | 권한 조회 및 필터링 |

**Acceptance Criteria**:
- [ ] 각 저장소 Client 구현 및 단위 테스트 통과
- [ ] 문서 저장 API 동작 확인
- [ ] ID 매핑 정합성 검증
- [ ] ACL 필터링 동작 확인

### Phase 3: 검색 기능 구현

**Scope**: Hybrid Search 구현

| 항목 | 산출물 |
|------|--------|
| Dense Search | Milvus 코사인 유사도 검색 |
| Sparse Search | Milvus BM25 키워드 검색 |
| Graph Search | Neo4j Cypher 기반 관계 탐색 |
| Hybrid Search API | 3개 검색 결과 통합 반환 |

**Acceptance Criteria**:
- [ ] 각 검색 방식 개별 동작 확인
- [ ] Hybrid Search API 통합 테스트 통과
- [ ] 검색 응답 시간 P95 < 100ms

### Phase 4: 동기화 및 운영 기능

**Scope**: 변경 동기화, 모니터링

| 항목 | 산출물 |
|------|--------|
| Change Sync Service | 문서 변경 시 3개 저장소 동기화 |
| Audit Logger | 조회/수정 이력 기록 |
| Health Check API | 각 저장소 상태 모니터링 |
| Metrics Exporter | Prometheus 메트릭 노출 |

**Acceptance Criteria**:
- [ ] Kafka Consumer 동작 확인
- [ ] 변경 동기화 5분 이내 완료
- [ ] 감사 로그 기록 확인
- [ ] Health Check / Metrics 엔드포인트 동작

---

## Claude Code Instructions

### Before Starting
1. Read this entire PRD
2. Confirm understanding of:
   - Problem Statement (Section 2)
   - All P0 Requirements (Section 5)
   - Data Models (Section 7.3)
3. If anything is unclear, ASK before coding

### During Implementation
1. Implement requirements in order: FR-1 → FR-2 → ... → FR-8
2. Use data models EXACTLY as defined in Section 7.3
3. Include all acceptance criteria as test cases
4. Follow testing strategy in Section 8
5. Do NOT add features not in P0 requirements

### Validation Checklist
- [ ] All P0 requirements implemented
- [ ] All acceptance criteria met
- [ ] All tests passing (unit + integration + E2E)
- [ ] No Out-of-Scope features added
- [ ] Performance requirements met (Section 6)

### When in Doubt
- **DON'T**: Make assumptions
- **DO**: Ask "The requirement says X but doesn't specify Y. Should I...?"

---

## 10. Risks & Open Questions

### 10.1 Risks

| 위험 | 영향도 | 완화 방안 |
|------|--------|----------|
| 3개 저장소 간 트랜잭션 실패 | 높음 | Saga 패턴 + 보상 트랜잭션 구현 |
| Milvus Hybrid Search 성능 저하 | 중간 | 인덱스 튜닝, 파티션 분리 |
| Neo4j 대용량 그래프 쿼리 지연 | 중간 | 쿼리 최적화, 캐싱 적용 |
| 기존 인프라 버전 호환성 | 중간 | 버전 확인 후 마이그레이션 계획 수립 |
| ACL 필터링 누락으로 보안 이슈 | 높음 | 필터링 레이어 이중화, 보안 테스트 강화 |

### 10.2 Open Questions

> 모든 Open Questions 결정 완료

| 항목 | 결정 |
|------|------|
| 임베딩 모델 | BGE-M3 (오픈소스) |
| 개발 언어/프레임워크 | Python + FastAPI |
| 배포 환경 | 로컬 실행 (Docker Compose) |
| 메시지 큐 | Kafka |

---

## 11. Metrics & Monitoring

### Launch Criteria
- [ ] All P0 requirements implemented and tested
- [ ] Performance benchmarks met
- [ ] Security review completed
- [ ] Stakeholder approval received

### Success Metrics (30일 후 측정)

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| API 가용성 | 99.9% Uptime | Prometheus/Grafana |
| 검색 응답 시간 | P95 < 100ms | API Latency 측정 |
| 데이터 동기화 정합성 | 오류율 < 0.1% | ID 매핑 검증 배치 |
| Hybrid Search 정확도 | MRR@10 > 0.7 | 테스트 쿼리셋 평가 |
| ACL 필터링 정확도 | 100% | 보안 테스트 |

---

## 12. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial version |
