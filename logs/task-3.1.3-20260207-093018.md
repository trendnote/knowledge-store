# Task 3.1.3: Graph Search 구현

## 작업 정보
- **Task ID**: 3.1.3
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 09:30:18
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/22
- **Task Plan**: docs/task-plans/task-3.1.3-plan.md

## 작업 개요
Neo4j Cypher 기반 관계 탐색 검색을 구현합니다.

## 생성/수정된 파일

### 1. Search Service 확장
**파일**: `src/services/search_service.py`

#### Neo4jRepositoryProtocol (신규)
```python
class Neo4jRepositoryProtocol(Protocol):
    async def search_by_keyword(
        self, keyword: str, doc_uuids: list[str], top_k: int = 10
    ) -> list[dict[str, Any]]: ...

    async def search_by_entity(
        self, entity_name: str, doc_uuids: list[str], top_k: int = 10
    ) -> list[dict[str, Any]]: ...

    async def search_related(
        self, chunk_uuid: str, doc_uuids: list[str], max_depth: int = 2, top_k: int = 10
    ) -> list[dict[str, Any]]: ...
```

#### SearchService 확장
- `__init__`: `neo4j_repo` 파라미터 추가 (optional)
- `_extract_keywords()`: 쿼리에서 키워드 추출 (불용어 제거)
- `_extract_primary_keyword()`: 가장 긴 키워드 선택
- `_format_graph_results()`: Neo4j 결과 → SearchHit 변환
- `graph_search()`: Cypher 기반 키워드 검색
- `graph_search_by_entity()`: 엔티티 기반 검색
- `graph_search_with_response()`: SearchResponse 래핑

#### Factory 업데이트
```python
def get_search_service(
    milvus_repo: MilvusRepositoryProtocol | None = None,
    embedding_service: EmbeddingServiceProtocol | None = None,
    acl_service: AclServiceProtocol | None = None,
    neo4j_repo: Neo4jRepositoryProtocol | None = None,  # 추가
) -> SearchService:
```

### 2. Unit Tests 확장
**파일**: `tests/unit/test_services/test_search_service.py`

#### 신규 테스트 클래스
- `TestKeywordExtraction`: 7개 테스트
  - 영어 키워드 추출
  - 한국어 키워드 추출
  - 불용어 제거
  - 짧은 토큰 필터
  - Primary 키워드 선택
- `TestGraphSearch`: 7개 테스트
  - 성공 케이스
  - Neo4j 없을 때
  - ACL 필터
  - 스코어링
  - min_score 필터
  - 키워드 추출
  - 예외 전파
- `TestGraphSearchByEntity`: 3개 테스트
- `TestGraphSearchWithResponse`: 2개 테스트
- `TestFormatGraphResults`: 3개 테스트

**총 60개 테스트, 100% PASSED**

## 기술적 특징

### 1. 키워드 추출
```python
def _extract_keywords(self, query: str) -> list[str]:
    # 불용어 (영어 + 한국어)
    stopwords = {
        'the', 'a', 'an', 'is', 'are', ...  # 영어
        '의', '를', '을', '이', '가', ...     # 한국어 조사
    }

    # 2자 이상, 불용어 제외
    keywords = [
        token.lower()
        for token in tokens
        if len(token) >= 2 and token.lower() not in stopwords
    ]
```

### 2. 그래프 결과 스코어링
```python
def _format_graph_results(self, hits):
    for i, hit in enumerate(hits):
        path_length = hit.get("path_length", 0)
        base_score = 1.0 - (i * 0.05)    # 위치 페널티
        path_penalty = path_length * 0.1  # 경로 깊이 페널티
        score = max(0.0, base_score - path_penalty)
```

### 3. Neo4j 선택적 의존성
```python
async def graph_search(self, ...):
    if self._neo4j_repo is None:
        logger.warning("Neo4j repository not configured")
        return []  # 빈 결과 반환
```

## 테스트 결과

```
============================== test session starts ==============================
60 passed in 0.43s

Coverage:
- src/services/search_service.py: 89%
```

## 검색 흐름

```
1. 사용자 요청: graph_search(query, user_id, groups)
2. ACL 서비스: 접근 가능한 doc_uuids 조회
3. 키워드 추출: _extract_primary_keyword(query)
4. Neo4j: Cypher 쿼리 실행 (CONTAINS 매칭)
5. 스코어링: 위치 + 경로 깊이 기반 점수
6. 후처리: min_score 필터링
7. 반환: list[SearchHit] 또는 SearchResponse
```

## Dense vs Sparse vs Graph 비교

| 특성 | Dense | Sparse | Graph |
|------|-------|--------|-------|
| 기반 | 의미 벡터 | 키워드 | 관계 |
| 메트릭 | COSINE | IP | 경로 깊이 |
| 강점 | 의미적 유사성 | 정확 매칭 | 관계 탐색 |
| 약점 | 키워드 누락 | 의미 한계 | 성능 |

## 다음 단계
- Task 3.1.4: Hybrid Search 구현 (RRF 융합)
- Task 3.2: Search API 엔드포인트 구현
