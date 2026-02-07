"""API schemas package.

This package provides Pydantic schemas for API validation and documentation:
- Search schemas: For hybrid search operations
- Document schemas: For document CRUD operations
"""

from src.api.schemas.documents import (
    DocumentCreateSchema,
    DocumentErrorSchema,
    DocumentListResponseSchema,
    DocumentResponseSchema,
    DocumentSourceEnum,
    DocumentStatusEnum,
    DocumentUpdateSchema,
    SecurityLevelEnum,
)
from src.api.schemas.search import (
    SearchErrorSchema,
    SearchRequestSchema,
    SearchResponseSchema,
    SearchResultSchema,
    SearchTypeEnum,
)

__all__ = [
    # Document schemas
    "DocumentCreateSchema",
    "DocumentErrorSchema",
    "DocumentListResponseSchema",
    "DocumentResponseSchema",
    "DocumentSourceEnum",
    "DocumentStatusEnum",
    "DocumentUpdateSchema",
    "SecurityLevelEnum",
    # Search schemas
    "SearchTypeEnum",
    "SearchRequestSchema",
    "SearchResultSchema",
    "SearchResponseSchema",
    "SearchErrorSchema",
]
