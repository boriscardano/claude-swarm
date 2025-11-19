"""
Claude Swarm Cloud - E2B Integration Module

This module provides cloud-native capabilities for Claude Swarm,
enabling multi-agent coordination in E2B sandboxes.
"""

from claudeswarm.cloud.e2b_launcher import CloudSandbox
from claudeswarm.cloud.mcp_bridge import MCPBridge
from claudeswarm.cloud.mcp_config import (
    attach_exa_mcp,
    attach_filesystem_mcp,
    attach_github_mcp,
    attach_multiple_mcps,
    attach_perplexity_mcp,
    parse_mcp_list,
)
from claudeswarm.cloud.types import MCPConfig, MCPContainerInfo, MCPError, MCPResponse

__all__ = [
    # Core classes
    "CloudSandbox",
    "MCPBridge",
    # MCP attachment functions
    "attach_github_mcp",
    "attach_filesystem_mcp",
    "attach_exa_mcp",
    "attach_perplexity_mcp",
    "attach_multiple_mcps",
    "parse_mcp_list",
    # Types
    "MCPConfig",
    "MCPContainerInfo",
    "MCPError",
    "MCPResponse",
]
