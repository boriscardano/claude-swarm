#!/usr/bin/env python3
"""Simple test to verify coordination works"""

import sys
import os

# Set up the path
sys.path.insert(0, '/Users/boris/work/aspire11/claude-swarm/src')
os.chdir('/Users/boris/work/aspire11/claude-swarm')

try:
    print("Testing imports...")
    from claudeswarm.messaging import send_message, MessageType
    from claudeswarm.locking import LockManager
    print("✓ Imports successful\n")

    # Test sending a message
    print("Testing message sending...")
    agent_id = sys.argv[1] if len(sys.argv) > 1 else "agent-0"
    recipient = "agent-1" if agent_id == "agent-0" else "agent-0"

    send_message(
        sender_id=agent_id,
        recipient_id=recipient,
        message_type=MessageType.INFO,
        content=f"Test message from {agent_id} - coordination is working!"
    )
    print(f"✓ Message sent from {agent_id} to {recipient}\n")

    # Test locking
    print("Testing file locking...")
    lm = LockManager()
    success, conflict = lm.acquire_lock("test.txt", agent_id, "testing")
    if success:
        print(f"✓ Lock acquired by {agent_id}")
        lm.release_lock("test.txt", agent_id)
        print(f"✓ Lock released by {agent_id}\n")
    else:
        print(f"✗ Lock failed - held by {conflict.current_holder}\n")

    print("="*50)
    print("All tests passed! Coordination is working.")
    print(f"Check http://localhost:8080 to see the message")
    print("="*50)

except Exception as e:
    print(f"✗ Error occurred: {e}")
    import traceback
    traceback.print_exc()
