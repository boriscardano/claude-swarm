# Monitoring Dashboard Quick Start Guide

**For:** Claude Swarm users and developers
**Module:** `claudeswarm.monitoring`
**Author:** Agent-5

---

## TL;DR

```bash
# Start monitoring dashboard
$ claudeswarm start-monitoring

# Or in current terminal
$ claudeswarm start-monitoring --no-tmux
```

---

## What is it?

The Monitoring Dashboard provides **real-time visibility** into agent coordination activities. It shows:

- 📝 **Recent messages** between agents (with color coding)
- 👥 **Active agents** currently running
- 🔒 **File locks** being held
- ✉️ **Pending ACKs** awaiting response

Updates automatically every 2 seconds.

---

## Quick Start

### 1. Basic Usage

```bash
# Start in dedicated tmux pane (recommended)
$ claudeswarm start-monitoring

# Or run in current terminal
$ claudeswarm start-monitoring --no-tmux
```

Press **Ctrl+C** to exit.

### 2. With Filters

```bash
# Show only blocked messages
$ claudeswarm start-monitoring --filter-type BLOCKED

# Monitor specific agent
$ claudeswarm start-monitoring --filter-agent agent-0

# Combine filters
$ claudeswarm start-monitoring --filter-type QUESTION --filter-agent agent-1
```

### 3. Available Filters

**Message Types:**
- `BLOCKED` - Agent is blocked waiting for something
- `QUESTION` - Agent has a question
- `INFO` - Informational message
- `COMPLETED` - Task completed
- `REVIEW-REQUEST` - Code review requested
- `ACK` - Acknowledgment
- `CHALLENGE` - Agent disagrees/challenges

**Agent IDs:**
- Any agent ID (e.g., `agent-0`, `agent-1`, `agent-2`)

---

## Color Scheme

Messages are color-coded for easy scanning:

| Color | Message Type | Meaning |
|-------|--------------|---------|
| 🔴 **Red** | BLOCKED | Critical - needs attention |
| 🟡 **Yellow** | QUESTION, ACK | Needs response |
| 🟢 **Green** | COMPLETED | Success |
| 🔵 **Blue** | INFO, REVIEW-REQUEST | Informational |
| 🟣 **Purple** | CHALLENGE, LOCK | Coordination event |

---

## Dashboard Layout

```
┌─────────────────────────────────────────┐
│  === CLAUDE SWARM STATUS ===            │
│                                         │
│  Active Agents: 3                       │
│    • agent-0 (0:0.0)                   │
│    • agent-1 (0:0.1)                   │
│                                         │
│  Active Locks: 2                        │
│    • src/auth.py (agent-0, 45s)        │
│                                         │
│  Pending ACKs: 1                        │
│    • agent-0 → agent-1 (2 retries)     │
│                                         │
├─────────────────────────────────────────┤
│  RECENT MESSAGES                        │
├─────────────────────────────────────────┤
│                                         │
│  [14:28:12] agent-0 [INFO] Starting... │
│  [14:28:15] agent-1 [QUESTION] What... │
│  [14:28:45] agent-2 [BLOCKED] Need...  │
│                                         │
└─────────────────────────────────────────┘
```

---

## Troubleshooting

### "tmux is not available"
**Solution:** Install tmux or use `--no-tmux` flag
```bash
$ claudeswarm start-monitoring --no-tmux
```

### "No messages appearing"
**Solution:** Agents need to send messages first
```bash
# Run demo to create sample messages
$ python3 demo_monitoring.py

# Then start monitoring
$ claudeswarm start-monitoring --no-tmux
```

### "Module not found: claudeswarm"
**Solution:** Install the package
```bash
$ pip install -e .
# or
$ uv pip install -e .
```

### "Colors not showing"
**Solution:** Your terminal may not support ANSI colors. Most modern terminals (iTerm2, Terminal.app, Windows Terminal) support colors by default.

---

## Tips and Tricks

### 1. Run alongside agents
Open monitoring in a separate tmux pane while agents work:
```bash
# Terminal 1: Start agents
$ tmux new -s swarm

# Terminal 1: Split pane and start monitoring
$ claudeswarm start-monitoring
```

### 2. Focus on problems
Filter to blocked messages to see where agents need help:
```bash
$ claudeswarm start-monitoring --filter-type BLOCKED
```

### 3. Track specific agent
Watch a single agent's activity:
```bash
$ claudeswarm start-monitoring --filter-agent agent-0
```

### 4. Demo mode
Create sample data to test the dashboard:
```bash
$ python3 demo_monitoring.py
$ claudeswarm start-monitoring --no-tmux
```

---

## Python API

For programmatic access:

```python
from claudeswarm.monitoring import Monitor, MessageFilter, MessageType

# Create custom filter
msg_filter = MessageFilter(
    msg_types={MessageType.BLOCKED, MessageType.QUESTION}
)

# Create and run monitor
monitor = Monitor(
    log_path=Path("agent_messages.log"),
    refresh_interval=2.0,
    message_filter=msg_filter
)

monitor.run_dashboard()
```

---

## Requirements

- Python 3.12+
- claudeswarm package installed
- Terminal with ANSI color support
- (Optional) tmux for split-pane layout

---

## Getting Help

**Full Documentation:**
- `MONITORING_IMPLEMENTATION_SUMMARY.md` - Technical details
- `MONITORING_VISUAL_DEMO.md` - Visual examples
- `AGENT_5_FINAL_REPORT.md` - Complete report

**Command Help:**
```bash
$ claudeswarm start-monitoring --help
```

**Demo:**
```bash
$ python3 demo_monitoring.py
```

---

## Key Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+C` | Exit monitoring |
| `Ctrl+Z` | Suspend (then `fg` to resume) |

---

## Example Workflow

```bash
# 1. Start your Claude Swarm session
$ tmux new -s my-project

# 2. Launch monitoring dashboard
$ claudeswarm start-monitoring

# 3. Work in main pane while monitoring in side pane
# The dashboard updates automatically as agents communicate

# 4. When done, Ctrl+C to exit monitoring
```

---

**Quick Start Complete!**

For more details, see the full documentation files in the repository.
