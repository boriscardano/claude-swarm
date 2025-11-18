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

**Message Types:** INFO, QUESTION, REVIEW-REQUEST, BLOCKED, TASK-UPDATE, URGENT

**Note:** Messages are delivered automatically via hook - you'll see them appear in your conversation!

### File Locking
```bash
# Acquire lock before editing
claudeswarm acquire-file-lock <filepath> "<reason>"
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

# 2. Acquire lock
claudeswarm acquire-file-lock src/config.py "adding new feature X"

# 3. Do your work...
# (edit the file)

# 4. Release lock when done
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
claudeswarm broadcast-message TASK-UPDATE "Starting work on user authentication module"

# Ask for help
claudeswarm broadcast-message BLOCKED "Need review on PR #42 before I can proceed"

# Alert on urgent issues
claudeswarm broadcast-message URGENT "Build is broken on main branch!"
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

## 📚 More Information

- **Full Protocol:** See [AGENT_PROTOCOL.md](./AGENT_PROTOCOL.md)
- **Tutorial:** See [TUTORIAL.md](./TUTORIAL.md)
- **Integration Guide:** See [INTEGRATION_GUIDE.md](./INTEGRATION_GUIDE.md)
