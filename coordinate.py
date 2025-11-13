#!/usr/bin/env python3
"""
Simple coordination helper for agents.
Usage:
  python3 coordinate.py agent-0 send agent-1 "Your message here"
  python3 coordinate.py agent-0 read
  python3 coordinate.py agent-0 lock path/to/file "reason"
  python3 coordinate.py agent-0 unlock path/to/file
"""

import sys
import os

# Setup
sys.path.insert(0, '/Users/boris/work/aspire11/claude-swarm/src')
os.chdir('/Users/boris/work/aspire11/claude-swarm')

from claudeswarm.messaging import send_message, MessageType
from claudeswarm.locking import LockManager
from read_messages import show_my_messages

def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Send message:  python3 coordinate.py <your-id> send <recipient-id> <message>")
        print("  Read messages: python3 coordinate.py <your-id> read")
        print("  Lock file:     python3 coordinate.py <your-id> lock <filepath> <reason>")
        print("  Unlock file:   python3 coordinate.py <your-id> unlock <filepath>")
        return

    agent_id = sys.argv[1]
    command = sys.argv[2]

    if command == "send":
        if len(sys.argv) < 5:
            print("Usage: python3 coordinate.py <your-id> send <recipient-id> <message>")
            return
        recipient = sys.argv[3]
        message = " ".join(sys.argv[4:])

        send_message(agent_id, recipient, MessageType.INFO, message)
        print(f"✓ Message sent from {agent_id} to {recipient}")

    elif command == "read":
        show_my_messages(agent_id)

    elif command == "lock":
        if len(sys.argv) < 5:
            print("Usage: python3 coordinate.py <your-id> lock <filepath> <reason>")
            return
        filepath = sys.argv[3]
        reason = " ".join(sys.argv[4:])

        lm = LockManager()
        success, conflict = lm.acquire_lock(filepath, agent_id, reason)

        if success:
            print(f"✓ Lock acquired on {filepath}")
        else:
            print(f"✗ Lock failed: {filepath} is held by {conflict.current_holder}")

    elif command == "unlock":
        if len(sys.argv) < 4:
            print("Usage: python3 coordinate.py <your-id> unlock <filepath>")
            return
        filepath = sys.argv[3]

        lm = LockManager()
        lm.release_lock(filepath, agent_id)
        print(f"✓ Lock released on {filepath}")

    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
