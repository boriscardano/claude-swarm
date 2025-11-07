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
python -m claudeswarm.cli discover
```

### Messaging Commands

Send a direct message:
```bash
python -m claudeswarm.cli send --to agent-1 --type INFO --message "Hello!"
```

Broadcast to all agents:
```bash
python -m claudeswarm.cli broadcast --type INFO --message "Team announcement"
```

### Locking Commands

Acquire a file lock:
```bash
python -m claudeswarm.cli lock acquire --file src/example.py --reason "Working on feature"
```

Release a lock:
```bash
python -m claudeswarm.cli lock release --file src/example.py
```

List all active locks:
```bash
python -m claudeswarm.cli lock list
```

Check who holds a specific lock:
```bash
python -m claudeswarm.cli lock who --file src/example.py
```

### Monitoring Commands

Start the monitoring dashboard:
```bash
python -m claudeswarm.cli monitor
```

## Demo Scenarios

### Scenario 1: Basic Coordination

**Panes:** Agent 0, Agent 1, Agent 2

1. **Agent 0:** Discover agents and broadcast task
   ```bash
   python -m claudeswarm.cli discover
   python -m claudeswarm.cli broadcast --type INFO --message "Starting sprint - check COORDINATION.md"
   ```

2. **Agent 1 & 2:** Acknowledge
   ```bash
   python -m claudeswarm.cli send --to agent-0 --type ACK --message "Acknowledged"
   ```

3. **Agent 1:** Lock file, work, release
   ```bash
   python -m claudeswarm.cli lock acquire --file src/auth.py --reason "Implementing auth"
   # ... do work ...
   python -m claudeswarm.cli lock release --file src/auth.py
   ```

4. **Agent 2:** Lock for review
   ```bash
   python -m claudeswarm.cli lock acquire --file src/auth.py --reason "Code review"
   python -m claudeswarm.cli send --to agent-1 --type REVIEW-REQUEST --message "Looks good!"
   python -m claudeswarm.cli lock release --file src/auth.py
   ```

### Scenario 2: Code Review Workflow

**Panes:** Agent 3, Agent 1

1. **Agent 3:** Request review
   ```bash
   python -m claudeswarm.cli lock acquire --file src/feature.py --reason "New feature"
   echo "def new_feature(): pass" > src/feature.py
   python -m claudeswarm.cli lock release --file src/feature.py
   python -m claudeswarm.cli send --to agent-1 --type REVIEW-REQUEST --message "Please review src/feature.py"
   ```

2. **Agent 1:** Review and provide feedback
   ```bash
   python -m claudeswarm.cli send --to agent-3 --type ACK --message "Starting review"
   python -m claudeswarm.cli lock acquire --file src/feature.py --reason "Code review"
   python -m claudeswarm.cli send --to agent-3 --type REVIEW-REQUEST --message "Add docstring"
   python -m claudeswarm.cli lock release --file src/feature.py
   ```

3. **Agent 3:** Address feedback
   ```bash
   python -m claudeswarm.cli lock acquire --file src/feature.py --reason "Addressing feedback"
   echo "def new_feature():\n    \"\"\"New feature.\"\"\"\n    pass" > src/feature.py
   python -m claudeswarm.cli lock release --file src/feature.py
   python -m claudeswarm.cli send --to agent-1 --type INFO --message "Feedback addressed"
   ```

4. **Agent 1:** Approve
   ```bash
   python -m claudeswarm.cli send --to agent-3 --type COMPLETED --message "APPROVED!"
   ```

### Scenario 3: Lock Conflict Resolution

**Panes:** Agent 1, Agent 2

1. **Agent 1:** Acquire lock
   ```bash
   python -m claudeswarm.cli lock acquire --file src/shared.py --reason "Refactoring"
   ```

2. **Agent 2:** Try to lock (will fail)
   ```bash
   python -m claudeswarm.cli lock acquire --file src/shared.py --reason "Bug fix"
   # This will show a conflict message
   ```

3. **Agent 2:** Send blocked message
   ```bash
   python -m claudeswarm.cli send --to agent-1 --type BLOCKED --message "Waiting for src/shared.py"
   ```

4. **Agent 1:** Finish and release
   ```bash
   python -m claudeswarm.cli lock release --file src/shared.py
   python -m claudeswarm.cli send --to agent-2 --type INFO --message "Lock released"
   ```

5. **Agent 2:** Acquire and proceed
   ```bash
   python -m claudeswarm.cli lock acquire --file src/shared.py --reason "Bug fix"
   # Now succeeds
   ```

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
