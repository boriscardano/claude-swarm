# Claude Swarm Agent Protocol

**Version:** 1.0
**Last Updated:** 2025-11-07
**Audience:** Claude Code agents working on multi-agent projects

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Communication Rules](#communication-rules)
3. [File Locking Protocol](#file-locking-protocol)
4. [Acknowledgment Requirements](#acknowledgment-requirements)
5. [Coordination Patterns](#coordination-patterns)
6. [Best Practices](#best-practices)
7. [Examples](#examples)
8. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Prerequisites

- **tmux 3.0+** - Terminal multiplexer for agent isolation
- **Python 3.12+** - Runtime environment
- **uv** - Package manager (install: `curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Claude Swarm** - Installed in project: `uv sync`

### Quick Setup

```bash
# 1. In your tmux session, verify claudeswarm is installed
uv run claudeswarm discover-agents

# 2. Get your agent ID from the output
# You'll see: agent-0, agent-1, agent-2, etc.

# 3. Register your presence (automatic on first discovery)
# Your agent ID will be listed in ACTIVE_AGENTS.json

# 4. Ready! You can now coordinate with other agents
```

### Your First Message

```bash
# Send a message to another agent
uv run claudeswarm send-to-agent agent-1 INFO "Starting work on auth module"

# Broadcast to all agents
uv run claudeswarm broadcast-to-all INFO "Feature branch created: feature/auth-jwt"
```

---

## Communication Rules

### Message Types

Claude Swarm defines 7 standard message types:

| Type | Purpose | When to Use | Requires ACK? |
|------|---------|-------------|---------------|
| **QUESTION** | Ask for information | Need clarification or input | Optional |
| **REVIEW-REQUEST** | Request code review | PR ready, need approval | Recommended |
| **BLOCKED** | Indicate blockage | Cannot proceed without help | **Required** |
| **COMPLETED** | Announce completion | Task finished | Optional |
| **CHALLENGE** | Challenge decision | Disagree with approach | Optional |
| **INFO** | Share information | Status updates, FYI | No |
| **ACK** | Acknowledge receipt | Confirm message received | No |

### Message Format

All messages follow this format:

```
[AGENT-{id}][YYYY-MM-DD HH:MM:SS][TYPE]: content
```

**Example:**
```
[agent-2][2025-11-07 14:30:15][QUESTION]: What database schema are we using?
[agent-1][2025-11-07 14:30:45][INFO]: Using PostgreSQL with SQLAlchemy ORM
[agent-2][2025-11-07 14:31:00][ACK]: Thanks, proceeding with Postgres models
```

### Sending Messages

#### Direct Message (Point-to-Point)

```python
# Python API
from claudeswarm.messaging import send_message, MessageType

send_message(
    sender_id="agent-2",
    recipient_id="agent-1",
    message_type=MessageType.QUESTION,
    content="What database schema are we using?"
)
```

```bash
# CLI
uv run claudeswarm send-to-agent agent-1 QUESTION "What database schema are we using?"
```

#### Broadcast (To All Agents)

```python
# Python API
from claudeswarm.messaging import broadcast_message, MessageType

broadcast_message(
    sender_id="agent-2",
    message_type=MessageType.INFO,
    content="Starting work on auth module",
    exclude_self=True  # Don't send to yourself
)
```

```bash
# CLI
uv run claudeswarm broadcast-to-all INFO "Starting work on auth module"
```

### Rate Limiting

- **Limit:** 10 messages per agent per minute
- **Why:** Prevent message spam, ensure tmux stability
- **What happens:** Messages exceeding limit are dropped
- **Best practice:** Batch updates, use INFO sparingly

---

## File Locking Protocol

### CRITICAL RULE

**NEVER edit a file without acquiring its lock first.**

This is the most important rule in Claude Swarm. Violating it causes merge conflicts, data corruption, and agent coordination failures.

### Lock Lifecycle

```
┌─────────────────────────────────────────────────┐
│  1. Check if file is locked                     │
│     uv run claudeswarm who-has-lock src/auth.py │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│  2. Acquire lock (if available)                  │
│     uv run claudeswarm acquire-file-lock \       │
│       src/auth.py agent-2 "implementing JWT"     │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│  3. Edit the file                                │
│     [Make your changes safely]                   │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│  4. Release lock when done                       │
│     uv run claudeswarm release-file-lock \       │
│       src/auth.py agent-2                        │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│  5. Broadcast completion (optional)              │
│     uv run claudeswarm broadcast-to-all \        │
│       COMPLETED "Finished JWT implementation"    │
└─────────────────────────────────────────────────┘
```

### Acquiring Locks

```python
# Python API
from claudeswarm.locking import LockManager

manager = LockManager()
success, conflict = manager.acquire_lock(
    filepath="src/auth.py",
    agent_id="agent-2",
    reason="implementing JWT authentication"
)

if success:
    # Lock acquired, safe to edit
    edit_file("src/auth.py")
    manager.release_lock("src/auth.py", "agent-2")
else:
    # Lock conflict
    print(f"File locked by {conflict.current_holder}")
    print(f"Reason: {conflict.reason}")
    # Send message to lock holder
    send_message(
        sender_id="agent-2",
        recipient_id=conflict.current_holder,
        message_type=MessageType.QUESTION,
        content=f"When will you be done with {conflict.filepath}?"
    )
```

```bash
# CLI
uv run claudeswarm acquire-file-lock src/auth.py agent-2 "implementing JWT"
# ... edit file ...
uv run claudeswarm release-file-lock src/auth.py agent-2
```

### Handling Lock Conflicts

**When you encounter a lock conflict:**

1. **Don't wait silently** - Message the lock holder
2. **Ask for ETA** - "When will you finish?"
3. **Offer alternatives** - "Can I help with a different part?"
4. **Check lock age** - Locks older than 5 minutes are auto-released

```bash
# Check who has lock
uv run claudeswarm who-has-lock src/auth.py

# Output:
# Lock on: src/auth.py
#   Held by: agent-1
#   Locked at: 2025-11-07 14:25:00 UTC
#   Age: 120.5 seconds
#   Reason: implementing JWT authentication
```

### Glob Pattern Locking

You can lock multiple files with patterns:

```bash
# Lock all Python files in src/auth/
uv run claudeswarm acquire-file-lock "src/auth/*.py" agent-2 "refactoring auth module"

# Lock all test files
uv run claudeswarm acquire-file-lock "tests/**/*_test.py" agent-3 "updating tests"
```

**Warning:** Glob locks are checked symmetrically. If you try to lock `src/auth/jwt.py` while someone holds `src/auth/*.py`, it will conflict.

### Stale Lock Cleanup

- **Timeout:** 5 minutes
- **Auto-cleanup:** Stale locks are automatically released
- **Manual cleanup:** `uv run claudeswarm cleanup-stale-locks`

---

## Acknowledgment Requirements

### When to Use ACKs

Use acknowledgment-required messages when:

1. **Blocking others:** Your message blocks another agent's work
2. **Critical information:** Must confirm receipt (security, deployment)
3. **Task handoff:** Passing responsibility to another agent
4. **Coordination changes:** Sprint goals, deadlines, priorities

### Sending with ACK

```python
# Python API (when implemented)
from claudeswarm.ack import send_with_ack

send_with_ack(
    target="agent-1",
    msg_type="BLOCKED",
    content="Need auth.py changes before I can proceed",
    timeout=30  # seconds
)
```

```bash
# CLI (when implemented)
uv run claudeswarm send-with-ack agent-1 BLOCKED "Need auth.py changes before I can proceed"
```

### Acknowledging Messages

```python
# Python API (when implemented)
from claudeswarm.ack import acknowledge_message

acknowledge_message(
    msg_id="abc-123-def",
    agent_id="agent-1"
)
```

```bash
# CLI (when implemented)
uv run claudeswarm send-ack abc-123-def agent-1
```

### Retry and Escalation

If no ACK received within timeout:

1. **First retry:** 30 seconds (same timeout)
2. **Second retry:** 60 seconds (exponential backoff)
3. **Third retry:** 120 seconds
4. **Escalation:** Broadcast to ALL agents after 3 retries

**When escalated, any agent can respond.**

---

## Coordination Patterns

### Pattern 1: Code Review Workflow

```
Agent-3 (implements feature)
    │
    ├─► [COMPLETED] "Feature X ready for review"
    │
Agent-1 (reviewer)
    │
    ├─► [ACK] "Starting review"
    ├─► Acquires lock on feature files
    ├─► Reviews code
    ├─► [REVIEW-REQUEST] "Changes needed: ..."
    └─► Releases lock
    │
Agent-3 (addresses feedback)
    │
    ├─► Acquires lock
    ├─► Makes changes
    ├─► Releases lock
    ├─► [COMPLETED] "Feedback addressed"
    │
Agent-1 (approves)
    │
    └─► [COMPLETED] "Approved, ready to merge"
```

### Pattern 2: Parallel Development

```
Agent-0 (coordinator)
    │
    ├─► [INFO] "Sprint goal: Implement auth module"
    ├─► [INFO] "Tasks: JWT (agent-1), OAuth (agent-2), RBAC (agent-3)"
    │
Agent-1, Agent-2, Agent-3 (workers)
    │
    ├─► Each acquires locks on their files
    ├─► Work in parallel
    ├─► [COMPLETED] when done
    │
Agent-0 (integrator)
    │
    ├─► Reviews all completed work
    └─► [COMPLETED] "Auth module complete"
```

### Pattern 3: Blocking and Escalation

```
Agent-2 (blocked)
    │
    ├─► [BLOCKED][REQUIRES-ACK] "Need auth schema from Agent-1"
    │
    ├─► Waits 30 seconds...
    ├─► Retry #1
    ├─► Waits 60 seconds...
    ├─► Retry #2
    ├─► Waits 120 seconds...
    ├─► Retry #3
    │
    └─► [ESCALATED] Broadcast to ALL agents
        "Agent-1 unresponsive, need auth schema, can anyone help?"
    │
Agent-4 (responder)
    │
    └─► [INFO] "I have auth schema, sharing..."
```

### Pattern 4: Lock Contention Resolution

```
Agent-1 (working)
    │
    ├─► Acquires lock: src/auth.py
    │
Agent-2 (needs same file)
    │
    ├─► Tries to acquire lock: src/auth.py
    ├─► Lock conflict!
    ├─► [QUESTION] "Agent-1, when will you finish auth.py?"
    │
Agent-1 (responds)
    │
    ├─► [INFO] "Need 10 more minutes for JWT implementation"
    │
Agent-2 (waits or pivots)
    │
    ├─► [INFO] "OK, working on tests meanwhile"
    │
    └─► (10 minutes later)
    │
Agent-1 (releases)
    │
    ├─► Releases lock: src/auth.py
    ├─► [COMPLETED] "JWT done, auth.py available"
    │
Agent-2 (acquires)
    │
    └─► Acquires lock: src/auth.py
        └─► Continues work
```

---

## Automatic Message Delivery

### Overview

Claude Swarm supports automatic message delivery via Claude Code hooks. When configured,
new messages from other agents appear automatically in your conversation context - no
manual checking required.

### How It Works

1. A `UserPromptSubmit` hook fires before each prompt you send
2. The hook runs `claudeswarm check-messages --new-only --quiet`
3. New messages (if any) are injected into Claude's context
4. Messages are marked as read to prevent duplicates

### Setup

Run `claudeswarm init` to set up hooks automatically, or configure manually:

**1. Create the hook script (`.claude/hooks/check-for-messages.sh`):**

```bash
#!/bin/bash
set -euo pipefail
MESSAGES=$(timeout 5s claudeswarm check-messages --new-only --quiet --limit 5 2>/dev/null || echo "")
if [ -n "$MESSAGES" ]; then
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  printf '%s\n' "$MESSAGES"
  echo "Reply with: claudeswarm send-message <agent-id> INFO \"your message\""
  echo "───────────────────────────────────────────────────────────────"
fi
exit 0
```

**2. Configure Claude Code (`.claude/settings.json`):**

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

### Check Messages Flags

| Flag | Description |
|------|-------------|
| `--new-only` | Only show messages since last check (prevents duplicates) |
| `--quiet` | Compact one-line format: `[sender:TYPE] content` |
| `--limit N` | Show at most N messages (default: 10) |

### Example Output

When another agent sends you a message:

```
╔════════════════════════════════════════════════════════════════╗
║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║
╚════════════════════════════════════════════════════════════════╝
[agent-8:INFO] Hey, can you help review my changes to auth.py?
[agent-8:QUESTION] What's the best approach for error handling?
Reply with: claudeswarm send-message <agent-id> INFO "your message"
───────────────────────────────────────────────────────────────
```

---

## Best Practices

### DO

1. **Discover before messaging**
   ```bash
   uv run claudeswarm discover-agents
   # Check ACTIVE_AGENTS.json to see who's available
   ```

2. **Always acquire locks before editing**
   ```bash
   uv run claudeswarm acquire-file-lock src/file.py agent-id "reason"
   # EDIT
   uv run claudeswarm release-file-lock src/file.py agent-id
   ```

3. **Use specific message types**
   ```bash
   # Good
   uv run claudeswarm send-to-agent agent-1 REVIEW-REQUEST "Check PR #42"

   # Avoid
   uv run claudeswarm send-to-agent agent-1 INFO "Hey can you review my PR?"
   ```

4. **Broadcast important status updates**
   ```bash
   uv run claudeswarm broadcast-to-all COMPLETED "Auth module deployed to staging"
   ```

5. **Respond to BLOCKED messages immediately**
   ```bash
   # When you see [BLOCKED] message, drop everything and respond
   uv run claudeswarm send-to-agent agent-2 INFO "Unblocking you now..."
   ```

6. **Check for locks before starting work**
   ```bash
   uv run claudeswarm list-all-locks
   # See what's currently locked
   ```

7. **Release locks promptly**
   ```bash
   # Release as soon as you're done editing
   # Don't hold locks while testing or thinking
   ```

8. **Use descriptive lock reasons**
   ```bash
   # Good
   uv run claudeswarm acquire-file-lock src/auth.py agent-2 "implementing JWT token validation"

   # Bad
   uv run claudeswarm acquire-file-lock src/auth.py agent-2 "working"
   ```

### DON'T

1. **Don't edit files without locks**
   ```bash
   # WRONG - will cause conflicts!
   vim src/auth.py

   # RIGHT
   uv run claudeswarm acquire-file-lock src/auth.py agent-2 "fixing bug"
   vim src/auth.py
   uv run claudeswarm release-file-lock src/auth.py agent-2
   ```

2. **Don't spam messages**
   ```bash
   # WRONG - rate limit will block you
   for i in {1..20}; do
       uv run claudeswarm broadcast-to-all INFO "Still working..."
   done

   # RIGHT - batch updates
   uv run claudeswarm broadcast-to-all INFO "Status: 5/20 tests passing, investigating failures"
   ```

3. **Don't hold locks while idle**
   ```bash
   # WRONG
   uv run claudeswarm acquire-file-lock src/auth.py agent-2 "thinking"
   # ... think for 10 minutes ...

   # RIGHT
   # Think first, then acquire lock when ready to edit
   ```

4. **Don't ignore lock conflicts**
   ```bash
   # WRONG - silent waiting
   while ! uv run claudeswarm acquire-file-lock src/auth.py agent-2 "work"; do
       sleep 10
   done

   # RIGHT - communicate
   uv run claudeswarm acquire-file-lock src/auth.py agent-2 "work" || \
   uv run claudeswarm send-to-agent agent-1 QUESTION "ETA on auth.py?"
   ```

5. **Don't use INFO for critical messages**
   ```bash
   # WRONG
   uv run claudeswarm send-to-agent agent-1 INFO "Deploying to production in 5 minutes!"

   # RIGHT
   uv run claudeswarm broadcast-to-all BLOCKED "URGENT: Need approval before production deploy"
   ```

6. **Don't forget to release locks**
   ```bash
   # WRONG - lock held forever
   uv run claudeswarm acquire-file-lock src/auth.py agent-2 "editing"
   vim src/auth.py
   # ... forget to release ...

   # RIGHT - always release
   uv run claudeswarm acquire-file-lock src/auth.py agent-2 "editing"
   vim src/auth.py
   uv run claudeswarm release-file-lock src/auth.py agent-2
   ```

---

## Examples

### Example 1: Starting a New Feature

```bash
# 1. Check available agents
uv run claudeswarm discover-agents

# 2. Announce your work
uv run claudeswarm broadcast-to-all INFO "Starting feature: JWT authentication"

# 3. Check if files are locked
uv run claudeswarm who-has-lock src/auth.py
uv run claudeswarm who-has-lock src/models/user.py

# 4. Acquire locks
uv run claudeswarm acquire-file-lock src/auth.py agent-2 "implementing JWT"
uv run claudeswarm acquire-file-lock src/models/user.py agent-2 "adding token fields"

# 5. Do your work
vim src/auth.py
vim src/models/user.py

# 6. Release locks
uv run claudeswarm release-file-lock src/auth.py agent-2
uv run claudeswarm release-file-lock src/models/user.py agent-2

# 7. Announce completion
uv run claudeswarm broadcast-to-all COMPLETED "JWT authentication implemented, ready for review"
```

### Example 2: Responding to a Review Request

```bash
# You receive:
# [agent-3][2025-11-07 15:00:00][REVIEW-REQUEST]: Please review PR #42 - OAuth integration

# 1. Acknowledge
uv run claudeswarm send-to-agent agent-3 ACK "Starting review of PR #42"

# 2. Acquire locks on files to review
uv run claudeswarm acquire-file-lock "src/oauth/*.py" agent-1 "reviewing PR #42"

# 3. Review the code
# ... check files, run tests ...

# 4. Provide feedback
uv run claudeswarm send-to-agent agent-3 REVIEW-REQUEST "PR #42: Please add error handling for token expiration"

# 5. Release locks
uv run claudeswarm release-file-lock "src/oauth/*.py" agent-1

# 6. Wait for updates, then approve
# (after agent-3 makes changes)
uv run claudeswarm send-to-agent agent-3 COMPLETED "PR #42 approved, ready to merge"
```

### Example 3: Handling a Lock Conflict

```bash
# You try to acquire a lock
uv run claudeswarm acquire-file-lock src/database.py agent-4 "adding migrations"

# Output:
# Lock conflict on: src/database.py
#   Currently held by: agent-2
#   Locked at: 2025-11-07 14:55:00 UTC
#   Reason: refactoring schema

# 1. Check lock age
uv run claudeswarm who-has-lock src/database.py
# Age: 180.5 seconds (3 minutes)

# 2. Message the lock holder
uv run claudeswarm send-to-agent agent-2 QUESTION "How much longer on database.py? I need to add migrations"

# 3. Wait for response
# [agent-2][2025-11-07 15:05:00][INFO]: Need 5 more minutes for schema refactor

# 4. Work on something else meanwhile
uv run claudeswarm send-to-agent agent-2 ACK "OK, working on tests meanwhile"

# 5. Try again later
# (5 minutes later)
uv run claudeswarm acquire-file-lock src/database.py agent-4 "adding migrations"
# Success!
```

### Example 4: Coordinating a Multi-Agent Feature

```bash
# Agent-0 (coordinator)
uv run claudeswarm broadcast-to-all INFO "New sprint: E-commerce checkout system"
uv run claudeswarm broadcast-to-all INFO "Tasks: Cart (agent-1), Payment (agent-2), Shipping (agent-3)"

# Agent-1 (cart)
uv run claudeswarm send-to-agent agent-0 ACK "Starting cart implementation"
uv run claudeswarm acquire-file-lock "src/cart/*.py" agent-1 "implementing cart"
# ... work ...
uv run claudeswarm release-file-lock "src/cart/*.py" agent-1
uv run claudeswarm send-to-agent agent-0 COMPLETED "Cart complete"

# Agent-2 (payment)
uv run claudeswarm send-to-agent agent-0 ACK "Starting payment integration"
uv run claudeswarm acquire-file-lock "src/payment/*.py" agent-2 "implementing payment"
# ... work ...
uv run claudeswarm release-file-lock "src/payment/*.py" agent-2
uv run claudeswarm send-to-agent agent-0 COMPLETED "Payment complete"

# Agent-3 (shipping)
uv run claudeswarm send-to-agent agent-0 ACK "Starting shipping calculator"
uv run claudeswarm acquire-file-lock "src/shipping/*.py" agent-3 "implementing shipping"
# ... work ...
uv run claudeswarm release-file-lock "src/shipping/*.py" agent-3
uv run claudeswarm send-to-agent agent-0 COMPLETED "Shipping complete"

# Agent-0 (integration)
uv run claudeswarm broadcast-to-all REVIEW-REQUEST "All components ready, requesting integration review"
```

---

## Troubleshooting

### Problem: "Rate limit exceeded"

**Symptom:** Your messages aren't being sent

**Cause:** Sent more than 10 messages in 60 seconds

**Solution:**
```bash
# Wait 60 seconds, then retry
sleep 60
uv run claudeswarm send-to-agent agent-1 INFO "Your message"

# Better: Batch your updates
uv run claudeswarm broadcast-to-all INFO "Status update: Feature 1 done, Feature 2 in progress, Feature 3 blocked"
```

### Problem: "Lock conflict" on every file

**Symptom:** Can't acquire any locks

**Cause:** Another agent has glob pattern lock

**Solution:**
```bash
# Check all locks
uv run claudeswarm list-all-locks

# You might see:
#   src/**/*.py [Held by: agent-1] [Reason: mass refactoring]

# Message the holder
uv run claudeswarm send-to-agent agent-1 QUESTION "Can you release the glob lock? I need to work on src/auth.py"
```

### Problem: "Agent not found in registry"

**Symptom:** Message delivery fails

**Cause:** Agent registry is stale or recipient is offline

**Solution:**
```bash
# Refresh agent registry
uv run claudeswarm discover-agents

# Check active agents
uv run claudeswarm list-agents

# If agent is offline, broadcast instead
uv run claudeswarm broadcast-to-all QUESTION "Anyone know about the auth module?"
```

### Problem: Lock held for >5 minutes

**Symptom:** Waiting forever for lock

**Cause:** Agent crashed or forgot to release

**Solution:**
```bash
# Check lock age
uv run claudeswarm who-has-lock src/auth.py
# Age: 320.0 seconds (5+ minutes)

# Stale locks are auto-cleaned, just retry
uv run claudeswarm acquire-file-lock src/auth.py agent-2 "continuing work"
# Should succeed now

# Or manually cleanup all stale locks
uv run claudeswarm cleanup-stale-locks
```

### Problem: Messages not appearing in terminal

**Symptom:** Not seeing messages from other agents

**Cause:** tmux send-keys isn't working or pane is wrong

**Solution:**
```bash
# Verify your pane is active
tmux list-panes -a | grep $(ps -o ppid= -p $$)

# Check agent registry
cat ACTIVE_AGENTS.json

# Test message to yourself
uv run claudeswarm send-to-agent agent-0 INFO "Test message"
```

### Problem: Can't start monitoring

**Symptom:** `start-monitoring` command fails

**Cause:** Monitoring not yet implemented

**Solution:**
```bash
# Manual monitoring: tail message log
tail -f agent_messages.log | jq .

# Watch agent registry
watch -n 2 'uv run claudeswarm list-agents'

# Watch locks
watch -n 2 'uv run claudeswarm list-all-locks'
```

### Getting Help

1. **Check logs:** `tail -f agent_messages.log`
2. **Check registry:** `cat ACTIVE_AGENTS.json`
3. **Check locks:** `ls -la .agent_locks/`
4. **Ask other agents:** Broadcast a QUESTION message
5. **Consult docs:** See [docs/troubleshooting.md](docs/troubleshooting.md)

---

## Quick Reference Card

### Essential Commands

```bash
# Discovery
uv run claudeswarm discover-agents
uv run claudeswarm list-agents

# Messaging
uv run claudeswarm send-to-agent <target> <type> "<message>"
uv run claudeswarm broadcast-to-all <type> "<message>"

# Locking
uv run claudeswarm acquire-file-lock <file> <agent-id> "<reason>"
uv run claudeswarm release-file-lock <file> <agent-id>
uv run claudeswarm who-has-lock <file>
uv run claudeswarm list-all-locks

# Maintenance
uv run claudeswarm cleanup-stale-locks
```

### Message Type Quick Reference

- **INFO** - Status updates, announcements
- **QUESTION** - Ask for information
- **REVIEW-REQUEST** - Request code review
- **BLOCKED** - Cannot proceed (use with ACK)
- **COMPLETED** - Task finished
- **CHALLENGE** - Disagree with approach
- **ACK** - Acknowledge receipt

### Lock Workflow

```
Check → Acquire → Edit → Release → Announce
```

### When in Doubt

1. **Discover** agents first
2. **Acquire** locks before editing
3. **Communicate** early and often
4. **Release** locks promptly
5. **Broadcast** completion

---

**Remember:** Communication and coordination prevent conflicts. When in doubt, send a message or acquire a lock. It's better to over-communicate than to cause a merge conflict!
