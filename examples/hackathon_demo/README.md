# E2B Hackathon Demo: Multi-Agent Collaborative Development

This demo showcases Claude Swarm's ability to coordinate multiple AI agents to collaboratively develop features on a real GitHub repository.

## What This Demo Shows

**Multi-Agent Coordination**: 4 agents working together with different roles:
- 🧑‍💼 **Agent 0 (Project Manager)**: Clones repo, analyzes codebase, delegates tasks
- ⚙️ **Agent 1 (Backend Developer)**: Implements backend logic
- 🎨 **Agent 2 (Frontend Developer)**: Implements UI changes
- 🧪 **Agent 3 (QA Engineer)**: Writes tests, validates, and pushes to GitHub

**E2B Integration**: All agents run in isolated E2B sandboxes with:
- Pre-installed tools (git, tmux, Claude Code CLI)
- MCP server access (GitHub, filesystem, etc.)
- Secure, scalable cloud execution

**Real-World Utility**: Agents collaborate on actual GitHub repositories, demonstrating:
- True parallel execution (not sequential)
- Inter-agent communication and synchronization
- Git operations (clone, commit, push, PR creation)
- Production-ready workflows

## Quick Start

### 1. Deploy to E2B Cloud

```bash
# Deploy 4 agents to E2B with GitHub MCP
claudeswarm cloud deploy --agents 4 --mcps github,filesystem

# The output will show:
# ✓ Sandbox created: <sandbox-id>
# ✓ Dependencies installed
# ✓ Tmux session created with 4 panes
# ✓ MCPs attached: github, filesystem
```

### 2. Connect to the Sandbox

```bash
# Connect to the interactive shell
claudeswarm cloud shell

# Or use E2B CLI directly:
e2b sandbox connect <sandbox-id>
```

### 3. Run the Demo Workflow

Inside the E2B sandbox, each agent runs in its own tmux pane:

```bash
# In tmux pane 0 (Project Manager):
claudeswarm run-collaborative-dev \
  --repo https://github.com/yourusername/demo-app \
  --feature "Add user authentication with JWT" \
  --branch feature/auth

# Agents 1-3 automatically receive tasks and execute them in parallel
```

### 4. Watch the Magic Happen

Navigate between tmux panes to watch each agent work:
- `Ctrl+b` + arrow keys to switch panes
- `Ctrl+b` + `z` to zoom into a pane

You'll see:
- **Pane 0**: PM analyzing repo and broadcasting tasks
- **Pane 1**: Backend dev implementing auth logic
- **Pane 2**: Frontend dev creating login UI
- **Pane 3**: QA writing tests and committing changes

## 2-Minute Demo Script

### Scene 1: The Problem (0:00-0:20)

**Narration**:
> "Building AI agents is hard. Coordinating multiple agents is even harder. Most frameworks run locally, can't scale, and struggle with real-world tools. We built Claude Swarm to solve this."

**Visual**: Show terminal, maybe a diagram of the challenge

### Scene 2: Deployment (0:20-0:40)

**Command**:
```bash
claudeswarm cloud deploy --agents 4 --mcps github,filesystem
```

**Narration**:
> "In 30 seconds, we deploy 4 Claude agents to E2B cloud, each with access to GitHub and filesystem MCPs."

**Visual**: Show deployment output, highlight key steps

### Scene 3: The Workflow (0:40-1:30)

**Command**:
```bash
# Inside E2B sandbox
claudeswarm run-collaborative-dev \
  --repo https://github.com/demo/app \
  --feature "Add dark mode support"
```

**Narration**:
> "Now watch 4 agents collaborate to add a new feature to a real repository:
> - Agent 0 clones the repo and delegates tasks
> - Agent 1 implements backend changes
> - Agent 2 creates the UI
> - Agent 3 writes tests and pushes to GitHub
> All working in parallel, coordinating through our messaging system."

**Visual**: Split screen showing all 4 tmux panes, maybe sped up

### Scene 4: The Result (1:30-2:00)

**Visual**: Show:
- GitHub commit
- Tests passing
- New branch created
- (Optional) Quick look at the diff

**Narration**:
> "In under 2 minutes, four agents collaborated to implement a complete feature. This is impossible with single-agent systems. Claude Swarm + E2B + MCP Hub = production-ready multi-agent coordination. Try it yourself at github.com/aspire11/claude-swarm"

## Example Scenarios

### Scenario 1: Add Authentication

```bash
claudeswarm run-collaborative-dev \
  --repo https://github.com/yourusername/api-server \
  --feature "Add JWT authentication middleware" \
  --branch feature/jwt-auth
```

**What happens**:
1. PM analyzes the FastAPI/Express codebase
2. Backend dev adds auth middleware
3. Frontend dev adds login form
4. QA adds integration tests

### Scenario 2: Implement Dark Mode

```bash
claudeswarm run-collaborative-dev \
  --repo https://github.com/yourusername/web-app \
  --feature "Add dark mode theme toggle" \
  --branch feature/dark-mode
```

**What happens**:
1. PM identifies CSS/React components
2. Backend dev adds theme preference API
3. Frontend dev implements theme switcher
4. QA adds visual regression tests

### Scenario 3: Add Monitoring

```bash
claudeswarm run-collaborative-dev \
  --repo https://github.com/yourusername/service \
  --feature "Add Prometheus metrics endpoint" \
  --branch feature/metrics
```

**What happens**:
1. PM analyzes service architecture
2. Backend dev adds metrics collection
3. Frontend dev creates metrics dashboard
4. QA validates metric accuracy

## Architecture

```
┌─────────────────────────────────────────────────┐
│            E2B Cloud Sandbox                    │
│                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌────┐│
│  │ Agent 0 │  │ Agent 1 │  │ Agent 2 │  │ A3 ││
│  │   PM    │  │ Backend │  │Frontend │  │ QA ││
│  └────┬────┘  └────┬────┘  └────┬────┘  └─┬──┘│
│       │            │            │          │   │
│       └────────────┴────────────┴──────────┘   │
│                     │                          │
│           ┌─────────▼─────────┐                │
│           │ Message Bus       │                │
│           │ (File-based)      │                │
│           └─────────┬─────────┘                │
│                     │                          │
│           ┌─────────▼─────────┐                │
│           │ MCP Servers       │                │
│           │ - GitHub          │                │
│           │ - Filesystem      │                │
│           │ - (+ more)        │                │
│           └───────────────────┘                │
└─────────────────────────────────────────────────┘
```

## Technical Highlights

### Why This Impresses Judges

1. **True Multi-Agent Coordination**
   - Not sequential task execution
   - Real parallel work with synchronization
   - Agent-to-agent communication protocol

2. **Production-Ready**
   - Runs in E2B cloud sandboxes
   - Uses Docker MCP Hub for tools
   - Proper error handling and recovery

3. **Real-World Utility**
   - Works with actual GitHub repos
   - Demonstrates practical use cases
   - Could be used in production today

4. **Technical Excellence**
   - Clean, modular architecture
   - Proper async/await patterns
   - Comprehensive workflow system

### MCPs Used

- **GitHub MCP**: Clone repos, commit, push, create PRs
- **Filesystem MCP**: Read/write code files
- *Optional*: Exa, Perplexity for research; Slack for notifications

## Tips for Recording Demo

1. **Pre-setup**:
   - Have a test repo ready
   - Pre-deploy to E2B to avoid waiting
   - Test the workflow once to ensure smooth recording

2. **Camera Work**:
   - Use terminal recording tool (asciinema, ttyrec)
   - Zoom in on important parts
   - Use split-screen for multiple panes

3. **Pacing**:
   - Speed up deployment (show it works, but don't waste time)
   - Show agents working in real-time (this is the impressive part)
   - Quickly show the result (don't dwell)

4. **Backup Plan**:
   - Record the workflow in advance
   - Have screenshots ready
   - Test everything multiple times

## Questions?

See the main [Claude Swarm README](../../README.md) or open an issue at [github.com/aspire11/claude-swarm](https://github.com/aspire11/claude-swarm).
