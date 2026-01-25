# Task Execution Plan: 1.1.2 - 설정 관리 구현 (Pydantic Settings)

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 1.1.2 |
| **Task Name** | 설정 관리 구현 (Pydantic Settings) |
| **Estimate** | 2h |
| **Priority** | P0 |
| **Dependencies** | Task 1.1.1 |

### Description
환경 변수 기반 설정 관리 클래스를 구현합니다.

### Acceptance Criteria
- [ ] `src/config.py`에 Settings 클래스 구현
- [ ] PostgreSQL, Milvus, Neo4j, Kafka 연결 설정 포함
- [ ] `.env` 파일에서 설정 로드
- [ ] 설정 검증 (필수 값 누락 시 에러)

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 8.2 Environment Variables
- **Tech Stack**: `docs/tech-stack/tech-stack.md` Section 4.1 Required Versions

### 2.2 설정 구조
```python
Settings
├── PostgresSettings (중첩)
├── MilvusSettings (중첩)
├── Neo4jSettings (중첩)
├── KafkaSettings (중첩)
└── EmbeddingSettings (중첩)
```

### 2.3 설계 결정
1. **Pydantic v2 BaseSettings** 사용
2. **중첩 설정 클래스**로 관심사 분리
3. **환경 변수 prefix**로 네임스페이스 구분
4. **Validator**로 필수 값 검증

---

## 3. Implementation Steps

### Step 1: Settings 클래스 구조 설계 (0.5h)

**작업 내용:**
1. 중첩 Settings 클래스 정의
2. 환경 변수 매핑 정의
3. 기본값 설정

**src/config.py:**
```python
"""Configuration management using Pydantic Settings."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PostgresSettings(BaseSettings):
    """PostgreSQL connection settings."""

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

    host: str = "localhost"
    port: int = 5432
    db: str = "knowledge_store"
    user: str = Field(..., description="PostgreSQL user (required)")
    password: str = Field(..., description="PostgreSQL password (required)")
    pool_size: int = 20

    @property
    def dsn(self) -> str:
        """Generate PostgreSQL DSN."""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def async_dsn(self) -> str:
        """Generate async PostgreSQL DSN for asyncpg."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


class MilvusSettings(BaseSettings):
    """Milvus connection settings."""

    model_config = SettingsConfigDict(env_prefix="MILVUS_")

    host: str = "localhost"
    port: int = 19530
    collection: str = "knowledge_chunks"


class Neo4jSettings(BaseSettings):
    """Neo4j connection settings."""

    model_config = SettingsConfigDict(env_prefix="NEO4J_")

    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = Field(..., description="Neo4j password (required)")


class KafkaSettings(BaseSettings):
    """Kafka connection settings."""

    model_config = SettingsConfigDict(env_prefix="KAFKA_")

    bootstrap_servers: str = "localhost:9092"
    consumer_group: str = "knowledge-store"


class EmbeddingSettings(BaseSettings):
    """BGE-M3 embedding model settings."""

    model_config = SettingsConfigDict(env_prefix="BGE_M3_")

    model: str = "BAAI/bge-m3"
    use_fp16: bool = True


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "knowledge-store"
    app_env: str = "development"
    debug: bool = True

    # Sub-settings (loaded from environment)
    postgres: PostgresSettings = Field(default_factory=PostgresSettings)
    milvus: MilvusSettings = Field(default_factory=MilvusSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    kafka: KafkaSettings = Field(default_factory=KafkaSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
```

**완료 기준:**
- [ ] 모든 Settings 클래스 정의 완료
- [ ] Type hints 완전

---

### Step 2: 테스트 작성 (1h)

**작업 내용:**
1. 환경 변수 로드 테스트
2. 기본값 테스트
3. 필수 값 누락 시 ValidationError 테스트
4. DSN 생성 테스트

**tests/unit/test_config.py:**
```python
"""Tests for configuration management."""
import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from src.config import (
    EmbeddingSettings,
    KafkaSettings,
    MilvusSettings,
    Neo4jSettings,
    PostgresSettings,
    Settings,
    get_settings,
)


class TestPostgresSettings:
    """Tests for PostgresSettings."""

    def test_default_values(self) -> None:
        """Test default values are set correctly."""
        with patch.dict(os.environ, {
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_pass",
        }):
            settings = PostgresSettings()
            assert settings.host == "localhost"
            assert settings.port == 5432
            assert settings.db == "knowledge_store"
            assert settings.pool_size == 20

    def test_dsn_generation(self) -> None:
        """Test DSN string generation."""
        with patch.dict(os.environ, {
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_pass",
        }):
            settings = PostgresSettings()
            assert settings.dsn == "postgresql://test_user:test_pass@localhost:5432/knowledge_store"

    def test_required_fields_validation(self) -> None:
        """Test that required fields raise ValidationError when missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError):
                PostgresSettings()


class TestMilvusSettings:
    """Tests for MilvusSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = MilvusSettings()
        assert settings.host == "localhost"
        assert settings.port == 19530
        assert settings.collection == "knowledge_chunks"


class TestNeo4jSettings:
    """Tests for Neo4jSettings."""

    def test_required_password(self) -> None:
        """Test that password is required."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValidationError):
                Neo4jSettings()


class TestKafkaSettings:
    """Tests for KafkaSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = KafkaSettings()
        assert settings.bootstrap_servers == "localhost:9092"
        assert settings.consumer_group == "knowledge-store"


class TestEmbeddingSettings:
    """Tests for EmbeddingSettings."""

    def test_default_values(self) -> None:
        """Test default values."""
        settings = EmbeddingSettings()
        assert settings.model == "BAAI/bge-m3"
        assert settings.use_fp16 is True


class TestSettings:
    """Tests for main Settings class."""

    def test_load_from_env(self) -> None:
        """Test loading settings from environment."""
        with patch.dict(os.environ, {
            "POSTGRES_USER": "test_user",
            "POSTGRES_PASSWORD": "test_pass",
            "NEO4J_PASSWORD": "neo4j_pass",
            "APP_ENV": "testing",
        }):
            settings = Settings()
            assert settings.app_env == "development"  # env_file takes precedence
            assert settings.postgres.user == "test_user"

    def test_get_settings_cached(self) -> None:
        """Test that get_settings returns cached instance."""
        get_settings.cache_clear()  # Clear cache for test
        with patch.dict(os.environ, {
            "POSTGRES_USER": "test",
            "POSTGRES_PASSWORD": "test",
            "NEO4J_PASSWORD": "test",
        }):
            settings1 = get_settings()
            settings2 = get_settings()
            assert settings1 is settings2
```

**완료 기준:**
- [ ] 모든 테스트 통과
- [ ] 커버리지 > 90%

---

### Step 3: .env 샘플 파일 업데이트 및 문서화 (0.5h)

**작업 내용:**
1. `.env.example` 필수 값 표시
2. 설정 사용 예제 문서화

**.env 업데이트:**
```bash
# Application
APP_NAME=knowledge-store
APP_ENV=development
DEBUG=true

# PostgreSQL (REQUIRED: POSTGRES_USER, POSTGRES_PASSWORD)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=knowledge_store
POSTGRES_USER=ks_user          # Required
POSTGRES_PASSWORD=ks_password  # Required
POSTGRES_POOL_SIZE=20

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=knowledge_chunks

# Neo4j (REQUIRED: NEO4J_PASSWORD)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=neo4j_password  # Required

# Kafka
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_CONSUMER_GROUP=knowledge-store

# Embedding
BGE_M3_MODEL=BAAI/bge-m3
BGE_M3_USE_FP16=true
```

**완료 기준:**
- [ ] `.env.example` 업데이트
- [ ] 필수 값 주석 표시

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected Result |
|-----------|-------------|-----------------|
| `test_default_values` | 기본값 확인 | 기본값 정상 로드 |
| `test_dsn_generation` | DSN 문자열 생성 | 올바른 포맷 |
| `test_required_fields_validation` | 필수 필드 누락 | ValidationError |
| `test_load_from_env` | 환경 변수 로드 | 정상 로드 |
| `test_get_settings_cached` | 캐싱 확인 | 동일 인스턴스 |

### 4.2 Quality Checks
| Check | Command | Expected |
|-------|---------|----------|
| Test | `pytest tests/unit/test_config.py` | All passed |
| Coverage | `pytest --cov=src/config` | > 90% |
| Type Check | `mypy src/config.py` | No errors |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| 중첩 설정 환경 변수 매핑 복잡 | Medium | Medium | SettingsConfigDict prefix 사용 |
| 테스트 환경 격리 | Low | Medium | `patch.dict(os.environ)` 사용 |

---

## 6. Definition of Done

- [ ] `src/config.py` Settings 클래스 구현
- [ ] 모든 DB 연결 설정 포함
- [ ] `.env` 파일에서 설정 로드
- [ ] 필수 값 누락 시 ValidationError
- [ ] 모든 테스트 통과
- [ ] 커버리지 > 90%
- [ ] `mypy src/config.py` 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: Settings 클래스 구현 | 0.5h | - |
| Step 2: 테스트 작성 | 1h | - |
| Step 3: 문서화 | 0.5h | - |
| **Total** | **2h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-25 | Platform Team | Initial plan |
