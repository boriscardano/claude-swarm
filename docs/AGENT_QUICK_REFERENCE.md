# Agent Quick Reference

This guide is for Claude Code agents working within the Claude Swarm coordination system.

## ✅ Commands That Work in Sandboxed Environments

These commands work reliably when called from Claude Code's Bash tool (sandboxed environment):

### Identity & Discovery
```bash
# Find out who you are
claudeswarm whoami

# See all active agents (read from registry)
claudeswarm list-agents
```

### Messaging
```bash
# Send message to specific agent
claudeswarm send-message <recipient-id> <TYPE> "<message>"
# Example: claudeswarm send-message agent-1 INFO "Ready to start!"

# Broadcast to all agents
claudeswarm broadcast-message <TYPE> "<message>"
# Example: claudeswarm broadcast-message QUESTION "Who's working on the API?"
```

**Message Types:** INFO, QUESTION, REVIEW-REQUEST, BLOCKED, COMPLETED, CHALLENGE, ACK

**Note:** Messages are delivered automatically via hook - you'll see them appear in your conversation!

### File Locking
```bash
# Acquire lock before editing
claudeswarm acquire-file-lock <filepath> [reason]
# Example: claudeswarm acquire-file-lock src/main.py "refactoring auth"

# Release lock after editing
claudeswarm release-file-lock <filepath>

# Check who has a lock
claudeswarm who-has-lock <filepath>

# List all locks
claudeswarm list-all-locks

# Clean up stale locks
claudeswarm cleanup-stale-locks
```

## ⚠️ Commands That DON'T Work in Sandbox

These require tmux socket access and will fail in Claude Code's sandboxed Bash tool:

```bash
# ❌ Don't use these from Claude Code:
claudeswarm discover-agents    # Use list-agents instead
claudeswarm onboard            # Run from regular terminal
```

## 📋 Typical Workflows

### Starting Work on a File
```bash
# 1. Check if anyone has a lock
claudeswarm who-has-lock src/config.py

# 2. Acquire lock (reason is optional)
claudeswarm acquire-file-lock src/config.py "adding new feature X"

# 3. If lock acquisition fails, handle the conflict
# Check who has the lock and coordinate with them
claudeswarm send-message <holder-agent-id> QUESTION "When will you release src/config.py?"

# 4. Do your work...
# (edit the file)

# 5. Release lock when done
claudeswarm release-file-lock src/config.py
```

### Coordinating with Other Agents
```bash
# 1. See who's active
claudeswarm list-agents

# 2. Send message to specific agent
claudeswarm send-message agent-1 QUESTION "Are you working on the API endpoints?"

# 3. Wait for response (appears automatically in your conversation)

# 4. Coordinate next steps
```

### Broadcasting Status Updates
```bash
# Let everyone know what you're doing
claudeswarm broadcast-message INFO "Starting work on user authentication module"

# Notify when task is complete
claudeswarm broadcast-message COMPLETED "Finished implementing user authentication module"

# Ask for help when blocked
claudeswarm broadcast-message BLOCKED "Need review on PR #42 before I can proceed"

# Challenge a decision or approach
claudeswarm broadcast-message CHALLENGE "The current API design might cause performance issues"
```

## 🔄 How Messages Are Delivered

1. **You send a message** → It's logged to `agent_messages.log`
2. **Before each prompt** → A hook automatically checks for new messages
3. **Messages appear automatically** → No manual checking needed!

You'll see messages formatted like this:
```
╔════════════════════════════════════════════════════════════════╗
║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║
╚════════════════════════════════════════════════════════════════╝

[2025-11-18T17:30:45] From: agent-1 (QUESTION)
  Are you working on the API endpoints?
```

## 🚫 Common Mistakes to Avoid

1. ❌ **Don't run `claudeswarm discover-agents` from Claude Code**
   - ✅ Use `claudeswarm list-agents` instead

2. ❌ **Don't forget to release file locks**
   - ✅ Always release locks immediately after editing

3. ❌ **Don't manually check messages with `check-messages`**
   - ✅ Messages appear automatically - just wait for them

4. ❌ **Don't skip lock acquisition for "quick edits"**
   - ✅ ALWAYS acquire locks before editing - prevents conflicts

## ⚡ Important Edge Cases & Limits

### Stale Lock Timeout
- **Default timeout:** 5 minutes (300 seconds)
- Locks older than this are considered stale and can be cleaned up
- Use `claudeswarm cleanup-stale-locks` to remove stale locks
- Configurable via `config.locking.stale_timeout`

```bash
# Clean up locks that have been held for more than 5 minutes
claudeswarm cleanup-stale-locks
```

### Rate Limiting
- **Default limit:** 10 messages per minute per agent
- Prevents message flooding and system overload
- Both `send-message` and `broadcast-message` count toward this limit
- If you exceed the limit, you'll get a `RateLimitExceeded` error
- Wait 60 seconds for the rate limit window to reset

**Best practice:** Consolidate related updates into single messages instead of sending many small messages.

### Agent ID Auto-Detection
- Most commands auto-detect your agent ID from the tmux pane
- The `--agent-id` flag is optional and rarely needed
- Auto-detection works when running commands from within an agent's tmux pane
- If auto-detection fails, you'll be prompted to provide the agent ID manually

```bash
# These are equivalent if you're running from agent-1's pane:
claudeswarm acquire-file-lock src/main.py "editing"
claudeswarm acquire-file-lock src/main.py "editing" --agent-id agent-1
```

### Lock Conflict Resolution
When you can't acquire a lock because another agent holds it:

```bash
# 1. Check who has the lock
claudeswarm who-has-lock src/config.py
# Output: Lock held by: agent-2 (Reason: refactoring, Since: 2025-11-18T15:30:00)

# 2. Contact the lock holder
claudeswarm send-message agent-2 QUESTION "How long will you need src/config.py?"

# 3. Wait for their response or check if the lock is stale
claudeswarm cleanup-stale-locks

# 4. Try acquiring again
claudeswarm acquire-file-lock src/config.py "my feature"
```

## 📚 More Information

- **Full Protocol:** See [AGENT_PROTOCOL.md](./AGENT_PROTOCOL.md)
- **Tutorial:** See [TUTORIAL.md](./TUTORIAL.md)
- **Integration Guide:** See [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)
