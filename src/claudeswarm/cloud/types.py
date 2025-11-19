"""
Type definitions for MCP integration.

Provides standardized data structures for MCP server communication,
ensuring type safety and consistent error handling across all MCP implementations.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MCPStatus(str, Enum):
    """MCP server connection status."""

    INITIALIZING = "initializing"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class MCPType(str, Enum):
    """Supported MCP server types."""

    GITHUB = "github"
    FILESYSTEM = "filesystem"
    EXA = "exa"
    PERPLEXITY = "perplexity"


@dataclass
class MCPConfig:
    """
    Configuration for an MCP server.

    Attributes:
        mcp_type: Type of MCP server (github, exa, etc.)
        container_image: Docker image to use for this MCP
        environment: Environment variables for the container
        port: Port the MCP server listens on (default: 3000)
        network_mode: Docker network mode (default: bridge)
        timeout: Request timeout in seconds (default: 30)
        max_retries: Maximum number of retry attempts (default: 3)
        rate_limit: Maximum requests per minute (default: 60)
    """

    mcp_type: MCPType
    container_image: str
    environment: dict[str, str] = field(default_factory=dict)
    port: int = 3000
    network_mode: str = "bridge"
    timeout: float = 30.0
    max_retries: int = 3
    rate_limit: int = 60  # requests per minute


@dataclass
class MCPResponse:
    """
    Standardized response from an MCP server.

    Attributes:
        success: Whether the request was successful
        data: Response data from the MCP server
        error: Error information if request failed
        mcp_name: Name of the MCP that generated this response
        method: Method that was called
        duration_ms: Time taken to process the request in milliseconds
    """

    success: bool
    data: Any = None
    error: Optional[str] = None
    mcp_name: str = ""
    method: str = ""
    duration_ms: float = 0.0

    def __post_init__(self) -> None:
        """Validate response state."""
        if not self.success and self.error is None:
            raise ValueError("Failed responses must include an error message")


@dataclass
class MCPError(Exception):
    """
    Exception raised when MCP operations fail.

    Attributes:
        message: Human-readable error message
        mcp_name: Name of the MCP that encountered the error
        method: Method that was being called
        original_error: Original exception if available
        retry_count: Number of retries attempted
    """

    message: str
    mcp_name: str = ""
    method: str = ""
    original_error: Optional[Exception] = None
    retry_count: int = 0

    def __str__(self) -> str:
        """Return formatted error message."""
        parts = [f"MCP Error: {self.message}"]
        if self.mcp_name:
            parts.append(f"MCP: {self.mcp_name}")
        if self.method:
            parts.append(f"Method: {self.method}")
        if self.retry_count > 0:
            parts.append(f"Retries: {self.retry_count}")
        if self.original_error:
            parts.append(f"Cause: {str(self.original_error)}")
        return " | ".join(parts)


@dataclass
class MCPContainerInfo:
    """
    Information about a running MCP container.

    Attributes:
        container_id: Docker container ID
        mcp_type: Type of MCP server
        ip_address: Container IP address
        port: Port the MCP is listening on
        status: Current connection status
        endpoint_url: Full URL to reach the MCP server
        started_at: Container start timestamp
    """

    container_id: str
    mcp_type: MCPType
    ip_address: str
    port: int
    status: MCPStatus
    endpoint_url: str
    started_at: str = ""

    @property
    def is_healthy(self) -> bool:
        """Check if container is in a healthy state."""
        return self.status == MCPStatus.CONNECTED
