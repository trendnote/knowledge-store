# Task Execution Plan: 3.1.3 - Graph Search 구현

---

## 1. Task Overview

| 항목 | 내용 |
|------|------|
| **Task ID** | 3.1.3 |
| **Task Name** | Graph Search 구현 |
| **Estimate** | 6h |
| **Priority** | P0 |
| **Dependencies** | Task 2.2.3 |

### Description
Neo4j Cypher 기반 관계 탐색 검색을 구현합니다.

### Acceptance Criteria
- [ ] 키워드 추출 (간단한 토큰화)
- [ ] Cypher 쿼리 생성
- [ ] Neo4j Graph Search 호출
- [ ] ACL 필터 적용
- [ ] 검색 결과 포맷팅

---

## 2. Research & Design

### 2.1 참조 문서
- **Architecture**: `docs/architecture/architecture.md` Section 5.4 Search Service
- **PRD**: `docs/prd/knowledge-store-layer-prd.md` Section 5 FR-3

### 2.2 Graph Search 개요
```cypher
// 키워드 기반 Chunk 검색
MATCH (d:Document)-[:CONTAINS]->(c:Chunk)
WHERE d.doc_uuid IN $doc_uuids
AND c.text_preview CONTAINS $keyword
RETURN c.chunk_uuid, c.text_preview, d.title, d.doc_uuid
LIMIT $top_k

// 관계 탐색 (2-hop)
MATCH (d:Document)-[:CONTAINS]->(c:Chunk)-[:MENTIONS]->(e:Entity)
WHERE e.name CONTAINS $keyword
AND d.doc_uuid IN $doc_uuids
RETURN DISTINCT c.chunk_uuid, c.text_preview, d.title, e.name as entity
LIMIT $top_k
```

### 2.3 설계 결정
1. **텍스트 매칭**: CONTAINS 연산자 사용
2. **ACL 적용**: doc_uuid IN 절로 필터링
3. **관계 탐색**: MENTIONS, WROTE 등 관계 활용
4. **스코어링**: 매칭 깊이/개수 기반 점수

### 2.4 검색 전략
| 전략 | 설명 | Cypher 패턴 |
|------|------|-------------|
| Direct | Chunk 텍스트 직접 매칭 | `(c:Chunk)` |
| Entity | 엔티티 통한 간접 매칭 | `(c)-[:MENTIONS]->(e:Entity)` |
| Author | 작성자 기반 | `(d)-[:WROTE]-(p:Person)` |

---

## 3. Implementation Steps

### Step 1: Neo4j Repository 프로토콜 확장 (1h)

**작업 내용:**
1. Neo4jRepositoryProtocol 정의
2. Graph search 결과 모델

**src/services/search_service.py (추가):**
```python
class Neo4jRepositoryProtocol(Protocol):
    """Protocol for Neo4j repository."""

    async def search_by_keyword(
        self,
        keyword: str,
        doc_uuids: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Search chunks by keyword in text."""
        ...

    async def search_by_entity(
        self,
        entity_name: str,
        doc_uuids: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Search chunks mentioning entity."""
        ...

    async def search_related(
        self,
        chunk_uuid: str,
        doc_uuids: list[str],
        max_depth: int,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Search related chunks by graph traversal."""
        ...
```

**src/domain/models/search.py (추가):**
```python
@dataclass
class GraphSearchHit:
    """Graph search hit with relationship info."""

    chunk_uuid: str
    doc_uuid: str
    text_preview: str | None
    title: str | None
    path_length: int = 0
    relationships: list[str] = field(default_factory=list)
    matched_entity: str | None = None
```

**완료 기준:**
- [ ] Neo4jRepositoryProtocol 정의
- [ ] GraphSearchHit 모델 정의

---

### Step 2: 키워드 추출 (1h)

**작업 내용:**
1. 간단한 토큰화
2. 불용어 제거
3. 키워드 추출 로직

**src/services/search_service.py (추가):**
```python
    def _extract_keywords(self, query: str) -> list[str]:
        """Extract keywords from query for graph search.

        Simple tokenization - can be enhanced with NLP.

        Args:
            query: Search query

        Returns:
            List of keywords
        """
        import re

        # Normalize whitespace
        text = re.sub(r'\s+', ' ', query.strip())

        # Split by whitespace and punctuation
        tokens = re.split(r'[\s,;:!?()[\]{}]+', text)

        # Filter short tokens and stopwords
        stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be',
                     '의', '를', '을', '이', '가', '은', '는', '에', '에서'}

        keywords = [
            token.lower()
            for token in tokens
            if len(token) >= 2 and token.lower() not in stopwords
        ]

        return keywords

    def _extract_primary_keyword(self, query: str) -> str:
        """Extract primary keyword for graph search.

        Uses the longest keyword as primary.

        Args:
            query: Search query

        Returns:
            Primary keyword
        """
        keywords = self._extract_keywords(query)
        if not keywords:
            return query.strip()

        # Use longest keyword as primary
        return max(keywords, key=len)
```

**완료 기준:**
- [ ] _extract_keywords 구현
- [ ] _extract_primary_keyword 구현
- [ ] 한국어 불용어 처리

---

### Step 3: Graph Search 메서드 구현 (2h)

**작업 내용:**
1. graph_search 메서드
2. Cypher 쿼리 실행
3. 결과 스코어링

**src/services/search_service.py (추가):**
```python
    def __init__(
        self,
        milvus_repo: MilvusRepositoryProtocol,
        embedding_service: EmbeddingServiceProtocol,
        acl_service: AclServiceProtocol,
        neo4j_repo: Neo4jRepositoryProtocol | None = None,
    ) -> None:
        """Initialize search service.

        Args:
            milvus_repo: Milvus repository for vector search
            embedding_service: Service for generating embeddings
            acl_service: Service for access control
            neo4j_repo: Neo4j repository for graph search (optional)
        """
        self._milvus_repo = milvus_repo
        self._embedding_service = embedding_service
        self._acl_service = acl_service
        self._neo4j_repo = neo4j_repo

    def _format_graph_results(
        self,
        hits: list[dict[str, Any]],
    ) -> list[SearchResult]:
        """Format Neo4j search hits to SearchResult.

        Args:
            hits: Raw search hits from Neo4j

        Returns:
            List of formatted SearchResult
        """
        results = []
        for i, hit in enumerate(hits):
            # Score based on position and path length
            path_length = hit.get("path_length", 0)
            base_score = 1.0 - (i * 0.05)  # Position penalty
            path_penalty = path_length * 0.1  # Longer paths score lower
            score = max(0.0, base_score - path_penalty)

            results.append(
                SearchResult(
                    chunk_uuid=hit.get("chunk_uuid", ""),
                    doc_uuid=hit.get("doc_uuid", ""),
                    score=score,
                    search_type=SearchType.GRAPH,
                    text_preview=hit.get("text_preview"),
                    title=hit.get("title"),
                    metadata={
                        "path_length": path_length,
                        "matched_entity": hit.get("matched_entity"),
                        "relationships": hit.get("relationships", []),
                    },
                )
            )
        return results

    async def graph_search(
        self,
        query: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Execute graph-based search.

        Searches for chunks based on text content and graph relationships.

        Args:
            query: Search query text
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return
            min_score: Minimum score threshold

        Returns:
            List of search results
        """
        import logging

        logger = logging.getLogger(__name__)

        if self._neo4j_repo is None:
            logger.warning("Neo4j repository not configured, skipping graph search")
            return []

        groups = user_groups or []

        # 1. Get accessible documents
        accessible_docs = await self._acl_service.get_accessible_documents(
            user_id, groups
        )

        if not accessible_docs:
            logger.debug("No accessible documents for user")
            return []

        # 2. Extract keyword
        keyword = self._extract_primary_keyword(query)
        logger.debug(f"Graph search keyword: {keyword}")

        # 3. Execute graph search
        try:
            hits = await self._neo4j_repo.search_by_keyword(
                keyword=keyword,
                doc_uuids=accessible_docs,
                top_k=top_k,
            )
        except Exception as e:
            logger.error(f"Graph search failed: {e}")
            raise

        # 4. Format and filter results
        results = self._format_graph_results(hits)

        if min_score > 0:
            results = [r for r in results if r.score >= min_score]

        logger.info(f"Graph search returned {len(results)} results")
        return results

    async def graph_search_by_entity(
        self,
        entity_name: str,
        user_id: str,
        user_groups: list[str] | None = None,
        top_k: int = 10,
    ) -> list[SearchResult]:
        """Search chunks by entity name.

        Finds chunks that mention a specific entity.

        Args:
            entity_name: Entity name to search for
            user_id: User identifier for ACL
            user_groups: User's group memberships
            top_k: Maximum results to return

        Returns:
            List of search results
        """
        import logging

        logger = logging.getLogger(__name__)

        if self._neo4j_repo is None:
            return []

        groups = user_groups or []

        accessible_docs = await self._acl_service.get_accessible_documents(
            user_id, groups
        )

        if not accessible_docs:
            return []

        try:
            hits = await self._neo4j_repo.search_by_entity(
                entity_name=entity_name,
                doc_uuids=accessible_docs,
                top_k=top_k,
            )
        except Exception as e:
            logger.error(f"Entity search failed: {e}")
            raise

        return self._format_graph_results(hits)
```

**완료 기준:**
- [ ] graph_search 구현
- [ ] graph_search_by_entity 구현
- [ ] 결과 스코어링 로직
- [ ] ACL 필터 적용

---

### Step 4: 테스트 작성 (2h)

**작업 내용:**
1. Graph search 단위 테스트
2. 키워드 추출 테스트
3. 엔티티 검색 테스트

**tests/unit/test_services/test_graph_search.py:**
```python
"""Tests for graph search."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from src.services.search_service import SearchService
from src.domain.models.search import SearchType


@pytest.fixture
def mock_neo4j_repo() -> MagicMock:
    """Create mock Neo4j repository."""
    return MagicMock()


@pytest.fixture
def mock_milvus_repo() -> MagicMock:
    """Create mock Milvus repository."""
    return MagicMock()


@pytest.fixture
def mock_embedding_service() -> MagicMock:
    """Create mock embedding service."""
    return MagicMock()


@pytest.fixture
def mock_acl_service() -> MagicMock:
    """Create mock ACL service."""
    mock = MagicMock()
    mock.get_accessible_documents = AsyncMock(return_value=["doc-1", "doc-2"])
    return mock


@pytest.fixture
def search_service(
    mock_milvus_repo: MagicMock,
    mock_embedding_service: MagicMock,
    mock_acl_service: MagicMock,
    mock_neo4j_repo: MagicMock,
) -> SearchService:
    """Create search service with mocks."""
    return SearchService(
        mock_milvus_repo,
        mock_embedding_service,
        mock_acl_service,
        mock_neo4j_repo,
    )


class TestKeywordExtraction:
    """Tests for keyword extraction."""

    def test_extract_keywords_english(
        self,
        search_service: SearchService,
    ) -> None:
        """Test keyword extraction for English."""
        keywords = search_service._extract_keywords("Find the important documents")
        assert "find" in keywords
        assert "important" in keywords
        assert "documents" in keywords
        assert "the" not in keywords  # Stopword

    def test_extract_keywords_korean(
        self,
        search_service: SearchService,
    ) -> None:
        """Test keyword extraction for Korean."""
        keywords = search_service._extract_keywords("인공지능 기술 문서를 찾아주세요")
        assert "인공지능" in keywords
        assert "기술" in keywords
        assert "문서" in keywords or "문서를" in keywords

    def test_extract_primary_keyword(
        self,
        search_service: SearchService,
    ) -> None:
        """Test primary keyword extraction."""
        keyword = search_service._extract_primary_keyword("AI technology documents")
        # Should pick longest non-stopword
        assert keyword in ["technology", "documents"]


class TestGraphSearch:
    """Tests for graph search."""

    async def test_graph_search_success(
        self,
        search_service: SearchService,
        mock_neo4j_repo: MagicMock,
    ) -> None:
        """Test successful graph search."""
        mock_neo4j_repo.search_by_keyword = AsyncMock(
            return_value=[
                {
                    "chunk_uuid": "c1",
                    "doc_uuid": "doc-1",
                    "text_preview": "Found text",
                    "title": "Document 1",
                    "path_length": 0,
                },
            ]
        )

        results = await search_service.graph_search(
            query="test keyword",
            user_id="user1",
            top_k=10,
        )

        assert len(results) == 1
        assert results[0].search_type == SearchType.GRAPH

    async def test_graph_search_no_neo4j_repo(
        self,
        mock_milvus_repo: MagicMock,
        mock_embedding_service: MagicMock,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test graph search without Neo4j repo."""
        service = SearchService(
            mock_milvus_repo,
            mock_embedding_service,
            mock_acl_service,
            neo4j_repo=None,
        )

        results = await service.graph_search(
            query="test",
            user_id="user1",
        )

        assert len(results) == 0

    async def test_graph_search_no_accessible_docs(
        self,
        search_service: SearchService,
        mock_acl_service: MagicMock,
    ) -> None:
        """Test graph search with no accessible documents."""
        mock_acl_service.get_accessible_documents = AsyncMock(return_value=[])

        results = await search_service.graph_search(
            query="test",
            user_id="user1",
        )

        assert len(results) == 0

    async def test_graph_search_scoring(
        self,
        search_service: SearchService,
        mock_neo4j_repo: MagicMock,
    ) -> None:
        """Test graph search result scoring."""
        mock_neo4j_repo.search_by_keyword = AsyncMock(
            return_value=[
                {"chunk_uuid": "c1", "doc_uuid": "d1", "path_length": 0},
                {"chunk_uuid": "c2", "doc_uuid": "d1", "path_length": 1},
                {"chunk_uuid": "c3", "doc_uuid": "d1", "path_length": 2},
            ]
        )

        results = await search_service.graph_search(
            query="test",
            user_id="user1",
        )

        # First result should have highest score
        assert results[0].score > results[1].score
        assert results[1].score > results[2].score


class TestEntitySearch:
    """Tests for entity-based search."""

    async def test_entity_search_success(
        self,
        search_service: SearchService,
        mock_neo4j_repo: MagicMock,
    ) -> None:
        """Test successful entity search."""
        mock_neo4j_repo.search_by_entity = AsyncMock(
            return_value=[
                {
                    "chunk_uuid": "c1",
                    "doc_uuid": "doc-1",
                    "matched_entity": "AI",
                },
            ]
        )

        results = await search_service.graph_search_by_entity(
            entity_name="AI",
            user_id="user1",
        )

        assert len(results) == 1
        assert results[0].metadata.get("matched_entity") == "AI"
```

**완료 기준:**
- [ ] 키워드 추출 테스트
- [ ] graph_search 성공 테스트
- [ ] Neo4j 없을 때 테스트
- [ ] 스코어링 테스트
- [ ] 엔티티 검색 테스트

---

## 4. Testing Plan

### 4.1 Unit Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_extract_keywords_english` | 영어 키워드 추출 | 불용어 제외 |
| `test_extract_keywords_korean` | 한국어 키워드 추출 | 조사 처리 |
| `test_graph_search_success` | 정상 검색 | 결과 반환 |
| `test_graph_search_scoring` | 스코어링 | 거리 반비례 |

### 4.2 Integration Tests
| Test Case | Description | Expected |
|-----------|-------------|----------|
| `test_graph_search_real_neo4j` | 실제 Neo4j 검색 | 결과 반환 |
| `test_graph_search_relationship` | 관계 탐색 | 연결된 노드 |

---

## 5. Risks & Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Cypher 쿼리 성능 | High | Medium | 인덱스 활용, LIMIT 적용 |
| 깊은 그래프 탐색 | Medium | Low | max_depth 제한 |
| 키워드 추출 품질 | Medium | Medium | NLP 라이브러리 고려 |

---

## 6. Definition of Done

- [ ] 키워드 추출 구현
- [ ] graph_search 메서드 구현
- [ ] graph_search_by_entity 구현
- [ ] ACL 필터 적용
- [ ] 결과 스코어링
- [ ] 테스트 작성 및 통과
- [ ] mypy 타입 체크 통과

---

## 7. Time Breakdown

| Step | Estimated | Actual |
|------|-----------|--------|
| Step 1: 프로토콜 및 모델 | 1h | - |
| Step 2: 키워드 추출 | 1h | - |
| Step 3: Graph Search 구현 | 2h | - |
| Step 4: 테스트 | 2h | - |
| **Total** | **6h** | - |

---

## 8. Change Log

| Date | Author | Description |
|------|--------|-------------|
| 2026-01-26 | Platform Team | Initial plan |
