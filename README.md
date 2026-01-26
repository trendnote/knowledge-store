# Knowledge Store

Tri-Store Architecture (Vector + Graph + RDB) for GraphRAG Platform.

## Overview

Knowledge Store is the core storage layer for the GraphRAG Platform, implementing a tri-store architecture that combines:

- **Vector Store (Milvus)**: Dense and sparse embeddings for semantic search
- **Graph Store (Neo4j)**: Knowledge graph for relationship-based queries
- **Relational Store (PostgreSQL)**: Structured metadata and ACL management

## Features

- Hybrid search combining dense, sparse, and graph-based retrieval
- ACL-based access control at document level
- Saga pattern for distributed transaction management
- Event-driven synchronization via Kafka
- BGE-M3 embeddings for multilingual support

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git

### Installation

```bash
# Clone the repository
git clone https://github.com/trendnote/knowledge-store.git
cd knowledge-store

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment file
cp .env.example .env
```

### Running the Application

```bash
# Start infrastructure services
docker compose -f docker/docker-compose.yml up -d

# Run the application
uvicorn src.main:app --reload

# Visit http://localhost:8000/docs for API documentation
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Application                      │
├─────────────────────────────────────────────────────────────┤
│  API Layer        │  Service Layer    │  Repository Layer   │
│  - Routers        │  - DocumentSvc    │  - PostgresRepo     │
│  - Schemas        │  - SearchSvc      │  - MilvusRepo       │
│  - Dependencies   │  - AclSvc         │  - Neo4jRepo        │
│                   │  - SagaCoordinator│  - KafkaRepo        │
├─────────────────────────────────────────────────────────────┤
│                   Infrastructure Layer                       │
│  - PostgreSQL Client  - Milvus Client  - Neo4j Client       │
│  - Kafka Producer/Consumer  - BGE-M3 Embedding Service      │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
knowledge-store/
├── src/
│   ├── api/              # FastAPI routers and schemas
│   ├── services/         # Business logic layer
│   ├── repositories/     # Data access layer
│   ├── infrastructure/   # External service clients
│   └── domain/          # Domain models
├── tests/
│   ├── unit/            # Unit tests
│   ├── integration/     # Integration tests
│   └── e2e/             # End-to-end tests
├── scripts/             # Utility scripts
├── docker/              # Docker configuration
└── docs/                # Documentation
```

## Development

### Code Quality

```bash
# Run linter
ruff check src/

# Run type checker
mypy src/

# Run tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=html
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

## Testing

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run with verbose output
pytest -v
```

## API Documentation

Once the application is running, visit:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Configuration

Configuration is managed via environment variables. See `.env.example` for available options.

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENV` | Environment (development/production) | development |
| `POSTGRES_HOST` | PostgreSQL host | localhost |
| `MILVUS_HOST` | Milvus host | localhost |
| `NEO4J_URI` | Neo4j connection URI | bolt://localhost:7687 |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka servers | localhost:9092 |

## Documentation

- [PRD](docs/prd/knowledge-store-layer-prd.md)
- [Architecture](docs/architecture/architecture.md)
- [Tech Stack](docs/tech-stack/tech-stack.md)
- [Task Breakdown](docs/tasks/all-phases-tasks.md)

## License

Proprietary - All Rights Reserved
