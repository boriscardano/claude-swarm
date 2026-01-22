"""
MCP Bridge for connecting Claude Swarm to MCP servers.

This module provides the core infrastructure for managing MCP server containers,
handling communication with MCP servers, and providing a standardized API for
agents to call MCP methods.
"""

import asyncio
import time
from collections import defaultdict
from typing import Any

import docker
import httpx

from claudeswarm.cloud.security_utils import (
    ValidationError,
    sanitize_api_key_for_logging,
    sanitize_container_name,
    validate_sandbox_id,
)
from claudeswarm.cloud.types import (
    MCPConfig,
    MCPContainerInfo,
    MCPError,
    MCPResponse,
    MCPStatus,
    MCPType,
)


class MCPBridge:
    """
    Manages MCP server containers and provides communication interface.

    This class handles:
    - Starting and stopping MCP Docker containers
    - Managing container lifecycle and health
    - Making HTTP requests to MCP servers with retry logic
    - Rate limiting MCP calls
    - Standardized error handling and logging

    Example:
        ```python
        bridge = MCPBridge(sandbox_id="e2b-abc123")

        # Attach GitHub MCP
        await bridge.attach_mcp(
            mcp_type=MCPType.GITHUB,
            config=MCPConfig(
                mcp_type=MCPType.GITHUB,
                container_image="mcp/github:latest",
                environment={"GITHUB_TOKEN": "ghp_xxx"}
            )
        )

        # Call GitHub MCP method
        response = await bridge.call_mcp(
            mcp_name="github",
            method="create_issue",
            params={"title": "Bug report", "body": "Details..."}
        )
        ```
    """

    def __init__(self, sandbox_id: str) -> None:
        """
        Initialize MCP Bridge.

        Args:
            sandbox_id: E2B sandbox identifier for container naming

        Raises:
            ValidationError: If sandbox_id format is invalid
        """
        # Validate sandbox_id to prevent command injection
        try:
            self.sandbox_id = validate_sandbox_id(sandbox_id)
        except ValidationError as e:
            raise ValueError(f"Invalid sandbox_id: {e}") from e

        # Initialize Docker client with helpful error message
        try:
            self.docker_client: docker.DockerClient = docker.from_env()
        except Exception as e:
            error_msg = str(e)
            if "Connection refused" in error_msg or "ConnectionRefusedError" in error_msg:
                raise RuntimeError(
                    "❌ Docker is not running!\n\n"
                    "MCPs require Docker to run MCP server containers.\n\n"
                    "Please start Docker:\n"
                    "  • macOS: Open Docker Desktop\n"
                    "  • Linux: sudo systemctl start docker\n"
                    "  • Windows: Start Docker Desktop\n\n"
                    f"Original error: {error_msg}"
                ) from e
            elif "docker" not in error_msg.lower():
                raise RuntimeError(
                    "❌ Failed to connect to Docker!\n\n"
                    "Make sure Docker is installed and running.\n"
                    "Install Docker from: https://docs.docker.com/get-docker/\n\n"
                    f"Original error: {error_msg}"
                ) from e
            else:
                raise RuntimeError(f"Docker connection error: {error_msg}") from e

        self.mcp_containers: dict[str, MCPContainerInfo] = {}
        self.mcp_configs: dict[str, MCPConfig] = {}
        self._rate_limiters: dict[str, list[float]] = defaultdict(list)
        self._http_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "MCPBridge":
        """Async context manager entry."""
        self._http_client = httpx.AsyncClient()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.cleanup()

    async def attach_mcp(self, mcp_type: MCPType, config: MCPConfig) -> MCPContainerInfo:
        """
        Attach an MCP server by starting its Docker container.

        This method:
        1. Pulls the MCP Docker image if not present
        2. Starts the container with specified configuration
        3. Waits for the MCP server to become healthy
        4. Stores container information for future calls

        Args:
            mcp_type: Type of MCP to attach (GITHUB, EXA, etc.)
            config: Configuration for the MCP server

        Returns:
            Information about the running container

        Raises:
            MCPError: If container fails to start or become healthy

        Example:
            ```python
            info = await bridge.attach_mcp(
                mcp_type=MCPType.GITHUB,
                config=MCPConfig(
                    mcp_type=MCPType.GITHUB,
                    container_image="mcp/github:latest",
                    environment={"GITHUB_TOKEN": token}
                )
            )
            print(f"GitHub MCP available at {info.endpoint_url}")
            ```
        """
        mcp_name = mcp_type.value

        # Check if already attached
        if mcp_name in self.mcp_containers:
            existing = self.mcp_containers[mcp_name]
            if existing.is_healthy:
                return existing

        try:
            # Pull image if needed
            try:
                self.docker_client.images.pull(config.container_image)
            except docker.errors.ImageNotFound:
                raise MCPError(
                    message=f"MCP image not found: {config.container_image}",
                    mcp_name=mcp_name,
                    method="attach_mcp",
                )

            # Start container
            container_name = sanitize_container_name(f"{mcp_name}-mcp-{self.sandbox_id}")

            # Security: Sanitize environment variables for logging
            # Check for common credential patterns in environment variable names
            credential_patterns = ["key", "token", "secret", "password", "auth", "credential"]
            {
                k: (
                    sanitize_api_key_for_logging(v)
                    if any(pattern in k.lower() for pattern in credential_patterns)
                    else v
                )
                for k, v in config.environment.items()
            }

            # Remove existing container with same name if it exists
            try:
                existing = self.docker_client.containers.get(container_name)
                existing.remove(force=True)
            except docker.errors.NotFound:
                pass

            # Start MCP container
            container = self.docker_client.containers.run(
                image=config.container_image,
                name=container_name,
                environment=config.environment,
                network_mode=config.network_mode,
                detach=True,
                remove=False,
                ports={f"{config.port}/tcp": config.port},
                restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
            )

            # Get container network info
            container.reload()
            ip_address = container.attrs["NetworkSettings"]["IPAddress"]
            if not ip_address:
                # If bridge mode, use localhost
                ip_address = "127.0.0.1"

            container_info = MCPContainerInfo(
                container_id=container.id,
                mcp_type=mcp_type,
                ip_address=ip_address,
                port=config.port,
                status=MCPStatus.INITIALIZING,
                endpoint_url=f"http://{ip_address}:{config.port}",
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )

            # Wait for container to become healthy
            await self._wait_for_health(container_info, timeout=30)

            # Store container and config
            self.mcp_containers[mcp_name] = container_info
            self.mcp_configs[mcp_name] = config

            return container_info

        except docker.errors.DockerException as e:
            raise MCPError(
                message=f"Failed to start MCP container: {str(e)}",
                mcp_name=mcp_name,
                method="attach_mcp",
                original_error=e,
            ) from e

    async def call_mcp(self, mcp_name: str, method: str, params: dict[str, Any]) -> MCPResponse:
        """
        Call an MCP server method with retry logic and rate limiting.

        This method:
        1. Validates the MCP is attached and healthy
        2. Checks rate limits
        3. Makes HTTP request to MCP server
        4. Retries on transient failures
        5. Returns standardized response

        Args:
            mcp_name: Name of the MCP server (e.g., "github", "exa")
            method: MCP method to call
            params: Parameters for the method call

        Returns:
            Standardized MCPResponse with result data

        Raises:
            MCPError: If MCP is not attached, unhealthy, or call fails after retries

        Example:
            ```python
            # Create a GitHub issue
            response = await bridge.call_mcp(
                mcp_name="github",
                method="create_issue",
                params={
                    "repo": "owner/repo",
                    "title": "Bug found",
                    "body": "Description..."
                }
            )

            if response.success:
                issue_url = response.data["html_url"]
                print(f"Created issue: {issue_url}")
            ```
        """
        # Validate MCP is attached
        if mcp_name not in self.mcp_containers:
            raise MCPError(
                message=f"MCP '{mcp_name}' is not attached",
                mcp_name=mcp_name,
                method=method,
            )

        container_info = self.mcp_containers[mcp_name]
        config = self.mcp_configs[mcp_name]

        # Check if container is healthy
        if not container_info.is_healthy:
            raise MCPError(
                message=f"MCP '{mcp_name}' is not healthy (status: {container_info.status})",
                mcp_name=mcp_name,
                method=method,
            )

        # Check rate limits
        await self._check_rate_limit(mcp_name, config)

        # Make request with retries
        start_time = time.time()
        last_error: Exception | None = None

        for retry_count in range(config.max_retries):
            try:
                response = await self._make_request(
                    endpoint_url=container_info.endpoint_url,
                    method=method,
                    params=params,
                    timeout=config.timeout,
                )

                duration_ms = (time.time() - start_time) * 1000

                return MCPResponse(
                    success=True,
                    data=response,
                    mcp_name=mcp_name,
                    method=method,
                    duration_ms=duration_ms,
                )

            except httpx.HTTPError as e:
                last_error = e

                # Exponential backoff before retry
                if retry_count < config.max_retries - 1:
                    await asyncio.sleep(2**retry_count)

        # All retries failed
        duration_ms = (time.time() - start_time) * 1000

        return MCPResponse(
            success=False,
            error=f"Request failed after {config.max_retries} retries: {str(last_error)}",
            mcp_name=mcp_name,
            method=method,
            duration_ms=duration_ms,
        )

    async def _make_request(
        self, endpoint_url: str, method: str, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        """
        Make HTTP request to MCP server.

        Args:
            endpoint_url: Base URL of the MCP server
            method: Method to call
            params: Request parameters
            timeout: Request timeout in seconds

        Returns:
            Response data from MCP server

        Raises:
            httpx.HTTPError: If request fails
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()

        # TODO: Update endpoint format based on actual MCP server API
        # This is a placeholder - real MCP servers may use different protocols
        url = f"{endpoint_url}/mcp/{method}"

        response = await self._http_client.post(url, json=params, timeout=timeout)
        response.raise_for_status()

        return response.json()

    async def _check_rate_limit(self, mcp_name: str, config: MCPConfig) -> None:
        """
        Check if we're within rate limits for this MCP.

        Args:
            mcp_name: Name of the MCP
            config: MCP configuration with rate limit settings

        Raises:
            MCPError: If rate limit is exceeded
        """
        now = time.time()
        window_start = now - 60  # 1-minute window

        # Remove old timestamps outside the window
        self._rate_limiters[mcp_name] = [
            ts for ts in self._rate_limiters[mcp_name] if ts > window_start
        ]

        # Check if we're at the limit
        if len(self._rate_limiters[mcp_name]) >= config.rate_limit:
            raise MCPError(
                message=f"Rate limit exceeded for '{mcp_name}' "
                f"({config.rate_limit} requests/minute)",
                mcp_name=mcp_name,
                method="rate_limit_check",
            )

        # Record this request
        self._rate_limiters[mcp_name].append(now)

    async def _wait_for_health(self, container_info: MCPContainerInfo, timeout: float = 30) -> None:
        """
        Wait for MCP container to become healthy.

        Polls the MCP endpoint until it responds successfully or timeout is reached.

        Args:
            container_info: Container information
            timeout: Maximum time to wait in seconds

        Raises:
            MCPError: If container doesn't become healthy within timeout
        """
        start_time = time.time()
        poll_interval = 0.5  # Poll every 500ms

        while time.time() - start_time < timeout:
            try:
                # Try to connect to MCP endpoint
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient()

                # Simple health check - try to reach the endpoint
                response = await self._http_client.get(
                    f"{container_info.endpoint_url}/health", timeout=2.0
                )

                if response.status_code == 200:
                    # Container is healthy
                    container_info.status = MCPStatus.CONNECTED
                    return

            except (httpx.HTTPError, Exception):
                # Container not ready yet, wait and retry
                await asyncio.sleep(poll_interval)

        # Timeout reached without successful health check
        container_info.status = MCPStatus.ERROR
        raise MCPError(
            message=f"MCP container failed to become healthy within {timeout}s",
            mcp_name=container_info.mcp_type.value,
            method="_wait_for_health",
        )

    def get_mcp_status(self, mcp_name: str) -> MCPContainerInfo | None:
        """
        Get status of an MCP container.

        Args:
            mcp_name: Name of the MCP

        Returns:
            Container information if MCP is attached, None otherwise
        """
        return self.mcp_containers.get(mcp_name)

    def list_mcps(self) -> list[MCPContainerInfo]:
        """
        List all attached MCP containers.

        Returns:
            List of container information for all attached MCPs
        """
        return list(self.mcp_containers.values())

    async def cleanup(self) -> None:
        """
        Stop and remove all MCP containers.

        This method should be called when shutting down the bridge
        to ensure all resources are properly released.
        """
        # Close HTTP client
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        # Stop and remove containers
        for mcp_name, container_info in self.mcp_containers.items():
            try:
                # Get container and stop it gracefully
                container = self.docker_client.containers.get(container_info.container_id)
                print(f"Stopping MCP container: {mcp_name}")
                container.stop(timeout=10)
                print(f"Removing MCP container: {mcp_name}")
                container.remove()
            except docker.errors.NotFound:
                # Container already removed, this is fine
                print(f"MCP container {mcp_name} already removed")
            except docker.errors.DockerException as e:
                # Log error but continue cleanup of other containers
                print(f"Error cleaning up {mcp_name}: {e}")

        self.mcp_containers.clear()
        self.mcp_configs.clear()
