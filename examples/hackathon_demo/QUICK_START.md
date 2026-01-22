# Quick Start: Hackathon Demo (Simplified)

## The Simplest Way to Demo

For the hackathon, we'll use **git commands directly** instead of MCP servers. This makes the demo work immediately without complex setup.

### 1. Deploy to E2B

```bash
claudeswarm cloud deploy --agents 4
```

Note: We removed `--mcps` flag since we'll use git directly

### 2. Connect to Sandbox

```bash
claudeswarm cloud shell
```

### 3. Prepare a Test Repo

Inside the E2B sandbox:

```bash
# Create a simple test repository
cd /workspace
mkdir demo-app
cd demo-app
git init
git config user.name "Claude Swarm"
git config user.email "swarm@claude.ai"

# Create initial files
cat > README.md << 'EOF'
# Demo App
Simple app for Claude Swarm demo
EOF

cat > app.py << 'EOF'
def greet(name):
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("World"))
EOF

git add .
git commit -m "Initial commit"
```

### 4. Run the Demo

In each tmux pane (or use `start_demo.sh`):

```bash
# Pane 0 (PM):
python /workspace/claude-swarm/examples/hackathon_demo/run_demo.py \
  --agent 0 \
  --repo /workspace/demo-app \
  --feature "Add user authentication"

# Panes 1, 2, 3 will automatically pick up tasks from the message bus
```

### 5. What Happens

1. **Agent 0 (PM)**: Analyzes the codebase and creates task breakdown
2. **Agent 1 (Backend)**: Adds authentication functions to `app.py`
3. **Agent 2 (Frontend)**: Creates a simple UI (if applicable)
4. **Agent 3 (QA)**: Writes tests and commits everything

### Alternative: Simple Shell Demo

For the 2-minute video, you can show it even more simply:

```bash
# In each pane, just show agents working
# Pane 0: PM discovers other agents and broadcasts tasks
claudeswarm discover-agents

# Pane 1-3: Agents receive messages and respond
claudeswarm check-messages
```

## For Video Recording

### What to Show

**Scene 1** (15 sec): Deploy
```bash
claudeswarm cloud deploy --agents 4
```

**Scene 2** (10 sec): Connect
```bash
e2b sandbox connect <sandbox-id>
```

**Scene 3** (60 sec): Agents Working
- Show tmux with 4 panes
- Each agent has a role displayed
- Messages flowing between agents
- Code being written

**Scene 4** (15 sec): Result
```bash
git log --oneline
git diff
```

## Simplified Demo Script

Instead of full collaborative development, show **message coordination**:

```bash
# Pane 0 (Leader):
claudeswarm broadcast-message \
  --message '{"type":"task","action":"analyze","target":"app.py"}'

# Panes 1-3 (Workers):
# Watch messages appear
claudeswarm check-messages
```

This shows:
- ✅ Multi-agent coordination
- ✅ E2B sandbox execution
- ✅ Real-time messaging
- ✅ Practical use case

## What to Emphasize

1. **E2B Integration**: "Running in isolated E2B sandbox"
2. **True Coordination**: "Agents communicate via message bus"
3. **Parallel Execution**: "All 4 agents working simultaneously"
4. **Production-Ready**: "Built for real-world team collaboration"

## Why This Works for Hackathon

- ✅ Shows E2B sandbox usage (REQUIRED)
- ✅ Shows real coordination (not fake)
- ✅ Simple to record (no complex setup)
- ✅ Actually works (tested)
- ✅ Impressive visual (4 panes working together)

The judges care about:
1. Does it use E2B? **YES**
2. Is it innovative? **YES** (multi-agent coordination)
3. Does it work? **YES** (simple, reliable demo)
4. Is it useful? **YES** (agent teamwork)

You don't NEED MCP servers for a winning demo. The multi-agent coordination itself is the innovation!
