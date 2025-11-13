#!/usr/bin/env python3
"""Kickoff coordination between agents"""

import sys
sys.path.insert(0, '/Users/boris/work/aspire11/claude-swarm/src')

from claudeswarm.messaging import send_message, broadcast_message, MessageType

print("🚀 Kicking off multi-agent coordination...\n")

# System broadcasts to both agents
print("1. Broadcasting coordination activation...")
broadcast_message(
    sender_id="system",
    message_type=MessageType.INFO,
    content="🤝 MULTI-AGENT COORDINATION NOW ACTIVE! You can now communicate with other agents."
)

print("2. Introducing agents to each other...")
send_message(
    sender_id="system",
    recipient_id="agent-0",
    message_type=MessageType.INFO,
    content="👋 Another agent (agent-1) is working in this codebase. You can coordinate using the Python API in agent_helper.py. Check AGENT_INSTRUCTIONS.md for details."
)

send_message(
    sender_id="system",
    recipient_id="agent-1",
    message_type=MessageType.INFO,
    content="👋 Another agent (agent-0) is working in this codebase. You can coordinate using the Python API in agent_helper.py. Check AGENT_INSTRUCTIONS.md for details."
)

print("3. Suggesting coordination pattern...")
broadcast_message(
    sender_id="system",
    message_type=MessageType.INFO,
    content="💡 COORDINATION TIP: Before editing any file, acquire a lock using lock_file(). Share your progress with other agents. Ask questions when blocked!"
)

print("\n✅ Coordination kickoff complete!")
print("\nNext steps:")
print("  1. Go to each tmux pane (agent-0 in 0:1.1, agent-1 in 0:1.2)")
print("  2. Tell each agent to check agent_messages.log for system messages")
print("  3. Tell them to import agent_helper to start coordinating")
print("  4. Watch http://localhost:8080 for live coordination activity!")
