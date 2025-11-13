#!/usr/bin/env python3
"""Test script to make agents communicate"""

from claudeswarm.messaging import send_message, broadcast_message, MessageType
import time

# Agent 0 sends a question to Agent 1
print("Agent 0 asking Agent 1 a question...")
send_message(
    sender_id="agent-0",
    recipient_id="agent-1",
    message_type=MessageType.QUESTION,
    content="Hey agent-1, can you review the auth module when you get a chance?"
)

time.sleep(1)

# Agent 1 responds
print("Agent 1 responding...")
send_message(
    sender_id="agent-1",
    recipient_id="agent-0",
    message_type=MessageType.ACK,
    content="Sure! I'll take a look at the auth module now."
)

time.sleep(1)

# Agent 0 broadcasts to everyone
print("Agent 0 broadcasting to all agents...")
broadcast_message(
    sender_id="agent-0",
    message_type=MessageType.INFO,
    content="Sprint planning meeting at 3pm - check COORDINATION.md for details"
)

time.sleep(1)

# Agent 1 reports being blocked
print("Agent 1 reporting a blocker...")
send_message(
    sender_id="agent-1",
    recipient_id="agent-0",
    message_type=MessageType.BLOCKED,
    content="I'm blocked on the database schema - need clarification on the user table"
)

print("\n✓ Messages sent! Check the dashboard at http://localhost:8080 to see them!")
print("✓ Also check agent_messages.log for the message history")
