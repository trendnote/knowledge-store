# Task Execution Plan: 1.1.1 - 프로젝트 구조 생성

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.1.1 |
| **Task Name** | 프로젝트 구조 생성 |
| **Estimate** | 4h |
| **Priority** | P0 |
| **Dependencies** | None |

### Description
Architecture 문서의 Project Structure에 따라 Python 프로젝트 기본 구조를 생성합니다.

### Acceptance Criteria
- [ ] `knowledge-store/` 폴더 구조 생성 (src/, tests/, scripts/, docker/)
- [ ] `pyproject.toml` 생성 (Tech Stack 문서의 dependencies 반영)
- [ ] `.env.example` 생성 (환경 변수 템플릿)
- [ ] `.gitignore` 업데이트 (Python 프로젝트 특화)
- [ ] `README.md` 기본 구조 작성
- [ ] `ruff`, `mypy` 설정 파일 생성
- [ ] `pytest` 설정 (`conftest.py`)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 7. Project Structure
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 3. Python Dependencies

### 2.2 프로젝트 구조 (Architecture 문서 기반)
```
knowledge-store/
├── src/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── dependencies.py
│   │   ├── routers/
│   │   │   └── __init__.py
│   │   └── schemas/
│   │       └── __init__.py
│   ├── services/
│   │   ├── __init__.py
│   │   └── saga/
│   │       └── __init__.py
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── postgres/
│   │   │   └── __init__.py
│   │   ├── milvus/
│   │   │   └── __init__.py
│   │   ├── neo4j/
│   │   │   └── __init__.py
│   │   └── kafka/
│   │       └── __init__.py
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   └── __init__.py
│   │   ├── messaging/
│   │   │   └── __init__.py
│   │   └── embedding/
│   │       └── __init__.py
│   └── domain/
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   └── __init__.py
│   ├── integration/
│   │   └── __init__.py
│   └── e2e/
│       └── __init__.py
├── scripts/
│   └── __init__.py
├── docker/
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

### 2.3 설계 결정
1. **패키지 관리**: `pyproject.toml` (PEP 517/518 표준)
2. **Linter/Formatter**: `ruff` (빠른 속도, Black + isort + flake8 통합)
3. **Type Checker**: `mypy` (strict 모드)
4. **Test Framework**: `pytest` + `pytest-asyncio`

---

## 3. Implementation Steps

### Step 1: 디렉토리 구조 생성 (0.5h)

**작업 내용:**
1. src/ 하위 디렉토리 생성
2. tests/ 하위 디렉토리 생성
3. scripts/, docker/ 디렉토리 생성
4. 모든 Python 패키지에 `__init__.py` 생성

**명령어:**
```bash
# src 구조
mkdir -p src/{api/{routers,schemas},services/saga,repositories/{postgres,milvus,neo4j,kafka},infrastructure/{database,messaging,embedding},domain}

# tests 구조
mkdir -p tests/{unit,integration,e2e}

# scripts, docker
mkdir -p scripts docker
```

**완료 기준:**
- [ ] 모든 디렉토리 생성 확인
- [ ] 모든 `__init__.py` 파일 생성 확인

---

### Step 2: pyproject.toml 생성 (1h)

**작업 내용:**
1. 프로젝트 메타데이터 정의
2. Core dependencies 추가 (Tech Stack 문서 반영)
3. Dev dependencies 추가
4. ruff, mypy, pytest 설정 통합

**파일 내용:**
```toml
[project]
name = "knowledge-store"
version = "0.1.0"
description = "Knowledge Store Layer - Tri-Store Architecture for GraphRAG Platform"
requires-python = ">=3.11"
readme = "README.md"

dependencies = [
    # Web Framework
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",

    # Database Clients
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "pymilvus>=2.4.0",
    "neo4j>=5.0.0",

    # Message Queue
    "aiokafka>=0.10.0",

    # Embedding
    "FlagEmbedding>=1.2.0",
    "torch>=2.0.0",

    # Utilities
    "httpx>=0.27.0",
    "structlog>=24.0.0",
    "prometheus-client>=0.20.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.3.0",
    "mypy>=1.8.0",
    "pre-commit>=3.6.0",
    "testcontainers>=4.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "C4", "SIM"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --cov=src --cov-report=term-missing"
```

**완료 기준:**
- [ ] `pip install -e .` 성공
- [ ] `pip install -e ".[dev]"` 성공

---

### Step 3: 환경 변수 및 설정 파일 생성 (0.5h)

**작업 내용:**
1. `.env.example` 생성 (Architecture 문서 Section 8.2 반영)
2. `.gitignore` 업데이트

**.env.example:**
```bash
# Application
APP_NAME=knowledge-store
APP_ENV=development
DEBUG=true

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=knowledge_store
POSTGRES_USER=ks_user
POSTGRES_PASSWORD=ks_password
POSTGRES_POOL_SIZE=20

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=knowledge_chunks

# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_GROUP=knowledge-store

# Embedding
BGE_M3_MODEL=BAAI/bge-m3
BGE_M3_USE_FP16=true
```

**완료 기준:**
- [ ] `.env.example` 모든 환경 변수 포함
- [ ] `.gitignore`에 `.env` 포함 확인

---

### Step 4: 기본 소스 파일 생성 (1h)

**작업 내용:**
1. `src/__init__.py` - 패키지 버전 정의
2. `src/main.py` - FastAPI 애플리케이션 진입점 스캐폴드
3. `src/config.py` - Pydantic Settings 스캐폴드 (Task 1.1.2에서 완성)

**src/main.py:**
```python
"""Knowledge Store Layer - FastAPI Application Entry Point."""
from fastapi import FastAPI

app = FastAPI(
    title="Knowledge Store",
    description="Tri-Store Architecture for GraphRAG Platform",
    version="0.1.0",
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Knowledge Store API"}
```

**src/config.py:**
```python
"""Configuration management using Pydantic Settings."""
# Placeholder - Will be implemented in Task 1.1.2
```

**완료 기준:**
- [ ] `uvicorn src.main:app --reload` 실행 성공
- [ ] `http://localhost:8000/` 응답 확인

---

### Step 5: 테스트 설정 및 README 작성 (1h)

**작업 내용:**
1. `tests/conftest.py` - pytest fixtures
2. `tests/unit/test_main.py` - 기본 테스트
3. `README.md` 작성

**tests/conftest.py:**
```python
"""Pytest configuration and fixtures."""
import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

**tests/unit/test_main.py:**
```python
"""Tests for main application."""
from fastapi.testclient import TestClient

from src.main import app


def test_root_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Knowledge Store API"}
```

**README.md 구조:**
```markdown
# Knowledge Store

Tri-Store Architecture (Vector + Graph + RDB) for GraphRAG Platform.

## Quick Start
## Architecture
## Development
## Testing
## License
```

**완료 기준:**
- [ ] `pytest` 실행 성공
- [ ] `ruff check src/` 통과
- [ ] `mypy src/` 통과

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected Result |
|-----------|-------------|-----------------|
| `test_root_endpoint` | GET / 응답 확인 | 200, JSON 응답 |
| `test_app_title` | FastAPI 타이틀 확인 | "Knowledge Store" |

### 4.2 Quality Checks
| Check | Command | Expected |
|-------|---------|----------|
| Linter | `ruff check src/` | No errors |
| Type Check | `mypy src/` | No errors |
| Test | `pytest` | All passed |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Dependency 충돌 | Medium | Low | `pip-tools` 또는 `uv`로 의존성 관리 |
| Python 버전 호환성 | Low | Low | `requires-python = ">=3.11"` 명시 |

---

## 6. Definition of Done

- [ ] 모든 디렉토리 구조 생성
- [ ] `pyproject.toml` 생성 및 설치 성공
- [ ] `.env.example` 생성
- [ ] `src/main.py` 실행 가능
- [ ] `pytest` 통과
- [ ] `ruff check src/` 통과
- [ ] `mypy src/` 통과
- [ ] `README.md` 기본 구조 작성

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 디렉토리 구조 | 0.5h | - |
| Step 2: pyproject.toml | 1h | - |
| Step 3: 환경 변수 설정 | 0.5h | - |
| Step 4: 기본 소스 파일 | 1h | - |
| Step 5: 테스트 및 README | 1h | - |
| **Total** | **4h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
