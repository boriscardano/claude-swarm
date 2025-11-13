#!/usr/bin/env python3
"""Test specifically for agent-1 to send a message"""

import sys
import os

# Critical setup
sys.path.insert(0, '/Users/boris/work/aspire11/claude-swarm/src')
os.chdir('/Users/boris/work/aspire11/claude-swarm')

print("="*60)
print("AGENT-1 COMMUNICATION TEST")
print("="*60)

try:
    print("\n[1/3] Importing modules...")
    from claudeswarm.messaging import send_message, MessageType
    print("    ✓ Import successful")

    print("\n[2/3] Sending message from agent-1 to agent-0...")
    send_message(
        sender_id="agent-1",
        recipient_id="agent-0",
        message_type=MessageType.INFO,
        content="Hello from agent-1! I can communicate now!"
    )
    print("    ✓ Message sent successfully")

    print("\n[3/3] Verification...")
    print("    ✓ Check agent_messages.log for the message")
    print("    ✓ Check http://localhost:8080 dashboard")

    print("\n" + "="*60)
    print("SUCCESS! Agent-1 message was sent.")
    print("="*60)

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    print("\nFull error details:")
    import traceback
    traceback.print_exc()
    print("\n" + "="*60)
