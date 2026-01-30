# Claude Swarm Demo Scripts

This directory contains demo scripts to showcase the Claude Swarm multi-agent coordination system.

## Quick Start

### Option 1: Automated Demo Walkthrough

Run the fully automated demo that showcases all key features:

```bash
./examples/demo_walkthrough.sh
```

This will:
1. Create an 8-pane tmux session
2. Automatically demonstrate agent discovery
3. Show message broadcasting and ACKs
4. Demonstrate file locking and conflict resolution
5. Walk through a code review workflow
6. Display monitoring and status checking

**Duration:** ~2-3 minutes

### Option 2: Manual Exploration

Set up the tmux environment for manual exploration:

```bash
./examples/demo_setup.sh
```

This creates an 8-pane tmux session with:
- **Agent 0 (Coordinator):** Coordinates work and broadcasts tasks
- **Agents 1, 2, 4, 5 (Developers):** Implement features
- **Agents 3, 6 (Reviewers):** Review code and provide feedback
- **Agent 7 (Monitor):** Monitors system activity

## Tmux Keyboard Shortcuts

- **Ctrl+B then arrow keys:** Navigate between panes
- **Ctrl+B then [:** Enter scroll mode (press `q` to exit)
- **Ctrl+B then ?:** Show all keybindings
- **Ctrl+B then d:** Detach from session (keeps it running in background)
- **Ctrl+B then &:** Kill the current window (use with caution!)

To re-attach to a detached session:
```bash
tmux attach-session -t claude-swarm-demo
```

To kill the demo session entirely:
```bash
tmux kill-session -t claude-swarm-demo
```

## Available Commands

### Discovery Commands

Discover active agents:
```bash
claudeswarm discover-agents
```

### Messaging Commands

Send a direct message:
```bash
claudeswarm send-to-agent agent-1 INFO "Hello!"
```

Broadcast to all agents:
```bash
claudeswarm broadcast-to-all INFO "Team announcement"
```

### Locking Commands

Acquire a file lock:
```bash
claudeswarm lock acquire --file src/example.py --reason "Working on feature"
```

Release a lock:
```bash
claudeswarm lock release --file src/example.py
```

List all active locks:
```bash
claudeswarm list-all-locks
```

Check who holds a specific lock:
```bash
claudeswarm who-has-lock src/example.py
```

### Monitoring Commands

Start the monitoring dashboard:
```bash
claudeswarm start-monitoring
```

## Demo Scenarios

### Scenario 1: Basic Coordination

**Panes:** Agent 0, Agent 1, Agent 2

1. **Agent 0:** Discover agents and broadcast task
   ```bash
   claudeswarm discover-agents
   claudeswarm broadcast-to-all INFO "Starting sprint - check COORDINATION.md"
   ```

2. **Agent 1 & 2:** Acknowledge
   ```bash
   claudeswarm send-to-agent agent-0 ACK "Acknowledged"
   ```

3. **Agent 1:** Lock file, work, release
   ```bash
   claudeswarm lock acquire --file src/auth.py --reason "Implementing auth"
   # ... do work ...
   claudeswarm lock release --file src/auth.py
   ```

4. **Agent 2:** Lock for review
   ```bash
   claudeswarm lock acquire --file src/auth.py --reason "Code review"
   claudeswarm send-to-agent agent-1 REVIEW-REQUEST "Looks good!"
   claudeswarm lock release --file src/auth.py
   ```

### Scenario 2: Code Review Workflow

**Panes:** Agent 3, Agent 1

1. **Agent 3:** Request review
   ```bash
   claudeswarm lock acquire --file src/feature.py --reason "New feature"
   echo "def new_feature(): pass" > src/feature.py
   claudeswarm lock release --file src/feature.py
   claudeswarm send-to-agent agent-1 REVIEW-REQUEST "Please review src/feature.py"
   ```

2. **Agent 1:** Review and provide feedback
   ```bash
   claudeswarm send-to-agent agent-3 ACK "Starting review"
   claudeswarm lock acquire --file src/feature.py --reason "Code review"
   claudeswarm send-to-agent agent-3 REVIEW-REQUEST "Add docstring"
   claudeswarm lock release --file src/feature.py
   ```

3. **Agent 3:** Address feedback
   ```bash
   claudeswarm lock acquire --file src/feature.py --reason "Addressing feedback"
   echo "def new_feature():\n    \"\"\"New feature.\"\"\"\n    pass" > src/feature.py
   claudeswarm lock release --file src/feature.py
   claudeswarm send-to-agent agent-1 INFO "Feedback addressed"
   ```

4. **Agent 1:** Approve
   ```bash
   claudeswarm send-to-agent agent-3 COMPLETED "APPROVED!"
   ```

### Scenario 3: Lock Conflict Resolution

**Panes:** Agent 1, Agent 2

1. **Agent 1:** Acquire lock
   ```bash
   claudeswarm lock acquire --file src/shared.py --reason "Refactoring"
   ```

2. **Agent 2:** Try to lock (will fail)
   ```bash
   claudeswarm lock acquire --file src/shared.py --reason "Bug fix"
   # This will show a conflict message
   ```

3. **Agent 2:** Send blocked message
   ```bash
   claudeswarm send-to-agent agent-1 BLOCKED "Waiting for src/shared.py"
   ```

4. **Agent 1:** Finish and release
   ```bash
   claudeswarm lock release --file src/shared.py
   claudeswarm send-to-agent agent-2 INFO "Lock released"
   ```

5. **Agent 2:** Acquire and proceed
   ```bash
   claudeswarm lock acquire --file src/shared.py --reason "Bug fix"
   # Now succeeds
   ```

## Automatic Message Delivery with Hooks

Claude Swarm can automatically deliver messages to agents using Claude Code hooks.
When configured, messages from other agents appear automatically in your conversation.

### Quick Setup

Run `claudeswarm init` in your project - it will offer to set up hooks automatically.

### Manual Setup

1. Copy the hook script to your project:

```bash
mkdir -p .claude/hooks
cat > .claude/hooks/check-for-messages.sh << 'EOF'
#!/bin/bash
set -euo pipefail
MESSAGES=$(timeout 5s claudeswarm check-messages --new-only --quiet --limit 5 2>/dev/null || echo "")
if [ -n "$MESSAGES" ]; then
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo ""
  printf '%s\n' "$MESSAGES"
  echo "Reply with: claudeswarm send-message <agent-id> INFO \"your message\""
  echo "───────────────────────────────────────────────────────────────"
fi
exit 0
EOF
chmod +x .claude/hooks/check-for-messages.sh
```

2. Configure Claude Code settings (`.claude/settings.json`):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "type": "command",
        "command": "./.claude/hooks/check-for-messages.sh"
      }
    ]
  }
}
```

### Command Flags

- `--new-only`: Only show messages since last check (prevents duplicates)
- `--quiet`: Compact one-line format (ideal for hooks)
- `--limit N`: Show at most N messages (default: 10)

## System Files

The system creates several files during operation:

- **ACTIVE_AGENTS.json:** Registry of discovered agents
- **agent_messages.log:** Log of all messages sent between agents
- **.agent_locks/*.lock:** Lock files for coordinated file access
- **COORDINATION.md:** Shared coordination file (if initialized)

## Troubleshooting

### "tmux server not running"

Install or start tmux:
```bash
# macOS
brew install tmux

# Ubuntu/Debian
sudo apt-get install tmux
```

### "No agents discovered"

Make sure tmux is running and you have panes with processes:
```bash
tmux list-panes -a
```

### "Rate limit exceeded"

The system limits messages to 10 per agent per minute. Wait a minute or restart the session to reset.

### Clean up test files

```bash
rm -rf .agent_locks/ ACTIVE_AGENTS.json agent_messages.log COORDINATION.md
```

## Next Steps

After exploring the demo:

1. **Read the documentation:** See `../docs/` for detailed guides
2. **Run integration tests:** `pytest tests/integration/`
3. **Build your own workflow:** Adapt the demo scripts to your use case
4. **Integrate with Claude Code:** Use these coordination primitives in your actual development workflow

## Contributing

Found a bug or have a feature request? Open an issue or submit a pull request!

## License

MIT License - See LICENSE file for details
