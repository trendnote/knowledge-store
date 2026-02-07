"""Tests for API dependencies."""

from unittest.mock import MagicMock

import pytest

from src.api.dependencies import (
    get_search_service,
    reset_dependencies,
    set_search_service,
)


class TestSearchServiceDependency:
    """Tests for search service dependency."""

    def setup_method(self) -> None:
        """Reset dependencies before each test."""
        reset_dependencies()

    def teardown_method(self) -> None:
        """Reset dependencies after each test."""
        reset_dependencies()

    @pytest.mark.asyncio
    async def test_get_search_service_not_initialized(self) -> None:
        """Test getting service when not initialized raises error."""
        with pytest.raises(RuntimeError, match="Search service not initialized"):
            await get_search_service()

    @pytest.mark.asyncio
    async def test_set_and_get_search_service(self) -> None:
        """Test setting and getting search service."""
        mock_service = MagicMock()
        set_search_service(mock_service)

        service = await get_search_service()
        assert service is mock_service

    @pytest.mark.asyncio
    async def test_reset_dependencies(self) -> None:
        """Test resetting dependencies."""
        mock_service = MagicMock()
        set_search_service(mock_service)

        # Should work before reset
        service = await get_search_service()
        assert service is mock_service

        # Reset
        reset_dependencies()

        # Should fail after reset
        with pytest.raises(RuntimeError):
            await get_search_service()

    @pytest.mark.asyncio
    async def test_set_search_service_replaces_existing(self) -> None:
        """Test setting service replaces existing one."""
        service1 = MagicMock()
        service2 = MagicMock()

        set_search_service(service1)
        assert await get_search_service() is service1

        set_search_service(service2)
        assert await get_search_service() is service2
