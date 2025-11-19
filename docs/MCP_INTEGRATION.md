# MCP Integration Documentation

## Overview

Claude Swarm integrates with the Docker MCP Catalog to provide autonomous agents with powerful external capabilities. This document describes how MCPs are integrated and how to use them in autonomous workflows.

**Implemented by:** agent-4 (core infrastructure), agent-5 (Exa and Perplexity integrations)

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                    E2B Sandbox                                  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  CloudSandbox (E2B Launcher)                             │  │
│  │  ├─ Creates persistent sandbox                           │  │
│  │  ├─ Manages tmux session with agents                     │  │
│  │  └─ Initializes MCPBridge                                │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  MCPBridge (Core Infrastructure)                         │  │
│  │  ├─ Docker container management                          │  │
│  │  ├─ HTTP client with retry logic                         │  │
│  │  ├─ Rate limiting (per MCP)                              │  │
│  │  └─ Standardized error handling                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                           │                                     │
│                           ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  MCP Containers (Docker)                                 │  │
│  │  ├─ GitHub MCP     (mcp/github:latest)                   │  │
│  │  ├─ Filesystem MCP (mcp/filesystem:latest)               │  │
│  │  ├─ Exa MCP        (mcp/exa:latest)                      │  │
│  │  └─ Perplexity MCP (mcp/perplexity-ask:latest)           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                             │
                             │ Network Calls
                             ▼
                    External Services
                    ├─ GitHub API
                    ├─ Exa AI Search
                    └─ Perplexity AI
```

---

## Supported MCPs

### 1. GitHub MCP (MUST HAVE)

**Purpose:** Create repositories, commit code, create pull requests

**Docker Image:** `mcp/github:latest`

**Environment Variables:**
- `GITHUB_TOKEN`: Personal access token with `repo` scope

**Available Methods:**
- `create_repo`: Create a new GitHub repository
- `create_pull_request`: Create a pull request
- `commit_files`: Commit multiple files to a branch

**Rate Limit:** 30 requests/minute

**Example Usage:**
```python
from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.mcp_config import (
    attach_github_mcp,
    github_create_repo,
    github_commit_files,
    github_create_pull_request
)

# Attach GitHub MCP
bridge = MCPBridge(sandbox_id="e2b-abc123")
github_info = await attach_github_mcp(bridge, github_token)

# Create a repository
repo = await github_create_repo(
    bridge,
    name="autonomous-auth",
    description="JWT auth built by Claude Swarm",
    private=False
)

# Commit files
await github_commit_files(
    bridge,
    repo="owner/autonomous-auth",
    branch="main",
    message="Add JWT authentication",
    files={
        "auth/jwt.py": "# JWT implementation...",
        "models/user.py": "# User model..."
    }
)

# Create PR
pr = await github_create_pull_request(
    bridge,
    repo="owner/autonomous-auth",
    title="Add JWT authentication",
    body="Implemented by autonomous agents",
    head="feature/jwt",
    base="main"
)
```

---

### 2. Filesystem MCP (MUST HAVE)

**Purpose:** Safe file read/write operations within workspace

**Docker Image:** `mcp/filesystem:latest`

**Environment Variables:**
- `WORKSPACE_PATH`: Path to workspace directory (default: `/workspace`)

**Available Methods:**
- `read_file`: Read file contents
- `write_file`: Write file contents
- `list_directory`: List directory contents

**Rate Limit:** 100 requests/minute (filesystem ops can be frequent)

**Example Usage:**
```python
from claudeswarm.cloud.mcp_config import (
    attach_filesystem_mcp,
    filesystem_read_file,
    filesystem_write_file
)

# Attach Filesystem MCP
fs_info = await attach_filesystem_mcp(bridge, workspace_path="/workspace")

# Read a file
content = await filesystem_read_file(bridge, "main.py")
print(content)

# Write a file
await filesystem_write_file(
    bridge,
    "config.json",
    '{"api_key": "xxx", "env": "production"}'
)
```

---

### 3. Exa MCP (SHOULD HAVE)

**Purpose:** AI-powered web search for research and best practices

**Docker Image:** `mcp/exa:latest`

**Environment Variables:**
- `EXA_API_KEY`: API key from https://exa.ai

**Available Methods:**
- `web_search_exa`: General web search
- `get_code_context_exa`: Code-specific search (examples, docs, libraries)
- `company_research_exa`: Comprehensive company research
- `crawling_exa`: Extract content from specific URLs
- `linkedin_search_exa`: Search LinkedIn (companies/people)
- `deep_researcher_start`: Start deep research task
- `deep_researcher_check`: Check research task results

**Default Enabled Tools:** `web_search_exa`, `get_code_context_exa`

**Rate Limit:** 20 requests/minute

**Example Usage:**
```python
from claudeswarm.cloud.mcp_config import (
    attach_exa_mcp,
    exa_search,
    exa_company_research
)

# Attach Exa MCP
exa_info = await attach_exa_mcp(bridge, exa_api_key)

# General web search for best practices
results = await exa_search(
    bridge,
    query="JWT authentication best practices Python FastAPI",
    num_results=5
)

for result in results:
    print(f"{result['title']}: {result['url']}")
    print(f"  {result['snippet']}")

# Code-specific search
code_results = await exa_search(
    bridge,
    query="Python argon2 password hashing example",
    use_code_context=True  # Uses get_code_context_exa
)

# Company research
research = await exa_company_research(bridge, "Anthropic")
print(research['summary'])
```

---

### 4. Perplexity MCP (NICE TO HAVE)

**Purpose:** Real-time web search, conversational AI, deep research, reasoning

**Docker Image:** `mcp/perplexity-ask:latest`

**Environment Variables:**
- `PERPLEXITY_API_KEY`: API key from https://perplexity.ai
- `PERPLEXITY_TIMEOUT_MS`: Request timeout (default: 300000 = 5 minutes)

**Available Methods:**
- `perplexity_search`: Direct web search with ranked results
- `perplexity_ask`: Conversational AI (sonar-pro model)
- `perplexity_research`: Deep research (sonar-deep-research model)
- `perplexity_reason`: Advanced reasoning (sonar-reasoning-pro model)

**Parameters:**
- `strip_thinking` (boolean): Remove `<think>...</think>` tags to save tokens

**Rate Limit:** 20 requests/minute

**Example Usage:**
```python
from claudeswarm.cloud.mcp_config import (
    attach_perplexity_mcp,
    perplexity_search,
    perplexity_ask,
    perplexity_research,
    perplexity_reason
)

# Attach Perplexity MCP
perplexity_info = await attach_perplexity_mcp(bridge, perplexity_api_key)

# Direct web search
search_results = await perplexity_search(
    bridge,
    query="OWASP top 10 security vulnerabilities 2025"
)

# Ask a question (conversational AI)
answer = await perplexity_ask(
    bridge,
    question="Should I use bcrypt or argon2 for password hashing?",
    strip_thinking=True
)
print(answer)

# Deep research
report = await perplexity_research(
    bridge,
    topic="Security best practices for JWT implementation in Python"
)
print(report)  # Comprehensive report with citations

# Advanced reasoning
solution = await perplexity_reason(
    bridge,
    problem="Should we implement refresh tokens in v1 or defer to v2?",
    strip_thinking=False  # Keep reasoning process visible
)
print(solution)
```

---

## Type Safety

All MCP operations use strongly-typed data structures from `cloud/types.py`:

### MCPConfig
```python
@dataclass
class MCPConfig:
    mcp_type: MCPType
    container_image: str
    environment: dict[str, str]
    port: int = 3000
    network_mode: str = "bridge"
    timeout: float = 30.0
    max_retries: int = 3
    rate_limit: int = 60
```

### MCPResponse
```python
@dataclass
class MCPResponse:
    success: bool
    data: Any
    error: Optional[str]
    mcp_name: str
    method: str
    duration_ms: float
```

### MCPError
```python
@dataclass
class MCPError(Exception):
    message: str
    mcp_name: str
    method: str
    original_error: Optional[Exception]
    retry_count: int
```

---

## Error Handling

The MCP Bridge provides automatic retry logic with exponential backoff:

```python
# Automatic retries (configured per MCP)
response = await bridge.call_mcp(
    mcp_name="github",
    method="create_repo",
    params={"name": "test-repo"}
)

if not response.success:
    # Error is automatically logged
    print(f"Failed after {config.max_retries} retries: {response.error}")
```

For critical operations, use explicit error handling:

```python
from claudeswarm.cloud.types import MCPError

try:
    pr = await github_create_pull_request(...)
except MCPError as e:
    print(f"GitHub operation failed: {e}")
    print(f"  MCP: {e.mcp_name}")
    print(f"  Method: {e.method}")
    print(f"  Retries attempted: {e.retry_count}")
    # Handle error (notify team, log, retry later, etc.)
```

---

## Rate Limiting

Each MCP has configured rate limits to prevent API quota exhaustion:

| MCP | Rate Limit (req/min) | Notes |
|-----|----------------------|-------|
| GitHub | 30 | GitHub API has strict limits |
| Filesystem | 100 | Local ops, higher throughput |
| Exa | 20 | Research API limits |
| Perplexity | 20 | AI model API limits |

The MCPBridge automatically enforces these limits using token bucket algorithm.

---

## Usage in Autonomous Workflows

### Research Phase (Agent 1)
```python
# Use Exa for initial research
results = await exa_search(
    bridge,
    query=f"{feature_description} best practices security",
    num_results=5
)

# Use Perplexity to validate findings
validation = await perplexity_research(
    bridge,
    topic=f"Security considerations for {feature_description}"
)

# Compile research summary
research_summary = {
    "feature": feature_description,
    "best_practices": results,
    "security_considerations": validation,
    "recommendations": extract_recommendations(results)
}
```

### Code Review Phase (All Agents)
```python
# Use Perplexity to fact-check during debates
if agent_disagrees:
    evidence = await perplexity_ask(
        bridge,
        question=f"Is {proposed_approach} better than {alternative}?"
    )

    # Share evidence with team
    messaging.send_message(
        recipient=other_agent,
        type=MessageType.CHALLENGE,
        content=f"Evidence against your approach: {evidence}"
    )
```

### Deployment Phase (Agent 4)
```python
# Commit all changes
await github_commit_files(
    bridge,
    repo="owner/repo",
    branch="feature/jwt-auth",
    message="Implement JWT authentication\n\nAutonomous development by Claude Swarm",
    files=code_changes
)

# Create pull request
pr = await github_create_pull_request(
    bridge,
    repo="owner/repo",
    title="Add JWT authentication",
    body=generate_pr_description(research_summary, implementations),
    head="feature/jwt-auth",
    base="main"
)

# Broadcast completion
messaging.broadcast_message(
    sender_id="agent-4",
    type=MessageType.COMPLETED,
    content=f"PR created: {pr['html_url']}"
)
```

---

## Configuration Files

### .env.example
```bash
# E2B Sandbox
E2B_API_KEY=your_e2b_api_key_here

# MCP Credentials
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx
EXA_API_KEY=your_exa_api_key_here
PERPLEXITY_API_KEY=your_perplexity_api_key_here
```

### pyproject.toml
```toml
[project.optional-dependencies]
cloud = [
    "e2b-code-interpreter>=0.1.0",
    "docker>=6.0.0",
    "httpx>=0.24.0",
]
```

---

## Testing

### Unit Tests
```python
# tests/cloud/test_mcp_bridge.py - 16 unit tests
# tests/cloud/test_mcp_config.py - Additional tests for configs

pytest tests/cloud/
```

### Integration Tests
```python
# Requires actual API keys in environment
pytest tests/cloud/ --integration
```

### Manual Testing
```bash
# Test GitHub MCP
python -c "
from claudeswarm.cloud import MCPBridge, attach_github_mcp
bridge = MCPBridge('test-sandbox')
await attach_github_mcp(bridge)
print('GitHub MCP attached successfully!')
"

# Test Exa MCP
python -c "
from claudeswarm.cloud import MCPBridge, attach_exa_mcp, exa_search
bridge = MCPBridge('test-sandbox')
await attach_exa_mcp(bridge)
results = await exa_search(bridge, 'test query')
print(f'Found {len(results)} results')
"
```

---

## Troubleshooting

### MCP Container Won't Start
```python
# Check Docker daemon
docker ps

# Check logs
docker logs <container_id>

# Verify image exists
docker images | grep mcp
```

### API Key Not Working
```python
# Verify environment variable is set
import os
print(os.getenv('GITHUB_TOKEN'))

# Check token permissions (GitHub)
# - Must have 'repo' scope
# - Must not be expired
```

### Rate Limit Errors
```python
# Check current rate limit status
bridge.get_rate_limit_status("github")

# Adjust rate limits in config
GITHUB_MCP_CONFIG.rate_limit = 15  # Lower limit
```

### Network Connectivity
```python
# Test container network
docker exec <container_id> ping google.com

# Check container IP
docker inspect <container_id> | grep IPAddress
```

---

## Future Enhancements

### Post-Hackathon Roadmap

**Week 1-2:**
- Add more MCPs (Slack, Jira, AWS, etc.)
- Implement MCP health monitoring
- Add metrics and observability

**Week 3-4:**
- MCP hot-swapping (update without restart)
- Advanced rate limiting strategies
- MCP caching layer

**Month 2+:**
- Custom MCP development SDK
- MCP marketplace integration
- Multi-tenant MCP sharing

---

## References

- Docker MCP Catalog: https://hub.docker.com/mcp
- E2B Documentation: https://e2b.dev/docs
- Exa API: https://docs.exa.ai/reference/exa-mcp
- Perplexity API: https://docs.perplexity.ai/guides/mcp-server
- GitHub MCP: https://hub.docker.com/mcp/server/github/overview

---

**Last Updated:** 2025-11-19 by agent-5
**Status:** Production Ready
**Code Files:**
- `src/claudeswarm/cloud/types.py` (2.9KB)
- `src/claudeswarm/cloud/mcp_bridge.py` (13.2KB)
- `src/claudeswarm/cloud/mcp_config.py` (15KB+)
- `tests/cloud/test_mcp_bridge.py` (11.3KB)
