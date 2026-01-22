"""
Tests for E2B Sandbox Launcher

Tests the CloudSandbox class for creating and managing E2B sandboxes
with multi-agent coordination capabilities.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claudeswarm.cloud.e2b_launcher import CloudSandbox


class TestCloudSandbox:
    """Test suite for CloudSandbox class."""

    def test_init(self) -> None:
        """Test CloudSandbox initialization."""
        sandbox = CloudSandbox(num_agents=4)
        assert sandbox.num_agents == 4
        assert sandbox.sandbox is None
        assert sandbox.sandbox_id is None

    def test_init_custom_agents(self) -> None:
        """Test CloudSandbox with custom number of agents."""
        sandbox = CloudSandbox(num_agents=8)
        assert sandbox.num_agents == 8

    @pytest.mark.asyncio
    async def test_create_without_e2b_package(self) -> None:
        """Test create() fails gracefully when E2B package not installed."""
        with patch("claudeswarm.cloud.e2b_launcher.E2BSandbox", None):
            sandbox = CloudSandbox(num_agents=4)
            with pytest.raises(RuntimeError, match="e2b-code-interpreter package not installed"):
                await sandbox.create()

    @pytest.mark.asyncio
    async def test_create_without_api_key(self) -> None:
        """Test create() fails when E2B_API_KEY is not set."""
        # Mock the E2B Sandbox class
        mock_sandbox_class = MagicMock()

        with (
            patch("claudeswarm.cloud.e2b_launcher.E2BSandbox", mock_sandbox_class),
            patch.dict(os.environ, {}, clear=True),
        ):
            sandbox = CloudSandbox(num_agents=4)
            with pytest.raises(RuntimeError, match="E2B_API_KEY environment variable not set"):
                await sandbox.create()

    @pytest.mark.asyncio
    async def test_create_with_api_key(self) -> None:
        """Test create() with valid API key."""
        # Mock E2B Sandbox
        mock_sandbox_instance = MagicMock()
        mock_sandbox_instance.id = "test-sandbox-123"
        mock_sandbox_instance.run_code = MagicMock()

        # Mock successful command execution
        mock_result = MagicMock()
        mock_result.error = None
        mock_sandbox_instance.run_code.return_value = mock_result

        mock_sandbox_class = MagicMock(return_value=mock_sandbox_instance)

        with (
            patch("claudeswarm.cloud.e2b_launcher.E2BSandbox", mock_sandbox_class),
            patch.dict(os.environ, {"E2B_API_KEY": "test-key"}),
        ):
            sandbox = CloudSandbox(num_agents=4)
            sandbox_id = await sandbox.create()

            assert sandbox_id == "test-sandbox-123"
            assert sandbox.sandbox_id == "test-sandbox-123"
            assert sandbox.sandbox == mock_sandbox_instance

    @pytest.mark.asyncio
    async def test_install_dependencies_failure(self) -> None:
        """Test _install_dependencies handles errors."""
        mock_sandbox_instance = MagicMock()
        mock_sandbox_instance.id = "test-sandbox-123"

        # Mock failed command execution
        mock_result = MagicMock()
        mock_result.error = "Installation failed"
        mock_sandbox_instance.run_code = MagicMock(return_value=mock_result)

        mock_sandbox_class = MagicMock(return_value=mock_sandbox_instance)

        with (
            patch("claudeswarm.cloud.e2b_launcher.E2BSandbox", mock_sandbox_class),
            patch.dict(os.environ, {"E2B_API_KEY": "test-key"}),
        ):
            sandbox = CloudSandbox(num_agents=4)
            sandbox.sandbox = mock_sandbox_instance

            with pytest.raises(RuntimeError, match="Failed to install dependencies"):
                await sandbox._install_dependencies()

    @pytest.mark.asyncio
    async def test_setup_tmux_creates_session(self) -> None:
        """Test _setup_tmux creates tmux session with correct number of panes."""
        mock_sandbox_instance = MagicMock()
        mock_sandbox_instance.id = "test-sandbox-123"

        # Mock successful command execution
        mock_result = MagicMock()
        mock_result.error = None
        mock_sandbox_instance.run_code = MagicMock(return_value=mock_result)

        sandbox = CloudSandbox(num_agents=4)
        sandbox.sandbox = mock_sandbox_instance

        await sandbox._setup_tmux()

        # Verify tmux session creation was called
        calls = mock_sandbox_instance.run_code.call_args_list
        assert any("tmux new-session" in str(call) for call in calls)

        # Verify correct number of splits (num_agents - 1)
        split_calls = [call for call in calls if "split-window" in str(call)]
        assert len(split_calls) >= 3  # 4 agents = 3 splits

    @pytest.mark.asyncio
    async def test_setup_tmux_failure(self) -> None:
        """Test _setup_tmux handles errors."""
        mock_sandbox_instance = MagicMock()
        mock_sandbox_instance.id = "test-sandbox-123"

        # Mock failed command execution
        mock_result = MagicMock()
        mock_result.error = "Tmux creation failed"
        mock_sandbox_instance.run_code = MagicMock(return_value=mock_result)

        sandbox = CloudSandbox(num_agents=4)
        sandbox.sandbox = mock_sandbox_instance

        with pytest.raises(RuntimeError, match="Failed to create tmux session"):
            await sandbox._setup_tmux()

    @pytest.mark.asyncio
    async def test_initialize_swarm(self) -> None:
        """Test _initialize_swarm runs discovery in each pane."""
        mock_sandbox_instance = MagicMock()
        mock_sandbox_instance.id = "test-sandbox-123"

        # Mock successful command execution
        mock_result = MagicMock()
        mock_result.error = None
        mock_sandbox_instance.run_code = MagicMock(return_value=mock_result)

        sandbox = CloudSandbox(num_agents=4)
        sandbox.sandbox = mock_sandbox_instance

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await sandbox._initialize_swarm()

        # Verify discovery command was sent to each pane
        calls = mock_sandbox_instance.run_code.call_args_list
        assert len(calls) == 4  # One per agent

        # Verify commands contain claudeswarm discover-agents
        for call in calls:
            assert "discover-agents" in str(call)

    @pytest.mark.asyncio
    async def test_attach_mcp_not_implemented(self) -> None:
        """Test attach_mcp raises NotImplementedError."""
        sandbox = CloudSandbox(num_agents=4)

        with pytest.raises(NotImplementedError, match="MCP attachment"):
            await sandbox.attach_mcp("github", {})

    @pytest.mark.asyncio
    async def test_execute_autonomous_dev_not_implemented(self) -> None:
        """Test execute_autonomous_dev raises NotImplementedError."""
        sandbox = CloudSandbox(num_agents=4)

        with pytest.raises(NotImplementedError, match="Autonomous development"):
            await sandbox.execute_autonomous_dev("Add JWT auth")

    @pytest.mark.asyncio
    async def test_cleanup(self) -> None:
        """Test cleanup() closes sandbox."""
        mock_sandbox_instance = MagicMock()
        mock_sandbox_instance.close = MagicMock()
        mock_sandbox_instance.id = "test-sandbox-123"

        sandbox = CloudSandbox(num_agents=4)
        sandbox.sandbox = mock_sandbox_instance
        sandbox.sandbox_id = "test-sandbox-123"

        await sandbox.cleanup()

        mock_sandbox_instance.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_sandbox(self) -> None:
        """Test cleanup() handles case when sandbox is None."""
        sandbox = CloudSandbox(num_agents=4)
        # Should not raise any errors
        await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test CloudSandbox works as async context manager."""
        mock_sandbox_instance = MagicMock()
        mock_sandbox_instance.id = "test-sandbox-123"
        mock_sandbox_instance.close = MagicMock()

        # Mock successful command execution
        mock_result = MagicMock()
        mock_result.error = None
        mock_sandbox_instance.run_code = MagicMock(return_value=mock_result)

        mock_sandbox_class = MagicMock(return_value=mock_sandbox_instance)

        with (
            patch("claudeswarm.cloud.e2b_launcher.E2BSandbox", mock_sandbox_class),
            patch.dict(os.environ, {"E2B_API_KEY": "test-key"}),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            async with CloudSandbox(num_agents=4) as sandbox:
                assert sandbox.sandbox_id == "test-sandbox-123"

            # Verify cleanup was called
            mock_sandbox_instance.close.assert_called_once()


class TestCloudSandboxIntegration:
    """Integration tests requiring E2B API key (marked as integration)."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_create_real_sandbox(self) -> None:
        """
        Test creating a real E2B sandbox.

        This test requires:
        - e2b-code-interpreter package installed
        - E2B_API_KEY environment variable set

        Run with: pytest -m integration
        """
        api_key = os.getenv("E2B_API_KEY")
        if not api_key:
            pytest.skip("E2B_API_KEY not set - skipping real sandbox test")

        try:
            from e2b_code_interpreter import Sandbox as E2BSandbox

            # Create a minimal sandbox (don't install all deps to save time)
            sandbox = CloudSandbox(num_agents=2)
            sandbox_id = await sandbox.create()

            # Verify sandbox was created
            assert sandbox_id is not None
            assert len(sandbox_id) > 0
            assert sandbox.sandbox is not None

            # Cleanup
            await sandbox.cleanup()

        except ImportError:
            pytest.skip("e2b-code-interpreter not installed")
