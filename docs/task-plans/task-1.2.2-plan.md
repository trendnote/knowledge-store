# Task Execution Plan: 1.2.2 - Docker Compose 설정

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.2.2 |
| **Task Name** | Docker Compose 설정 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | Task 1.2.1 |

### Description
Tech Stack 문서의 Docker Compose 설정을 기반으로 `docker-compose.yml`을 생성합니다.

### Acceptance Criteria
- [ ] `docker/docker-compose.yml` 생성
- [ ] PostgreSQL 15-alpine 설정
- [ ] Milvus 2.5 Standalone 설정 (etcd, minio 포함)
- [ ] Neo4j 5.x Community 설정
- [ ] Kafka 3.x KRaft 모드 설정
- [ ] 모든 컨테이너 healthcheck 설정
- [ ] `docker compose up -d` 실행 성공

---

## 2. Research & Design

### 2.1 참조 문서
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 4.2 Docker Compose Configuration

### 2.2 서비스 구성
```
docker-compose.yml
├── postgres (PostgreSQL 15-alpine)
├── etcd (Milvus dependency)
├── minio (Milvus dependency)
├── milvus (Milvus 2.5 Standalone)
├── neo4j (Neo4j 5.x Community)
└── kafka (Kafka 3.x KRaft mode)
```

### 2.3 네트워크 설계
- **Network**: `knowledge-store-network` (bridge)
- **모든 서비스**: 동일 네트워크에서 통신

### 2.4 볼륨 설계
| Service | Volume | Purpose |
|---------|--------|---------|
| postgres | postgres_data | 데이터 영속성 |
| neo4j | neo4j_data | 데이터 영속성 |
| kafka | kafka_data | 데이터 영속성 |
| minio | minio_data | Milvus 오브젝트 스토리지 |
| etcd | etcd_data | Milvus 메타데이터 |

---

## 3. Implementation Steps

### Step 1: PostgreSQL 서비스 설정 (0.5h)

**작업 내용:**
1. PostgreSQL 15-alpine 이미지 설정
2. 환경 변수 설정
3. healthcheck 설정
4. 볼륨 마운트

**설정:**
```yaml
postgres:
  image: postgres:15-alpine
  container_name: knowledge-store-postgres
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
  networks:
    - knowledge-store-network
```

**완료 기준:**
- [ ] PostgreSQL 컨테이너 설정 완료
- [ ] healthcheck 정의

---

### Step 2: Milvus 스택 설정 (1.5h)

**작업 내용:**
1. etcd 설정 (Milvus 메타데이터)
2. MinIO 설정 (Milvus 오브젝트 스토리지)
3. Milvus Standalone 설정
4. 의존성 설정

**etcd 설정:**
```yaml
etcd:
  image: quay.io/coreos/etcd:v3.5.5
  container_name: knowledge-store-etcd
  environment:
    ETCD_AUTO_COMPACTION_MODE: revision
    ETCD_AUTO_COMPACTION_RETENTION: "1000"
    ETCD_QUOTA_BACKEND_BYTES: "4294967296"
    ETCD_SNAPSHOT_COUNT: "50000"
  command: >
    etcd
    -advertise-client-urls=http://127.0.0.1:2379
    -listen-client-urls=http://0.0.0.0:2379
    --data-dir=/etcd
  volumes:
    - etcd_data:/etcd
  healthcheck:
    test: ["CMD", "etcdctl", "endpoint", "health"]
    interval: 30s
    timeout: 20s
    retries: 3
  networks:
    - knowledge-store-network
```

**MinIO 설정:**
```yaml
minio:
  image: minio/minio:RELEASE.2023-09-04T19-57-37Z
  container_name: knowledge-store-minio
  environment:
    MINIO_ROOT_USER: minioadmin
    MINIO_ROOT_PASSWORD: minioadmin
  command: minio server /data --console-address ":9001"
  ports:
    - "9000:9000"
    - "9001:9001"
  volumes:
    - minio_data:/data
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
    interval: 30s
    timeout: 20s
    retries: 3
  networks:
    - knowledge-store-network
```

**Milvus 설정:**
```yaml
milvus:
  image: milvusdb/milvus:v2.5.0
  container_name: knowledge-store-milvus
  command: ["milvus", "run", "standalone"]
  environment:
    ETCD_ENDPOINTS: etcd:2379
    MINIO_ADDRESS: minio:9000
    MINIO_ACCESS_KEY_ID: minioadmin
    MINIO_SECRET_ACCESS_KEY: minioadmin
  ports:
    - "19530:19530"
    - "9091:9091"
  depends_on:
    etcd:
      condition: service_healthy
    minio:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
    interval: 30s
    timeout: 20s
    retries: 5
  networks:
    - knowledge-store-network
```

**완료 기준:**
- [ ] etcd 설정 완료
- [ ] MinIO 설정 완료
- [ ] Milvus 설정 완료
- [ ] 의존성 순서 정의

---

### Step 3: Neo4j 서비스 설정 (0.5h)

**작업 내용:**
1. Neo4j 5.x Community 이미지 설정
2. APOC 플러그인 설정
3. 인증 설정
4. healthcheck 설정

**설정:**
```yaml
neo4j:
  image: neo4j:5.15-community
  container_name: knowledge-store-neo4j
  environment:
    NEO4J_AUTH: neo4j/neo4j_password
    NEO4J_PLUGINS: '["apoc"]'
    NEO4J_dbms_security_procedures_unrestricted: apoc.*
    NEO4J_apoc_export_file_enabled: "true"
    NEO4J_apoc_import_file_enabled: "true"
  ports:
    - "7474:7474"
    - "7687:7687"
  volumes:
    - neo4j_data:/data
  healthcheck:
    test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:7474 || exit 1"]
    interval: 15s
    timeout: 10s
    retries: 5
  networks:
    - knowledge-store-network
```

**완료 기준:**
- [ ] Neo4j 설정 완료
- [ ] APOC 플러그인 활성화

---

### Step 4: Kafka 서비스 설정 (0.5h)

**작업 내용:**
1. Kafka 3.x KRaft 모드 설정 (Zookeeper 없이)
2. 리스너 설정
3. healthcheck 설정

**설정:**
```yaml
kafka:
  image: bitnami/kafka:3.6
  container_name: knowledge-store-kafka
  environment:
    KAFKA_CFG_NODE_ID: 0
    KAFKA_CFG_PROCESS_ROLES: controller,broker
    KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
    KAFKA_CFG_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
    KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
    KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 0@kafka:9093
    KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
    KAFKA_CFG_INTER_BROKER_LISTENER_NAME: PLAINTEXT
    ALLOW_PLAINTEXT_LISTENER: "yes"
  ports:
    - "9092:9092"
  volumes:
    - kafka_data:/bitnami/kafka
  healthcheck:
    test: ["CMD-SHELL", "kafka-topics.sh --bootstrap-server localhost:9092 --list"]
    interval: 30s
    timeout: 10s
    retries: 5
  networks:
    - knowledge-store-network
```

**완료 기준:**
- [ ] Kafka KRaft 모드 설정 완료
- [ ] healthcheck 정의

---

### Step 5: 통합 및 검증 (1h)

**작업 내용:**
1. 전체 docker-compose.yml 통합
2. `docker compose up -d` 실행
3. 모든 서비스 healthy 상태 확인
4. 포트 접근 테스트

**전체 docker-compose.yml:**
```yaml
version: '3.8'

services:
  # PostgreSQL
  postgres:
    # ... (Step 1 내용)

  # etcd (Milvus dependency)
  etcd:
    # ... (Step 2 내용)

  # MinIO (Milvus dependency)
  minio:
    # ... (Step 2 내용)

  # Milvus
  milvus:
    # ... (Step 2 내용)

  # Neo4j
  neo4j:
    # ... (Step 3 내용)

  # Kafka
  kafka:
    # ... (Step 4 내용)

networks:
  knowledge-store-network:
    driver: bridge

volumes:
  postgres_data:
  etcd_data:
  minio_data:
  neo4j_data:
  kafka_data:
```

**검증 명령어:**
```bash
# 서비스 시작
cd docker && docker compose up -d

# 상태 확인
docker compose ps

# 모든 서비스 healthy 확인
docker compose ps --format "table {{.Name}}\t{{.Status}}"

# 포트 접근 테스트
curl http://localhost:5432  # PostgreSQL (에러 예상, 연결만 확인)
curl http://localhost:9091/healthz  # Milvus
curl http://localhost:7474  # Neo4j
```

**완료 기준:**
- [ ] `docker compose up -d` 성공
- [ ] 모든 서비스 healthy 상태
- [ ] 각 포트 접근 가능

---

## 4. Testing Plan

### 4.1 Service Health Checks
| Service | Test Method | Expected |
|---------|-------------|----------|
| PostgreSQL | `pg_isready` | healthy |
| Milvus | `/healthz` API | healthy |
| Neo4j | HTTP 7474 | healthy |
| Kafka | `kafka-topics.sh --list` | healthy |
| etcd | `etcdctl endpoint health` | healthy |
| MinIO | `/minio/health/live` | healthy |

### 4.2 Integration Checks
| Check | Command | Expected |
|-------|---------|----------|
| 전체 시작 | `docker compose up -d` | 0 errors |
| 상태 확인 | `docker compose ps` | 모든 서비스 Up |
| 네트워크 | 서비스 간 통신 | 정상 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Milvus 메모리 요구 높음 | Medium | Medium | Docker 리소스 제한 설정 확인 |
| etcd/MinIO 시작 순서 | Medium | Low | depends_on + healthcheck 조건 |
| 포트 충돌 | High | Medium | 기존 서비스 중지 후 시작 |

---

## 6. Definition of Done

- [ ] `docker/docker-compose.yml` 파일 생성
- [ ] 모든 서비스 (6개) 설정 완료
- [ ] 모든 healthcheck 정의
- [ ] `docker compose up -d` 성공
- [ ] 모든 서비스 healthy 상태
- [ ] 문서에 기록된 포트로 접근 가능

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: PostgreSQL 설정 | 0.5h | - |
| Step 2: Milvus 스택 설정 | 1.5h | - |
| Step 3: Neo4j 설정 | 0.5h | - |
| Step 4: Kafka 설정 | 0.5h | - |
| Step 5: 통합 및 검증 | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
