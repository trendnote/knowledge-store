"""Base repository interfaces and abstract classes."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Abstract base class for all repositories."""

    @abstractmethod
    async def get(self, id: str) -> T | None:
        """Get an entity by its ID."""
        ...

    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity."""
        ...

    @abstractmethod
    async def update(self, id: str, entity: T) -> T:
        """Update an existing entity."""
        ...

    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete an entity by its ID."""
        ...
