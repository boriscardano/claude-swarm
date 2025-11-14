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
- `INFO` - General information and status updates
- `QUESTION` - Ask for help or clarification
- `BLOCKED` - Indicate you're blocked on something
- `REVIEW_REQUEST` - Request code review (note: value is "REVIEW-REQUEST")
- `COMPLETED` - Signal task completion
- `CHALLENGE` - Challenge another agent's approach or decision
- `ACK` - Acknowledge receipt of a message

**Broadcast to all agents:**
```bash
claudeswarm broadcast-message <sender-id> <type> <content>
claudeswarm broadcast-message system INFO "Starting new sprint"
claudeswarm broadcast-message agent-1 INFO "50% complete" --verbose
claudeswarm broadcast-message system INFO "All tests passing!" --include-self
```

**Options:**
- `--json` - Get JSON output for programmatic parsing
- `--verbose` - See delivery status for each agent
- `--include-self` - Include sender in broadcast (default: exclude)

**Rate Limiting:**
- Messages are rate-limited to **10 messages per minute per agent** (configurable)
- Broadcasts count as one message regardless of recipient count
- If rate limit is exceeded, the command will fail with exit code 1
- Wait 60 seconds before retrying if rate-limited

### 3. File Locking

**Acquire a lock:**
```bash
claudeswarm acquire-file-lock <filepath> <agent-id> [reason]
# Example with project file (replace with actual file path)
claudeswarm acquire-file-lock /path/to/project/src/main.py agent-1 "Fixing bug"
```

**Release a lock:**
```bash
claudeswarm release-file-lock <filepath> <agent-id>
# Example with project file
claudeswarm release-file-lock /path/to/project/src/main.py agent-1
```

**Check who has a lock:**
```bash
claudeswarm who-has-lock <filepath>
# Example with project file
claudeswarm who-has-lock /path/to/project/src/main.py --json
```

**Note:** File paths should be absolute paths or relative to the project root. The examples above use placeholder paths - replace with actual files from your project.

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
claudeswarm broadcast-message "$AGENT_ID" INFO "Completed testing phase"

# Acquire lock before editing (use actual project file path)
claudeswarm acquire-file-lock "/absolute/path/to/src/main.py" "$AGENT_ID" "Implementing feature X"

# ... do work ...

# Release lock after editing
claudeswarm release-file-lock "/absolute/path/to/src/main.py" "$AGENT_ID"
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
filepath = "/absolute/path/to/src/main.py"
if acquire_file_lock(filepath, "agent-1", "fixing bug"):
    # Edit file
    edit_file(filepath)
    # Release lock
    release_file_lock(filepath, "agent-1")
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

# Progress updates (use INFO for progress)
broadcast_to_all("agent-1", "INFO", "Feature X: 50% complete")

# Completion (use COMPLETED for task completion)
broadcast_to_all("agent-1", "COMPLETED", "Feature X completed and tested")
```

### 6. Use Appropriate Message Types

Choose the right message type for the situation:

- **INFO**: General updates, status information, or notifications
- **QUESTION**: When you need help, clarification, or input from another agent
- **BLOCKED**: When you can't proceed and need intervention
- **REVIEW_REQUEST**: When code is ready for review (note: the actual value sent is "REVIEW-REQUEST")
- **COMPLETED**: Signal successful task completion
- **CHALLENGE**: Challenge another agent's approach or propose alternative
- **ACK**: Acknowledge receipt of a message

**When to use each type:**
- Use `INFO` for progress updates and general communication
- Use `QUESTION` when you expect a response
- Use `BLOCKED` to escalate issues that prevent progress
- Use `COMPLETED` to signal task completion (not INFO)
- Use `ACK` to confirm you received and understood a message

## Error Handling

All commands handle errors gracefully and won't crash. They return:

- **Exit code 0**: Success
- **Exit code 1**: Failure (check stderr for details)
- **stderr**: Human-readable error messages

### Common Error Scenarios

#### 1. Rate Limit Exceeded
```python
result = subprocess.run(
    ["claudeswarm", "send-message", "agent-1", "agent-2", "INFO", "Hello"],
    capture_output=True,
    text=True
)

if result.returncode != 0:
    if "rate limit" in result.stderr.lower():
        # Wait and retry
        import time
        time.sleep(60)
        # Retry the message
```

#### 2. Recipient Does Not Exist
```python
# Always discover agents before sending messages
agents = list_active_agents()
agent_ids = [agent['id'] for agent in agents]

if recipient_id in agent_ids:
    send_message_to_agent(sender_id, recipient_id, "INFO", "Hello")
else:
    print(f"Agent {recipient_id} not found")
```

#### 3. Message Too Long
```python
# Messages are limited to 10KB (10,240 bytes)
MAX_MESSAGE_LENGTH = 10 * 1024

def send_safe_message(sender_id, recipient_id, msg_type, content):
    if len(content.encode('utf-8')) > MAX_MESSAGE_LENGTH:
        # Truncate or split message
        content = content[:MAX_MESSAGE_LENGTH - 100] + "... (truncated)"

    return send_message_to_agent(sender_id, recipient_id, msg_type, content)
```

#### 4. Tmux Socket Permission Issues
```bash
# Ensure you're running commands from within a tmux pane
# Check tmux is available:
if ! command -v tmux &> /dev/null; then
    echo "Error: tmux not installed"
    exit 1
fi

# Check you're in a tmux session:
if [ -z "$TMUX" ]; then
    echo "Error: Not in a tmux session"
    exit 1
fi
```

### General Error Handling Pattern

```python
def safe_send_message(sender_id, recipient_id, msg_type, content):
    """Send message with comprehensive error handling."""
    try:
        result = subprocess.run(
            ["claudeswarm", "send-message", sender_id, recipient_id, msg_type, content, "--json"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            error = result.stderr.strip()

            # Handle specific errors
            if "rate limit" in error.lower():
                return {"error": "rate_limit", "message": "Too many messages, wait 60s"}
            elif "not found" in error.lower():
                return {"error": "not_found", "message": f"Agent {recipient_id} not found"}
            elif "too long" in error.lower():
                return {"error": "too_long", "message": "Message exceeds 10KB limit"}
            else:
                return {"error": "unknown", "message": error}

        return json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        return {"error": "timeout", "message": "Command timed out after 10s"}
    except Exception as e:
        return {"error": "exception", "message": str(e)}
```

## Testing Your Integration

Use the test commands to verify your integration works:

```bash
# Test sending a message
claudeswarm send-message test-sender test-recipient INFO "Test message"

# Test broadcasting
claudeswarm broadcast-message test-sender INFO "Test broadcast"

# Test file locking (use actual project file)
claudeswarm acquire-file-lock /tmp/test.txt test-agent "testing"
claudeswarm release-file-lock /tmp/test.txt test-agent
```

**Note:** File locking examples use `/tmp/test.txt` for testing. In production, use actual project file paths.

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
filepath = "/absolute/path/to/src/main.py"
if acquire_file_lock(filepath, "agent-2", "adding feature"):
    # Edit file
    edit_code(filepath)

    # Notify others
    broadcast_to_all("agent-2", "INFO", "Updated main.py with new feature")

    # Release lock
    release_file_lock(filepath, "agent-2")
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

    # Update progress (use INFO for status updates)
    progress = f"{(i+1)/total_steps * 100:.0f}% complete"
    broadcast_to_all("agent-3", "INFO", progress)

# Final completion signal
broadcast_to_all("agent-3", "COMPLETED", "All steps finished successfully")
```

## Troubleshooting

### Problem: Commands not found

**Solution:** Ensure claudeswarm is installed:
```bash
which claudeswarm
# Should show: /Users/<user>/.local/bin/claudeswarm or similar path
```

If not found:
```bash
pip install -e .  # Install from project root
# Or
pip install claudeswarm
```

### Problem: Permission denied errors

**Cause:** Commands must be run from within tmux panes

**Solution:**
```bash
# Check if you're in a tmux session
echo $TMUX
# Should output something like: /tmp/tmux-501/default,12345,0

# If empty, start a tmux session:
tmux new -s myproject
```

### Problem: No agents discovered

**Cause:** Not in the same project directory or tmux session

**Solution:**
```bash
# 1. Check you're in the right directory
pwd  # Verify project root

# 2. Check you're in a tmux session
echo $TMUX

# 3. Try discovering agents
claudeswarm discover-agents

# 4. If still no agents, create a test agent in another tmux pane:
# Press Ctrl+b then " to split the pane
```

### Problem: Message not delivered

**Cause:** Recipient agent doesn't exist or rate limit exceeded

**Solution:**
```bash
# 1. Check if recipient agent exists
claudeswarm list-agents --json

# 2. Check for rate limiting in error message
claudeswarm send-message sender receiver INFO "test" 2>&1 | grep -i "rate"

# 3. If rate limited, wait 60 seconds before retrying
```

### Problem: Rate limit exceeded

**Cause:** Sending more than 10 messages per minute per agent

**Solution:**
```python
import time

# Option 1: Add delays between messages
for msg in messages:
    send_message_to_agent(sender, recipient, "INFO", msg)
    time.sleep(6)  # 6 seconds = max 10 messages/minute

# Option 2: Batch updates into fewer messages
combined_msg = "\n".join(updates[:5])
send_message_to_agent(sender, recipient, "INFO", combined_msg)

# Option 3: Wait and retry
result = send_message_to_agent(sender, recipient, "INFO", msg)
if result and result.get("error") == "rate_limit":
    time.sleep(60)
    send_message_to_agent(sender, recipient, "INFO", msg)
```

### Problem: Message too long error

**Cause:** Message content exceeds 10KB limit

**Solution:**
```python
MAX_MESSAGE_LENGTH = 10 * 1024  # 10KB

def send_large_content(sender_id, recipient_id, content):
    """Split large content into multiple messages."""
    if len(content.encode('utf-8')) <= MAX_MESSAGE_LENGTH:
        send_message_to_agent(sender_id, recipient_id, "INFO", content)
    else:
        # Split into chunks
        chunks = [content[i:i+9000] for i in range(0, len(content), 9000)]
        for i, chunk in enumerate(chunks):
            msg = f"Part {i+1}/{len(chunks)}: {chunk}"
            send_message_to_agent(sender_id, recipient_id, "INFO", msg)
            time.sleep(1)  # Avoid rate limiting
```

### Problem: File lock acquisition fails

**Cause:** Another agent has the lock

**Solution:**
```python
# Option 1: Check who has the lock
result = subprocess.run(
    ["claudeswarm", "who-has-lock", filepath, "--json"],
    capture_output=True,
    text=True
)
lock_info = json.loads(result.stdout)
print(f"Lock held by: {lock_info}")

# Option 2: Ask the other agent to release
send_message_to_agent(
    "agent-2",
    lock_info['agent_id'],
    "QUESTION",
    f"Can you release lock on {filepath}? I need to edit it."
)

# Option 3: Wait and retry with timeout
import time
max_wait = 60
waited = 0
while waited < max_wait:
    if acquire_file_lock(filepath, agent_id, reason):
        break
    time.sleep(5)
    waited += 5
else:
    send_message_to_agent(agent_id, "system", "BLOCKED", f"Can't acquire lock on {filepath}")
```

### Problem: Tools fail with timeout errors

**Cause:** Network issues, system overload, or stuck commands

**Solution:**
```python
# Always set reasonable timeouts
try:
    result = subprocess.run(
        ["claudeswarm", "send-message", ...],
        capture_output=True,
        text=True,
        timeout=10  # 10 second timeout
    )
except subprocess.TimeoutExpired:
    # Handle timeout
    print("Command timed out, retrying...")
    # Optionally retry with exponential backoff
```

### Problem: Invalid message type error

**Cause:** Using incorrect message type name

**Solution:** Use only these valid message types:
- `INFO`
- `QUESTION`
- `BLOCKED`
- `REVIEW_REQUEST` (note: sends as "REVIEW-REQUEST")
- `COMPLETED`
- `CHALLENGE`
- `ACK`

**Do NOT use:** `PROGRESS-UPDATE`, `ERROR`, `WARNING` (these are not valid types)

## Summary

All tools are designed to be:
- ✅ Reliable when called as subprocesses
- ✅ Safe with proper error handling
- ✅ Easy to use with clear interfaces
- ✅ Well-tested for agent usage

Use these tools to build powerful multi-agent coordination systems!
