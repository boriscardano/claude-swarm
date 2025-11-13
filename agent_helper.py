#!/usr/bin/env python3
"""
Helper functions for Claude Code agents to coordinate with each other.
Import this in your agent code to send messages and manage locks.
"""

import sys
sys.path.insert(0, '/Users/boris/work/aspire11/claude-swarm/src')

from claudeswarm.messaging import send_message, broadcast_message, MessageType
from claudeswarm.locking import LockManager
from claudeswarm.discovery import list_active_agents

# Initialize lock manager
lock_manager = LockManager()

def send_to_agent(my_id: str, recipient_id: str, message: str, msg_type: str = "INFO"):
    """
    Send a message to another agent.

    Args:
        my_id: Your agent ID (e.g., "agent-0")
        recipient_id: Target agent ID (e.g., "agent-1")
        message: The message content
        msg_type: Type of message (INFO, QUESTION, BLOCKED, ACK, REVIEW-REQUEST)
    """
    msg_type_enum = MessageType[msg_type.upper().replace("-", "_")]
    send_message(my_id, recipient_id, msg_type_enum, message)
    print(f"✓ Sent {msg_type} to {recipient_id}")

def broadcast_to_all(my_id: str, message: str, msg_type: str = "INFO"):
    """
    Broadcast a message to all agents.

    Args:
        my_id: Your agent ID (e.g., "agent-0")
        message: The message content
        msg_type: Type of message (INFO, QUESTION, BLOCKED, etc.)
    """
    msg_type_enum = MessageType[msg_type.upper().replace("-", "_")]
    broadcast_message(my_id, msg_type_enum, message)
    print(f"✓ Broadcast {msg_type} to all agents")

def lock_file(filepath: str, my_id: str, reason: str = "working"):
    """
    Acquire a lock on a file.

    Args:
        filepath: Path to the file
        my_id: Your agent ID
        reason: Reason for locking

    Returns:
        True if lock acquired, False otherwise
    """
    success, conflict = lock_manager.acquire_lock(filepath, my_id, reason)
    if success:
        print(f"✓ Lock acquired on {filepath}")
        return True
    else:
        print(f"✗ Lock failed: {filepath} is locked by {conflict.current_holder}")
        return False

def unlock_file(filepath: str, my_id: str):
    """
    Release a lock on a file.

    Args:
        filepath: Path to the file
        my_id: Your agent ID
    """
    lock_manager.release_lock(filepath, my_id)
    print(f"✓ Lock released on {filepath}")

def get_other_agents():
    """Get list of other active agents."""
    agents = list_active_agents()
    return [agent.id for agent in agents]

# Example usage (commented out):
"""
# Send a question to agent-1
send_to_agent("agent-0", "agent-1", "Can you review auth.py?", "QUESTION")

# Broadcast to everyone
broadcast_to_all("agent-0", "Sprint planning in progress", "INFO")

# Lock a file before editing
if lock_file("src/auth.py", "agent-0", "Implementing OAuth"):
    # Do your work here
    print("Working on auth.py...")
    # Release when done
    unlock_file("src/auth.py", "agent-0")

# See who else is active
print("Other agents:", get_other_agents())
"""
