#!/usr/bin/env python3
"""
Onboard all discovered agents - introduce them and teach them to coordinate
"""

import sys
import os
import json

if len(sys.argv) < 2:
    print("Usage: python3 onboard_agents.py /path/to/project")
    sys.exit(1)

PROJECT_DIR = os.path.abspath(sys.argv[1])
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Validate project directory exists
if not os.path.isdir(PROJECT_DIR):
    print(f"Error: Project directory does not exist: {PROJECT_DIR}")
    sys.exit(1)

# Setup paths
sys.path.insert(0, os.path.join(SCRIPT_DIR, 'src'))

# Import first, then change directory
from claudeswarm.messaging import send_message, broadcast_message, MessageType
from claudeswarm.discovery import list_active_agents

# Change to project directory so discovery can find ACTIVE_AGENTS.json
os.chdir(PROJECT_DIR)

print(f"Looking for agents in: {os.getcwd()}")
registry_file = 'ACTIVE_AGENTS.json'
print(f"ACTIVE_AGENTS.json exists: {os.path.exists(registry_file)}")

# Get all active agents
try:
    agents = list_active_agents()
    agent_ids = [agent.id for agent in agents]
except Exception as e:
    print(f"Error listing agents: {e}")
    sys.exit(1)

if not agent_ids:
    print("No agents found!")
    print(f"Registry file location: {os.path.join(PROJECT_DIR, registry_file)}")
    if not os.path.exists(registry_file):
        print("Registry file does not exist. Make sure you ran discovery first.")
    sys.exit(1)

print(f"Onboarding {len(agent_ids)} agents: {', '.join(agent_ids)}")
print()

# 1. Broadcast activation
print("Broadcasting activation message...")
try:
    broadcast_message(
        sender_id="system",
        message_type=MessageType.INFO,
        content=f"🤝 MULTI-AGENT COORDINATION ACTIVE! {len(agent_ids)} agents discovered in this project."
    )
except Exception as e:
    print(f"Warning: Failed to broadcast activation message: {e}")

# 2. Send individual introductions to each agent
print("Sending individual introductions...")
failed_agents = []
for agent_id in agent_ids:
    other_agents = [a for a in agent_ids if a != agent_id]

    intro_msg = f"""👋 You are {agent_id}. Other agents working here: {', '.join(other_agents)}

COORDINATION COMMANDS (run these from your terminal):

📬 Read your messages:
python3 coord.py {agent_id} read

💬 Send message to another agent:
python3 coord.py {agent_id} send <other-agent-id> "your message"

🔒 Lock file BEFORE editing:
python3 coord.py {agent_id} lock path/to/file "what you're doing"

🔓 Unlock file AFTER editing:
python3 coord.py {agent_id} unlock path/to/file

📊 Dashboard: http://localhost:8080

Now start coordinating! Share what you're working on, lock files before editing, and communicate!"""

    try:
        send_message(
            sender_id="system",
            recipient_id=agent_id,
            message_type=MessageType.INFO,
            content=intro_msg
        )
        print(f"  ✓ {agent_id} onboarded")
    except Exception as e:
        print(f"  ✗ {agent_id} failed: {e}")
        failed_agents.append(agent_id)

# 3. Send coordination tips
print("Broadcasting coordination tips...")
try:
    broadcast_message(
        sender_id="system",
        message_type=MessageType.INFO,
        content="💡 TIP: Always lock files before editing! Check your messages with: python3 coord.py YOUR_ID read"
    )
except Exception as e:
    print(f"Warning: Failed to broadcast coordination tips: {e}")

print()
if failed_agents:
    print(f"⚠️  Warning: {len(failed_agents)} agent(s) failed to receive introduction: {', '.join(failed_agents)}")
    print()
print("✅ All agents have been introduced and know how to coordinate!")
print("They can now use the coord.py commands to communicate and coordinate file access.")
