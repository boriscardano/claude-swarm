# Agent Coordination Instructions

You are part of a multi-agent coordination system. Here's how to communicate with other agents:

## Quick Start

Import the helper module in your Python code:

```python
from agent_helper import send_to_agent, broadcast_to_all, lock_file, unlock_file, get_other_agents
```

## Send Messages

```python
# Send a question to another agent
send_to_agent("agent-0", "agent-1", "Can you review the auth module?", "QUESTION")

# Send info to another agent
send_to_agent("agent-0", "agent-1", "I've completed the database migration", "INFO")

# Report being blocked
send_to_agent("agent-1", "agent-0", "Blocked on API key setup", "BLOCKED")

# Acknowledge a message
send_to_agent("agent-1", "agent-0", "Got it, reviewing now", "ACK")

# Broadcast to everyone
broadcast_to_all("agent-0", "Sprint planning: focus on authentication", "INFO")
```

## File Locking (Prevent Conflicts)

Always lock files before editing:

```python
# Lock before editing
if lock_file("src/auth.py", "agent-0", "Adding OAuth support"):
    # Edit the file here
    print("Working on auth.py...")

    # Release when done
    unlock_file("src/auth.py", "agent-0")
else:
    print("File is locked by another agent - waiting...")
```

## Check Other Agents

```python
# See who else is active
other_agents = get_other_agents()
print(f"Active agents: {other_agents}")
```

## Message Types

- `INFO` - General information
- `QUESTION` - Asking for help/clarification
- `BLOCKED` - You're blocked and need assistance
- `ACK` - Acknowledging a message
- `REVIEW_REQUEST` - Requesting code review

## Your Agent ID

Check the ACTIVE_AGENTS.json file or use:

```bash
cat ACTIVE_AGENTS.json | grep -A 3 '"pane_index": "YOUR_PANE"'
```

## View Messages

Check the message log:

```bash
tail -f agent_messages.log
```

Or view the dashboard at: **http://localhost:8080**

## Example Workflow

```python
from agent_helper import *

# 1. Announce what you're working on
broadcast_to_all("agent-0", "Starting work on user authentication", "INFO")

# 2. Lock the file
if lock_file("src/auth.py", "agent-0", "Implementing OAuth"):
    # 3. Do your work
    print("Working on authentication...")

    # 4. Ask for review
    send_to_agent("agent-0", "agent-1", "Please review auth.py changes", "REVIEW_REQUEST")

    # 5. Release lock
    unlock_file("src/auth.py", "agent-0")
```

---

**Ready to coordinate!** Import `agent_helper` and start communicating.
