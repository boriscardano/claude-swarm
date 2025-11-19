"""
E2B Sandbox Launcher

Manages E2B sandbox creation, configuration, and initialization for multi-agent
coordination. Handles tmux session setup and claudeswarm installation within sandboxes.
"""

import asyncio
import os
from typing import Optional

try:
    from e2b_code_interpreter import Sandbox as E2BSandbox
except ImportError:
    E2BSandbox = None  # type: ignore[assignment, misc]

from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.types import MCPConfig, MCPContainerInfo


class CloudSandbox:
    """
    Manages a single E2B sandbox with multiple agents.

    This class handles:
    - Creating and destroying E2B sandboxes
    - Installing dependencies (claudeswarm, tmux, etc.)
    - Setting up tmux sessions with multiple panes
    - Initializing the claudeswarm coordination system
    - Managing sandbox lifecycle

    Attributes:
        num_agents: Number of agent panes to create in tmux
        sandbox: The E2B sandbox instance
        sandbox_id: Unique identifier for the sandbox
    """

    def __init__(self, num_agents: int = 4) -> None:
        """
        Initialize a CloudSandbox.

        Args:
            num_agents: Number of agent panes to create (default: 4)
        """
        self.num_agents = num_agents
        self.sandbox: Optional[E2BSandbox] = None
        self.sandbox_id: Optional[str] = None
        self.mcp_bridge: Optional[MCPBridge] = None

    async def create(self) -> str:
        """
        Create E2B sandbox and initialize environment.

        This method:
        1. Creates a new E2B sandbox instance
        2. Installs required dependencies
        3. Sets up tmux session with multiple panes
        4. Initializes the claudeswarm coordination system

        Returns:
            str: The sandbox ID

        Raises:
            RuntimeError: If E2B SDK is not installed
            RuntimeError: If sandbox creation or initialization fails
        """
        if E2BSandbox is None:
            raise RuntimeError(
                "e2b-code-interpreter package not installed. "
                "Install with: pip install e2b-code-interpreter"
            )

        # Verify API key is set
        api_key = os.getenv("E2B_API_KEY")
        if not api_key:
            raise RuntimeError(
                "E2B_API_KEY environment variable not set. "
                "Get your API key from https://e2b.dev/docs"
            )

        # Create sandbox
        print("🚀 Creating E2B sandbox...")
        self.sandbox = E2BSandbox()
        self.sandbox_id = self.sandbox.id
        print(f"✓ Sandbox created: {self.sandbox_id}")

        # Install dependencies
        await self._install_dependencies()

        # Setup tmux
        await self._setup_tmux()

        # Initialize claudeswarm
        await self._initialize_swarm()

        print(f"✓ Sandbox {self.sandbox_id} ready with {self.num_agents} agents")
        return self.sandbox_id

    async def _install_dependencies(self) -> None:
        """
        Install required packages in sandbox.

        Installs:
        - claudeswarm package (from git repo)
        - fastapi and uvicorn (for web dashboard)
        - pytest (for testing)
        - tmux (for multi-pane coordination)

        Raises:
            RuntimeError: If any installation fails
        """
        print("📦 Installing dependencies...")

        commands = [
            # System packages
            "apt-get update && apt-get install -y tmux git",
            # Python packages
            "pip install --upgrade pip",
            "pip install git+https://github.com/borisbanach/claude-swarm.git",
            "pip install fastapi uvicorn pytest",
        ]

        for i, cmd in enumerate(commands, 1):
            print(f"  [{i}/{len(commands)}] {cmd.split()[0]}...")
            try:
                result = await asyncio.to_thread(
                    self.sandbox.run_code,  # type: ignore[union-attr]
                    f"!{cmd}",
                )
                if result.error:
                    raise RuntimeError(
                        f"Failed to install dependencies: {result.error}"
                    )
            except Exception as e:
                raise RuntimeError(f"Installation failed: {str(e)}") from e

        print("✓ Dependencies installed")

    async def _setup_tmux(self) -> None:
        """
        Create tmux session with multiple panes.

        Creates a tmux session named 'claude-swarm' and splits it into
        multiple panes (one per agent) using a tiled layout.

        Raises:
            RuntimeError: If tmux setup fails
        """
        print(f"🖥️  Setting up tmux with {self.num_agents} panes...")

        try:
            # Create initial session
            result = await asyncio.to_thread(
                self.sandbox.run_code,  # type: ignore[union-attr]
                '!tmux new-session -d -s claude-swarm -x 200 -y 50',
            )
            if result.error:
                raise RuntimeError(f"Failed to create tmux session: {result.error}")

            # Split into multiple panes
            for i in range(1, self.num_agents):
                # Split horizontally
                result = await asyncio.to_thread(
                    self.sandbox.run_code,  # type: ignore[union-attr]
                    f'!tmux split-window -h -t claude-swarm',
                )
                if result.error:
                    raise RuntimeError(f"Failed to split pane {i}: {result.error}")

                # Apply tiled layout after each split
                await asyncio.to_thread(
                    self.sandbox.run_code,  # type: ignore[union-attr]
                    f'!tmux select-layout -t claude-swarm tiled',
                )

            print("✓ Tmux session created")

        except Exception as e:
            raise RuntimeError(f"Tmux setup failed: {str(e)}") from e

    async def _initialize_swarm(self) -> None:
        """
        Initialize claudeswarm in each pane.

        Sends the agent discovery command to each tmux pane to initialize
        the coordination system. Waits for initialization to complete.

        Raises:
            RuntimeError: If initialization fails
        """
        print("🔗 Initializing claudeswarm agents...")

        try:
            # Set working directory and initialize in each pane
            for i in range(self.num_agents):
                # Send command to each pane
                cmd = (
                    f"!tmux send-keys -t claude-swarm:{i} "
                    f"'cd /workspace && claudeswarm discover-agents' Enter"
                )
                result = await asyncio.to_thread(
                    self.sandbox.run_code,  # type: ignore[union-attr]
                    cmd,
                )
                if result.error:
                    print(f"⚠️  Warning: Pane {i} initialization issue: {result.error}")

            # Wait for agents to initialize
            await asyncio.sleep(3)

            print("✓ Claudeswarm agents initialized")

        except Exception as e:
            raise RuntimeError(f"Swarm initialization failed: {str(e)}") from e

    async def attach_mcp(
        self, mcp_type: str, config: MCPConfig
    ) -> MCPContainerInfo:
        """
        Attach MCP server to sandbox.

        Creates an MCP bridge if not already created, then attaches the
        specified MCP server using the provided configuration.

        Args:
            mcp_type: Type of MCP server (e.g., "github", "exa", "filesystem")
            config: MCP configuration object with container settings

        Returns:
            MCPContainerInfo: Information about the running MCP container

        Raises:
            RuntimeError: If sandbox not created yet
            MCPError: If MCP attachment fails

        Example:
            ```python
            from claudeswarm.cloud.types import MCPConfig, MCPType
            from claudeswarm.cloud.mcp_config import GITHUB_MCP_CONFIG

            sandbox = CloudSandbox(num_agents=4)
            await sandbox.create()

            # Attach GitHub MCP
            github_info = await sandbox.attach_mcp(
                mcp_type=MCPType.GITHUB,
                config=GITHUB_MCP_CONFIG
            )
            ```
        """
        if not self.sandbox_id:
            raise RuntimeError("Sandbox must be created before attaching MCPs")

        # Create MCP bridge if not already created
        if self.mcp_bridge is None:
            self.mcp_bridge = MCPBridge(sandbox_id=self.sandbox_id)

        # Attach the MCP using the bridge
        container_info = await self.mcp_bridge.attach_mcp(
            mcp_type=mcp_type, config=config
        )

        print(f"✓ MCP {mcp_type} attached: {container_info.endpoint_url}")
        return container_info

    def get_mcp_bridge(self) -> Optional[MCPBridge]:
        """
        Get the MCP bridge instance for direct MCP calls.

        Returns:
            MCPBridge instance if MCPs have been attached, None otherwise

        Example:
            ```python
            bridge = sandbox.get_mcp_bridge()
            if bridge:
                response = await bridge.call_mcp(
                    mcp_name="github",
                    method="create_repo",
                    params={"name": "my-repo"}
                )
            ```
        """
        return self.mcp_bridge

    async def execute_autonomous_dev(self, feature: str) -> None:
        """
        Start autonomous development loop.

        Note: This is a placeholder for the autonomous workflow engine.
        Implementation will be completed by the Workflow team.

        Args:
            feature: Feature description to implement

        Raises:
            NotImplementedError: Implementation pending
        """
        # TODO: Implementation in workflows/autonomous_dev.py
        raise NotImplementedError(
            "Autonomous development will be implemented by Workflow team"
        )

    async def cleanup(self) -> None:
        """
        Shutdown sandbox and cleanup resources.

        Properly closes the E2B sandbox and all MCP containers
        to avoid resource leaks.
        """
        # Cleanup MCP containers first
        if self.mcp_bridge:
            print("🧹 Cleaning up MCP containers...")
            self.mcp_bridge.cleanup()

        # Then cleanup sandbox
        if self.sandbox:
            print(f"🧹 Cleaning up sandbox {self.sandbox_id}...")
            await asyncio.to_thread(self.sandbox.close)
            print("✓ Sandbox closed")

    async def __aenter__(self) -> "CloudSandbox":
        """Async context manager entry."""
        await self.create()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        """Async context manager exit."""
        await self.cleanup()


# Example usage (for testing/development)
async def main() -> None:
    """Example: Create a sandbox with 4 agents."""
    async with CloudSandbox(num_agents=4) as sandbox:
        print(f"Sandbox ID: {sandbox.sandbox_id}")
        print("Sandbox is ready for multi-agent coordination!")
        # Sandbox will be automatically cleaned up on exit


if __name__ == "__main__":
    asyncio.run(main())
