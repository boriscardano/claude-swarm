#!/usr/bin/env python3
"""Kickoff coordination for podcasts-chatbot project"""

import sys
import os

# Setup paths
sys.path.insert(0, '/Users/boris/work/aspire11/claude-swarm/src')
os.chdir('/Users/boris/work/aspire11/podcasts-chatbot')

from claudeswarm.messaging import send_message, broadcast_message, MessageType

print("🚀 Kicking off coordination for podcasts-chatbot project...\n")

# System broadcasts to both agents
print("1. Broadcasting coordination activation...")
broadcast_message(
    sender_id="system",
    message_type=MessageType.INFO,
    content="🤝 MULTI-AGENT COORDINATION ACTIVE for podcasts-chatbot! You can now communicate."
)

print("2. Introducing agents to each other...")
send_message(
    sender_id="system",
    recipient_id="agent-0",
    message_type=MessageType.INFO,
    content="👋 Agent-1 is also working on podcasts-chatbot. Coordinate using: python3 /Users/boris/work/aspire11/claude-swarm/podcast_coord.py"
)

send_message(
    sender_id="system",
    recipient_id="agent-1",
    message_type=MessageType.INFO,
    content="👋 Agent-0 is also working on podcasts-chatbot. Coordinate using: python3 /Users/boris/work/aspire11/claude-swarm/podcast_coord.py"
)

print("3. Sending coordination instructions...")
broadcast_message(
    sender_id="system",
    message_type=MessageType.INFO,
    content="📋 Instructions: See PODCAST_AGENT0.txt and PODCAST_AGENT1.txt in claude-swarm directory"
)

print("\n✅ Coordination kickoff complete!")
print("\nNext: Tell each agent to check their messages and start coordinating!")
print("Dashboard: http://localhost:8080")
