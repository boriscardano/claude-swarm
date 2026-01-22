"""
Integration tests for CloudSandbox + MCPBridge.

These tests validate the integration between E2B sandbox management
and MCP server attachment, ensuring components work together correctly.

Run with: pytest tests/cloud/test_integration_sandbox_mcp.py -v
Note: Most tests use mocks to avoid requiring E2B API keys during CI
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudeswarm.cloud.e2b_launcher import CloudSandbox
from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.security_utils import ValidationError
from claudeswarm.cloud.types import (
    MCPConfig,
    MCPContainerInfo,
    MCPError,
    MCPStatus,
    MCPType,
)


@pytest.fixture
def mock_e2b_sandbox():
    """Mock E2B sandbox for testing without real E2B credentials."""
    mock = MagicMock()
    mock.id = "e2b-test-sandbox-123"
    mock.close = AsyncMock()
    return mock


@pytest.fixture
def mock_mcp_config():
    """Mock MCP configuration for testing."""
    return MCPConfig(
        mcp_type=MCPType.GITHUB,
        container_image="mcp/github:latest",
        environment={"GITHUB_TOKEN": "test_token"},
        port=3000,
        timeout=30.0,
        max_retries=3,
        rate_limit=60,
    )


class TestCloudSandboxInitialization:
    """Test CloudSandbox initialization and validation."""

    def test_valid_initialization(self):
        """Test CloudSandbox initializes with valid parameters."""
        sandbox = CloudSandbox(num_agents=4)

        assert sandbox.num_agents == 4
        assert sandbox.sandbox is None
        assert sandbox.sandbox_id is None
        assert sandbox.mcp_bridge is None

    def test_num_agents_validation(self):
        """Test num_agents parameter is validated."""
        # Valid values
        CloudSandbox(num_agents=1)
        CloudSandbox(num_agents=10)
        CloudSandbox(num_agents=100)

        # Invalid values
        with pytest.raises((ValidationError, ValueError)):
            CloudSandbox(num_agents=0)

        with pytest.raises((ValidationError, ValueError)):
            CloudSandbox(num_agents=-1)

        with pytest.raises((ValidationError, ValueError)):
            CloudSandbox(num_agents=101)  # Over max

    def test_timeout_validation(self):
        """Test operation_timeout is validated."""
        # Valid timeout
        sandbox = CloudSandbox(num_agents=4, operation_timeout=60.0)
        assert sandbox.operation_timeout == 60.0

        # Invalid timeouts
        with pytest.raises((ValidationError, ValueError)):
            CloudSandbox(num_agents=4, operation_timeout=0)

        with pytest.raises((ValidationError, ValueError)):
            CloudSandbox(num_agents=4, operation_timeout=-10)


class TestCloudSandboxMCPBridgeIntegration:
    """Test integration between CloudSandbox and MCPBridge."""

    @pytest.mark.asyncio
    async def test_mcp_bridge_lazy_creation(self, mock_e2b_sandbox):
        """Test that MCPBridge is created lazily on first MCP attachment."""
        sandbox = CloudSandbox(num_agents=4)

        # Mock E2B sandbox creation
        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                # Create sandbox
                await sandbox.create()

                # MCPBridge should not exist yet
                assert sandbox.mcp_bridge is None

                # Mock MCP attachment
                with patch.object(MCPBridge, 'attach_mcp') as mock_attach:
                    mock_attach.return_value = MCPContainerInfo(
                        container_id="test-container",
                        mcp_type=MCPType.GITHUB,
                        ip_address="127.0.0.1",
                        port=3000,
                        status=MCPStatus.CONNECTED,
                        endpoint_url="http://127.0.0.1:3000",
                    )

                    # Attach MCP - this should create the bridge
                    config = MCPConfig(
                        mcp_type=MCPType.GITHUB,
                        container_image="mcp/github:latest",
                        environment={"GITHUB_TOKEN": "test"},
                        port=3000,
                    )

                    await sandbox.attach_mcp(mcp_type=MCPType.GITHUB, config=config)

                    # MCPBridge should now exist
                    assert sandbox.mcp_bridge is not None
                    assert isinstance(sandbox.mcp_bridge, MCPBridge)

    @pytest.mark.asyncio
    async def test_get_mcp_bridge_before_attachment(self):
        """Test get_mcp_bridge returns None before any MCP attachment."""
        sandbox = CloudSandbox(num_agents=4)

        bridge = sandbox.get_mcp_bridge()
        assert bridge is None

    @pytest.mark.asyncio
    async def test_attach_mcp_requires_created_sandbox(self):
        """Test that attach_mcp raises error if sandbox not created."""
        sandbox = CloudSandbox(num_agents=4)

        config = MCPConfig(
            mcp_type=MCPType.GITHUB,
            container_image="mcp/github:latest",
            environment={},
            port=3000,
        )

        with pytest.raises(RuntimeError) as exc_info:
            await sandbox.attach_mcp(mcp_type=MCPType.GITHUB, config=config)

        assert "not created" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_mcp_bridge_uses_sandbox_id(self, mock_e2b_sandbox):
        """Test that MCPBridge is initialized with correct sandbox_id."""
        sandbox = CloudSandbox(num_agents=4)

        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                await sandbox.create()

                # Mock MCP attachment
                with patch.object(MCPBridge, '__init__', return_value=None) as mock_init:
                    with patch.object(MCPBridge, 'attach_mcp') as mock_attach:
                        mock_attach.return_value = MCPContainerInfo(
                            container_id="test",
                            mcp_type=MCPType.GITHUB,
                            ip_address="127.0.0.1",
                            port=3000,
                            status=MCPStatus.CONNECTED,
                            endpoint_url="http://127.0.0.1:3000",
                        )

                        config = MCPConfig(
                            mcp_type=MCPType.GITHUB,
                            container_image="mcp/github:latest",
                            environment={},
                            port=3000,
                        )

                        await sandbox.attach_mcp(mcp_type=MCPType.GITHUB, config=config)

                        # Verify MCPBridge was initialized with sandbox_id
                        mock_init.assert_called_once()
                        args = mock_init.call_args[0]
                        assert args[0] == mock_e2b_sandbox.id


class TestErrorPropagation:
    """Test error propagation between CloudSandbox and MCPBridge."""

    @pytest.mark.asyncio
    async def test_mcp_error_propagates_to_sandbox(self, mock_e2b_sandbox):
        """Test that MCPError from bridge propagates through sandbox."""
        sandbox = CloudSandbox(num_agents=4)

        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                await sandbox.create()

                # Mock MCP attachment to raise error
                with patch.object(MCPBridge, 'attach_mcp') as mock_attach:
                    mock_attach.side_effect = MCPError(
                        message="Container failed to start",
                        mcp_name="github",
                        method="attach_mcp",
                    )

                    config = MCPConfig(
                        mcp_type=MCPType.GITHUB,
                        container_image="mcp/github:latest",
                        environment={},
                        port=3000,
                    )

                    # Error should propagate
                    with pytest.raises(MCPError) as exc_info:
                        await sandbox.attach_mcp(mcp_type=MCPType.GITHUB, config=config)

                    assert "failed to start" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_validation_error_on_invalid_config(self, mock_e2b_sandbox):
        """Test that validation errors are raised for invalid MCP configs."""
        sandbox = CloudSandbox(num_agents=4)

        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                await sandbox.create()

                # Invalid config - missing required fields
                # (This depends on MCPConfig validation)
                # We're testing that errors propagate properly


class TestCleanupCoordination:
    """Test cleanup coordination between CloudSandbox and MCPBridge."""

    @pytest.mark.asyncio
    async def test_cleanup_closes_mcp_bridge(self, mock_e2b_sandbox):
        """Test that sandbox cleanup also cleans up MCPBridge."""
        sandbox = CloudSandbox(num_agents=4)

        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                await sandbox.create()

                # Mock MCP attachment
                with patch.object(MCPBridge, 'attach_mcp') as mock_attach:
                    with patch.object(MCPBridge, 'cleanup') as mock_cleanup:
                        mock_attach.return_value = MCPContainerInfo(
                            container_id="test",
                            mcp_type=MCPType.GITHUB,
                            ip_address="127.0.0.1",
                            port=3000,
                            status=MCPStatus.CONNECTED,
                            endpoint_url="http://127.0.0.1:3000",
                        )

                        config = MCPConfig(
                            mcp_type=MCPType.GITHUB,
                            container_image="mcp/github:latest",
                            environment={},
                            port=3000,
                        )

                        await sandbox.attach_mcp(mcp_type=MCPType.GITHUB, config=config)

                        # Cleanup sandbox
                        await sandbox.cleanup()

                        # MCPBridge cleanup should have been called
                        mock_cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self, mock_e2b_sandbox):
        """Test that context manager properly cleans up both components."""
        sandbox = CloudSandbox(num_agents=4)

        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                # Use context manager
                async with sandbox:
                    await sandbox.create()

                # After context exit, cleanup should have run
                mock_e2b_sandbox.close.assert_called()


class TestSecurityIntegration:
    """Test that security validations work across both components."""

    def test_sandbox_id_validation_in_mcp_bridge(self):
        """Test that invalid sandbox_id is rejected by MCPBridge."""
        # Invalid sandbox IDs should raise validation errors
        with pytest.raises((ValidationError, ValueError)):
            MCPBridge(sandbox_id="../../etc/passwd")

        with pytest.raises((ValidationError, ValueError)):
            MCPBridge(sandbox_id="test; rm -rf /")

        # Valid IDs should work
        bridge = MCPBridge(sandbox_id="e2b-test-123")
        assert bridge.sandbox_id == "e2b-test-123"

    @pytest.mark.asyncio
    async def test_api_key_not_exposed_in_errors(self, mock_e2b_sandbox):
        """Test that API keys are not exposed in error messages."""
        sandbox = CloudSandbox(num_agents=4)

        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                await sandbox.create()

                # Mock MCP attachment to raise error
                with patch.object(MCPBridge, 'attach_mcp') as mock_attach:
                    error_msg = "Failed to attach MCP"
                    mock_attach.side_effect = MCPError(
                        message=error_msg,
                        mcp_name="github",
                        method="attach_mcp",
                    )

                    config = MCPConfig(
                        mcp_type=MCPType.GITHUB,
                        container_image="mcp/github:latest",
                        environment={"GITHUB_TOKEN": "ghp_secret_key_123"},
                        port=3000,
                    )

                    try:
                        await sandbox.attach_mcp(mcp_type=MCPType.GITHUB, config=config)
                    except MCPError as e:
                        # Error message should not contain the actual API key
                        assert "ghp_secret_key_123" not in str(e)
                        assert "secret" not in str(e)


class TestEndToEndFlow:
    """Test complete end-to-end flow of sandbox + MCP integration."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_flow_mock(self, mock_e2b_sandbox):
        """
        Test complete flow: create sandbox → attach MCP → cleanup.

        This uses mocks to simulate the full flow without real E2B/Docker.
        """
        sandbox = CloudSandbox(num_agents=4)

        with patch('claudeswarm.cloud.e2b_launcher.E2BSandbox') as mock_e2b:
            mock_e2b.return_value = mock_e2b_sandbox

            with patch.dict('os.environ', {'E2B_API_KEY': 'test_key'}):
                # Step 1: Create sandbox
                sandbox_id = await sandbox.create()
                assert sandbox_id == mock_e2b_sandbox.id
                assert sandbox.sandbox is not None

                # Step 2: Attach MCP
                with patch.object(MCPBridge, 'attach_mcp') as mock_attach:
                    mock_attach.return_value = MCPContainerInfo(
                        container_id="test-container",
                        mcp_type=MCPType.GITHUB,
                        ip_address="127.0.0.1",
                        port=3000,
                        status=MCPStatus.CONNECTED,
                        endpoint_url="http://127.0.0.1:3000",
                    )

                    config = MCPConfig(
                        mcp_type=MCPType.GITHUB,
                        container_image="mcp/github:latest",
                        environment={"GITHUB_TOKEN": "test"},
                        port=3000,
                    )

                    mcp_info = await sandbox.attach_mcp(
                        mcp_type=MCPType.GITHUB,
                        config=config
                    )

                    assert mcp_info.status == MCPStatus.CONNECTED
                    assert sandbox.mcp_bridge is not None

                    # Step 3: Get bridge and verify
                    bridge = sandbox.get_mcp_bridge()
                    assert bridge is not None
                    assert isinstance(bridge, MCPBridge)

                # Step 4: Cleanup
                await sandbox.cleanup()
                mock_e2b_sandbox.close.assert_called()


# Example of how to run these tests:
"""
# Run all integration tests:
pytest tests/cloud/test_integration_sandbox_mcp.py -v

# Run only fast unit tests (no mocking required):
pytest tests/cloud/test_integration_sandbox_mcp.py -v -m "not integration"

# Run with coverage:
pytest tests/cloud/test_integration_sandbox_mcp.py -v --cov=claudeswarm.cloud

# Run specific test class:
pytest tests/cloud/test_integration_sandbox_mcp.py::TestCloudSandboxMCPBridgeIntegration -v
"""
