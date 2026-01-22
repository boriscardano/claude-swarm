"""
MCP Configuration and Convenience Methods.

This module provides pre-configured settings for common MCP servers
and convenience methods for attaching them to the MCP Bridge.
"""

import os
from typing import Optional

from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.types import MCPConfig, MCPContainerInfo, MCPType


# Default configurations for supported MCP servers
# These can be customized per deployment

GITHUB_MCP_CONFIG = MCPConfig(
    mcp_type=MCPType.GITHUB,
    container_image="mcp/github:latest",  # TODO: Verify actual image name from Docker Hub
    port=3000,
    timeout=30.0,
    max_retries=3,
    rate_limit=30,  # GitHub has stricter rate limits
)

FILESYSTEM_MCP_CONFIG = MCPConfig(
    mcp_type=MCPType.FILESYSTEM,
    container_image="mcp/filesystem:latest",  # TODO: Verify actual image name
    port=3001,
    timeout=15.0,
    max_retries=3,
    rate_limit=100,  # Filesystem operations can be more frequent
)

# Exa and Perplexity MCP configurations
# Configured by agent-5 based on Docker MCP Catalog documentation

EXA_MCP_CONFIG = MCPConfig(
    mcp_type=MCPType.EXA,
    container_image="mcp/exa:latest",  # Docker MCP Catalog official image
    port=3002,
    timeout=60.0,  # Research queries may take longer
    max_retries=3,
    rate_limit=20,  # Research API typically has lower limits
)

PERPLEXITY_MCP_CONFIG = MCPConfig(
    mcp_type=MCPType.PERPLEXITY,
    container_image="mcp/perplexity-ask:latest",  # Docker MCP Catalog official image
    port=3003,
    timeout=300.0,  # 5 minutes default timeout for deep research
    max_retries=3,
    rate_limit=20,  # Perplexity API rate limits
)


async def attach_github_mcp(
    bridge: MCPBridge, github_token: Optional[str] = None
) -> MCPContainerInfo:
    """
    Attach GitHub MCP server with standard configuration.

    Args:
        bridge: MCPBridge instance
        github_token: GitHub personal access token (if None, reads from env)

    Returns:
        Container information for the running GitHub MCP

    Raises:
        MCPError: If GitHub token is not provided or MCP fails to start

    Example:
        ```python
        bridge = MCPBridge(sandbox_id="e2b-abc123")
        github_info = await attach_github_mcp(bridge, token)

        # Create a repository
        response = await bridge.call_mcp(
            mcp_name="github",
            method="create_repo",
            params={"name": "my-repo", "private": False}
        )
        ```
    """
    token = github_token or os.getenv("GITHUB_TOKEN")

    if not token:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message="GitHub token not provided. Set GITHUB_TOKEN env var or pass token parameter.",
            mcp_name="github",
            method="attach_github_mcp",
        )

    config = GITHUB_MCP_CONFIG
    config.environment = {"GITHUB_TOKEN": token}

    return await bridge.attach_mcp(mcp_type=MCPType.GITHUB, config=config)


async def attach_filesystem_mcp(
    bridge: MCPBridge, workspace_path: str = "/workspace"
) -> MCPContainerInfo:
    """
    Attach Filesystem MCP server with standard configuration.

    Args:
        bridge: MCPBridge instance
        workspace_path: Path to mount as workspace in container

    Returns:
        Container information for the running Filesystem MCP

    Example:
        ```python
        bridge = MCPBridge(sandbox_id="e2b-abc123")
        fs_info = await attach_filesystem_mcp(bridge)

        # Read a file
        response = await bridge.call_mcp(
            mcp_name="filesystem",
            method="read_file",
            params={"path": "/workspace/main.py"}
        )

        # Write a file
        response = await bridge.call_mcp(
            mcp_name="filesystem",
            method="write_file",
            params={
                "path": "/workspace/config.json",
                "content": '{"key": "value"}'
            }
        )
        ```
    """
    config = FILESYSTEM_MCP_CONFIG
    config.environment = {"WORKSPACE_PATH": workspace_path}

    # TODO: Add volume mount configuration once we know the MCP container structure
    # config.volumes = {workspace_path: {"bind": "/workspace", "mode": "rw"}}

    return await bridge.attach_mcp(mcp_type=MCPType.FILESYSTEM, config=config)


# Helper functions for common GitHub operations
# These wrap the generic call_mcp with type-safe interfaces


async def github_create_repo(
    bridge: MCPBridge,
    name: str,
    description: str = "",
    private: bool = False,
    auto_init: bool = True,
) -> dict:
    """
    Create a new GitHub repository.

    Args:
        bridge: MCPBridge instance with GitHub MCP attached
        name: Repository name
        description: Repository description
        private: Whether the repository should be private
        auto_init: Initialize with README

    Returns:
        Repository data from GitHub API

    Example:
        ```python
        repo = await github_create_repo(
            bridge,
            name="my-awesome-project",
            description="Built by autonomous agents!",
            private=False
        )
        print(f"Created: {repo['html_url']}")
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="github",
        method="create_repo",
        params={
            "name": name,
            "description": description,
            "private": private,
            "auto_init": auto_init,
        },
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Failed to create repository: {response.error}",
            mcp_name="github",
            method="create_repo",
        )

    return response.data


async def github_create_pull_request(
    bridge: MCPBridge,
    repo: str,
    title: str,
    body: str,
    head: str,
    base: str = "main",
) -> dict:
    """
    Create a pull request on GitHub.

    Args:
        bridge: MCPBridge instance with GitHub MCP attached
        repo: Repository in "owner/name" format
        title: PR title
        body: PR description
        head: Branch containing changes
        base: Branch to merge into (default: main)

    Returns:
        Pull request data from GitHub API

    Example:
        ```python
        pr = await github_create_pull_request(
            bridge,
            repo="owner/repo",
            title="Add JWT authentication",
            body="Autonomous implementation by Claude Swarm",
            head="feature/jwt-auth",
            base="main"
        )
        print(f"PR created: {pr['html_url']}")
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="github",
        method="create_pull_request",
        params={
            "repo": repo,
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        },
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Failed to create pull request: {response.error}",
            mcp_name="github",
            method="create_pull_request",
        )

    return response.data


async def github_commit_files(
    bridge: MCPBridge,
    repo: str,
    branch: str,
    message: str,
    files: dict[str, str],
) -> dict:
    """
    Commit multiple files to a repository.

    Args:
        bridge: MCPBridge instance with GitHub MCP attached
        repo: Repository in "owner/name" format
        branch: Branch to commit to
        message: Commit message
        files: Dictionary mapping file paths to contents

    Returns:
        Commit data from GitHub API

    Example:
        ```python
        commit = await github_commit_files(
            bridge,
            repo="owner/repo",
            branch="feature/auth",
            message="Implement user authentication",
            files={
                "auth/jwt.py": "# JWT implementation...",
                "models/user.py": "# User model..."
            }
        )
        print(f"Committed: {commit['sha']}")
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="github",
        method="commit_files",
        params={
            "repo": repo,
            "branch": branch,
            "message": message,
            "files": files,
        },
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Failed to commit files: {response.error}",
            mcp_name="github",
            method="commit_files",
        )

    return response.data


# Helper functions for Filesystem operations


async def filesystem_read_file(bridge: MCPBridge, path: str) -> str:
    """
    Read a file from the workspace.

    Args:
        bridge: MCPBridge instance with Filesystem MCP attached
        path: File path relative to workspace

    Returns:
        File contents as string

    Example:
        ```python
        content = await filesystem_read_file(bridge, "main.py")
        print(content)
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="filesystem", method="read_file", params={"path": path}
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Failed to read file: {response.error}",
            mcp_name="filesystem",
            method="read_file",
        )

    return response.data["content"]


async def filesystem_write_file(
    bridge: MCPBridge, path: str, content: str
) -> None:
    """
    Write a file to the workspace.

    Args:
        bridge: MCPBridge instance with Filesystem MCP attached
        path: File path relative to workspace
        content: File contents to write

    Example:
        ```python
        await filesystem_write_file(
            bridge,
            "config.json",
            '{"api_key": "xxx"}'
        )
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="filesystem",
        method="write_file",
        params={"path": path, "content": content},
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Failed to write file: {response.error}",
            mcp_name="filesystem",
            method="write_file",
        )


# Exa MCP Integration
# Implemented by agent-5


async def attach_exa_mcp(
    bridge: MCPBridge, exa_api_key: Optional[str] = None
) -> MCPContainerInfo:
    """
    Attach Exa MCP server with standard configuration.

    Exa provides AI-powered web search capabilities for research and
    best practices discovery.

    Args:
        bridge: MCPBridge instance
        exa_api_key: Exa API key (if None, reads from env)

    Returns:
        Container information for the running Exa MCP

    Raises:
        MCPError: If Exa API key is not provided or MCP fails to start

    Example:
        ```python
        bridge = MCPBridge(sandbox_id="e2b-abc123")
        exa_info = await attach_exa_mcp(bridge, api_key)

        # Perform web search for research
        response = await exa_search(
            bridge,
            query="JWT authentication best practices Python",
            num_results=5
        )
        ```
    """
    api_key = exa_api_key or os.getenv("EXA_API_KEY")

    if not api_key:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message="Exa API key not provided. Set EXA_API_KEY env var or pass api_key parameter.",
            mcp_name="exa",
            method="attach_exa_mcp",
        )

    config = EXA_MCP_CONFIG
    config.environment = {"EXA_API_KEY": api_key}

    return await bridge.attach_mcp(mcp_type=MCPType.EXA, config=config)


async def attach_perplexity_mcp(
    bridge: MCPBridge, perplexity_api_key: Optional[str] = None
) -> MCPContainerInfo:
    """
    Attach Perplexity MCP server with standard configuration.

    Perplexity provides real-time web search, conversational AI,
    deep research, and advanced reasoning capabilities.

    Args:
        bridge: MCPBridge instance
        perplexity_api_key: Perplexity API key (if None, reads from env)

    Returns:
        Container information for the running Perplexity MCP

    Raises:
        MCPError: If Perplexity API key is not provided or MCP fails to start

    Example:
        ```python
        bridge = MCPBridge(sandbox_id="e2b-abc123")
        perplexity_info = await attach_perplexity_mcp(bridge, api_key)

        # Perform fact-checking query
        response = await perplexity_ask(
            bridge,
            question="What are the security considerations for JWT tokens?"
        )
        ```
    """
    api_key = perplexity_api_key or os.getenv("PERPLEXITY_API_KEY")

    if not api_key:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message="Perplexity API key not provided. Set PERPLEXITY_API_KEY env var or pass api_key parameter.",
            mcp_name="perplexity",
            method="attach_perplexity_mcp",
        )

    config = PERPLEXITY_MCP_CONFIG
    config.environment = {
        "PERPLEXITY_API_KEY": api_key,
        "PERPLEXITY_TIMEOUT_MS": "300000",  # 5 minutes
    }

    return await bridge.attach_mcp(mcp_type=MCPType.PERPLEXITY, config=config)


# Helper functions for Exa operations


async def exa_search(
    bridge: MCPBridge,
    query: str,
    num_results: int = 5,
    use_code_context: bool = False,
) -> list[dict]:
    """
    Perform web search using Exa MCP.

    Args:
        bridge: MCPBridge instance with Exa MCP attached
        query: Search query string
        num_results: Number of results to return (default: 5)
        use_code_context: Use code-specific search (get_code_context_exa)

    Returns:
        List of search results with titles, URLs, snippets, and metadata

    Example:
        ```python
        # General web search
        results = await exa_search(
            bridge,
            query="FastAPI JWT authentication tutorial",
            num_results=5
        )

        # Code-specific search
        code_results = await exa_search(
            bridge,
            query="Python argon2 password hashing example",
            use_code_context=True
        )

        for result in results:
            print(f"{result['title']}: {result['url']}")
        ```
    """
    method = "get_code_context_exa" if use_code_context else "web_search_exa"

    response = await bridge.call_mcp(
        mcp_name="exa",
        method=method,
        params={"query": query, "num_results": num_results},
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Exa search failed: {response.error}",
            mcp_name="exa",
            method=method,
        )

    return response.data.get("results", [])


async def exa_company_research(bridge: MCPBridge, company_name: str) -> dict:
    """
    Perform comprehensive company research using Exa.

    Args:
        bridge: MCPBridge instance with Exa MCP attached
        company_name: Name of the company to research

    Returns:
        Company research data with website crawl results

    Example:
        ```python
        research = await exa_company_research(bridge, "Anthropic")
        print(research['summary'])
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="exa",
        method="company_research_exa",
        params={"company_name": company_name},
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Company research failed: {response.error}",
            mcp_name="exa",
            method="company_research_exa",
        )

    return response.data


# Helper functions for Perplexity operations


async def perplexity_search(bridge: MCPBridge, query: str) -> dict:
    """
    Direct web search using Perplexity Search API.

    Args:
        bridge: MCPBridge instance with Perplexity MCP attached
        query: Search query string

    Returns:
        Ranked search results with titles, URLs, snippets, and metadata

    Example:
        ```python
        results = await perplexity_search(
            bridge,
            query="What are OWASP top 10 security vulnerabilities?"
        )
        for result in results['results']:
            print(f"{result['title']}: {result['url']}")
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="perplexity",
        method="perplexity_search",
        params={"query": query},
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Perplexity search failed: {response.error}",
            mcp_name="perplexity",
            method="perplexity_search",
        )

    return response.data


async def perplexity_ask(
    bridge: MCPBridge, question: str, strip_thinking: bool = True
) -> str:
    """
    Ask a question using Perplexity's conversational AI (sonar-pro model).

    Args:
        bridge: MCPBridge instance with Perplexity MCP attached
        question: Question to ask
        strip_thinking: Remove <think>...</think> tags to save tokens

    Returns:
        AI-generated answer with real-time web search

    Example:
        ```python
        answer = await perplexity_ask(
            bridge,
            question="Should I use bcrypt or argon2 for password hashing?"
        )
        print(answer)
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="perplexity",
        method="perplexity_ask",
        params={"question": question, "strip_thinking": strip_thinking},
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Perplexity ask failed: {response.error}",
            mcp_name="perplexity",
            method="perplexity_ask",
        )

    return response.data.get("answer", "")


async def perplexity_research(
    bridge: MCPBridge, topic: str, strip_thinking: bool = True
) -> str:
    """
    Deep comprehensive research using Perplexity's sonar-deep-research model.

    Args:
        bridge: MCPBridge instance with Perplexity MCP attached
        topic: Research topic
        strip_thinking: Remove <think>...</think> tags to save tokens

    Returns:
        Comprehensive research report with citations

    Example:
        ```python
        report = await perplexity_research(
            bridge,
            topic="Security best practices for JWT implementation in Python"
        )
        print(report)
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="perplexity",
        method="perplexity_research",
        params={"topic": topic, "strip_thinking": strip_thinking},
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Perplexity research failed: {response.error}",
            mcp_name="perplexity",
            method="perplexity_research",
        )

    return response.data.get("report", "")


async def perplexity_reason(
    bridge: MCPBridge, problem: str, strip_thinking: bool = False
) -> str:
    """
    Advanced reasoning and problem-solving using sonar-reasoning-pro model.

    Args:
        bridge: MCPBridge instance with Perplexity MCP attached
        problem: Problem statement or question requiring deep reasoning
        strip_thinking: Remove <think>...</think> tags (default: False, keep reasoning)

    Returns:
        Detailed reasoning and solution

    Example:
        ```python
        solution = await perplexity_reason(
            bridge,
            problem="Should we implement refresh tokens in v1 or defer to v2?"
        )
        print(solution)
        ```
    """
    response = await bridge.call_mcp(
        mcp_name="perplexity",
        method="perplexity_reason",
        params={"problem": problem, "strip_thinking": strip_thinking},
    )

    if not response.success:
        from claudeswarm.cloud.types import MCPError

        raise MCPError(
            message=f"Perplexity reasoning failed: {response.error}",
            mcp_name="perplexity",
            method="perplexity_reason",
        )

    return response.data.get("reasoning", "")


# Bulk attachment helper for CLI integration


async def attach_multiple_mcps(
    bridge: MCPBridge,
    mcp_names: list[str],
    github_token: Optional[str] = None,
    exa_api_key: Optional[str] = None,
    perplexity_api_key: Optional[str] = None,
    workspace_path: str = "/workspace",
) -> dict[str, MCPContainerInfo]:
    """
    Attach multiple MCP servers at once.

    This is a convenience function for CLI usage and batch operations.
    Attaches MCPs in parallel for faster initialization.

    Args:
        bridge: MCPBridge instance
        mcp_names: List of MCP names to attach (e.g., ["github", "exa", "filesystem"])
        github_token: GitHub token (if attaching GitHub MCP)
        exa_api_key: Exa API key (if attaching Exa MCP)
        perplexity_api_key: Perplexity API key (if attaching Perplexity MCP)
        workspace_path: Workspace path for Filesystem MCP

    Returns:
        Dictionary mapping MCP names to their container info

    Raises:
        MCPError: If any MCP fails to attach

    Example:
        ```python
        bridge = MCPBridge(sandbox_id="e2b-abc123")

        # Attach multiple MCPs at once
        containers = await attach_multiple_mcps(
            bridge,
            mcp_names=["github", "exa", "filesystem"],
            github_token="ghp_xxx",
            exa_api_key="exa_xxx"
        )

        print(f"Attached {len(containers)} MCPs")
        for name, info in containers.items():
            print(f"  ✓ {name}: {info.endpoint_url}")
        ```
    """
    import asyncio

    # Map of MCP names to their attachment functions
    attach_functions = {
        "github": lambda: attach_github_mcp(bridge, github_token),
        "exa": lambda: attach_exa_mcp(bridge, exa_api_key),
        "perplexity": lambda: attach_perplexity_mcp(bridge, perplexity_api_key),
        "filesystem": lambda: attach_filesystem_mcp(bridge, workspace_path),
    }

    # Validate all requested MCPs are supported
    unsupported = [name for name in mcp_names if name not in attach_functions]
    if unsupported:
        raise ValueError(
            f"Unsupported MCP names: {unsupported}. "
            f"Supported: {list(attach_functions.keys())}"
        )

    # Create attachment tasks for requested MCPs
    tasks = {}
    for mcp_name in mcp_names:
        tasks[mcp_name] = attach_functions[mcp_name]()

    # Execute all attachments in parallel
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # Build result dictionary and check for errors
    containers = {}
    for (mcp_name, result) in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            # Re-raise the first error encountered
            raise result
        containers[mcp_name] = result

    return containers


def parse_mcp_list(mcp_string: str) -> list[str]:
    """
    Parse comma-separated MCP names from CLI input.

    Args:
        mcp_string: Comma-separated MCP names (e.g., "github,exa,filesystem")

    Returns:
        List of normalized MCP names

    Example:
        ```python
        # From CLI: --mcps github,exa,filesystem
        mcps = parse_mcp_list("github,exa,filesystem")
        # Returns: ["github", "exa", "filesystem"]

        # Handles whitespace and case
        mcps = parse_mcp_list(" GitHub, Exa , filesystem ")
        # Returns: ["github", "exa", "filesystem"]
        ```
    """
    return [name.strip().lower() for name in mcp_string.split(",") if name.strip()]
