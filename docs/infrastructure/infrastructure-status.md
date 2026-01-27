# Infrastructure Status Report

**Date**: 2026-01-26
**Checked by**: Platform Team

---

## Executive Summary

기존 RAG Platform 인프라를 확인한 결과, Knowledge Store Layer에 필요한 일부 컴포넌트가 이미 설치되어 있습니다. 다만, Milvus 버전 업그레이드와 Neo4j, Kafka 신규 설치가 필요합니다.

---

## Docker Environment

| Item | Version | Status |
|------|---------|--------|
| Docker Engine | 29.1.3 | ✅ Installed |
| Docker Compose | v2.40.3-desktop.1 | ✅ Installed |

---

## Container Status

### Required Components

| Component | Status | Container Name | Current Version | Required Version | Gap |
|-----------|--------|----------------|-----------------|------------------|-----|
| PostgreSQL | ✅ Running | rag-postgres | 15.15 | 15+ | ✅ Meets requirement |
| Milvus | ✅ Running | rag-milvus | 2.3.3 | 2.5+ | ⚠️ Needs upgrade |
| Neo4j | ❌ Not Found | - | - | 5.x | ❌ Not installed |
| Kafka | ❌ Not Found | - | - | 3.x | ❌ Not installed |
| etcd | ✅ Running | rag-etcd | 3.5.5 | 3.5+ | ✅ Meets requirement |
| MinIO | ✅ Running | rag-minio | RELEASE.2023-03-20 | - | ✅ Present |

### Additional Components (Existing RAG Platform)

| Component | Status | Container Name | Purpose |
|-----------|--------|----------------|---------|
| Open WebUI | ✅ Running | rag-open-webui | Web Interface |
| Ollama | ✅ Running | rag-ollama | LLM Inference |
| Attu | ✅ Running | rag-attu | Milvus GUI |

---

## Network Configuration

| Network Name | Driver | Containers |
|--------------|--------|------------|
| rag-platform_rag-network | bridge | All RAG containers |

All existing containers are connected to the same Docker bridge network (`rag-platform_rag-network`), enabling inter-container communication.

---

## Port Mappings

| Component | Internal Port | External Port | Status |
|-----------|--------------|---------------|--------|
| PostgreSQL | 5432 | 5432 | ✅ Available |
| Milvus | 19530 | 19530 | ✅ Available |
| Milvus Health | 9091 | 9091 | ✅ Available |
| Neo4j Bolt | 7687 | - | ❌ Not configured |
| Neo4j HTTP | 7474 | - | ❌ Not configured |
| Kafka | 9092 | - | ❌ Not configured |
| Open WebUI | 8080 | 3001 | ✅ Available |
| Attu | 3000 | 8080 | ✅ Available |
| Ollama | 11434 | 11434 | ✅ Available |

---

## Volume Configuration

| Volume Name | Purpose | Status |
|-------------|---------|--------|
| rag-platform_postgres-data | PostgreSQL data | ✅ Active |
| rag-platform_milvus-data | Milvus vector data | ✅ Active |
| rag-platform_minio-data | MinIO object storage | ✅ Active |
| rag-platform_etcd-data | etcd configuration | ✅ Active |
| rag-platform_ollama-data | Ollama models | ✅ Active |
| rag-platform_open-webui-data | Open WebUI data | ✅ Active |

---

## Gap Analysis

### Components Needing Attention

#### 1. Milvus Upgrade Required
- **Current**: v2.3.3
- **Required**: v2.5+
- **Reason**: Knowledge Store requires Milvus 2.5+ for improved sparse vector support and hybrid search capabilities
- **Risk**: Data migration may be required
- **Action**: Plan upgrade during maintenance window

#### 2. Neo4j Installation Required
- **Status**: Not installed
- **Required**: v5.x Community Edition
- **Purpose**: Graph storage for knowledge relationships
- **Action**: Add to docker-compose.yml

#### 3. Kafka Installation Required
- **Status**: Not installed
- **Required**: v3.x with KRaft mode
- **Purpose**: Event streaming for document synchronization
- **Action**: Add to docker-compose.yml

---

## Action Items

### High Priority (Before Development)

1. [ ] **Install Neo4j 5.x**
   - Add neo4j:5-community to docker-compose.yml
   - Configure ports 7687 (Bolt) and 7474 (HTTP)
   - Set up authentication

2. [ ] **Install Kafka 3.x**
   - Add confluentinc/cp-kafka or bitnami/kafka to docker-compose.yml
   - Configure KRaft mode (no Zookeeper)
   - Set up topics: documents, sync

### Medium Priority (During Development)

3. [ ] **Upgrade Milvus to 2.5+**
   - Plan data backup strategy
   - Test upgrade in staging environment
   - Schedule maintenance window for production upgrade

### Low Priority (Optimization)

4. [ ] **Network Configuration**
   - Consider creating a dedicated network for Knowledge Store
   - Review port exposure for security

5. [ ] **Volume Management**
   - Implement backup strategy for all data volumes
   - Consider using named volumes for new components

---

## Recommendations

### For Task 1.2.2 (Docker Compose Setup)

1. **Create New Docker Compose File**
   - Don't modify existing `rag-platform` docker-compose
   - Create `docker/docker-compose.yml` for Knowledge Store specific services
   - Use the existing network `rag-platform_rag-network` or create a new one

2. **Component Configuration**
   ```yaml
   # Recommended additions for Knowledge Store
   services:
     neo4j:
       image: neo4j:5-community
       ports:
         - "7474:7474"
         - "7687:7687"

     kafka:
       image: confluentinc/cp-kafka:7.5.0
       ports:
         - "9092:9092"
   ```

3. **Network Strategy**
   - Option A: Join existing `rag-platform_rag-network`
   - Option B: Create new `knowledge-store_network` with external links

---

## Appendix

### Docker Images Present

```
milvusdb/milvus:v2.3.3
postgres:15-alpine
quay.io/coreos/etcd:v3.5.5
minio/minio:RELEASE.2023-03-20T20-16-18Z
ollama/ollama:latest
ghcr.io/open-webui/open-webui:latest
zilliz/attu:v2.3.10
```

### Health Check Commands

```bash
# PostgreSQL
docker exec rag-postgres psql -V

# Milvus
curl http://localhost:9091/healthz

# etcd
docker exec rag-etcd etcd --version
```

---

## Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial infrastructure assessment |
