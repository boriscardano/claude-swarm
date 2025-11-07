# Troubleshooting Guide

Common issues and solutions for Claude Swarm.

---

## Table of Contents

1. [Installation Issues](#installation-issues)
2. [Discovery Problems](#discovery-problems)
3. [Messaging Issues](#messaging-issues)
4. [Lock Conflicts](#lock-conflicts)
5. [Integration Test Failures](#integration-test-failures)
6. [Performance Issues](#performance-issues)
7. [tmux Configuration](#tmux-configuration)
8. [Permission Errors](#permission-errors)

---

## Installation Issues

### Problem: `tmux: command not found`

**Symptoms:**
```bash
$ claudeswarm discover-agents
Error: tmux is not installed or not in PATH
```

**Solution:**

Install tmux for your platform:

```bash
# macOS
brew install tmux

# Ubuntu/Debian
sudo apt-get install tmux

# Fedora
sudo dnf install tmux

# Arch Linux
sudo pacman -S tmux
```

Verify installation:
```bash
tmux -V
# Should output: tmux 3.x or later
```

---

### Problem: `uv: command not found`

**Symptoms:**
```bash
$ uv sync
bash: uv: command not found
```

**Solution:**

Install uv and add to PATH:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (bash)
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Add to PATH (zsh)
echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Verify installation
uv --version
```

---

### Problem: Python version too old

**Symptoms:**
```bash
error: This project requires Python 3.12+, but 3.10 is installed
```

**Solution:**

Install Python 3.12 or later:

```bash
# macOS (using Homebrew)
brew install python@3.12

# Ubuntu (using deadsnakes PPA)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv

# Verify installation
python3.12 --version
```

Configure uv to use the correct Python:
```bash
uv python pin 3.12
```

---

## Discovery Problems

### Problem: No agents discovered

**Symptoms:**
```bash
$ claudeswarm discover-agents
No agents discovered.
```

**Diagnosis:**

Check if Claude Code is actually running in tmux:

```bash
# Check tmux panes
tmux list-panes -a

# Check for Claude processes
ps aux | grep claude
```

**Solutions:**

1. **tmux is not running:**

```bash
# Start a new tmux session
tmux new -s myproject

# Split into panes
# Ctrl+b " (horizontal split)
# Ctrl+b % (vertical split)
```

2. **Claude Code not running in panes:**

Launch Claude Code in each pane:
```bash
# In each pane
claude
```

3. **Wrong tmux session:**

Specify the session name:
```bash
claudeswarm discover-agents --session myproject
```

4. **Process name doesn't match:**

Claude Code might be running with a different process name. Check the process list:
```bash
tmux list-panes -a -F '#{pane_current_command}'
```

The discovery system looks for processes containing "claude", "claude-code", or "node". If your process has a different name, you may need to update the matching logic.

---

### Problem: Agents marked as "stale"

**Symptoms:**
```bash
$ claudeswarm discover-agents
agent-1  | stale
```

**Cause:**

Agent hasn't been seen in the last 60 seconds (default threshold).

**Solution:**

1. **Check if agent is still running:**

```bash
# Check process
ps -p <PID>
```

2. **Adjust stale threshold:**

```bash
claudeswarm discover-agents --stale-threshold 120
```

3. **Refresh the registry:**

```bash
# Force a fresh discovery
claudeswarm discover-agents
```

---

### Problem: Registry file corrupted

**Symptoms:**
```bash
Error loading agent registry: Invalid JSON
```

**Solution:**

Delete and recreate the registry:

```bash
# Backup (optional)
mv ACTIVE_AGENTS.json ACTIVE_AGENTS.json.bak

# Force fresh discovery
claudeswarm discover-agents
```

---

## Messaging Issues

### Problem: Messages not appearing in recipient pane

**Symptoms:**

Agent sends a message, but recipient never sees it.

**Diagnosis:**

1. **Check tmux integration:**

```bash
# Verify you're in a tmux session
echo $TMUX

# Should output something like: /tmp/tmux-1000/default,12345,0
```

2. **Test send-keys manually:**

```bash
# Get recipient pane ID from registry
cat ACTIVE_AGENTS.json

# Test manual message
tmux send-keys -t "session:0.1" 'echo "Test message"' Enter
```

3. **Check message log:**

```bash
# View recent messages
tail -20 agent_messages.log
```

**Solutions:**

1. **Not in tmux session:**

```bash
# Start tmux first
tmux new -s myproject
# Then launch Claude Code
```

2. **Wrong pane index:**

```bash
# Refresh registry to get current pane indices
claudeswarm discover-agents
```

3. **Rate limit exceeded:**

Messages are limited to 10 per agent per minute. Wait and retry:

```python
from time import sleep

# If send fails, wait
if msg is None:
    print("Rate limited, waiting 10 seconds...")
    sleep(10)
```

4. **tmux send-keys permission issues:**

Check tmux server permissions:
```bash
ls -la /tmp/tmux-*
```

---

### Problem: Messages have garbled characters

**Symptoms:**

Messages display with strange characters or quotes are escaped incorrectly.

**Cause:**

Special characters not properly escaped for tmux.

**Solution:**

The messaging system should handle escaping automatically. If you're manually sending messages, use the MessagingSystem class:

```python
from claudeswarm.messaging import send_message, MessageType

# Let the system handle escaping
send_message(
    sender_id="agent-0",
    recipient_id="agent-1",
    message_type=MessageType.INFO,
    content="Message with 'quotes' and \"double quotes\""
)
```

---

### Problem: Broadcast not reaching all agents

**Symptoms:**

Broadcast message only received by some agents.

**Diagnosis:**

Check delivery status:

```python
from claudeswarm.messaging import broadcast_message, MessageType

results = broadcast_message(
    sender_id="agent-0",
    message_type=MessageType.INFO,
    content="Test broadcast"
)

# Check results
for agent_id, success in results.items():
    print(f"{agent_id}: {'delivered' if success else 'FAILED'}")
```

**Solutions:**

1. **Stale agents in registry:**

```bash
# Refresh registry before broadcasting
claudeswarm discover-agents
```

2. **Some agents not active:**

Check agent status:
```bash
claudeswarm list-agents
```

Only agents with status "active" receive messages.

---

## Lock Conflicts

### Problem: Cannot acquire lock on file

**Symptoms:**
```bash
$ claudeswarm acquire-file-lock src/auth.py agent-1 "editing"
Lock conflict on: src/auth.py
  Currently held by: agent-0
```

**Diagnosis:**

Check who has the lock and why:

```bash
claudeswarm who-has-lock src/auth.py
```

Output:
```
Lock on: src/auth.py
  Held by: agent-0
  Locked at: 2025-11-07 14:30:00 UTC
  Age: 120.5 seconds
  Reason: Implementing OAuth
```

**Solutions:**

1. **Wait for lock to be released:**

Ask the lock holder when they'll be done:
```python
from claudeswarm.messaging import send_message, MessageType

send_message(
    sender_id="agent-1",
    recipient_id="agent-0",
    message_type=MessageType.QUESTION,
    content="When will you finish editing src/auth.py?"
)
```

2. **Lock is stale:**

If lock is older than 5 minutes (300 seconds), it's stale and will be automatically cleaned up:

```bash
# Manual cleanup
claudeswarm cleanup-stale-locks
```

3. **Agent crashed while holding lock:**

Clean up locks for a specific agent:

```python
from claudeswarm.locking import LockManager

lm = LockManager()
count = lm.cleanup_agent_locks("agent-0")
print(f"Cleaned up {count} locks")
```

---

### Problem: Glob pattern lock conflicts

**Symptoms:**

Lock on specific file fails because of glob pattern:

```
Lock conflict on: src/auth/login.py
  Currently held by: agent-2
  Filepath: src/**/*.py
```

**Cause:**

Agent-2 has a glob pattern lock on `src/**/*.py` which matches your specific file.

**Solution:**

Coordinate with the lock holder:

```python
from claudeswarm.messaging import send_message, MessageType

send_message(
    sender_id="agent-1",
    recipient_id="agent-2",
    message_type=MessageType.BLOCKED,
    content="Need to edit src/auth/login.py but you have src/**/*.py locked"
)
```

**Prevention:**

Use specific locks instead of broad globs when possible:

```bash
# Instead of
claudeswarm acquire-file-lock "src/**/*.py" agent-0 "refactoring"

# Use
claudeswarm acquire-file-lock "src/models/*.py" agent-0 "refactoring models"
```

---

### Problem: Lock not released after agent crash

**Symptoms:**

Agent crashed but lock remains:

```bash
$ claudeswarm who-has-lock src/auth.py
Lock on: src/auth.py
  Held by: agent-3
  Age: 1200.0 seconds  # 20 minutes
```

**Solution:**

Stale locks (older than 5 minutes) are automatically cleaned when another agent tries to acquire:

```bash
# Try to acquire - will auto-clean stale lock
claudeswarm acquire-file-lock src/auth.py agent-1 "fixing crash"
```

Or manually clean up:

```bash
claudeswarm cleanup-stale-locks
```

---

### Problem: Lock directory permission denied

**Symptoms:**
```bash
Error: Permission denied: .agent_locks
```

**Solution:**

Check directory permissions:

```bash
# Check permissions
ls -la .agent_locks/

# Fix permissions
chmod 755 .agent_locks/
```

If directory doesn't exist:
```bash
mkdir -p .agent_locks
chmod 755 .agent_locks
```

---

## Integration Test Failures

### Problem: Test isolation issues

**Symptoms:**

Tests fail intermittently or when run together but pass individually:

```bash
$ pytest tests/integration/test_basic_coordination.py
PASSED

$ pytest tests/integration/
FAILED: test_code_review_workflow
```

**Cause:**

Tests may share state through:
- Shared ACTIVE_AGENTS.json
- Shared lock files
- Shared COORDINATION.md

**Solution:**

1. **Use test fixtures with cleanup:**

```python
import pytest
from pathlib import Path

@pytest.fixture
def clean_test_env(tmp_path):
    """Provide clean test environment."""
    # Setup
    old_cwd = Path.cwd()
    os.chdir(tmp_path)

    yield tmp_path

    # Cleanup
    os.chdir(old_cwd)
    # Clean up files
    for f in tmp_path.glob("ACTIVE_AGENTS.json"):
        f.unlink()
    for f in tmp_path.glob(".agent_locks/*.lock"):
        f.unlink()
```

2. **Run tests in isolation:**

```bash
# Run each test file separately
for file in tests/integration/test_*.py; do
    pytest "$file"
done
```

3. **Use pytest-xdist for parallel isolation:**

```bash
pip install pytest-xdist
pytest -n auto tests/integration/
```

---

### Problem: tmux not found in tests

**Symptoms:**
```bash
RuntimeError: tmux is not installed or not in PATH
```

**Solution:**

Skip tests that require tmux if not available:

```python
import pytest
import shutil

@pytest.mark.skipif(
    shutil.which("tmux") is None,
    reason="tmux not available"
)
def test_discovery():
    # Test code
    pass
```

Or mock tmux for unit tests:

```python
from unittest.mock import patch, MagicMock

@patch('subprocess.run')
def test_discovery_mock(mock_run):
    # Mock tmux output
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout="session:0.0|12345|claude\n"
    )

    # Test code
    pass
```

---

### Problem: Rate limit exceeded during tests

**Symptoms:**
```bash
AssertionError: Expected message to be delivered, got None
```

**Cause:**

Tests sending too many messages too quickly.

**Solution:**

1. **Increase rate limit for tests:**

```python
from claudeswarm.messaging import MessagingSystem

# In test setup
messaging = MessagingSystem(
    rate_limit_messages=100,  # Increase for tests
    rate_limit_window=60
)
```

2. **Add delays between messages:**

```python
from time import sleep

send_message(...)
sleep(0.1)  # Small delay
send_message(...)
```

3. **Reset rate limiter between tests:**

```python
@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from claudeswarm.messaging import _default_messaging_system
    if _default_messaging_system:
        _default_messaging_system.rate_limiter = RateLimiter()
```

---

## Performance Issues

### Problem: Discovery is slow

**Symptoms:**

`discover_agents()` takes more than 2 seconds.

**Diagnosis:**

Check how many panes exist:

```bash
tmux list-panes -a | wc -l
```

**Solutions:**

1. **Too many tmux panes:**

Close unused panes:
```bash
# List all panes with processes
tmux list-panes -a -F '#{pane_id} #{pane_current_command}'

# Kill specific pane
tmux kill-pane -t <pane_id>
```

2. **Network-mounted home directory:**

Discovery writes to `ACTIVE_AGENTS.json` - ensure it's on local disk:

```bash
# Check filesystem type
df -T ACTIVE_AGENTS.json

# If on NFS/network, use local temp directory
export CLAUDESWARM_PROJECT_ROOT=/tmp/myproject
```

3. **Old/slow tmux version:**

Update tmux:
```bash
# macOS
brew upgrade tmux

# Linux (compile from source if needed)
wget https://github.com/tmux/tmux/releases/download/3.3a/tmux-3.3a.tar.gz
```

---

### Problem: Message log file growing too large

**Symptoms:**

`agent_messages.log` is several GB in size, slowing down operations.

**Solution:**

The log automatically rotates at 10MB, but manual rotation may be needed:

```bash
# Archive old log
mv agent_messages.log agent_messages.log.$(date +%Y%m%d)

# Compress archives
gzip agent_messages.log.*

# Delete very old logs
find . -name "agent_messages.log.*.gz" -mtime +30 -delete
```

Adjust monitoring to reduce log growth:

```python
# Only log failures, not all messages
from claudeswarm.messaging import MessagingSystem

messaging = MessagingSystem()
# Custom logger that filters
```

---

### Problem: Too many lock files

**Symptoms:**

`.agent_locks/` directory has thousands of files.

**Solution:**

Clean up stale locks:

```bash
# Manual cleanup
claudeswarm cleanup-stale-locks

# Or via Python
from claudeswarm.locking import LockManager

lm = LockManager()
count = lm.cleanup_stale_locks(timeout=300)
print(f"Cleaned up {count} locks")
```

Scheduled cleanup (cron):
```bash
# Add to crontab (run every hour)
0 * * * * cd /path/to/project && claudeswarm cleanup-stale-locks
```

---

## tmux Configuration

### Problem: Pane indices changing

**Symptoms:**

Agent pane indices change after closing/reopening panes, breaking communication.

**Solution:**

Configure tmux to maintain stable indices:

Add to `~/.tmux.conf`:
```tmux
# Renumber windows on close
set -g renumber-windows on

# Start numbering at 1 (easier to track)
set -g base-index 1
setw -g pane-base-index 1
```

Reload configuration:
```bash
tmux source-file ~/.tmux.conf
```

---

### Problem: Colors not displaying in monitoring

**Symptoms:**

Monitoring dashboard shows escape codes instead of colors.

**Solution:**

Enable 256 colors in tmux:

Add to `~/.tmux.conf`:
```tmux
# Enable 256 color terminal
set -g default-terminal "screen-256color"
```

Or set TERM variable:
```bash
export TERM=xterm-256color
```

Restart tmux session for changes to take effect.

---

### Problem: Mouse support not working

**Symptoms:**

Cannot resize panes or scroll with mouse in tmux.

**Solution:**

Enable mouse mode:

Add to `~/.tmux.conf`:
```tmux
# Enable mouse support
set -g mouse on
```

Reload:
```bash
tmux source-file ~/.tmux.conf
```

---

## Permission Errors

### Problem: Cannot write to project directory

**Symptoms:**
```bash
PermissionError: [Errno 13] Permission denied: 'ACTIVE_AGENTS.json'
```

**Solution:**

1. **Check directory permissions:**

```bash
ls -la
```

2. **Fix permissions:**

```bash
# If you own the directory
chmod u+w .

# If group-writable
chmod g+w .
```

3. **Use a different directory:**

```bash
# Use temp directory
export CLAUDESWARM_PROJECT_ROOT=/tmp/myproject
mkdir -p /tmp/myproject
cd /tmp/myproject
```

---

### Problem: Lock files owned by another user

**Symptoms:**
```bash
PermissionError: [Errno 13] Permission denied: '.agent_locks/abc123.lock'
```

**Cause:**

Multiple users trying to coordinate in same directory.

**Solution:**

1. **Each user has own project directory:**

```bash
# User 1
export CLAUDESWARM_PROJECT_ROOT=~/projects/myproject-user1

# User 2
export CLAUDESWARM_PROJECT_ROOT=~/projects/myproject-user2
```

2. **Shared directory with group permissions:**

```bash
# Set group ownership
sudo chgrp developers .agent_locks
sudo chmod 775 .agent_locks

# Set sticky bit so files inherit group
sudo chmod g+s .agent_locks
```

---

## General Debugging

### Enable debug logging

Add debug logging to troubleshoot issues:

```python
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Now run your code
from claudeswarm.discovery import discover_agents
registry = discover_agents()
```

Or via CLI:
```bash
export CLAUDESWARM_LOG_LEVEL=DEBUG
claudeswarm discover-agents
```

---

### Verify installation

Check that all components are installed correctly:

```bash
# Check Python version
python --version
# Should be 3.12+

# Check tmux
tmux -V
# Should be 3.0+

# Check uv
uv --version

# Check Claude Swarm installation
python -c "import claudeswarm; print(claudeswarm.__version__)"

# Test CLI
claudeswarm --help
```

---

### Reset to clean state

If all else fails, reset to a clean state:

```bash
# Backup (optional)
tar -czf claudeswarm-backup-$(date +%Y%m%d).tar.gz \
    ACTIVE_AGENTS.json agent_messages.log .agent_locks/ COORDINATION.md

# Clean up
rm -f ACTIVE_AGENTS.json agent_messages.log* PENDING_ACKS.json
rm -rf .agent_locks/

# Rediscover
claudeswarm discover-agents
```

---

## Getting Help

If you're still stuck after trying these solutions:

1. **Check the logs:**
   - `agent_messages.log` - Message delivery issues
   - `.agent_locks/*.lock` - Lock conflicts
   - `ACTIVE_AGENTS.json` - Discovery problems

2. **Enable debug logging:**
   ```bash
   export CLAUDESWARM_LOG_LEVEL=DEBUG
   ```

3. **File an issue:**
   - GitHub: https://github.com/yourusername/claude-swarm/issues
   - Include: OS, Python version, tmux version, error messages, logs

4. **Check documentation:**
   - [API Reference](api-reference.md) - Detailed API docs
   - [Getting Started](getting-started.md) - Setup and tutorials
   - [Architecture](architecture.md) - How it works

---

**Last Updated:** 2025-11-07
