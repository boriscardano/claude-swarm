# E2B Integration Documentation

**Claude Swarm Cloud: Autonomous Multi-Agent Development in E2B Sandboxes**

This document provides comprehensive technical documentation for the E2B integration in Claude Swarm, including architecture overview, component integration, code examples, and troubleshooting guides.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Component Integration](#component-integration)
3. [Quick Start Guide](#quick-start-guide)
4. [Code Examples](#code-examples)
5. [API Reference](#api-reference)
6. [Troubleshooting](#troubleshooting)
7. [Best Practices](#best-practices)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Single E2B Sandbox (Persistent)                 │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  tmux Session: "claude-swarm"                       │    │
│  │                                                      │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐        │    │
│  │  │ Agent 1   │ │ Agent 2   │ │ Agent 3   │  ...   │    │
│  │  │ (Pane 0)  │ │ (Pane 1)  │ │ (Pane 2)  │        │    │
│  │  │           │ │           │ │           │        │    │
│  │  │ Role:     │ │ Role:     │ │ Role:     │        │    │
│  │  │ Research  │ │ Implement │ │ Review    │        │    │
│  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘        │    │
│  │        │             │             │              │    │
│  └────────┼─────────────┼─────────────┼──────────────┘    │
│           │             │             │                   │
│  ┌────────┴─────────────┴─────────────┴────────────────┐   │
│  │          Shared Filesystem & State                  │   │
│  │  • ACTIVE_AGENTS.json (agent registry)              │   │
│  │  • agent_messages.log (message inbox)               │   │
│  │  • .agent_locks/*.lock (file locks)                 │   │
│  │  • /workspace (shared codebase)                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  MCP Servers (Accessible to All Agents)             │   │
│  │  ├── GitHub MCP (repo operations, commits, PRs)     │   │
│  │  ├── Exa MCP (web research, best practices)         │   │
│  │  ├── Filesystem MCP (safe file operations)          │   │
│  │  └── Perplexity MCP (fact-checking, validation)     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │
         │ Communication with Host
         ▼
┌─────────────────────────────────────┐
│   Claude Swarm Cloud CLI (Host)     │
│   • claudeswarm cloud deploy        │
│   • claudeswarm cloud monitor       │
│   • claudeswarm cloud status        │
└─────────────────────────────────────┘
```

### Component Layers

**Layer 1: E2B Sandbox Management** (`cloud/e2b_launcher.py`)
- CloudSandbox class
- Sandbox creation and lifecycle
- Dependency installation
- tmux session setup
- Agent initialization

**Layer 2: MCP Integration** (`cloud/mcp_bridge.py`, `cloud/mcp_config.py`)
- MCPBridge class
- Docker container management
- MCP server communication
- Rate limiting and retries
- Type-safe interfaces

**Layer 3: Autonomous Workflows** (`workflows/`)
- AutonomousDevelopmentLoop
- WorkDistributor
- CodeReviewProtocol
- ConsensusEngine

**Layer 4: CLI & Monitoring** (`cli.py`, `web/`)
- Cloud deployment commands
- Real-time monitoring
- Status dashboards

---

## Component Integration

### How Components Work Together

#### 1. CloudSandbox + MCPBridge Integration

The `CloudSandbox` class uses `MCPBridge` to connect MCP servers to the E2B sandbox:

```python
# In CloudSandbox.attach_mcp()
from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.mcp_config import attach_github_mcp, attach_filesystem_mcp

# Create bridge
self.mcp_bridge = MCPBridge(sandbox_id=self.sandbox_id)

# Attach MCP servers
await attach_github_mcp(self.mcp_bridge, github_token)
await attach_filesystem_mcp(self.mcp_bridge, workspace_path="/workspace")

# Bridge is now available for workflows
```

#### 2. Workflows + MCP Integration

Autonomous workflows use the MCP bridge to perform operations:

```python
# In AutonomousDevelopmentLoop
async def research_phase(self, feature_description: str):
    # Get MCP bridge from sandbox
    bridge = self.sandbox.get_mcp_bridge()

    # Use Exa MCP for research
    exa_results = await bridge.call_mcp(
        mcp_name="exa",
        method="search",
        params={"query": f"{feature_description} best practices"}
    )

    # Use GitHub MCP to commit results
    await bridge.call_mcp(
        mcp_name="github",
        method="commit_files",
        params={
            "repo": "owner/repo",
            "branch": "feature-branch",
            "message": "Add research findings",
            "files": {"RESEARCH.md": research_summary}
        }
    )
```

#### 3. Agent Coordination

Agents within the sandbox communicate using the existing messaging system:

```python
# Agent 1 broadcasts research results
from claudeswarm.messaging import MessagingSystem, MessageType

messaging = MessagingSystem()
messaging.broadcast_message(
    sender_id="agent-1",
    message_type=MessageType.INFO,
    content="Research complete. Key findings: Use JWT RS256..."
)

# Agent 2 receives and responds
# Messages appear automatically in their conversation
```

---

## Quick Start Guide

### Prerequisites

1. **API Keys**: Obtain the following credentials:
   - E2B API key from [e2b.dev](https://e2b.dev)
   - GitHub Personal Access Token (with `repo` scope)
   - Exa API key from [exa.ai](https://exa.ai)
   - (Optional) Perplexity API key

2. **Environment Setup**:
   ```bash
   # Copy .env.example to .env
   cp .env.example .env

   # Edit .env and add your credentials
   # E2B_API_KEY=your_key_here
   # GITHUB_TOKEN=your_token_here
   # EXA_API_KEY=your_key_here
   ```

3. **Install Dependencies**:
   ```bash
   # Install with cloud extras
   uv pip install -e ".[cloud]"
   ```

### Basic Usage

#### Deploy a Cloud Sandbox

```bash
# Deploy sandbox with 4 agents and GitHub + Exa MCPs
claudeswarm cloud deploy \
  --agents 4 \
  --mcps github,exa,filesystem \
  --feature "Add user authentication with JWT"

# Output:
# ✓ E2B sandbox created: e2b-abc123xyz
# ✓ Agents initialized: agent-0, agent-1, agent-2, agent-3
# ✓ MCPs attached: ✓ github ✓ exa ✓ filesystem
# ✓ Autonomous development started
#
# → Monitor: claudeswarm cloud monitor --sandbox-id e2b-abc123xyz
# → Dashboard: http://localhost:8080
```

#### Monitor Progress

```bash
# Live monitoring (follow mode)
claudeswarm cloud monitor --sandbox-id e2b-abc123xyz --follow

# Check status
claudeswarm cloud status --sandbox-id e2b-abc123xyz
```

#### Shutdown

```bash
# Cleanup sandbox and resources
claudeswarm cloud shutdown --sandbox-id e2b-abc123xyz
```

---

## Code Examples

### Example 1: Creating a Cloud Sandbox Programmatically

```python
import asyncio
import os
from claudeswarm.cloud.e2b_launcher import CloudSandbox
from claudeswarm.cloud.mcp_config import attach_github_mcp, attach_exa_mcp

async def deploy_autonomous_team():
    """Deploy a team of agents in E2B sandbox."""

    # Create sandbox with 4 agents
    sandbox = CloudSandbox(num_agents=4)

    try:
        # Initialize E2B sandbox
        sandbox_id = await sandbox.create()
        print(f"✓ Sandbox created: {sandbox_id}")

        # Attach MCP servers
        github_token = os.getenv("GITHUB_TOKEN")
        exa_api_key = os.getenv("EXA_API_KEY")

        await sandbox.attach_mcp(
            mcps=["github", "exa"],
            github_token=github_token,
            exa_api_key=exa_api_key
        )
        print("✓ MCPs attached")

        # Start autonomous development
        feature = "Implement user authentication with JWT tokens"
        pr_url = await sandbox.execute_autonomous_dev(feature)

        print(f"✓ Development complete!")
        print(f"✓ Pull request: {pr_url}")

    finally:
        # Cleanup
        await sandbox.cleanup()

# Run
asyncio.run(deploy_autonomous_team())
```

### Example 2: Using MCP Bridge Directly

```python
import asyncio
from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.mcp_config import (
    attach_github_mcp,
    github_create_repo,
    github_create_pull_request
)

async def create_project_with_pr():
    """Create a GitHub repo and PR using MCP bridge."""

    bridge = MCPBridge(sandbox_id="demo-sandbox")

    async with bridge:
        # Attach GitHub MCP
        await attach_github_mcp(bridge, github_token="ghp_xxx")

        # Create repository
        repo = await github_create_repo(
            bridge,
            name="ai-generated-project",
            description="Built by autonomous AI agents",
            private=False
        )
        print(f"Created repo: {repo['html_url']}")

        # Create pull request
        pr = await github_create_pull_request(
            bridge,
            repo="username/ai-generated-project",
            title="Add authentication system",
            body="Implemented by autonomous agents using Claude Swarm",
            head="feature/auth",
            base="main"
        )
        print(f"Created PR: {pr['html_url']}")

asyncio.run(create_project_with_pr())
```

### Example 3: Custom Autonomous Workflow

```python
from claudeswarm.cloud.e2b_launcher import CloudSandbox
from claudeswarm.workflows.autonomous_dev import AutonomousDevelopmentLoop

async def custom_workflow():
    """Run a custom autonomous development workflow."""

    # Create and initialize sandbox
    sandbox = CloudSandbox(num_agents=4)
    await sandbox.create()
    await sandbox.attach_mcp(mcps=["github", "exa", "filesystem"])

    # Get MCP bridge
    bridge = sandbox.get_mcp_bridge()

    # Create custom workflow
    workflow = AutonomousDevelopmentLoop(
        sandbox_id=sandbox.sandbox_id,
        num_agents=4,
        mcp_bridge=bridge
    )

    # Run development phases
    feature = "Add GraphQL API endpoints"

    # Phase 1: Research
    research = await workflow.research_phase(feature)
    print(f"Research complete: {len(research['best_practices'])} resources found")

    # Phase 2: Planning
    tasks = await workflow.planning_phase(research)
    print(f"Created {len(tasks)} implementation tasks")

    # Phase 3: Implementation
    results = await workflow.implementation_phase(tasks)
    print(f"Implemented {len(results)} tasks")

    # Phase 4: Create PR
    pr_url = await workflow.deployment_phase()
    print(f"Pull request created: {pr_url}")

    await sandbox.cleanup()

asyncio.run(custom_workflow())
```

### Example 4: Error Handling and Retries

```python
from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.types import MCPError, MCPResponse

async def resilient_mcp_call():
    """Make MCP calls with proper error handling."""

    bridge = MCPBridge(sandbox_id="test")

    async with bridge:
        try:
            # Call with automatic retries
            response = await bridge.call_mcp(
                mcp_name="github",
                method="create_issue",
                params={
                    "repo": "owner/repo",
                    "title": "Bug report",
                    "body": "Description..."
                }
            )

            if response.success:
                print(f"Issue created: {response.data['html_url']}")
                print(f"Took {response.duration_ms:.1f}ms")
            else:
                print(f"Failed: {response.error}")

        except MCPError as e:
            print(f"MCP Error: {e}")
            print(f"MCP: {e.mcp_name}, Method: {e.method}")
            print(f"Retry count: {e.retry_count}")
            if e.original_error:
                print(f"Caused by: {e.original_error}")

asyncio.run(resilient_mcp_call())
```

---

## API Reference

### CloudSandbox

```python
class CloudSandbox:
    """Manages an E2B sandbox with multiple agents."""

    def __init__(self, num_agents: int = 4) -> None:
        """Initialize sandbox configuration."""

    async def create(self) -> str:
        """Create E2B sandbox and initialize environment.

        Returns:
            Sandbox ID (e.g., "e2b-abc123")
        """

    async def attach_mcp(
        self,
        mcps: list[str],
        **credentials
    ) -> None:
        """Attach MCP servers to sandbox.

        Args:
            mcps: List of MCP names (e.g., ["github", "exa"])
            **credentials: API keys/tokens for each MCP
        """

    async def execute_autonomous_dev(
        self,
        feature_description: str
    ) -> str:
        """Start autonomous development workflow.

        Args:
            feature_description: Feature to implement

        Returns:
            GitHub PR URL when complete
        """

    def get_mcp_bridge(self) -> MCPBridge:
        """Get MCP bridge instance for custom workflows."""

    async def cleanup(self) -> None:
        """Shutdown sandbox and cleanup resources."""
```

### MCPBridge

```python
class MCPBridge:
    """Manages MCP server containers and communication."""

    def __init__(self, sandbox_id: str) -> None:
        """Initialize bridge."""

    async def attach_mcp(
        self,
        mcp_type: MCPType,
        config: MCPConfig
    ) -> MCPContainerInfo:
        """Attach an MCP server.

        Args:
            mcp_type: Type of MCP (GITHUB, EXA, etc.)
            config: MCP configuration

        Returns:
            Container information
        """

    async def call_mcp(
        self,
        mcp_name: str,
        method: str,
        params: dict[str, Any]
    ) -> MCPResponse:
        """Call an MCP method.

        Args:
            mcp_name: Name of MCP (e.g., "github")
            method: Method to call
            params: Method parameters

        Returns:
            Standardized response
        """

    def get_mcp_status(self, mcp_name: str) -> Optional[MCPContainerInfo]:
        """Get MCP container status."""

    def list_mcps(self) -> list[MCPContainerInfo]:
        """List all attached MCPs."""

    async def cleanup(self) -> None:
        """Stop and remove all MCP containers."""
```

### Helper Functions

```python
# GitHub MCP helpers
async def attach_github_mcp(
    bridge: MCPBridge,
    github_token: Optional[str] = None
) -> MCPContainerInfo

async def github_create_repo(
    bridge: MCPBridge,
    name: str,
    description: str = "",
    private: bool = False
) -> dict

async def github_create_pull_request(
    bridge: MCPBridge,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main"
) -> dict

async def github_commit_files(
    bridge: MCPBridge,
    repo: str,
    branch: str,
    message: str,
    files: dict[str, str]
) -> dict

# Filesystem MCP helpers
async def attach_filesystem_mcp(
    bridge: MCPBridge,
    workspace_path: str = "/workspace"
) -> MCPContainerInfo

async def filesystem_read_file(
    bridge: MCPBridge,
    path: str
) -> str

async def filesystem_write_file(
    bridge: MCPBridge,
    path: str,
    content: str
) -> None
```

---

## Troubleshooting

### Common Issues and Solutions

#### 1. E2B Sandbox Creation Fails

**Symptom**: `MCPError: Failed to create E2B sandbox`

**Possible Causes**:
- Invalid or missing E2B API key
- E2B service is down
- Rate limit exceeded

**Solutions**:
```bash
# Verify API key is set
echo $E2B_API_KEY

# Check E2B service status
curl https://status.e2b.dev

# Wait if rate limited (sandboxes have creation limits)
```

#### 2. MCP Container Won't Start

**Symptom**: `MCPError: Failed to start MCP container`

**Possible Causes**:
- Docker daemon not running
- Invalid MCP image name
- Missing credentials in environment

**Solutions**:
```bash
# Check Docker is running
docker ps

# Verify image exists
docker images | grep mcp

# Check environment variables
env | grep -E "(GITHUB_TOKEN|EXA_API_KEY)"

# Pull MCP images manually
docker pull mcp/github:latest
docker pull mcp/exa:latest
```

#### 3. MCP Call Timeout

**Symptom**: `MCPError: Request failed after 3 retries`

**Possible Causes**:
- MCP server is slow or hung
- Network issues
- Invalid parameters

**Solutions**:
```python
# Increase timeout in config
from claudeswarm.cloud.types import MCPConfig, MCPType

config = MCPConfig(
    mcp_type=MCPType.GITHUB,
    container_image="mcp/github:latest",
    timeout=60.0,  # Increase from default 30s
    max_retries=5   # More retry attempts
)
```

#### 4. Rate Limit Exceeded

**Symptom**: `MCPError: Rate limit exceeded for 'github' (30 requests/minute)`

**Possible Causes**:
- Too many rapid calls to same MCP
- Rate limit configuration too strict

**Solutions**:
```python
# Increase rate limit
from claudeswarm.cloud.mcp_config import GITHUB_MCP_CONFIG

GITHUB_MCP_CONFIG.rate_limit = 60  # Allow 60 req/min instead of 30

# Or add delays between calls
import asyncio
await asyncio.sleep(2)  # 2 second delay
```

#### 5. Agents Can't Communicate

**Symptom**: Agents not receiving messages from each other

**Possible Causes**:
- tmux session not properly initialized
- Messaging system not started
- File permissions issue

**Solutions**:
```bash
# Check tmux session exists
tmux list-sessions | grep claude-swarm

# Check agent registry
cat ACTIVE_AGENTS.json

# Check message log
tail -f agent_messages.log

# Verify file permissions
ls -la ACTIVE_AGENTS.json agent_messages.log
```

#### 6. Dependency Installation Fails

**Symptom**: `Error: Failed to install dependencies in sandbox`

**Possible Causes**:
- Network issues in E2B sandbox
- Package version conflicts
- PyPI rate limiting

**Solutions**:
```python
# Customize dependency installation
sandbox = CloudSandbox(num_agents=4)
await sandbox.create()

# Install with retry
for attempt in range(3):
    try:
        await sandbox._install_dependencies()
        break
    except Exception as e:
        if attempt == 2:
            raise
        await asyncio.sleep(5)
```

### Debug Mode

Enable detailed logging for troubleshooting:

```bash
# Set debug mode in .env
DEBUG=true

# Run with verbose output
claudeswarm cloud deploy --agents 4 --mcps github --feature "test" --verbose
```

```python
# Enable debug logging in code
import logging
logging.basicConfig(level=logging.DEBUG)

# MCPBridge will log all HTTP requests/responses
```

---

## Best Practices

### 1. Resource Management

Always use async context managers or explicit cleanup:

```python
# Good: Context manager
async with CloudSandbox(num_agents=4) as sandbox:
    await sandbox.execute_autonomous_dev(feature)
# Cleanup happens automatically

# Also good: Explicit cleanup
sandbox = CloudSandbox(num_agents=4)
try:
    await sandbox.create()
    await sandbox.execute_autonomous_dev(feature)
finally:
    await sandbox.cleanup()
```

### 2. Error Handling

Handle MCP errors gracefully:

```python
from claudeswarm.cloud.types import MCPError, MCPResponse

try:
    response = await bridge.call_mcp("github", "create_repo", params)
    if not response.success:
        # Handle failed response
        logger.error(f"MCP call failed: {response.error}")
except MCPError as e:
    # Handle MCP exception
    logger.error(f"MCP error: {e}")
    if e.retry_count >= 3:
        # All retries exhausted, use fallback
        pass
```

### 3. Rate Limiting

Configure appropriate rate limits for your use case:

```python
# For demo/testing: Higher limits
GITHUB_MCP_CONFIG.rate_limit = 100

# For production: Conservative limits
GITHUB_MCP_CONFIG.rate_limit = 30
GITHUB_MCP_CONFIG.max_retries = 5
```

### 4. Credential Security

Never hardcode credentials:

```python
# Bad
github_token = "ghp_xxxxxxxxxxxx"

# Good: Use environment variables
import os
github_token = os.getenv("GITHUB_TOKEN")

# Better: Validate before use
github_token = os.getenv("GITHUB_TOKEN")
if not github_token:
    raise ValueError("GITHUB_TOKEN environment variable not set")
```

### 5. Testing

Test with mocks before using real credentials:

```python
# Unit test with mocks
from unittest.mock import AsyncMock, patch

@patch('docker.from_env')
async def test_mcp_bridge(mock_docker):
    bridge = MCPBridge(sandbox_id="test")
    # Test without real Docker

# Integration test with real credentials (marked as integration)
@pytest.mark.integration
async def test_real_github_mcp():
    if not os.getenv("GITHUB_TOKEN"):
        pytest.skip("No credentials")
    # Test with real MCP
```

### 6. Monitoring

Monitor sandbox health and MCP status:

```python
# Check MCP health periodically
async def monitor_mcps(bridge: MCPBridge):
    while True:
        for mcp_info in bridge.list_mcps():
            if not mcp_info.is_healthy:
                logger.warning(f"{mcp_info.mcp_type} is unhealthy")
        await asyncio.sleep(30)
```

---

## Performance Considerations

### Sandbox Costs

E2B sandboxes incur costs based on uptime:

- **Development**: Use short-lived sandboxes, cleanup promptly
- **Testing**: Use local Docker when possible (`USE_LOCAL_DOCKER=true`)
- **Production**: Monitor sandbox duration, set timeouts

```python
# Set maximum sandbox duration
sandbox = CloudSandbox(num_agents=4)
await sandbox.create()

# Set timeout (2 hours)
timeout_seconds = 2 * 60 * 60

try:
    await asyncio.wait_for(
        sandbox.execute_autonomous_dev(feature),
        timeout=timeout_seconds
    )
except asyncio.TimeoutError:
    logger.error("Sandbox execution exceeded timeout")
finally:
    await sandbox.cleanup()
```

### MCP Response Times

Different MCPs have different performance characteristics:

- **Filesystem**: Fast (< 100ms)
- **GitHub**: Moderate (200-500ms)
- **Exa/Perplexity**: Slow (2-30 seconds for research)

Optimize by running independent calls in parallel:

```python
# Sequential (slow)
exa_results = await bridge.call_mcp("exa", "search", {...})
perplexity_results = await bridge.call_mcp("perplexity", "ask", {...})

# Parallel (fast)
exa_task = bridge.call_mcp("exa", "search", {...})
perplexity_task = bridge.call_mcp("perplexity", "ask", {...})
exa_results, perplexity_results = await asyncio.gather(exa_task, perplexity_task)
```

---

## Next Steps

After reading this documentation:

1. **Try the Quick Start**: Deploy your first cloud sandbox
2. **Review Code Examples**: Understand common patterns
3. **Experiment**: Modify examples for your use case
4. **Read Source Code**: Dive into implementation details
5. **Contribute**: Report issues, suggest improvements

For questions or issues:
- Check [Troubleshooting](#troubleshooting) section
- Review test files for usage examples
- Open an issue on GitHub

---

**Last Updated**: 2025-11-19
**Author**: Claude Swarm Team (agent-4)
**Status**: Ready for E2B Hackathon
