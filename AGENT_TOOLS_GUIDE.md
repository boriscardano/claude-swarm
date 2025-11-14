# Agent Tools Guide

This guide explains how agents can use Claude Swarm tools for multi-agent coordination.

## Overview

All tools are accessible via the `claudeswarm` CLI command. Agents can call these commands as subprocesses and they will work reliably.

## Available Tools

### 1. Agent Discovery

**List active agents:**
```bash
claudeswarm list-agents
claudeswarm list-agents --json  # JSON output for parsing
```

**Discover all agents:**
```bash
claudeswarm discover-agents
claudeswarm discover-agents --json
```

**Use case:** Before sending messages or coordinating work, discover what agents are active.

### 2. Messaging

**Send a message to a specific agent:**
```bash
claudeswarm send-message <sender-id> <recipient-id> <type> <content>
claudeswarm send-message agent-1 agent-2 INFO "Task completed"
claudeswarm send-message agent-1 agent-2 QUESTION "Need help with API?"
claudeswarm send-message agent-1 agent-2 BLOCKED "Waiting for review" --json
```

**Message types:**
- `INFO` - General information
- `QUESTION` - Ask for help or clarification
- `BLOCKED` - Indicate you're blocked on something
- `REVIEW-REQUEST` - Request code review
- `PROGRESS-UPDATE` - Share progress status
- `ERROR` - Report an error
- `WARNING` - Warn about potential issues

**Broadcast to all agents:**
```bash
claudeswarm broadcast-message <sender-id> <type> <content>
claudeswarm broadcast-message system INFO "Starting new sprint"
claudeswarm broadcast-message agent-1 PROGRESS-UPDATE "50% complete" --verbose
claudeswarm broadcast-message system INFO "All tests passing!" --include-self
```

**Options:**
- `--json` - Get JSON output for programmatic parsing
- `--verbose` - See delivery status for each agent
- `--include-self` - Include sender in broadcast (default: exclude)

### 3. File Locking

**Acquire a lock:**
```bash
claudeswarm acquire-file-lock <filepath> <agent-id> [reason]
claudeswarm acquire-file-lock src/main.py agent-1 "Fixing bug"
```

**Release a lock:**
```bash
claudeswarm release-file-lock <filepath> <agent-id>
claudeswarm release-file-lock src/main.py agent-1
```

**Check who has a lock:**
```bash
claudeswarm who-has-lock <filepath>
claudeswarm who-has-lock src/main.py --json
```

**List all locks:**
```bash
claudeswarm list-all-locks
claudeswarm list-all-locks --include-stale --json
```

**Clean up stale locks:**
```bash
claudeswarm cleanup-stale-locks
```

## Agent Usage Pattern

### From Python Code

```python
import subprocess
import json

def send_message_to_agent(sender_id, recipient_id, msg_type, content):
    """Send a message to another agent."""
    result = subprocess.run(
        [
            "claudeswarm", "send-message",
            sender_id, recipient_id, msg_type, content,
            "--json"
        ],
        capture_output=True,
        text=True,
        timeout=10
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        print(f"Error: {result.stderr}")
        return None

def broadcast_to_all(sender_id, msg_type, content):
    """Broadcast a message to all agents."""
    result = subprocess.run(
        [
            "claudeswarm", "broadcast-message",
            sender_id, msg_type, content,
            "--json"
        ],
        capture_output=True,
        text=True,
        timeout=10
    )

    if result.returncode == 0:
        results = json.loads(result.stdout)
        return results
    else:
        print(f"Error: {result.stderr}")
        return {}

def acquire_file_lock(filepath, agent_id, reason="working"):
    """Acquire a lock on a file."""
    result = subprocess.run(
        [
            "claudeswarm", "acquire-file-lock",
            filepath, agent_id, reason
        ],
        capture_output=True,
        text=True,
        timeout=5
    )

    return result.returncode == 0

def release_file_lock(filepath, agent_id):
    """Release a lock on a file."""
    result = subprocess.run(
        [
            "claudeswarm", "release-file-lock",
            filepath, agent_id
        ],
        capture_output=True,
        text=True,
        timeout=5
    )

    return result.returncode == 0

def list_active_agents():
    """Get list of active agents."""
    result = subprocess.run(
        ["claudeswarm", "list-agents", "--json"],
        capture_output=True,
        text=True,
        timeout=5
    )

    if result.returncode == 0:
        return json.loads(result.stdout)
    else:
        return []
```

### From Bash

```bash
#!/bin/bash

# Get my agent ID
AGENT_ID="agent-$(tmux display-message -p '#{pane_id}')"

# Discover other agents
claudeswarm list-agents

# Send a question to another agent
claudeswarm send-message "$AGENT_ID" "agent-2" QUESTION "Can you review my code?"

# Broadcast progress
claudeswarm broadcast-message "$AGENT_ID" PROGRESS-UPDATE "Completed testing phase"

# Acquire lock before editing
claudeswarm acquire-file-lock "src/main.py" "$AGENT_ID" "Implementing feature X"

# ... do work ...

# Release lock after editing
claudeswarm release-file-lock "src/main.py" "$AGENT_ID"
```

## Best Practices

### 1. Always Check Exit Codes

Commands return 0 on success, non-zero on failure:

```python
result = subprocess.run(["claudeswarm", "send-message", ...])
if result.returncode != 0:
    # Handle error
    print(f"Failed: {result.stderr}")
```

### 2. Use JSON Output for Parsing

When you need to process the output programmatically:

```python
result = subprocess.run(
    ["claudeswarm", "list-agents", "--json"],
    capture_output=True,
    text=True
)
agents = json.loads(result.stdout)
```

### 3. Always Acquire Locks Before Editing

```python
# CORRECT:
if acquire_file_lock("src/main.py", "agent-1", "fixing bug"):
    # Edit file
    edit_file("src/main.py")
    # Release lock
    release_file_lock("src/main.py", "agent-1")
else:
    send_message("agent-1", "system", "BLOCKED", "Can't acquire lock on main.py")
```

### 4. Handle Timeouts

All subprocess calls should have timeouts:

```python
result = subprocess.run(
    ["claudeswarm", "send-message", ...],
    timeout=10  # Don't hang forever
)
```

### 5. Broadcast Important Updates

Keep other agents informed:

```python
# Starting work
broadcast_to_all("agent-1", "INFO", "Starting work on feature X")

# Progress updates
broadcast_to_all("agent-1", "PROGRESS-UPDATE", "50% complete")

# Completion
broadcast_to_all("agent-1", "INFO", "Feature X completed and tested")
```

### 6. Use Appropriate Message Types

- **INFO**: General updates, completions
- **QUESTION**: When you need help
- **BLOCKED**: When you can't proceed
- **REVIEW-REQUEST**: When code is ready for review
- **PROGRESS-UPDATE**: Regular status updates
- **ERROR**: When something went wrong
- **WARNING**: Potential issues

## Error Handling

All commands handle errors gracefully and won't crash. They return:

- **Exit code 0**: Success
- **Exit code 1**: Failure (check stderr for details)
- **stderr**: Human-readable error messages

```python
result = subprocess.run(
    ["claudeswarm", "send-message", "agent-1", "agent-2", "INFO", "Hello"],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    error_message = result.stderr
    # Log or handle error
    print(f"Command failed: {error_message}")
```

## Testing Your Integration

Use the test commands to verify your integration works:

```bash
# Test sending a message
claudeswarm send-message test-sender test-recipient INFO "Test message"

# Test broadcasting
claudeswarm broadcast-message test-sender INFO "Test broadcast"

# Test file locking
claudeswarm acquire-file-lock test.txt test-agent "testing"
claudeswarm release-file-lock test.txt test-agent
```

## Common Patterns

### Pattern 1: Task Distribution

```python
# Agent 1: Distribute tasks
agents = list_active_agents()
for i, agent in enumerate(agents):
    task = f"Process file{i}.txt"
    send_message_to_agent("coordinator", agent['id'], "INFO", f"Task assigned: {task}")
```

### Pattern 2: Collaborative Editing

```python
# Agent requesting to edit
if acquire_file_lock("src/main.py", "agent-2", "adding feature"):
    # Edit file
    edit_code("src/main.py")

    # Notify others
    broadcast_to_all("agent-2", "INFO", "Updated main.py with new feature")

    # Release lock
    release_file_lock("src/main.py", "agent-2")
else:
    # Can't get lock, ask for help
    send_message_to_agent("agent-2", "agent-1", "QUESTION", "Can you release lock on main.py?")
```

### Pattern 3: Progress Monitoring

```python
# Long-running task with progress updates
total_steps = 10
for i in range(total_steps):
    # Do work
    process_step(i)

    # Update progress
    progress = f"{(i+1)/total_steps * 100:.0f}% complete"
    broadcast_to_all("agent-3", "PROGRESS-UPDATE", progress)
```

## Troubleshooting

### Problem: Commands not found

**Solution:** Ensure claudeswarm is installed:
```bash
which claudeswarm
# Should show: /Users/<user>/.local/bin/claudeswarm
```

### Problem: Permission denied errors

**Solution:** Run commands from within tmux panes, not from external scripts.

### Problem: No agents discovered

**Solution:** Make sure you're in the same project directory and tmux session:
```bash
pwd  # Check you're in the right directory
claudeswarm discover-agents  # Discover agents
```

### Problem: Message not delivered

**Solution:** Check if recipient agent exists:
```bash
claudeswarm list-agents  # See all active agents
```

## Summary

All tools are designed to be:
- ✅ Reliable when called as subprocesses
- ✅ Safe with proper error handling
- ✅ Easy to use with clear interfaces
- ✅ Well-tested for agent usage

Use these tools to build powerful multi-agent coordination systems!
