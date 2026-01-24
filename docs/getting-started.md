# Getting Started with Claude Swarm

This guide will walk you through installing and using Claude Swarm for multi-agent coordination.

---

## Table of Contents

1. [Installation](#installation)
2. [First-Time Setup](#first-time-setup)
3. [Quick Start Tutorial](#quick-start-tutorial)
4. [Two-Agent Coordination Example](#two-agent-coordination-example)
5. [Configuration](#configuration)
6. [Next Steps](#next-steps)

---

## Installation

### Prerequisites

- **macOS or Linux** (Windows via WSL2)
- **Python 3.12 or later**
- **tmux 3.0 or later**
- **uv package manager**

### Step 1: Install tmux

```bash
# macOS
brew install tmux

# Ubuntu/Debian
sudo apt-get install tmux

# Fedora
sudo dnf install tmux

# Verify installation
tmux -V
# Should output: tmux 3.x or later
```

### Step 2: Install uv

```bash
# Install uv (Astral's fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify installation
uv --version
```

### Step 3: Install Claude Swarm

```bash
# Clone the repository
git clone https://github.com/boriscardano/claude-swarm.git
cd claude-swarm

# Sync dependencies
uv sync --all-extras

# Verify installation
uv run claudeswarm --help
```

You should see the command-line help output.

---

## First-Time Setup

### 1. Start tmux Session

```bash
# Create a new tmux session for your project
tmux new -s myproject

# Split the window into multiple panes
# Ctrl+b " (split horizontally)
# Ctrl+b % (split vertically)
# Ctrl+b arrow-keys (navigate between panes)
```

### 2. Launch Claude Code Agents

In each tmux pane, start a Claude Code instance:

```bash
# Pane 1
claude

# Pane 2
claude

# Pane 3
claude

# etc.
```

### 3. Discover Agents

In any pane, run:

```bash
uv run claudeswarm discover-agents
```

Output:
```
=== Agent Discovery [2025-11-07T10:30:00+00:00] ===
Session: myproject
Total agents: 3

  ✓ agent-0       | myproject:0.0        | PID: 12345   | active
  ✓ agent-1       | myproject:0.1        | PID: 12346   | active
  ✓ agent-2       | myproject:0.2        | PID: 12347   | active

Registry saved to: ACTIVE_AGENTS.json
```

Your agents are now discoverable and can communicate!

---

## Quick Start Tutorial

### Tutorial: Send Your First Message

**Goal:** Learn basic messaging between agents.

#### Step 1: Identify Your Agent ID

In **Pane 1**, check the agent registry:

```bash
cat ACTIVE_AGENTS.json
```

You'll see your agent ID (e.g., `agent-0`).

#### Step 2: Send a Message

From **Pane 1** (agent-0), send a message to **Pane 2** (agent-1):

```bash
uv run claudeswarm send-to-agent agent-1 INFO "Hello from agent-0!"
```

#### Step 3: See the Message

In **Pane 2**, you should see:

```
[agent-0][2025-11-07 10:35:00][INFO]: Hello from agent-0!
```

#### Step 4: Reply

From **Pane 2** (agent-1), reply:

```bash
uv run claudeswarm send-to-agent agent-0 INFO "Hello back from agent-1!"
```

**Pane 1** receives:

```
[agent-1][2025-11-07 10:35:15][INFO]: Hello back from agent-1!
```

Congratulations! You've sent your first inter-agent messages.

---

### Tutorial: File Locking

**Goal:** Learn to coordinate file access safely.

#### Step 1: Create a Test File

```bash
echo "# Shared File" > shared.txt
```

#### Step 2: Agent-0 Acquires Lock

From **Pane 1** (agent-0):

```bash
uv run claudeswarm acquire-file-lock shared.txt agent-0 "editing content"
```

Output:
```
Lock acquired on: shared.txt
  Agent: agent-0
  Reason: editing content
```

#### Step 3: Agent-1 Tries to Acquire (Conflict)

From **Pane 2** (agent-1):

```bash
uv run claudeswarm acquire-file-lock shared.txt agent-1 "also editing"
```

Output:
```
Lock conflict on: shared.txt
  Currently held by: agent-0
  Locked at: 2025-11-07 10:40:00 UTC
  Reason: editing content
```

**Result:** Agent-1 cannot acquire the lock while agent-0 holds it.

#### Step 4: Agent-1 Asks Agent-0 for ETA

From **Pane 2** (agent-1):

```bash
uv run claudeswarm send-to-agent agent-0 QUESTION "When will you finish shared.txt?"
```

**Pane 1** receives:
```
[agent-1][2025-11-07 10:40:30][QUESTION]: When will you finish shared.txt?
```

#### Step 5: Agent-0 Responds

From **Pane 1** (agent-0):

```bash
uv run claudeswarm send-to-agent agent-1 INFO "Done in 2 minutes"
```

#### Step 6: Agent-0 Edits and Releases

From **Pane 1** (agent-0):

```bash
# Edit the file
echo "Content from agent-0" >> shared.txt

# Release the lock
uv run claudeswarm release-file-lock shared.txt agent-0
```

Output:
```
Lock released on: shared.txt
```

#### Step 7: Agent-1 Acquires Lock (Success)

From **Pane 2** (agent-1):

```bash
uv run claudeswarm acquire-file-lock shared.txt agent-1 "adding my content"
```

Output:
```
Lock acquired on: shared.txt
  Agent: agent-1
  Reason: adding my content
```

**Success!** Agent-1 can now safely edit the file.

```bash
# Edit the file
echo "Content from agent-1" >> shared.txt

# Release the lock
uv run claudeswarm release-file-lock shared.txt agent-1
```

---

## Two-Agent Coordination Example

Let's build a simple feature with two agents coordinating their work.

**Scenario:** Implement user authentication with JWT tokens.
- **Agent-0:** Implements the authentication module
- **Agent-1:** Writes tests for the authentication module

### Agent-0 (Implementation)

```bash
# 1. Announce work
uv run claudeswarm broadcast-to-all INFO "Starting JWT authentication implementation"

# 2. Acquire lock on implementation file
uv run claudeswarm acquire-file-lock src/auth.py agent-0 "implementing JWT"

# 3. Create the implementation
cat > src/auth.py << 'EOF'
"""JWT authentication module."""

def generate_token(user_id: str) -> str:
    """Generate JWT token for user."""
    return f"token-{user_id}"

def verify_token(token: str) -> str:
    """Verify JWT token and return user_id."""
    if token.startswith("token-"):
        return token.replace("token-", "")
    raise ValueError("Invalid token")
EOF

# 4. Release lock
uv run claudeswarm release-file-lock src/auth.py agent-0

# 5. Announce completion
uv run claudeswarm send-to-agent agent-1 COMPLETED "JWT auth implementation done, ready for tests"
```

### Agent-1 (Testing)

```bash
# 1. Wait for completion message from agent-0
# [agent-0][timestamp][COMPLETED]: JWT auth implementation done, ready for tests

# 2. Acknowledge
uv run claudeswarm send-to-agent agent-0 ACK "Starting tests for JWT auth"

# 3. Acquire lock on test file
uv run claudeswarm acquire-file-lock tests/test_auth.py agent-1 "writing tests"

# 4. Create tests
cat > tests/test_auth.py << 'EOF'
"""Tests for JWT authentication."""

from src.auth import generate_token, verify_token

def test_generate_token():
    token = generate_token("user123")
    assert token == "token-user123"

def test_verify_token():
    token = "token-user123"
    user_id = verify_token(token)
    assert user_id == "user123"

def test_verify_invalid_token():
    try:
        verify_token("invalid")
        assert False, "Should raise ValueError"
    except ValueError:
        pass
EOF

# 5. Run tests
pytest tests/test_auth.py

# 6. Release lock
uv run claudeswarm release-file-lock tests/test_auth.py agent-1

# 7. Report results
uv run claudeswarm send-to-agent agent-0 COMPLETED "All tests passing for JWT auth"
```

### Agent-0 (Final Integration)

```bash
# 1. Receive test results
# [agent-1][timestamp][COMPLETED]: All tests passing for JWT auth

# 2. Announce to all agents
uv run claudeswarm broadcast-to-all COMPLETED "JWT authentication feature complete and tested"
```

**Result:** Two agents successfully coordinated to implement and test a feature without conflicts!

---

## Configuration

### Project-Level Configuration

Create a `.claudeswarm.toml` file in your project root (optional):

```toml
[project]
name = "myproject"
session_name = "myproject"

[coordination]
stale_threshold = 60  # seconds
lock_timeout = 300    # seconds (5 minutes)

[messaging]
rate_limit = 10       # messages per minute
log_file = "agent_messages.log"
```

### Environment Variables

```bash
# Set project root (default: current directory)
export CLAUDESWARM_PROJECT_ROOT=/path/to/project

# Set lock directory (default: .agent_locks)
export CLAUDESWARM_LOCK_DIR=.locks

# Set log level
export CLAUDESWARM_LOG_LEVEL=INFO
```

### Tmux Configuration

Add to your `~/.tmux.conf` for better agent coordination:

```tmux
# Enable mouse support
set -g mouse on

# Increase scrollback buffer
set -g history-limit 10000

# Start window numbering at 1
set -g base-index 1

# Renumber windows on close
set -g renumber-windows on

# Display pane numbers longer
set -g display-panes-time 2000

# Status bar
set -g status-right '#{session_name} | #{window_index}.#{pane_index}'
```

---

## Next Steps

### Learn More

- **[AGENT_PROTOCOL.md](../AGENT_PROTOCOL.md)** - Complete protocol guide for agents
- **[architecture.md](architecture.md)** - System design and components
- **[api-reference.md](api-reference.md)** - Detailed API documentation
- **[protocol.md](protocol.md)** - Technical protocol specifications
- **[troubleshooting.md](troubleshooting.md)** - Common issues and solutions

### Try Advanced Features

1. **Glob Pattern Locking**
   ```bash
   uv run claudeswarm acquire-file-lock "src/**/*.py" agent-0 "refactoring"
   ```

2. **Broadcast Messages**
   ```bash
   uv run claudeswarm broadcast-to-all REVIEW-REQUEST "PR #42 ready for review"
   ```

3. **Watch Mode (Auto-discovery)**
   ```bash
   uv run claudeswarm discover-agents --watch
   ```

4. **Check All Locks**
   ```bash
   uv run claudeswarm list-all-locks
   ```

5. **Cleanup Stale Locks**
   ```bash
   uv run claudeswarm cleanup-stale-locks
   ```

### Set Up Your Team

1. Create a tmux session with 4-8 panes
2. Launch Claude Code in each pane
3. Run discovery: `uv run claudeswarm discover-agents`
4. Start coordinating!

### Example Multi-Agent Setup

```bash
# Create tmux session with 4 panes
tmux new -s team -n work

# Split into 4 panes
tmux split-window -h
tmux split-window -v
tmux select-pane -t 0
tmux split-window -v

# In each pane, start Claude Code
# Pane 0: claude  (agent-0 - coordinator)
# Pane 1: claude  (agent-1 - backend)
# Pane 2: claude  (agent-2 - frontend)
# Pane 3: claude  (agent-3 - testing)

# Discover agents
uv run claudeswarm discover-agents

# Agent-0 assigns work
uv run claudeswarm broadcast-to-all INFO "Sprint goal: Build user dashboard"
uv run claudeswarm send-to-agent agent-1 INFO "Task: API endpoints for user data"
uv run claudeswarm send-to-agent agent-2 INFO "Task: Dashboard UI components"
uv run claudeswarm send-to-agent agent-3 INFO "Task: Integration tests"
```

---

## Troubleshooting

### Common Setup Issues

**Problem:** `tmux: command not found`

**Solution:** Install tmux first (see [Installation](#installation))

---

**Problem:** `uv: command not found`

**Solution:** Install uv and add to PATH:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc  # or ~/.zshrc
```

---

**Problem:** No agents discovered

**Solution:** Ensure Claude Code is running in tmux panes:
```bash
# Check tmux panes
tmux list-panes -a

# Check if claude processes exist
ps aux | grep claude

# Try manual discovery
uv run claudeswarm discover-agents --json
```

---

**Problem:** Messages not appearing

**Solution:** Check tmux integration:
```bash
# Verify tmux session
echo $TMUX

# Test send-keys manually
tmux send-keys -t myproject:0.0 'echo "Test message"' Enter

# Check agent registry
cat ACTIVE_AGENTS.json
```

---

**Problem:** Lock conflicts on every file

**Solution:** Check for glob pattern locks:
```bash
uv run claudeswarm list-all-locks
```

Clean up if needed:
```bash
uv run claudeswarm cleanup-stale-locks
```

---

For more troubleshooting help, see **[troubleshooting.md](troubleshooting.md)**.

---

## Getting Help

- **Documentation:** See `docs/` directory
- **Issues:** File issues on GitHub
- **Protocol Questions:** See [AGENT_PROTOCOL.md](../AGENT_PROTOCOL.md)
- **API Reference:** See [api-reference.md](api-reference.md)

---

**Ready to coordinate!** Start your tmux session and let your agents work together.
