"""API schemas package.

This package provides Pydantic schemas for API validation and documentation.
"""

from src.api.schemas.search import (
    SearchErrorSchema,
    SearchRequestSchema,
    SearchResponseSchema,
    SearchResultSchema,
    SearchTypeEnum,
)

__all__ = [
    "SearchTypeEnum",
    "SearchRequestSchema",
    "SearchResultSchema",
    "SearchResponseSchema",
    "SearchErrorSchema",
]
