# Claude Swarm Integration Guide

This guide explains how to safely integrate Claude Swarm into your existing project.

## Table of Contents

1. [Installation Methods](#installation-methods)
2. [Git Safety](#git-safety)
3. [Quick Setup](#quick-setup)
4. [Agent Onboarding](#agent-onboarding)
5. [Best Practices](#best-practices)

---

## Installation Methods

There are three ways to use Claude Swarm with your project:

### Method 1: Package Installation (Recommended)

Install directly from GitHub as a Python package:

```bash
cd ~/work/your-project
pip install git+https://github.com/borisbanach/claude-swarm.git

# Or with uv
uv pip install git+https://github.com/borisbanach/claude-swarm.git
```

**Pros:**
- No git nesting issues
- Clean project structure
- Easy updates via pip/uv
- Works across all your projects

**Cons:**
- Cannot modify claude-swarm code easily

### Method 2: Clone Outside Project (Development)

Clone claude-swarm in a separate location and install in editable mode:

```bash
# Clone outside your project
cd ~/tools  # or any directory outside your project
git clone https://github.com/borisbanach/claude-swarm.git
cd claude-swarm

# Install in editable mode
pip install -e ".[dev]"

# Now use in any project
cd ~/work/your-project
claudeswarm discover-agents
```

**Pros:**
- Can modify claude-swarm code
- No git nesting issues
- Works across all projects

**Cons:**
- Need to manage separate directory

### Method 3: Clone Inside Project (Not Recommended)

**⚠️ WARNING:** This method requires extra care to avoid git issues.

```bash
cd ~/work/your-project
git clone https://github.com/borisbanach/claude-swarm.git
cd claude-swarm
pip install -e .
```

**Pros:**
- Project-specific installation
- Can modify code per-project

**Cons:**
- Risk of accidentally committing nested repo
- Requires careful .gitignore management
- More complex setup

If you must use this method, see [Git Safety](#git-safety) section below.

---

## Git Safety

### Automatic Protection

Git provides built-in protection against nested repositories:

- When you clone claude-swarm inside your project, Git recognizes the nested `.git` directory
- Running `git add .` in the parent project will **NOT** stage claude-swarm's files
- The nested repo appears as an untracked directory (but not its contents)

Example:
```bash
# In your project root
$ git status
Untracked files:
  claude-swarm/    # Shown as directory, not individual files
```

### Additional Protection Steps

1. **Add to Parent .gitignore (Recommended)**

Copy the entries from `.gitignore.template` to your project's `.gitignore`:

```bash
# In your project root
cat claude-swarm/.gitignore.template >> .gitignore
```

Or manually add:
```gitignore
# Claude Swarm
claude-swarm/

# Claude Swarm coordination files
.agent_locks/
ACTIVE_AGENTS.json
PENDING_ACKS.json
agent_messages.log
COORDINATION.md
```

2. **Verify Exclusion**

Check that claude-swarm won't be committed:
```bash
git status --ignored
# Should show claude-swarm/ as ignored
```

3. **Runtime Files**

Claude Swarm creates several runtime files during operation:
- `.agent_locks/` - Lock files for file coordination
- `ACTIVE_AGENTS.json` - Registry of discovered agents
- `PENDING_ACKS.json` - Pending acknowledgments
- `agent_messages.log` - Message delivery log
- `COORDINATION.md` - Shared coordination workspace

These files are already in claude-swarm's `.gitignore`, but you should add them to your project's `.gitignore` to be safe.

---

## Quick Setup

Here's the fastest way to get started:

### 1. Install Claude Swarm

```bash
# Choose your preferred method (Method 1 recommended)
pip install git+https://github.com/borisbanach/claude-swarm.git
```

### 2. Update Your .gitignore

```bash
# In your project root
cat << 'EOF' >> .gitignore

# Claude Swarm coordination files
.agent_locks/
ACTIVE_AGENTS.json
PENDING_ACKS.json
agent_messages.log
COORDINATION.md
EOF
```

### 3. Set Up tmux Session

```bash
# Create tmux session for your project
tmux new -s myproject

# Split into multiple panes
# Press: Ctrl+b "  (split horizontally)
# Press: Ctrl+b %  (split vertically)
# Press: Ctrl+b arrow-keys (navigate between panes)
```

### 4. Launch Claude Code Agents

In each tmux pane:
```bash
cd ~/work/your-project
claude
```

### 5. Discover Agents

In any pane:
```bash
claudeswarm discover-agents
```

### 6. Onboard All Agents

Use the automated onboarding script:
```bash
claudeswarm onboard
# or
bin/onboard-agents
```

All agents will receive standardized onboarding messages explaining the coordination system.

---

## Agent Onboarding

Once agents are discovered, they need to know about the coordination system.

### Automated Onboarding

The easiest way is to use the built-in onboarding command:

```bash
claudeswarm onboard
```

This broadcasts standardized messages to all agents explaining:
- The coordination protocol
- Available commands
- How to send messages
- How to use file locks
- Where to find documentation

### Manual Onboarding

If you prefer to customize the onboarding messages:

```bash
# Discover agents first
claudeswarm discover-agents

# Send custom welcome messages
claudeswarm broadcast-to-all INFO "=== Multi-Agent Coordination Active ==="
claudeswarm broadcast-to-all INFO "Protocol: Always acquire locks before editing files"
claudeswarm broadcast-to-all INFO "Commands: claudeswarm --help"
claudeswarm broadcast-to-all INFO "Docs: See AGENT_PROTOCOL.md for full protocol"
```

### Onboarding Message Content

The standard onboarding includes:
1. **System activation notice** - Agents know coordination is available
2. **Protocol summary** - Key rules (lock before edit, etc.)
3. **Command reference** - Essential commands
4. **Active agent list** - Who else is working
5. **Documentation links** - Where to learn more

---

## Best Practices

### Project Structure

Recommended structure when using Claude Swarm:

```
your-project/
├── .git/
├── .gitignore          # Include Claude Swarm entries
├── src/
├── tests/
├── .agent_locks/       # Created at runtime (gitignored)
├── ACTIVE_AGENTS.json  # Created at runtime (gitignored)
├── agent_messages.log  # Created at runtime (gitignored)
└── COORDINATION.md     # Created at runtime (gitignored)

# Claude Swarm installed elsewhere or as package
```

### tmux Session Management

1. **One session per project**
   ```bash
   tmux new -s project-name
   ```

2. **Name your panes** (optional but helpful)
   ```bash
   # In each pane
   printf '\033]2;%s\033\\' 'Agent-0-Backend'
   ```

3. **Save your layout** for reuse
   ```bash
   # After setting up panes
   tmux list-windows -F "#{window_layout}"
   # Save the output to restore later
   ```

### Coordination Workflow

1. **Start of session:**
   ```bash
   claudeswarm discover-agents
   claudeswarm onboard
   ```

2. **During work:**
   ```bash
   # Always lock before editing
   claudeswarm lock acquire --file src/auth.py --reason "implementing JWT"

   # Edit the file

   # Release immediately after
   claudeswarm lock release --file src/auth.py
   ```

3. **Communication:**
   ```bash
   # Direct messages for specific questions
   claudeswarm send-to-agent agent-1 QUESTION "What database schema are you using?"

   # Broadcasts for team-wide info
   claudeswarm broadcast-to-all COMPLETED "Authentication feature complete"
   ```

4. **End of session:**
   ```bash
   # Clean up stale locks
   claudeswarm cleanup-stale-locks
   ```

### Integration with CI/CD

You can use Claude Swarm in automated testing:

```yaml
# .github/workflows/multi-agent-test.yml
name: Multi-Agent Testing

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Install dependencies
        run: |
          pip install git+https://github.com/borisbanach/claude-swarm.git
          sudo apt-get install tmux

      - name: Run multi-agent tests
        run: |
          tmux new-session -d -s ci
          # Your test commands here
```

### Troubleshooting

**Issue: "No agents discovered"**

Solution:
```bash
# Verify tmux is running
echo $TMUX  # Should output session info

# Verify Claude Code processes
ps aux | grep claude

# Try verbose discovery
claudeswarm discover-agents --verbose
```

**Issue: "Lock conflicts everywhere"**

Solution:
```bash
# Check for glob pattern locks
claudeswarm lock list

# Clean up stale locks
claudeswarm cleanup-stale-locks
```

**Issue: "Messages not appearing"**

Solution:
```bash
# Test tmux send-keys directly
tmux list-panes -a
tmux send-keys -t SESSION:PANE 'echo "test"' Enter

# Check message log
tail -f agent_messages.log
```

---

## Security Considerations

1. **Message Log Contains Sensitive Info**
   - `agent_messages.log` contains all inter-agent communication
   - Add to `.gitignore` (already included in template)
   - Consider encrypting or deleting after sessions

2. **Lock Files May Contain Paths**
   - `.agent_locks/*.lock` files contain file paths and agent IDs
   - Ensure `.agent_locks/` is gitignored
   - Clean up after sessions: `rm -rf .agent_locks/`

3. **Coordination File**
   - `COORDINATION.md` may contain sprint goals and task details
   - Decide if you want to commit this (could be useful for team history)
   - If not, add to `.gitignore`

---

## Getting Help

- **Full Protocol**: See [AGENT_PROTOCOL.md](AGENT_PROTOCOL.md)
- **Tutorial**: See [TUTORIAL.md](TUTORIAL.md)
- **API Reference**: See [docs/api-reference.md](api-reference.md)
- **Quick Reference**: See [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- **Examples**: See [examples/README.md](../examples/README.md)

For issues and contributions:
- GitHub Issues: https://github.com/borisbanach/claude-swarm/issues
- GitHub Repo: https://github.com/borisbanach/claude-swarm

---

## Summary

**Recommended Setup:**

1. Install as package: `pip install git+https://github.com/borisbanach/claude-swarm.git`
2. Update `.gitignore` with coordination files
3. Create tmux session with multiple panes
4. Launch Claude Code in each pane
5. Run `claudeswarm discover-agents`
6. Run `claudeswarm onboard`
7. Start coordinating!

**Remember:**
- ALWAYS acquire locks before editing
- Use specific message types
- Keep COORDINATION.md updated
- Clean up stale locks regularly

Happy coordinating! 🚀
