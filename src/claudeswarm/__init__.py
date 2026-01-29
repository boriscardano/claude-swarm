"""Claude Swarm - Multi-agent coordination system for Claude Code instances.

This package provides a tmux-based coordination system that enables multiple Claude Code
agents to work together on shared projects through:
- Agent discovery and registry management
- Inter-agent messaging via tmux send-keys
- Distributed file locking to prevent conflicts
- Message acknowledgment and retry system
- Real-time monitoring and visibility
- Shared coordination file management
- Centralized configuration management

New A2A Protocol-inspired features:
- Agent Cards for capability discovery
- Task lifecycle management
- Skill-based task delegation
- Capability learning over time
- Autonomous conflict resolution
- Shared context preservation
- Agent memory system
"""

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # Core modules
    "discovery",
    "messaging",
    "locking",
    "ack",
    "monitoring",
    "coordination",
    "cli",
    "utils",
    "config",
    "logging_config",
    # A2A-inspired modules
    "agent_cards",
    "tasks",
    "delegation",
    "learning",
    "conflict_resolution",
    "context",
    "memory",
]
