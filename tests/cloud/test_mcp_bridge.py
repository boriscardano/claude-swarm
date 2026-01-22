"""
Tests for MCPBridge class and MCP integration.

These tests use mocking to avoid requiring real Docker containers
and MCP servers during CI/CD.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.types import (
    MCPConfig,
    MCPError,
    MCPResponse,
    MCPStatus,
    MCPType,
)


@pytest.fixture
def sandbox_id() -> str:
    """Fixture providing a test sandbox ID."""
    return "e2b-test-sandbox-123"


@pytest.fixture
def mcp_bridge(sandbox_id: str) -> MCPBridge:
    """Fixture providing an MCPBridge instance."""
    return MCPBridge(sandbox_id=sandbox_id)


@pytest.fixture
def github_config() -> MCPConfig:
    """Fixture providing GitHub MCP configuration."""
    return MCPConfig(
        mcp_type=MCPType.GITHUB,
        container_image="mcp/github:latest",
        environment={"GITHUB_TOKEN": "test_token_123"},
        port=3000,
        max_retries=3,
        rate_limit=30,
    )


class TestMCPBridgeInitialization:
    """Tests for MCPBridge initialization."""

    def test_init(self, sandbox_id: str) -> None:
        """Test MCPBridge initialization."""
        bridge = MCPBridge(sandbox_id=sandbox_id)

        assert bridge.sandbox_id == sandbox_id
        assert bridge.mcp_containers == {}
        assert bridge.mcp_configs == {}
        assert bridge._http_client is None

    @pytest.mark.asyncio
    async def test_context_manager(self, mcp_bridge: MCPBridge) -> None:
        """Test MCPBridge async context manager."""
        async with mcp_bridge as bridge:
            assert bridge._http_client is not None

        # After exit, HTTP client should be closed
        assert bridge._http_client is None or bridge._http_client.is_closed


class TestAttachMCP:
    """Tests for attaching MCP servers."""

    @pytest.mark.asyncio
    async def test_attach_mcp_success(
        self, mcp_bridge: MCPBridge, github_config: MCPConfig
    ) -> None:
        """Test successful MCP attachment."""
        # For now, test with placeholder logic
        # TODO: Update when real Docker integration is implemented

        container_info = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)

        assert container_info.mcp_type == MCPType.GITHUB
        assert container_info.endpoint_url is not None
        assert "github" in mcp_bridge.mcp_containers
        assert mcp_bridge.mcp_configs["github"] == github_config

    @pytest.mark.asyncio
    async def test_attach_mcp_already_attached(
        self, mcp_bridge: MCPBridge, github_config: MCPConfig
    ) -> None:
        """Test attaching an already-attached MCP returns existing instance."""
        # Attach first time
        container_info1 = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)

        # Mark as healthy
        container_info1.status = MCPStatus.CONNECTED

        # Attach second time
        container_info2 = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)

        # Should return same instance
        assert container_info1 == container_info2


class TestCallMCP:
    """Tests for calling MCP methods."""

    @pytest.mark.asyncio
    async def test_call_mcp_not_attached(self, mcp_bridge: MCPBridge) -> None:
        """Test calling MCP that is not attached raises error."""
        with pytest.raises(MCPError) as exc_info:
            await mcp_bridge.call_mcp(mcp_name="github", method="create_repo", params={})

        assert "not attached" in str(exc_info.value)
        assert exc_info.value.mcp_name == "github"
        assert exc_info.value.method == "create_repo"

    @pytest.mark.asyncio
    async def test_call_mcp_unhealthy(
        self, mcp_bridge: MCPBridge, github_config: MCPConfig
    ) -> None:
        """Test calling unhealthy MCP raises error."""
        # Attach MCP but leave it in INITIALIZING state
        container_info = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)
        container_info.status = MCPStatus.INITIALIZING

        with pytest.raises(MCPError) as exc_info:
            await mcp_bridge.call_mcp(mcp_name="github", method="create_repo", params={})

        assert "not healthy" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_mcp_success(self, mcp_bridge: MCPBridge, github_config: MCPConfig) -> None:
        """Test successful MCP call."""
        # Attach and mark as healthy
        container_info = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)
        container_info.status = MCPStatus.CONNECTED

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.json.return_value = {"repo_id": 123, "name": "test-repo"}

        with patch.object(mcp_bridge, "_http_client", AsyncMock()) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            response = await mcp_bridge.call_mcp(
                mcp_name="github",
                method="create_repo",
                params={"name": "test-repo"},
            )

        assert response.success is True
        assert response.data == {"repo_id": 123, "name": "test-repo"}
        assert response.mcp_name == "github"
        assert response.method == "create_repo"
        assert response.duration_ms > 0

    @pytest.mark.asyncio
    async def test_call_mcp_with_retry(
        self, mcp_bridge: MCPBridge, github_config: MCPConfig
    ) -> None:
        """Test MCP call retries on failure."""
        # Attach and mark as healthy
        container_info = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)
        container_info.status = MCPStatus.CONNECTED

        # Mock HTTP client to fail twice, then succeed
        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")

            mock_response = MagicMock()
            mock_response.json.return_value = {"success": True}
            return mock_response

        with patch.object(mcp_bridge, "_http_client", AsyncMock()) as mock_client:
            mock_client.post = mock_post

            response = await mcp_bridge.call_mcp(mcp_name="github", method="test", params={})

        assert call_count == 3  # Failed twice, succeeded on third try
        assert response.success is True


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(
        self, mcp_bridge: MCPBridge, github_config: MCPConfig
    ) -> None:
        """Test that rate limits are enforced."""
        # Set very low rate limit for testing
        github_config.rate_limit = 2

        # Attach and mark as healthy
        container_info = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)
        container_info.status = MCPStatus.CONNECTED

        # Mock HTTP client
        mock_response = MagicMock()
        mock_response.json.return_value = {"success": True}

        with patch.object(mcp_bridge, "_http_client", AsyncMock()) as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            # First two calls should succeed
            await mcp_bridge.call_mcp(mcp_name="github", method="test", params={})
            await mcp_bridge.call_mcp(mcp_name="github", method="test", params={})

            # Third call should hit rate limit
            with pytest.raises(MCPError) as exc_info:
                await mcp_bridge.call_mcp(mcp_name="github", method="test", params={})

            assert "Rate limit exceeded" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rate_limit_window_reset(
        self, mcp_bridge: MCPBridge, github_config: MCPConfig
    ) -> None:
        """Test that rate limit window resets after time."""
        github_config.rate_limit = 1

        container_info = await mcp_bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=github_config)
        container_info.status = MCPStatus.CONNECTED

        # Make first call
        mcp_bridge._rate_limiters["github"] = [0.0]  # Old timestamp

        # Check rate limit should pass because old timestamp is outside window
        await mcp_bridge._check_rate_limit("github", github_config)

        # Should have cleared old timestamp and added new one
        assert len(mcp_bridge._rate_limiters["github"]) == 1


class TestMCPStatus:
    """Tests for MCP status tracking."""

    def test_get_mcp_status(self, mcp_bridge: MCPBridge, github_config: MCPConfig) -> None:
        """Test getting MCP status."""
        # Before attachment
        status = mcp_bridge.get_mcp_status("github")
        assert status is None

        # TODO: Add test with attached MCP when Docker integration is complete

    def test_list_mcps(self, mcp_bridge: MCPBridge) -> None:
        """Test listing attached MCPs."""
        mcps = mcp_bridge.list_mcps()
        assert mcps == []

        # TODO: Add test with attached MCPs when Docker integration is complete


class TestCleanup:
    """Tests for cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup(self, mcp_bridge: MCPBridge) -> None:
        """Test cleanup closes HTTP client and clears state."""
        # Initialize HTTP client
        async with mcp_bridge:
            pass

        # Add some fake state
        mcp_bridge.mcp_containers["test"] = MagicMock()
        mcp_bridge.mcp_configs["test"] = MagicMock()

        await mcp_bridge.cleanup()

        # Should clear all state
        assert len(mcp_bridge.mcp_containers) == 0
        assert len(mcp_bridge.mcp_configs) == 0


class TestMCPResponse:
    """Tests for MCPResponse data class."""

    def test_mcp_response_success(self) -> None:
        """Test creating successful MCPResponse."""
        response = MCPResponse(
            success=True,
            data={"key": "value"},
            mcp_name="github",
            method="test",
            duration_ms=100.0,
        )

        assert response.success is True
        assert response.data == {"key": "value"}
        assert response.error is None

    def test_mcp_response_failure(self) -> None:
        """Test creating failed MCPResponse."""
        response = MCPResponse(
            success=False,
            error="Something went wrong",
            mcp_name="github",
            method="test",
            duration_ms=50.0,
        )

        assert response.success is False
        assert response.error == "Something went wrong"
        assert response.data is None

    def test_mcp_response_validation(self) -> None:
        """Test MCPResponse validates failed responses have error message."""
        with pytest.raises(ValueError):
            MCPResponse(
                success=False,
                mcp_name="github",
                method="test",
                # Missing error message - should raise
            )


class TestMCPError:
    """Tests for MCPError exception class."""

    def test_mcp_error_str(self) -> None:
        """Test MCPError string representation."""
        error = MCPError(
            message="Test error",
            mcp_name="github",
            method="create_repo",
            retry_count=2,
        )

        error_str = str(error)
        assert "Test error" in error_str
        assert "github" in error_str
        assert "create_repo" in error_str
        assert "Retries: 2" in error_str

    def test_mcp_error_with_original_exception(self) -> None:
        """Test MCPError with original exception."""
        original = ValueError("Original error")
        error = MCPError(
            message="Wrapped error",
            mcp_name="github",
            method="test",
            original_error=original,
        )

        error_str = str(error)
        assert "Wrapped error" in error_str
        assert "Original error" in error_str


# Integration-style test (will be skipped in CI without real credentials)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_mcp_workflow() -> None:
    """
    Integration test for full MCP workflow.

    This test requires real MCP Docker containers and credentials.
    It should only be run manually during development/testing.
    """
    # Skip if no credentials available
    import os

    if not os.getenv("GITHUB_TOKEN"):
        pytest.skip("GITHUB_TOKEN not set - skipping integration test")

    bridge = MCPBridge(sandbox_id="integration-test")

    try:
        # This would use real Docker and MCP servers
        # TODO: Implement when MCP images are available
        pass
    finally:
        await bridge.cleanup()
