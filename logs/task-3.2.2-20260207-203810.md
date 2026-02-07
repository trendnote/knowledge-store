# Task 3.2.2: Search 통합 테스트

## 작업 정보
- **Task ID**: 3.2.2
- **작업자**: Claude AI
- **작업일시**: 2026-02-07 20:38:10
- **GitHub Issue**: https://github.com/trendnote/knowledge-store/issues/25
- **Task Plan**: docs/task-plans/task-3.2.2-plan.md

## 작업 개요
Search 기능의 통합 테스트를 구현합니다. Mock 기반 테스트와 실제 인프라 테스트 모두 지원합니다.

## 생성/수정된 파일

### 1. Integration Test Fixtures
**파일**: `tests/integration/conftest.py`

#### 테스트 데이터
```python
TEST_DOCUMENTS = [
    {
        "doc_uuid": "doc-001",
        "title": "인공지능 기술 개요",
        "owner_id": "user1",
        "allowed_groups": ["engineering"],
        "chunks": [...]  # 3개 청크
    },
    {
        "doc_uuid": "doc-002",
        "title": "자연어 처리 가이드",
        "owner_id": "user1",
        "allowed_groups": ["engineering", "ml-team"],
        "chunks": [...]  # 2개 청크
    },
    {
        "doc_uuid": "doc-003",
        "title": "비공개 기밀 문서",
        "owner_id": "user2",
        "allowed_groups": [],  # Private
        "chunks": [...]  # 1개 청크
    },
    {
        "doc_uuid": "doc-004",
        "title": "전사 공개 문서",
        "owner_id": "admin",
        "allowed_groups": ["*"],  # Public
        "chunks": [...]  # 2개 청크
    },
]
```

#### Mock Services
- **create_mock_acl_service()**: ACL 권한 검증 (소유자, 그룹, 공개)
- **create_mock_embedding_service()**: 임베딩 생성 (dense + sparse)
- **create_mock_milvus_repo()**: 벡터 검색 (dense_search, sparse_search)
- **create_mock_neo4j_repo()**: 그래프 검색 (search_by_keyword, search_by_entity)

#### Fixtures
- `test_docs`: 테스트마다 고유 UUID 생성
- `mock_acl_service`: ACL 서비스 Mock
- `mock_embedding_service`: 임베딩 서비스 Mock
- `mock_milvus_repo`: Milvus 리포지토리 Mock
- `mock_neo4j_repo`: Neo4j 리포지토리 Mock
- `search_service`: SearchService 인스턴스
- `test_data`: 테스트 데이터 (user1_docs, user2_docs, public_docs)

### 2. Search Flow Integration Tests
**파일**: `tests/integration/test_search_flow.py`

#### TestDenseSearchIntegration (5개 테스트)
- `test_dense_search_returns_results`: 결과 반환 확인
- `test_dense_search_respects_top_k`: top_k 제한 확인
- `test_dense_search_respects_acl`: ACL 권한 검증
- `test_dense_search_with_min_score`: 최소 점수 필터링
- `test_dense_search_with_groups`: 그룹 권한 검색

#### TestSparseSearchIntegration (4개 테스트)
- `test_sparse_search_keyword_match`: 키워드 매칭
- `test_sparse_search_korean_keywords`: 한국어 키워드
- `test_sparse_search_respects_acl`: ACL 권한 검증
- `test_sparse_search_empty_query_returns_empty`: 빈 쿼리 처리

#### TestGraphSearchIntegration (3개 테스트)
- `test_graph_search_text_match`: 텍스트 매칭
- `test_graph_search_respects_acl`: ACL 권한 검증
- `test_graph_search_without_neo4j`: Neo4j 없는 경우 처리

#### TestHybridSearchIntegration (6개 테스트)
- `test_unified_search_combines_results`: 결과 통합
- `test_unified_search_selected_types`: 선택적 검색 타입
- `test_unified_search_deduplication`: 중복 제거
- `test_unified_search_with_min_score`: 최소 점수 필터링
- `test_search_convenience_method`: 편의 메서드
- `test_unified_search_respects_acl`: ACL 권한 검증

#### TestSearchPerformance (3개 테스트)
- `test_search_response_time`: 응답 시간 (< 1초)
- `test_multiple_sequential_searches`: 순차 검색 성능
- `test_large_top_k_performance`: 대용량 top_k (< 2초)

### 3. Search ACL Integration Tests
**파일**: `tests/integration/test_search_acl.py`

#### TestSearchACLUserPermissions (4개 테스트)
- `test_user_sees_own_documents`: 소유 문서 검색
- `test_user_cannot_see_others_private_documents`: 타인 비공개 문서 차단
- `test_owner_can_see_own_private_document`: 본인 비공개 문서 접근
- `test_no_accessible_documents_returns_empty`: 권한 없는 사용자

#### TestSearchACLGroupPermissions (3개 테스트)
- `test_group_member_can_access_group_documents`: 그룹 문서 접근
- `test_non_member_cannot_access_group_documents`: 비그룹원 차단
- `test_multiple_group_membership`: 다중 그룹 멤버십

#### TestSearchACLPublicDocuments (2개 테스트)
- `test_anyone_can_see_public_documents`: 공개 문서 접근
- `test_public_docs_appear_for_all_users`: 모든 사용자 공개 문서

#### TestSearchACLCrossChecks (3개 테스트)
- `test_acl_applied_to_all_search_types`: 모든 검색 타입 ACL
- `test_acl_respects_document_not_chunk_level`: 문서 레벨 ACL
- `test_same_query_different_users_different_results`: 사용자별 다른 결과

### 4. Pytest Configuration
**파일**: `pyproject.toml`

```toml
[tool.pytest.ini_options]
markers = [
    "integration: marks tests as integration tests (may require external services)",
    "slow: marks tests as slow running",
]
```

## 기술적 특징

### 1. Mock 기반 통합 테스트
```python
def use_real_infrastructure() -> bool:
    """Check if real infrastructure should be used."""
    return os.environ.get("INTEGRATION_TEST_REAL", "0") == "1"
```
- 기본: Mock 서비스 사용
- `INTEGRATION_TEST_REAL=1`: 실제 인프라 사용

### 2. 동적 테스트 데이터
```python
def get_test_documents() -> list[dict[str, Any]]:
    """Get test documents with unique UUIDs for each test run."""
    docs = copy.deepcopy(TEST_DOCUMENTS)
    for doc in docs:
        doc["doc_uuid"] = str(uuid4())
        for chunk in doc["chunks"]:
            chunk["chunk_uuid"] = str(uuid4())
    return docs
```

### 3. ACL 시뮬레이션
```python
async def get_accessible_documents(
    user_id: str,
    user_groups: list[str] | None = None,
) -> list[str]:
    groups = user_groups or []
    accessible = []

    for doc in test_docs:
        # Owner has access
        if doc["owner_id"] == user_id:
            accessible.append(doc["doc_uuid"])
            continue

        # Check group access
        allowed_groups = doc.get("allowed_groups", [])
        if "*" in allowed_groups:
            accessible.append(doc["doc_uuid"])
            continue

        if any(g in allowed_groups for g in groups):
            accessible.append(doc["doc_uuid"])

    return accessible
```

## 테스트 결과

```
============================== test session starts ==============================
33 passed in 0.33s

테스트 분류:
- TestSearchACLUserPermissions: 4개
- TestSearchACLGroupPermissions: 3개
- TestSearchACLPublicDocuments: 2개
- TestSearchACLCrossChecks: 3개
- TestDenseSearchIntegration: 5개
- TestSparseSearchIntegration: 4개
- TestGraphSearchIntegration: 3개
- TestHybridSearchIntegration: 6개
- TestSearchPerformance: 3개

총 33개 테스트 PASSED
```

## 테스트 시나리오

### ACL 권한 매트릭스
| 문서 | 소유자 | 그룹 | user1 | user2 | new_user (engineering) | random_user |
|------|--------|------|-------|-------|----------------------|-------------|
| doc-001 | user1 | engineering | ✅ | ❌ | ✅ | ❌ |
| doc-002 | user1 | engineering, ml-team | ✅ | ❌ | ✅ | ❌ |
| doc-003 | user2 | - (private) | ❌ | ✅ | ❌ | ❌ |
| doc-004 | admin | * (public) | ✅ | ✅ | ✅ | ✅ |

### 검색 플로우 테스트
```
1. Dense Search
   - 쿼리 → 임베딩 → ACL 필터 → Milvus 검색 → 결과

2. Sparse Search
   - 쿼리 → 토큰화 → ACL 필터 → Milvus 검색 → 결과

3. Graph Search
   - 쿼리 → 키워드 추출 → ACL 필터 → Neo4j 검색 → 결과

4. Hybrid Search
   - 쿼리 → 병렬 검색 (Dense + Sparse + Graph)
   → ACL 필터 → RRF 융합 → 중복 제거 → 결과
```

## 실행 방법

```bash
# Mock 기반 통합 테스트 (기본)
pytest tests/integration -v

# 특정 테스트 클래스만
pytest tests/integration/test_search_acl.py -v

# 실제 인프라 테스트 (Docker 필요)
INTEGRATION_TEST_REAL=1 pytest tests/integration -v

# 마커로 필터링
pytest -m integration -v
```

## 다음 단계
- Task 3.3: Search 성능 최적화
- Task 3.4: E2E 테스트 추가
