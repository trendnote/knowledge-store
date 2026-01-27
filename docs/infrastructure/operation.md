# Infrastructure Operations Guide

**Last Updated**: 2026-01-28

이 문서는 Knowledge Store Layer 인프라의 웹 관리 인터페이스 및 운영 도구에 대한 정보를 제공합니다.

---

## Web Management Interfaces

### Available UIs

| Service | Web UI | URL | Credentials | Status |
|---------|--------|-----|-------------|--------|
| Neo4j | Neo4j Browser | http://localhost:7474 | neo4j / neo4j_password | ✅ Built-in |
| MinIO | MinIO Console | http://localhost:9003 | minioadmin / minioadmin | ✅ Built-in |
| PostgreSQL | - | - | - | ❌ No built-in UI |
| Milvus | - | - | - | ❌ No built-in UI |
| Kafka | - | - | - | ❌ No built-in UI |

---

## Neo4j Browser

Neo4j는 내장 웹 브라우저를 제공합니다.

### Access
- **URL**: http://localhost:7474
- **Bolt URL**: bolt://localhost:7687
- **Username**: neo4j
- **Password**: neo4j_password

### Features
- Cypher 쿼리 실행
- 그래프 시각화
- 데이터베이스 상태 모니터링
- 인덱스 및 제약조건 관리

### Quick Start Queries
```cypher
// 노드 수 확인
MATCH (n) RETURN count(n) AS node_count;

// 관계 수 확인
MATCH ()-[r]->() RETURN count(r) AS relationship_count;

// 스키마 확인
CALL db.schema.visualization();

// 인덱스 확인
SHOW INDEXES;

// 제약조건 확인
SHOW CONSTRAINTS;
```

---

## MinIO Console

MinIO는 S3 호환 오브젝트 스토리지의 웹 콘솔을 제공합니다. Milvus의 데이터 저장소로 사용됩니다.

### Access
- **Console URL**: http://localhost:9003
- **API URL**: http://localhost:9002
- **Username**: minioadmin
- **Password**: minioadmin

### Features
- 버킷 관리
- 파일 업로드/다운로드
- 접근 정책 설정
- 사용량 모니터링

### Milvus Buckets
MinIO에서 Milvus 관련 버킷을 확인할 수 있습니다:
- `milvus-bucket` - Milvus 데이터 저장소

---

## PostgreSQL Management

PostgreSQL은 내장 웹 UI가 없습니다. 다음 옵션을 사용할 수 있습니다.

### Option 1: Command Line (psql)
```bash
# Docker를 통한 접속
docker exec -it knowledge-store-postgres psql -U ks_user -d knowledge_store

# 또는 호스트에서 직접 접속
psql -h localhost -p 5433 -U ks_user -d knowledge_store
```

### Option 2: pgAdmin (Optional)
pgAdmin을 Docker Compose에 추가하여 웹 UI를 사용할 수 있습니다.

```yaml
# docker/docker-compose.yml에 추가 (선택사항)
pgadmin:
  image: dpage/pgadmin4:latest
  container_name: knowledge-store-pgadmin
  restart: unless-stopped
  environment:
    PGADMIN_DEFAULT_EMAIL: admin@example.com
    PGADMIN_DEFAULT_PASSWORD: admin
  ports:
    - "5050:80"
  networks:
    - knowledge-store-network
```

### Option 3: DBeaver / DataGrip
데스크톱 애플리케이션 사용 권장:
- **Host**: localhost
- **Port**: 5433
- **Database**: knowledge_store
- **User**: ks_user
- **Password**: ks_password

---

## Milvus Management

Milvus는 내장 웹 UI가 없습니다. Attu를 사용할 수 있습니다.

### Option 1: Attu (Milvus GUI)
```yaml
# docker/docker-compose.yml에 추가 (선택사항)
attu:
  image: zilliz/attu:v2.4
  container_name: knowledge-store-attu
  restart: unless-stopped
  environment:
    MILVUS_URL: milvus:19530
  ports:
    - "8081:3000"
  depends_on:
    - milvus
  networks:
    - knowledge-store-network
```

설치 후 접속:
- **URL**: http://localhost:8081
- **Milvus Host**: localhost
- **Milvus Port**: 19531

### Option 2: pymilvus CLI
```bash
# Python 환경에서
python -c "
from pymilvus import MilvusClient
client = MilvusClient(uri='http://localhost:19531')
print('Collections:', client.list_collections())
client.close()
"
```

### Existing RAG Platform Attu
기존 RAG Platform의 Attu가 실행 중입니다:
- **URL**: http://localhost:8080
- **Connected to**: rag-milvus (port 19530)
- **Note**: Knowledge Store Milvus(19531)에는 연결되지 않음

---

## Kafka Management

Kafka는 내장 웹 UI가 없습니다. 다음 옵션을 사용할 수 있습니다.

### Option 1: Kafka UI (Recommended)
```yaml
# docker/docker-compose.yml에 추가 (선택사항)
kafka-ui:
  image: provectuslabs/kafka-ui:latest
  container_name: knowledge-store-kafka-ui
  restart: unless-stopped
  environment:
    KAFKA_CLUSTERS_0_NAME: knowledge-store
    KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
  ports:
    - "8082:8080"
  depends_on:
    - kafka
  networks:
    - knowledge-store-network
```

설치 후 접속:
- **URL**: http://localhost:8082

### Option 2: Command Line
```bash
# 토픽 목록 조회
docker exec knowledge-store-kafka kafka-topics --bootstrap-server localhost:9092 --list

# 토픽 생성
docker exec knowledge-store-kafka kafka-topics --bootstrap-server localhost:9092 \
  --create --topic my-topic --partitions 3 --replication-factor 1

# 토픽 상세 정보
docker exec knowledge-store-kafka kafka-topics --bootstrap-server localhost:9092 \
  --describe --topic my-topic

# 메시지 생산
docker exec -it knowledge-store-kafka kafka-console-producer \
  --bootstrap-server localhost:9092 --topic my-topic

# 메시지 소비
docker exec knowledge-store-kafka kafka-console-consumer \
  --bootstrap-server localhost:9092 --topic my-topic --from-beginning
```

---

## Service Health Monitoring

### Health Check Commands
```bash
# 모든 서비스 상태 확인
cd docker && docker compose ps

# 개별 서비스 상태
docker exec knowledge-store-postgres pg_isready -U ks_user -d knowledge_store
curl -sf http://localhost:9092/healthz && echo "Milvus OK"
curl -sf http://localhost:7474 && echo "Neo4j OK"
docker exec knowledge-store-kafka kafka-topics --bootstrap-server localhost:9092 --list

# 인프라 연결 스크립트 실행
python scripts/check_infrastructure.py
```

### Log Viewing
```bash
# 모든 서비스 로그
cd docker && docker compose logs -f

# 특정 서비스 로그
docker compose logs -f postgres
docker compose logs -f milvus
docker compose logs -f neo4j
docker compose logs -f kafka

# 최근 100줄만
docker compose logs --tail=100 [service]
```

---

## Quick Reference

### Connection Information

| Service | Host | Port | Protocol |
|---------|------|------|----------|
| PostgreSQL | localhost | 5433 | TCP |
| Milvus gRPC | localhost | 19531 | gRPC |
| Milvus Health | localhost | 9092 | HTTP |
| Neo4j HTTP | localhost | 7474 | HTTP |
| Neo4j Bolt | localhost | 7687 | Bolt |
| Kafka | localhost | 9093 | TCP |
| MinIO API | localhost | 9002 | HTTP |
| MinIO Console | localhost | 9003 | HTTP |

### Default Credentials

| Service | Username | Password |
|---------|----------|----------|
| PostgreSQL | ks_user | ks_password |
| Neo4j | neo4j | neo4j_password |
| MinIO | minioadmin | minioadmin |

---

## Recommended Additional Tools

운영 편의성을 위해 다음 도구 추가를 권장합니다:

| Tool | Purpose | Priority | Port |
|------|---------|----------|------|
| Attu | Milvus 관리 | Medium | 8081 |
| Kafka UI | Kafka 모니터링 | Medium | 8082 |
| pgAdmin | PostgreSQL 관리 | Low | 5050 |

설치가 필요한 경우 위의 각 섹션에 있는 docker-compose 설정을 참고하세요.

---

## Troubleshooting

### Neo4j Browser 접속 안됨
```bash
# 서비스 상태 확인
docker logs knowledge-store-neo4j

# 재시작
cd docker && docker compose restart neo4j
```

### MinIO Console 접속 안됨
```bash
# 서비스 상태 확인
docker logs knowledge-store-minio

# 헬스체크
curl http://localhost:9002/minio/health/live
```

### 포트 충돌
```bash
# 사용 중인 포트 확인
lsof -i :7474
lsof -i :9003

# docker/.env에서 포트 변경 후 재시작
cd docker && docker compose down && docker compose up -d
```
