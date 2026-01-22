"""
E2B Sandbox Launcher

Manages E2B sandbox creation, configuration, and initialization for multi-agent
coordination. Handles tmux session setup and claudeswarm installation within sandboxes.
"""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional

try:
    from e2b_code_interpreter import Sandbox as E2BSandbox
except ImportError:
    E2BSandbox = None  # type: ignore[assignment, misc]

from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.security_utils import (
    ValidationError,
    validate_num_agents,
    sanitize_for_shell,
    validate_timeout,
)
from claudeswarm.cloud.types import MCPConfig, MCPContainerInfo

# Security: Default timeout for async operations (in seconds)
DEFAULT_OPERATION_TIMEOUT = 600.0  # 10 minutes (increased for git clone operations)

# Security: Pin claudeswarm to specific commit for reproducibility
CLAUDESWARM_GIT_URL = "git+https://github.com/borisbanach/claude-swarm.git@d0e37ae"


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

    def __init__(self, num_agents: int = 4, operation_timeout: float = DEFAULT_OPERATION_TIMEOUT) -> None:
        """
        Initialize a CloudSandbox.

        Args:
            num_agents: Number of agent panes to create (default: 4)
            operation_timeout: Timeout for async operations in seconds (default: 300)

        Raises:
            ValidationError: If num_agents or operation_timeout is invalid
        """
        # Security: Use shared validation from security_utils
        self.num_agents = validate_num_agents(num_agents)
        self.operation_timeout = validate_timeout(operation_timeout)

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

        # Security: Verify API key is set (without storing it to prevent exposure)
        if not os.getenv("E2B_API_KEY"):
            raise RuntimeError(
                "E2B_API_KEY environment variable not set. "
                "Get your API key from https://e2b.dev/docs"
            )

        try:
            # Create sandbox (E2BSandbox retrieves API key internally)
            print("🚀 Creating E2B sandbox...")
            self.sandbox = await asyncio.wait_for(
                asyncio.to_thread(E2BSandbox.create),
                timeout=self.operation_timeout
            )
            self.sandbox_id = self.sandbox.sandbox_id
            print(f"✓ Sandbox created: {self.sandbox_id}")

            # Install dependencies with retry logic for E2B network stability
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                try:
                    print(f"📦 Installing dependencies (attempt {attempt}/{max_retries})...")
                    await self._install_dependencies()
                    break  # Success - exit retry loop
                except Exception as e:
                    if attempt == max_retries:
                        # Last attempt failed - propagate the error
                        raise
                    # Calculate exponential backoff: 2^attempt seconds (2s, 4s, 8s)
                    backoff = 2 ** attempt
                    print(f"⚠️  Installation failed (attempt {attempt}/{max_retries}): {str(e)}")
                    print(f"🔄 Retrying in {backoff} seconds...")
                    await asyncio.sleep(backoff)

            # Setup tmux
            await self._setup_tmux()

            # Initialize claudeswarm
            await self._initialize_swarm()

            print(f"✓ Sandbox {self.sandbox_id} ready with {self.num_agents} agents")
            return self.sandbox_id

        except Exception as e:
            # Security: Cleanup on partial initialization failure
            print(f"❌ Sandbox creation failed: {str(e)}")
            if self.sandbox:
                print("🧹 Cleaning up partial sandbox initialization...")
                try:
                    await asyncio.wait_for(
                        asyncio.to_thread(self.sandbox.kill),
                        timeout=30.0
                    )
                    print("✓ Cleanup complete")
                except Exception as cleanup_error:
                    print(f"⚠️  Cleanup error (non-fatal): {cleanup_error}")
            raise RuntimeError(f"Failed to create sandbox: {str(e)}") from e

    def _ensure_wheel_exists(self) -> Path:
        """
        Ensure the claudeswarm wheel is built and ready for upload.

        Automatically builds the wheel if it doesn't exist using python -m build.

        Returns:
            Path: Path to the wheel file

        Raises:
            RuntimeError: If wheel cannot be built
        """
        # Find project root (where pyproject.toml is located)
        project_root = Path(__file__).parent.parent.parent.parent
        wheel_path = project_root / "dist" / "claude_swarm-0.1.0-py3-none-any.whl"

        if wheel_path.exists():
            return wheel_path

        # Wheel doesn't exist - build it automatically
        print("📦 Wheel not found, building automatically...")
        pyproject_path = project_root / "pyproject.toml"

        if not pyproject_path.exists():
            raise RuntimeError(
                f"pyproject.toml not found at {pyproject_path}. "
                "Cannot build wheel automatically."
            )

        try:
            # Try to find python/python3 command
            python_cmd = None
            for cmd in ["python3", "python"]:
                try:
                    result = subprocess.run(
                        [cmd, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        python_cmd = cmd
                        break
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue

            if not python_cmd:
                raise RuntimeError("Python interpreter not found. Install Python 3.9+")

            # Build the wheel
            print(f"  Building with: {python_cmd} -m build")
            result = subprocess.run(
                [python_cmd, "-m", "build"],
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout for build
            )

            if result.returncode != 0:
                error_msg = f"Wheel build failed:\n{result.stderr}"
                # Check if 'build' module is missing
                if "No module named build" in result.stderr:
                    error_msg += f"\n\nInstall build module with: {python_cmd} -m pip install build"
                raise RuntimeError(error_msg)

            # Verify wheel was created
            if not wheel_path.exists():
                raise RuntimeError(
                    f"Build completed but wheel not found at {wheel_path}\n"
                    f"Build output: {result.stdout}"
                )

            print(f"✓ Wheel built successfully: {wheel_path.name}")
            return wheel_path

        except subprocess.TimeoutExpired:
            raise RuntimeError("Wheel build timed out after 120 seconds")
        except Exception as e:
            raise RuntimeError(f"Failed to build wheel: {str(e)}") from e

    async def _install_dependencies(self) -> None:
        """
        Install required packages in sandbox.

        Installs:
        - Node.js and npm (for Claude Code)
        - Claude Code CLI (@anthropic-ai/claude-code)
        - claudeswarm package (from pre-built wheel - FAST!)
        - fastapi and uvicorn (for web dashboard)
        - pytest (for testing)
        - tmux (for multi-pane coordination)

        Raises:
            RuntimeError: If any installation fails
            asyncio.TimeoutError: If installation exceeds timeout
        """
        # Ensure wheel exists (build automatically if needed)
        wheel_path = await asyncio.to_thread(self._ensure_wheel_exists)

        print(f"📦 Uploading claudeswarm wheel ({wheel_path.stat().st_size // 1024}KB)...")
        wheel_bytes = wheel_path.read_bytes()
        sandbox_wheel_path = "/tmp/claude_swarm-0.1.0-py3-none-any.whl"

        # Upload wheel to sandbox
        await asyncio.to_thread(
            self.sandbox.files.write,  # type: ignore[union-attr]
            sandbox_wheel_path,
            wheel_bytes
        )
        print(f"✓ Wheel uploaded to {sandbox_wheel_path}")

        # Get Claude Code OAuth token from local environment (if available)
        claude_oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")

        commands = [
            # CRITICAL: Update apt cache first (required for package installation)
            "apt-get update",
            # CRITICAL: Install system packages (tmux, git, curl are essential for coordination)
            # Note: nodejs and npm are pre-installed in E2B, but we install them explicitly
            # to ensure they're available. The DEBIAN_FRONTEND=noninteractive prevents
            # interactive prompts during installation.
            "DEBIAN_FRONTEND=noninteractive apt-get install -y tmux git curl",
            # Verify tmux was installed successfully (this will fail deployment if not)
            "which tmux",
            # Create workspace directory
            "mkdir -p /workspace",
            # Configure shell PATH for ALL shell types (interactive, login, non-interactive)
            # .bashrc is sourced by interactive non-login shells
            "echo 'export PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin:$PATH' >> ~/.bashrc",
            # .bash_profile is sourced by login shells
            "echo 'export PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin:$PATH' >> ~/.bash_profile",
            # .profile is sourced by login shells if .bash_profile doesn't exist
            "echo 'export PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin:$PATH' >> ~/.profile",
            # Install Claude Code CLI - this creates a 'claude' binary in /usr/local/bin
            "npm install -g @anthropic-ai/claude-code",
            # Create Claude Code directories for BOTH root and user
            "mkdir -p /root/.claude",
            "mkdir -p /root/.config/claude-code",
            "mkdir -p /home/user/.claude",
            "mkdir -p /home/user/.config/claude-code",
            # Skip onboarding prompts by creating config files for BOTH root and user
            # Root configs
            'echo \'{"hasCompletedOnboarding": true}\' > /root/.claude.json',
            'echo \'{"hasCompletedOnboarding": true}\' > /root/.config/claude-code/config.json',
            # User configs (critical for E2B CLI sessions)
            'echo \'{"hasCompletedOnboarding": true}\' > /home/user/.claude.json',
            'echo \'{"hasCompletedOnboarding": true}\' > /home/user/.config/claude-code/config.json',
            # Fix permissions: ensure user owns their directories (CRITICAL for claude to work)
            "chown -R user:user /home/user/.claude",
            "chown -R user:user /home/user/.config/claude-code",
        ]

        # Configure GitHub MCP server if GITHUB_PERSONAL_ACCESS_TOKEN is available
        github_token = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN") or os.getenv("GITHUB_TOKEN")
        if github_token:
            print("🔧 Configuring GitHub MCP server from Docker Hub...")
            # Security: Use proper shell escaping with shlex.quote for all token usage
            import json
            import shlex

            # Create MCP settings JSON for both root and user
            # Using Docker Hub MCP catalog image (mcp/github) as required by E2B hackathon
            mcp_config_json = {
                "mcpServers": {
                    "github": {
                        "command": "docker",
                        "args": [
                            "run", "-i", "--rm",
                            "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                            "mcp/github"  # Official Docker Hub MCP catalog image
                        ],
                        "env": {
                            "GITHUB_PERSONAL_ACCESS_TOKEN": github_token
                        }
                    }
                }
            }

            # Safely escape the JSON config string for shell
            mcp_config_str = shlex.quote(json.dumps(mcp_config_json))

            # Security: Use shlex.quote for the token to prevent command injection
            escaped_github_token = shlex.quote(github_token)
            token_export = f"export GITHUB_PERSONAL_ACCESS_TOKEN={escaped_github_token}"

            # Add commands to write MCP config and export token
            # NOTE: .mcp.json must be in the PROJECT ROOT directory (not ~/.claude/)
            # Claude Code looks for .mcp.json in the current working directory
            mcp_commands = [
                # Write .mcp.json to /workspace (project root) as 'user' for proper ownership
                f"su - user -c \"echo {mcp_config_str} > /workspace/.mcp.json\"",
                # Export GITHUB_PERSONAL_ACCESS_TOKEN in all shell configs
                # Root user configs (for run_code operations)
                f"echo {shlex.quote(token_export)} >> /root/.bashrc",
                f"echo {shlex.quote(token_export)} >> /root/.bash_profile",
                # Regular user configs (for E2B CLI interactive sessions)
                f"echo {shlex.quote(token_export)} >> /home/user/.bashrc",
                f"echo {shlex.quote(token_export)} >> /home/user/.bash_profile",
                f"echo {shlex.quote(token_export)} >> /home/user/.profile",
            ]
            commands.extend(mcp_commands)
        else:
            print("⚠️  GITHUB_PERSONAL_ACCESS_TOKEN not found in environment.")
            print("   GitHub MCP server will not be configured.")
            print("   Set GITHUB_PERSONAL_ACCESS_TOKEN or GITHUB_TOKEN to enable GitHub MCP integration.")

        commands.extend([
            # Install claudeswarm from uploaded wheel (FAST: <5 seconds, no network issues!)
            f"pip3 install {sandbox_wheel_path}",
            # Install other Python packages
            "pip3 install --retries 5 fastapi uvicorn pytest",
            # Verify installations (these should succeed or deployment fails)
            "python3 -c 'import claudeswarm'",
            "which claudeswarm",
            "tmux -V",  # Verify tmux is working
            "claudeswarm --version",
            "which claude",  # Verify claude binary is in PATH
            "claude --version",  # Verify claude works (npm creates 'claude' binary, not 'claude-code')
        ])

        # If Claude OAuth token is available, add it to all shell configs for automatic authentication
        if claude_oauth_token:
            print("⚠️  Claude Code OAuth token found but NOT recommended for E2B")
            print("   OAuth tokens don't work in headless environments (will show API Error: 401)")
            print("   Recommended: Use ANTHROPIC_API_KEY for API billing instead")
            print("   Skipping OAuth token configuration...")
            # Don't configure OAuth token as it doesn't work in headless environments
        else:
            print("ℹ️  CLAUDE_CODE_OAUTH_TOKEN not found in environment.")
            print("   To use Claude Code in E2B, set ANTHROPIC_API_KEY for API billing")
            print("   (Note: This will charge API usage, not use Claude subscription)")

        for i, cmd in enumerate(commands, 1):
            print(f"  [{i}/{len(commands)}] {cmd.split()[0]}...")
            try:
                # Security: Add timeout protection for all async operations
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.sandbox.run_code,  # type: ignore[union-attr]
                        f"!{cmd}",
                    ),
                    timeout=self.operation_timeout
                )

                # Check for errors (both result.error and exit codes)
                if result.error:
                    error_msg = f"Command failed: {cmd}\nError: {result.error}"
                    if hasattr(result, 'logs') and result.logs:
                        if result.logs.stderr:
                            error_msg += f"\nStderr: {''.join(result.logs.stderr)}"
                    raise RuntimeError(error_msg)

                # Check exit code if available
                if hasattr(result, 'exit_code') and result.exit_code != 0:
                    error_msg = f"Command exited with code {result.exit_code}: {cmd}"
                    if hasattr(result, 'logs') and result.logs:
                        if result.logs.stdout:
                            error_msg += f"\nStdout: {''.join(result.logs.stdout)}"
                        if result.logs.stderr:
                            error_msg += f"\nStderr: {''.join(result.logs.stderr)}"
                    raise RuntimeError(error_msg)

            except asyncio.TimeoutError:
                raise RuntimeError(
                    f"Installation timed out after {self.operation_timeout}s: {cmd}"
                )
            except Exception as e:
                raise RuntimeError(f"Installation failed at step [{i}/{len(commands)}]: {str(e)}") from e

        print("✓ Dependencies installed")

    async def _setup_tmux(self) -> None:
        """
        Create tmux session with multiple panes.

        Creates a tmux session named 'claude-swarm' and splits it into
        multiple panes (one per agent) using a tiled layout.

        Configures tmux with standard Ctrl+b prefix, vim-style navigation,
        and mouse support.

        Raises:
            RuntimeError: If tmux setup fails
            asyncio.TimeoutError: If tmux setup exceeds timeout
        """
        print(f"🖥️  Setting up tmux with {self.num_agents} panes...")

        try:
            # Create tmux config for E2B sandbox
            # Write to /home/user/.tmux.conf since tmux runs as 'user'
            tmux_config_lines = [
                "# Claude Swarm tmux configuration",
                "# Using standard Ctrl+b prefix",
                "",
                "# Better colors",
                "set -g default-terminal screen-256color",
                "",
                "# Status bar styling",
                "set -g status-bg black",
                "set -g status-fg white",
                "set -g status-left '[Claude Swarm] '",
                "set -g status-right '%H:%M %d-%b-%y'",
                "",
                "# Vim-style pane navigation",
                "bind h select-pane -L",
                "bind j select-pane -D",
                "bind k select-pane -U",
                "bind l select-pane -R",
                "",
                "# Enable mouse support",
                "set -g mouse on",
                "",
                "# Pane resizing with vim keys",
                "bind -r H resize-pane -L 5",
                "bind -r J resize-pane -D 5",
                "bind -r K resize-pane -U 5",
                "bind -r L resize-pane -R 5",
            ]
            # Write config file line by line to avoid heredoc issues with E2B's run_code
            # First, clear the file
            clear_cmd = "su - user -c '> /home/user/.tmux.conf'"
            await asyncio.wait_for(
                asyncio.to_thread(
                    self.sandbox.run_code,  # type: ignore[union-attr]
                    f"!{clear_cmd}",
                ),
                timeout=self.operation_timeout
            )

            # Write each line of config
            for line in tmux_config_lines:
                # Escape single quotes for shell
                escaped_line = line.replace("'", "'\\''")
                # Append line to file
                append_cmd = f"su - user -c \"echo '{escaped_line}' >> /home/user/.tmux.conf\""
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.sandbox.run_code,  # type: ignore[union-attr]
                        f"!{append_cmd}",
                    ),
                    timeout=self.operation_timeout
                )
                if result.error:
                    print(f"⚠️  Warning: Failed to write tmux config line: {result.error}")
                    break

            # Verify config was written correctly
            verify_cmd = "su - user -c 'cat /home/user/.tmux.conf'"
            verify_result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.sandbox.run_code,  # type: ignore[union-attr]
                    f"!{verify_cmd}",
                ),
                timeout=self.operation_timeout
            )
            if verify_result.error or not verify_result.text:
                print(f"⚠️  Warning: Could not verify tmux config was written")

            # Security: Sanitize session name for shell
            session_name = sanitize_for_shell("claude-swarm")

            # Create initial session as the 'user' (not root) so it's accessible from E2B CLI
            # E2B CLI connects as 'user', so tmux session must be owned by 'user'
            # The -f flag ensures tmux loads the config from /home/user/.tmux.conf
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    self.sandbox.run_code,  # type: ignore[union-attr]
                    f'!su - user -c "/usr/bin/tmux -f /home/user/.tmux.conf new-session -d -s {session_name} -x 200 -y 50"',
                ),
                timeout=self.operation_timeout
            )
            if result.error:
                raise RuntimeError(f"Failed to create tmux session: {result.error}")

            # Split into multiple panes (run as 'user' to match session ownership)
            for i in range(1, self.num_agents):
                # Split horizontally
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.sandbox.run_code,  # type: ignore[union-attr]
                        f'!su - user -c "/usr/bin/tmux split-window -h -t {session_name}"',
                    ),
                    timeout=self.operation_timeout
                )
                if result.error:
                    raise RuntimeError(f"Failed to split pane {i}: {result.error}")

                # Apply tiled layout after each split
                await asyncio.wait_for(
                    asyncio.to_thread(
                        self.sandbox.run_code,  # type: ignore[union-attr]
                        f'!su - user -c "/usr/bin/tmux select-layout -t {session_name} tiled"',
                    ),
                    timeout=self.operation_timeout
                )

            print("✓ Tmux session created")

        except asyncio.TimeoutError:
            raise RuntimeError(f"Tmux setup timed out after {self.operation_timeout}s")
        except Exception as e:
            raise RuntimeError(f"Tmux setup failed: {str(e)}") from e

    async def _initialize_swarm(self) -> None:
        """
        Initialize claudeswarm in each pane.

        Sends the agent discovery command to each tmux pane to initialize
        the coordination system. Waits for initialization to complete.

        Raises:
            RuntimeError: If initialization fails
            asyncio.TimeoutError: If initialization exceeds timeout
        """
        print("🔗 Initializing claudeswarm agents...")

        try:
            # Security: Sanitize all shell arguments
            session_name = sanitize_for_shell("claude-swarm")
            workspace_dir = sanitize_for_shell("/workspace")
            discover_cmd = sanitize_for_shell("claudeswarm discover-agents")

            # Set working directory and initialize in each pane
            for i in range(self.num_agents):
                # Validate pane index is safe
                if not isinstance(i, int) or i < 0 or i >= self.num_agents:
                    raise RuntimeError(f"Invalid pane index: {i}")

                # Send command to each pane as 'user' (use full path for E2B PATH compatibility)
                cmd = (
                    f"!su - user -c \"/usr/bin/tmux send-keys -t {session_name}:{i} "
                    f"'cd {workspace_dir} && {discover_cmd}' Enter\""
                )
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.sandbox.run_code,  # type: ignore[union-attr]
                        cmd,
                    ),
                    timeout=self.operation_timeout
                )
                if result.error:
                    print(f"⚠️  Warning: Pane {i} initialization issue: {result.error}")

            # Wait for agents to initialize
            await asyncio.sleep(3)

            print("✓ Claudeswarm agents initialized")

        except asyncio.TimeoutError:
            raise RuntimeError(f"Swarm initialization timed out after {self.operation_timeout}s")
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
            try:
                # Security: Add timeout for cleanup operations
                await asyncio.wait_for(
                    asyncio.to_thread(self.sandbox.kill),
                    timeout=30.0  # Use shorter timeout for cleanup
                )
                print("✓ Sandbox closed")
            except asyncio.TimeoutError:
                print(f"⚠️  Sandbox cleanup timed out after 30s (non-fatal)")
            except Exception as e:
                print(f"⚠️  Sandbox cleanup error: {e} (non-fatal)")

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
