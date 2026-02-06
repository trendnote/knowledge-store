"""Graph-related domain models.

This module provides domain models for Neo4j graph operations:
- DocumentNode: Document node representation
- ChunkNode: Chunk node representation
- Entity: Entity mentioned in chunks
- GraphSearchResult: Graph search result
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DocumentNode:
    """Document node for Neo4j.

    Attributes:
        doc_uuid: Document unique identifier
        title: Document title
        source: Document source (wiki, agit, etc.)
        security_level: Security classification
        created_at: Creation timestamp
        properties: Additional properties
    """

    doc_uuid: str
    title: str
    source: str
    security_level: str = "internal"
    created_at: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkNode:
    """Chunk node for Neo4j.

    Attributes:
        chunk_uuid: Chunk unique identifier
        doc_uuid: Parent document UUID
        sequence: Chunk sequence number in document
        text_preview: First 500 chars for search
        section_path: Section path in document
        properties: Additional properties
    """

    chunk_uuid: str
    doc_uuid: str
    sequence: int
    text_preview: str
    section_path: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Entity:
    """Entity mentioned in chunk.

    Attributes:
        entity_type: Type of entity (Person, Organization, Project, Policy)
        entity_id: Entity identifier
        name: Entity display name
        confidence: Mention confidence score
    """

    entity_type: str  # Person, Organization, Project, Policy
    entity_id: str
    name: str
    confidence: float = 1.0


@dataclass
class GraphSearchResult:
    """Graph search result.

    Attributes:
        chunk_uuid: Chunk identifier
        doc_uuid: Document identifier
        title: Document title
        text_preview: Chunk text preview
        section_path: Section path
        score: Relevance score
        path_length: Graph path length
        related_entities: List of related entity names
    """

    chunk_uuid: str
    doc_uuid: str
    title: str
    text_preview: str
    section_path: str | None
    score: float
    path_length: int = 0
    related_entities: list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> GraphSearchResult:
        """Create from Neo4j record.

        Args:
            record: Dictionary from Neo4j query result

        Returns:
            GraphSearchResult instance
        """
        return cls(
            chunk_uuid=record.get("chunk_uuid", ""),
            doc_uuid=record.get("doc_uuid", ""),
            title=record.get("title", ""),
            text_preview=record.get("text_preview", ""),
            section_path=record.get("section_path"),
            score=record.get("score", 0.0),
            path_length=record.get("path_length", 0),
            related_entities=record.get("related_entities", []),
        )
