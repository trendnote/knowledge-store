# Knowledge Store - Docker Infrastructure

Docker Compose 설정으로 Knowledge Store Layer에 필요한 모든 인프라 서비스를 제공합니다.

## Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| PostgreSQL | postgres:15-alpine | 5432 | Metadata, ACL, Audit logs |
| Milvus | milvusdb/milvus:v2.5.0 | 19530, 9091 | Vector database |
| Neo4j | neo4j:5.15-community | 7474, 7687 | Graph database |
| Kafka | confluentinc/cp-kafka:7.5.0 | 9092 | Event streaming |
| etcd | quay.io/coreos/etcd:v3.5.5 | 2379 (internal) | Milvus metadata |
| MinIO | minio/minio | 9000, 9001 | Milvus object storage |

## Quick Start

```bash
# 1. Navigate to docker directory
cd docker

# 2. Copy environment file (optional, defaults are provided)
cp .env.example .env

# 3. Start all services
docker compose up -d

# 4. Check service status
docker compose ps

# 5. View logs
docker compose logs -f

# 6. Stop all services
docker compose down
```

## Port Conflicts

기존 RAG Platform이 실행 중인 경우, 포트 충돌이 발생할 수 있습니다.

### Option 1: Stop existing services first
```bash
# Stop existing RAG platform
cd /path/to/rag-platform
docker compose down

# Then start Knowledge Store
cd /path/to/knowledge-store/docker
docker compose up -d
```

### Option 2: Use alternate ports
`.env` 파일을 수정하여 다른 포트를 사용할 수 있습니다:

```bash
# .env
POSTGRES_PORT=5433        # Instead of 5432
MILVUS_PORT=19531         # Instead of 19530
NEO4J_HTTP_PORT=7475      # Instead of 7474
NEO4J_BOLT_PORT=7688      # Instead of 7687
KAFKA_PORT=9093           # Instead of 9092
```

## Service Health Checks

각 서비스의 상태를 확인하는 방법:

```bash
# PostgreSQL
docker exec knowledge-store-postgres pg_isready -U ks_user -d knowledge_store

# Milvus
curl http://localhost:9091/healthz

# Neo4j
curl http://localhost:7474

# Kafka
docker exec knowledge-store-kafka kafka-topics.sh --bootstrap-server localhost:9092 --list

# All services at once
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

## Data Persistence

모든 데이터는 Docker named volumes에 저장됩니다:

| Volume | Service | Purpose |
|--------|---------|---------|
| knowledge-store-postgres-data | PostgreSQL | Database files |
| knowledge-store-milvus-data | Milvus | Vector data |
| knowledge-store-neo4j-data | Neo4j | Graph data |
| knowledge-store-kafka-data | Kafka | Event logs |
| knowledge-store-minio-data | MinIO | Object storage |
| knowledge-store-etcd-data | etcd | Milvus metadata |

### Backup Volumes
```bash
# List volumes
docker volume ls | grep knowledge-store

# Backup a volume (example: postgres)
docker run --rm -v knowledge-store-postgres-data:/data -v $(pwd):/backup alpine tar cvf /backup/postgres-backup.tar /data
```

### Reset All Data
```bash
# WARNING: This will delete all data!
docker compose down -v
```

## Troubleshooting

### Milvus fails to start
Milvus requires etcd and MinIO to be healthy first. Check their logs:
```bash
docker compose logs etcd
docker compose logs minio
```

### Neo4j authentication issues
Default credentials are `neo4j/neo4j_password`. To reset:
```bash
docker compose down
docker volume rm knowledge-store-neo4j-data
docker compose up -d neo4j
```

### Kafka broker not accessible
Ensure the advertised listeners are correctly configured for your environment:
```bash
docker compose logs kafka
```

## Resource Requirements

Recommended minimum resources for all services:

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 4 cores | 8 cores |
| Memory | 8 GB | 16 GB |
| Disk | 20 GB | 50 GB |

Neo4j and Milvus are memory-intensive. Adjust memory settings in docker-compose.yml if needed.
