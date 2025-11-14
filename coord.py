#!/usr/bin/env python3
"""
Universal coordination helper - works with any project!

Usage:
  python3 coord.py <agent-id> send <recipient> <message>
  python3 coord.py <agent-id> read
  python3 coord.py <agent-id> lock <filepath> <reason>
  python3 coord.py <agent-id> unlock <filepath>
"""

import sys
import os
import json

# Add claudeswarm to path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'src'))

# Use current directory as project root (where the agent is working)
PROJECT_ROOT = os.getcwd()

from claudeswarm.messaging import send_message, MessageType
from claudeswarm.locking import LockManager

def read_messages(agent_id, last_n=15):
    """Read messages for an agent from current project"""
    messages = []
    log_file = os.path.join(PROJECT_ROOT, 'agent_messages.log')

    try:
        with open(log_file, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except:
                    continue
    except FileNotFoundError:
        return []

    # Filter by recipient
    messages = [m for m in messages if agent_id in m.get('recipients', [])]
    return messages[-last_n:]

def show_messages(agent_id):
    """Display messages for agent"""
    print(f"\n📬 Messages for {agent_id}:")
    print(f"Project: {PROJECT_ROOT}")
    print("="*70)

    messages = read_messages(agent_id)

    if not messages:
        print("No messages yet")
    else:
        for msg in messages:
            sender = msg['sender']
            content = msg['content']
            msg_type = msg['msg_type']
            time = msg['timestamp'][11:19]

            emoji = "📢" if sender == "system" else "💬"
            print(f"{emoji} [{time}] {sender:10} ({msg_type:12}): {content[:60]}")

    print("="*70)

def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Send:   python3 coord.py <your-id> send <recipient> <message>")
        print("  Read:   python3 coord.py <your-id> read")
        print("  Lock:   python3 coord.py <your-id> lock <filepath> <reason>")
        print("  Unlock: python3 coord.py <your-id> unlock <filepath>")
        print(f"\nCurrent project: {PROJECT_ROOT}")
        return

    agent_id = sys.argv[1]
    command = sys.argv[2]

    if command == "send":
        if len(sys.argv) < 5:
            print("Usage: python3 coord.py <your-id> send <recipient> <message>")
            return
        recipient = sys.argv[3]
        message = " ".join(sys.argv[4:])

        send_message(agent_id, recipient, MessageType.INFO, message)
        print(f"✓ Message sent from {agent_id} to {recipient}")

    elif command == "read":
        show_messages(agent_id)

    elif command == "lock":
        if len(sys.argv) < 5:
            print("Usage: python3 coord.py <your-id> lock <filepath> <reason>")
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
            print("Usage: python3 coord.py <your-id> unlock <filepath>")
            return
        filepath = sys.argv[3]

        lm = LockManager()
        lm.release_lock(filepath, agent_id)
        print(f"✓ Lock released on {filepath}")

    else:
        print(f"Unknown command: {command}")

if __name__ == "__main__":
    main()
