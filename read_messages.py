#!/usr/bin/env python3
"""Helper to read messages from the log file"""

import json
import sys

def read_messages(agent_id=None, last_n=10):
    """
    Read messages from agent_messages.log

    Args:
        agent_id: Filter by recipient (e.g., "agent-0" to see messages TO agent-0)
        last_n: Number of recent messages to show

    Returns:
        List of message dictionaries
    """
    messages = []

    try:
        with open('/Users/boris/work/aspire11/claude-swarm/agent_messages.log', 'r') as f:
            # Read each line as a separate JSON object
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        print("No messages yet")
        return []

    # Filter by recipient if specified
    if agent_id:
        messages = [m for m in messages if agent_id in m.get('recipients', [])]

    # Return last N messages
    return messages[-last_n:] if last_n else messages


def show_my_messages(agent_id):
    """Show messages addressed to this agent"""
    print(f"\n📬 Messages for {agent_id}:")
    print("="*70)

    messages = read_messages(agent_id=agent_id, last_n=20)

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


if __name__ == "__main__":
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "agent-0"
    show_my_messages(agent_id)
