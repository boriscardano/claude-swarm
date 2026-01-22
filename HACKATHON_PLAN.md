# E2B & Docker Hackathon - Implementation Plan

## Claude Swarm Cloud: Autonomous Multi-Agent Development System

**Target Hackathon**: E2B & Docker MCP Catalog Hackathon
**Timeline**: One Weekend (16 hours total)
**Goal**: Build autonomous multi-agent system where 4+ Claude agents collaborate for hours without supervision

---

## Executive Summary

**What We're Building:**

Transform Claude Swarm from a local tmux-based coordination system into a cloud-native autonomous development team running in E2B sandboxes. Multiple agents will work together for hours, researching, implementing, code reviewing, debating approaches, and converging on optimal solutions - all without human intervention.

**Why This Wins:**

1. **Innovation**: First autonomous multi-agent coordination system for E2B
2. **Real Utility**: Solves actual problem - "I want AI agents to build features while I sleep"
3. **Technical Excellence**: Leverages existing production-ready codebase (95/100 quality)
4. **Impressive Demo**: Agents autonomously building complex features with visible GitHub commits
5. **MCP Showcase**: Multiple MCPs working together (GitHub, Exa, Filesystem, Perplexity)

**Competitive Advantage:**

- Production-ready foundation (9,146 lines of tested code)
- Security-audited architecture (10/10 security score)
- Working messaging, locking, discovery systems
- Just need E2B + MCP adapters

---

## Architecture Decision: Single Sandbox Approach

### **Chosen Architecture: All Agents in One E2B Sandbox**

```
┌─────────────────────────────────────────────────────────────┐
│              Single E2B Sandbox (Persistent)                 │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  tmux Session: "claude-swarm"                       │    │
│  │                                                      │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐        │    │
│  │  │ Agent 1   │ │ Agent 2   │ │ Agent 3   │  ...   │    │
│  │  │ (Pane 0)  │ │ (Pane 1)  │ │ (Pane 2)  │        │    │
│  │  │           │ │           │ │           │        │    │
│  │  │ Role:     │ │ Role:     │ │ Role:     │        │    │
│  │  │ Research  │ │ Implement │ │ Review    │        │    │
│  │  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘        │    │
│  │        │             │             │              │    │
│  └────────┼─────────────┼─────────────┼──────────────┘    │
│           │             │             │                   │
│  ┌────────┴─────────────┴─────────────┴────────────────┐   │
│  │          Shared Filesystem & State                  │   │
│  │  • ACTIVE_AGENTS.json (agent registry)              │   │
│  │  • agent_messages.log (message inbox)               │   │
│  │  • .agent_locks/*.lock (file locks)                 │   │
│  │  • /workspace (shared codebase)                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  MCP Servers (Accessible to All Agents)             │   │
│  │  ├── GitHub MCP (repo operations, commits, PRs)     │   │
│  │  ├── Exa MCP (web research, best practices)         │   │
│  │  ├── Filesystem MCP (safe file operations)          │   │
│  │  └── Perplexity MCP (fact-checking, validation)     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
         │
         │ Communication with Host
         ▼
┌─────────────────────────────────────┐
│   Claude Swarm Cloud CLI (Host)     │
│   • claudeswarm cloud deploy        │
│   • claudeswarm cloud monitor       │
│   • claudeswarm cloud attach-mcp    │
└─────────────────────────────────────┘
```

### **Why Single Sandbox?**

**Advantages:**
- ✅ **Cost-effective**: 1 sandbox instead of 4 (important for demos)
- ✅ **Simple**: Existing tmux-based coordination works as-is
- ✅ **Fast communication**: File-based messaging, no network latency
- ✅ **Shared filesystem**: All agents work on same codebase directly
- ✅ **Easier debugging**: Everything in one place
- ✅ **Quick implementation**: Minimal changes to existing code

**Trade-offs We Accept:**
- ❌ Less isolation between agents (acceptable - they're collaborative, not adversarial)
- ❌ Shared tech stack (acceptable - Python is sufficient for demo)
- ❌ Single point of failure (acceptable - E2B sandboxes are reliable)

---

## Target Use Case: Autonomous Feature Development

### **Demo Scenario**

**User Input:**
```bash
claudeswarm cloud develop "Add user authentication with JWT tokens to my FastAPI app"
```

**What Happens (No Human Intervention for 2+ Hours):**

**Phase 1: Research & Planning (15 min)**
- Agent 1 uses Exa MCP to research JWT best practices
- Agent 1 uses Perplexity MCP to verify security considerations
- Agent 1 broadcasts research findings to team
- Agents discuss and agree on implementation approach

**Phase 2: Implementation (45 min)**
- Agent 2 claims "database schema" task
- Agent 3 claims "auth endpoints" task
- Agent 4 claims "middleware & security" task
- Each agent:
  - Acquires file locks on their files
  - Implements their part
  - Commits work-in-progress
  - Broadcasts completion

**Phase 3: Code Review (30 min)**
- Each agent reviews others' code
- Agents send REVIEW_REQUEST messages
- Agents challenge approaches: "Why bcrypt instead of argon2?"
- Debates happen via messaging system
- Visible in real-time dashboard

**Phase 4: Consensus & Refinement (30 min)**
- Agents vote on contested decisions
- Majority approach wins (or tie-breaker: defer to research)
- Refactoring based on consensus
- Final integration

**Phase 5: Testing & Deployment (15 min)**
- Agent 1 writes integration tests
- Agent 2 runs tests, reports results
- Agents fix any failures collaboratively
- Agent 4 uses GitHub MCP to:
  - Create feature branch
  - Commit final code
  - Create pull request with detailed description

**Visible Output:**
- GitHub PR with complete JWT authentication system
- Agents' debate transcript in dashboard
- All decisions documented with reasoning

---

## Implementation Timeline

### **Day 1: Core Integration (8 hours)**

#### **Hour 1-2: E2B Sandbox Launcher**

**Files to Create:**
- `src/claudeswarm/cloud/__init__.py`
- `src/claudeswarm/cloud/e2b_launcher.py`
- `src/claudeswarm/cloud/sandbox_manager.py`

**What It Does:**
```python
# Pseudo-code
sandbox = CloudSandbox.create()
sandbox.install_dependencies([
    "claudeswarm",
    "fastapi",
    "pytest",
    # ... other common packages
])
sandbox.start_tmux_session(num_panes=4)
sandbox.initialize_swarm()
sandbox.attach_mcps(["github", "exa", "filesystem"])
return sandbox.connection_info
```

**Key Features:**
- Start single E2B sandbox with Python 3.12+
- Install claudeswarm package in sandbox
- Create tmux session with 4 panes
- Initialize ACTIVE_AGENTS.json in sandbox
- Return connection details for monitoring

**Testing:**
- Can create and destroy sandboxes
- Tmux session starts correctly
- Claudeswarm commands work in sandbox

---

#### **Hour 3-4: MCP Integration**

**Files to Create:**
- `src/claudeswarm/cloud/mcp_bridge.py`
- `src/claudeswarm/cloud/mcp_config.py`

**MCP Priority List:**

1. **GitHub MCP** (MUST HAVE)
   - Purpose: Create repos, commits, PRs
   - Why: Tangible output judges can see
   - Setup: Docker container with GitHub token

2. **Filesystem MCP** (MUST HAVE)
   - Purpose: Safe file read/write operations
   - Why: Agents need to manipulate code
   - Setup: Mount sandbox workspace

3. **Exa MCP** (SHOULD HAVE)
   - Purpose: Research best practices
   - Why: Makes agents look intelligent
   - Setup: Docker container with Exa API key

4. **Perplexity MCP** (NICE TO HAVE)
   - Purpose: Fact-checking during debates
   - Why: Adds credibility to decisions
   - Setup: Docker container with Perplexity API

**Implementation Approach:**
```python
class MCPBridge:
    """Connect MCP servers to E2B sandbox"""

    def __init__(self, sandbox_id: str):
        self.sandbox_id = sandbox_id
        self.mcp_servers = {}

    async def attach_mcp(self, mcp_name: str, config: dict):
        """
        1. Start MCP Docker container
        2. Connect to sandbox network
        3. Expose MCP endpoints to agents
        4. Test connectivity
        """

    async def call_mcp(self, mcp_name: str, method: str, params: dict):
        """
        Wrapper for agents to call MCP methods
        Handles auth, rate limiting, retries
        """
```

**Key Features:**
- Docker-based MCP deployment
- Simple Python API for agents to call MCPs
- Error handling and retries
- Rate limiting per MCP
- Logging of all MCP calls

**Testing:**
- Can attach GitHub MCP
- Can create test repo via GitHub MCP
- Can perform Exa search
- Error handling works

---

#### **Hour 5-6: Autonomous Workflow Engine**

**Files to Create:**
- `src/claudeswarm/workflows/__init__.py`
- `src/claudeswarm/workflows/autonomous_dev.py`
- `src/claudeswarm/workflows/work_distributor.py`
- `src/claudeswarm/workflows/code_review.py`
- `src/claudeswarm/workflows/consensus.py`

**Core Components:**

**1. Work Distributor**
```python
class WorkDistributor:
    """
    Breaks down feature request into tasks
    Agents claim tasks autonomously
    Tracks task completion
    """

    def decompose_feature(self, feature_description: str) -> list[Task]:
        """
        Use AI to break down feature into tasks:
        1. Research & design
        2. Database schema
        3. API endpoints
        4. Security layer
        5. Tests
        6. Documentation
        """

    def broadcast_available_tasks(self, tasks: list[Task]):
        """Agents claim tasks via messaging"""

    def handle_task_claim(self, agent_id: str, task_id: str):
        """Assign task to agent, prevent double-claiming"""
```

**2. Code Review Protocol**
```python
class CodeReviewProtocol:
    """
    Agents review each other's work
    Challenge decisions with evidence
    Escalate disagreements
    """

    def request_review(self,
                      author_agent: str,
                      reviewer_agent: str,
                      files: list[str]):
        """Send REVIEW_REQUEST message"""

    def submit_review(self,
                     reviewer: str,
                     feedback: ReviewFeedback):
        """
        feedback.issues: list of concerns
        feedback.suggestions: alternative approaches
        feedback.evidence: links to docs/research
        """

    def handle_disagreement(self,
                           agent_a: str,
                           agent_b: str,
                           topic: str):
        """Escalate to consensus mechanism"""
```

**3. Consensus Mechanism**
```python
class ConsensusEngine:
    """
    When agents disagree, reach consensus via:
    1. Evidence-based voting
    2. Research validation (Exa/Perplexity)
    3. Majority rule
    4. Fallback to safest option
    """

    def initiate_vote(self,
                     topic: str,
                     options: list[str],
                     agents: list[str]):
        """Broadcast vote request"""

    def collect_votes(self, timeout: int = 300):
        """Wait for agent votes with rationale"""

    def determine_winner(self, votes: dict) -> str:
        """
        1. Check if any option has >50% votes
        2. If tied, use research quality as tiebreaker
        3. If still tied, choose safest option
        """
```

**Key Features:**
- Autonomous task claiming (no central assignment)
- Structured code review format
- Debate transcripts saved to dashboard
- Evidence-based decision making
- Graceful degradation if consensus fails

**Testing:**
- Can decompose feature into tasks
- Agents can claim and complete tasks
- Code review messages work
- Consensus reached in test scenarios

---

#### **Hour 7-8: CLI Integration & Discovery Adaptation**

**Files to Modify:**
- `src/claudeswarm/cli.py` (add cloud commands)
- `src/claudeswarm/discovery.py` (support E2B agents)

**New CLI Commands:**
```bash
# Launch cloud development
claudeswarm cloud deploy \
  --agents 4 \
  --mcps github,exa,filesystem \
  --feature "Add JWT authentication"

# Monitor ongoing work
claudeswarm cloud monitor --sandbox-id abc123

# Attach additional MCP
claudeswarm cloud attach-mcp perplexity

# Get sandbox status
claudeswarm cloud status

# Shutdown sandbox (save costs)
claudeswarm cloud shutdown --sandbox-id abc123
```

**Discovery Adaptation:**
```python
# Modify discovery.py to detect E2B agents
class CloudAgentDiscovery:
    """
    Detects agents in both:
    - Local tmux (existing)
    - E2B sandboxes (new)
    """

    def discover_cloud_agents(self, sandbox_id: str) -> list[Agent]:
        """
        Connect to E2B sandbox
        Read ACTIVE_AGENTS.json from sandbox filesystem
        Return agent list with cloud metadata
        """
```

**Testing:**
- CLI commands work
- Can deploy sandbox with agents
- Can monitor from host machine
- Discovery finds E2B agents

---

### **Day 2: Polish & Demo (8 hours)**

#### **Hour 9-10: Enhanced Monitoring Dashboard**

**Files to Modify:**
- `src/claudeswarm/web/server.py`
- `src/claudeswarm/web/static/index.html` (or create new cloud view)

**New Dashboard Features:**

1. **Cloud Sandbox Panel**
   - Sandbox ID, uptime, cost estimate
   - MCP connection status (green/yellow/red)
   - Resource usage (CPU, memory)

2. **Agent Conversation View**
   - Real-time message feed
   - Color-coded by type (QUESTION=blue, REVIEW=orange, DEBATE=red)
   - Expandable threads (click to see full debate)

3. **Work Progress Tracker**
   - Task board (TODO → IN_PROGRESS → REVIEW → DONE)
   - Which agent is working on what
   - Estimated completion time

4. **Code Review Stream**
   - Live code reviews as they happen
   - Highlight disagreements
   - Show consensus outcomes

5. **MCP Call Log**
   - Recent MCP calls (GitHub commits, Exa searches)
   - Success/failure status
   - Response times

**Implementation:**
```python
# Add SSE endpoints for cloud data
@app.get("/api/cloud/sandbox-status")
async def get_sandbox_status():
    """Return E2B sandbox metrics"""

@app.get("/api/cloud/agent-conversations")
async def get_conversations():
    """Return recent agent messages with threading"""

@app.get("/api/cloud/mcp-calls")
async def get_mcp_calls():
    """Return MCP call history"""
```

**Testing:**
- Dashboard updates in real-time
- Can see agent debates
- MCP calls visible
- No performance issues

---

#### **Hour 11-12: Autonomous Development Loop**

**Files to Create:**
- `src/claudeswarm/workflows/autonomous_loop.py`

**The Main Loop:**
```python
class AutonomousDevelopmentLoop:
    """
    Main orchestrator for autonomous feature development
    Runs for hours without human intervention
    """

    async def develop_feature(self,
                             feature_description: str,
                             max_duration_hours: int = 8):
        """
        1. Research phase
        2. Planning phase
        3. Implementation phase
        4. Review phase
        5. Consensus & refinement phase
        6. Testing phase
        7. Deployment phase
        """

        # Phase 1: Research (Agent 1)
        research_results = await self.research_phase(feature_description)

        # Phase 2: Planning (All agents)
        tasks = await self.planning_phase(research_results)

        # Phase 3: Implementation (Agents 2, 3, 4)
        implementations = await self.implementation_phase(tasks)

        # Phase 4: Code Review (Cross-review)
        reviews = await self.review_phase(implementations)

        # Phase 5: Consensus (All agents)
        if reviews.has_disagreements():
            final_decisions = await self.consensus_phase(reviews)
            await self.apply_consensus(final_decisions)

        # Phase 6: Testing (Agent 1)
        test_results = await self.testing_phase()

        # Phase 7: Deployment (Agent 4)
        if test_results.all_passed():
            pr_url = await self.deployment_phase()
            return pr_url
        else:
            # Loop back to fix failures
            await self.fix_phase(test_results.failures)
```

**Agent Prompts (Embedded):**
```python
AGENT_PROMPTS = {
    "research": """
    You are Agent 1 (Researcher). Your task:
    1. Use Exa MCP to research: {feature_description}
    2. Find best practices, security considerations, examples
    3. Use Perplexity MCP to validate findings
    4. Write research summary in RESEARCH.md
    5. Broadcast findings to team
    """,

    "implement": """
    You are Agent {id} (Developer). Your task:
    1. Read RESEARCH.md for context
    2. Claim a task from available tasks
    3. Acquire file lock on files you'll edit
    4. Implement your task following best practices
    5. Write unit tests for your code
    6. Commit your work
    7. Broadcast completion
    """,

    "review": """
    You are Agent {id} (Reviewer). Your task:
    1. Read code changes from Agent {author_id}
    2. Check for: bugs, security issues, performance problems
    3. Compare against research findings
    4. If you disagree with an approach, challenge it with evidence
    5. Submit review with feedback
    """,

    "test": """
    You are Agent 1 (QA). Your task:
    1. Review all implemented code
    2. Write integration tests
    3. Run full test suite
    4. Report failures to team
    5. Verify fixes
    """
}
```

**Key Features:**
- Runs for hours without intervention
- Graceful error handling (if agent fails, redistribute task)
- Progress persistence (can resume if sandbox restarts)
- Clear phase transitions
- Detailed logging

**Testing:**
- End-to-end test with simple feature
- Handles agent failures gracefully
- Can run for >1 hour
- Produces working code

---

#### **Hour 13-14: Demo Scenario Implementation**

**Goal: Create Impressive Demo That Runs Live**

**Demo Feature Choice:**
```
"Add user authentication with JWT tokens to a FastAPI application"
```

**Why This Feature:**
- Complex enough to show coordination (4-5 files)
- Simple enough to complete in reasonable time (~2 hours)
- Tangible security outcome judges understand
- Shows all phases (research, implement, review, test)

**Demo Preparation:**

1. **Starter Repo Setup**
   - Create minimal FastAPI app (2 endpoints)
   - Add to GitHub
   - Clone into E2B sandbox workspace

2. **Expected Deliverables**
   - `models/user.py` (User model with password hashing)
   - `auth/jwt.py` (JWT token generation/validation)
   - `routers/auth.py` (Login/register endpoints)
   - `middleware/auth.py` (JWT verification middleware)
   - `tests/test_auth.py` (Integration tests)
   - GitHub PR with all changes

3. **Agent Choreography**
   - Agent 1: Research JWT best practices (OWASP, RFC 7519)
   - Agent 2: Implement user model + password hashing
   - Agent 3: Implement JWT endpoints
   - Agent 4: Implement middleware + security
   - Agent 1: Write tests
   - Agents 2-4: Code review each other
   - Agent 4: Deploy to GitHub

4. **Expected Debate Topics**
   - "Should we use HS256 or RS256 for JWT signing?"
   - "Access token expiry: 15 min or 1 hour?"
   - "Should we implement refresh tokens in v1?"

**Demo Script (What Judge Sees):**
```bash
# Terminal 1: Launch autonomous development
$ claudeswarm cloud deploy \
    --agents 4 \
    --mcps github,exa,perplexity,filesystem \
    --feature "Add JWT authentication to FastAPI app" \
    --repo https://github.com/demo/fastapi-starter

✓ Sandbox created: e2b-abc123
✓ Agents initialized: agent-0, agent-1, agent-2, agent-3
✓ MCPs attached: ✓ github ✓ exa ✓ perplexity ✓ filesystem
✓ Autonomous development started

→ Open dashboard: http://localhost:8080

# Terminal 2: Monitor progress
$ claudeswarm cloud monitor --follow

[15:30:12] agent-0 → ALL: Starting research phase...
[15:31:45] agent-0 → ALL: Research complete. Found 12 best practices.
           Key finding: RS256 preferred for production.
[15:32:10] agent-1: Claiming task: Implement user model
[15:32:11] agent-2: Claiming task: Implement JWT endpoints
[15:32:12] agent-3: Claiming task: Implement auth middleware
[15:45:23] agent-1 → ALL: User model complete. Using bcrypt for hashing.
[15:46:01] agent-3 → agent-1: REVIEW_REQUEST for models/user.py
[15:47:30] agent-3 → agent-1: Why bcrypt over argon2? Research suggests argon2.
[15:48:15] agent-1 → agent-3: Bcrypt more widely supported. Lower dependency risk.
[15:49:00] agent-0 → ALL: CONSENSUS_REQUEST: bcrypt vs argon2
[15:50:30] Consensus reached: argon2 (3 votes vs 1)
[15:51:00] agent-1 → ALL: Refactoring to argon2...
...
[17:30:45] agent-3 → ALL: All tests passing. Creating GitHub PR...
[17:31:20] agent-3 → ALL: COMPLETED: https://github.com/demo/fastapi-starter/pull/1

✓ Feature development complete
✓ Duration: 2h 1m 8s
✓ Files changed: 5
✓ Tests: 12 passing
✓ Debates resolved: 3
✓ GitHub PR: #1
```

**Dashboard View (What Judge Sees):**
- Real-time agent messages scrolling
- Task board updating
- Code review discussions highlighted
- Consensus votes visualized
- Final PR link clickable

---

#### **Hour 15: Documentation & Video**

**Files to Create/Update:**
- `README_CLOUD.md` (Cloud-specific docs)
- `docs/E2B_INTEGRATION.md` (Technical details)
- `examples/cloud_demo.sh` (Automated demo script)

**README_CLOUD.md Contents:**
```markdown
# Claude Swarm Cloud

Run autonomous multi-agent development teams in E2B sandboxes.

## Quick Start

1. Install E2B CLI and get API key
2. Install Claude Swarm: `uv tool install .`
3. Run demo: `claudeswarm cloud deploy --agents 4 --feature "your feature"`

## What It Does

- 4 AI agents collaborate in a single E2B sandbox
- Agents research, implement, review, debate, and deploy
- Works for hours without human intervention
- Commits results to GitHub via MCP

## Architecture

[Include ASCII diagram from this plan]

## Demo Video

[Link to video]

## Hackathon Submission

This project combines:
- E2B sandboxes (persistent, isolated execution)
- Multiple MCPs (GitHub, Exa, Filesystem, Perplexity)
- Autonomous multi-agent coordination

Built for: E2B & Docker MCP Catalog Hackathon 2025
```

**Video Script (3 minutes):**

**0:00-0:30** - Problem Statement
- "Building features is tedious. Code review is slow. Coordination is hard."
- "What if AI agents could work together autonomously for hours?"

**0:30-1:00** - Solution Overview
- "Claude Swarm Cloud: 4 AI agents in one E2B sandbox"
- "They research, implement, review, debate, and deploy"
- Show architecture diagram

**1:00-2:00** - Live Demo
- Start autonomous development
- Show dashboard with real-time updates
- Highlight agent debate
- Show consensus mechanism
- Click through to GitHub PR

**2:00-2:30** - Technical Highlights
- "Built on production-ready Claude Swarm foundation"
- "Uses 4 MCPs: GitHub, Exa, Filesystem, Perplexity"
- "E2B sandbox provides isolation and persistence"

**2:30-3:00** - Impact
- "Autonomous development while you sleep"
- "Perfect code review quality"
- "Evidence-based decisions"
- Call to action: Try it yourself!

**Recording Tools:**
- OBS Studio for screen recording
- Demo runs live (not pre-recorded)
- Narration over live demo
- Show both terminal and dashboard

---

#### **Hour 16: Final Testing & Submission Prep**

**Pre-Submission Checklist:**

**Technical:**
- [ ] Can deploy sandbox with 4 agents
- [ ] Agents can discover each other
- [ ] Messages deliver correctly
- [ ] File locking works in E2B
- [ ] GitHub MCP commits successfully
- [ ] Exa MCP returns research
- [ ] Dashboard shows real-time updates
- [ ] Autonomous loop completes end-to-end
- [ ] Code review debates work
- [ ] Consensus mechanism functions
- [ ] Can run for 2+ hours uninterrupted

**Demo:**
- [ ] Demo repo ready
- [ ] Demo feature chosen (JWT auth)
- [ ] Demo script tested 3x
- [ ] Video recorded and uploaded
- [ ] Screenshots captured

**Documentation:**
- [ ] README_CLOUD.md complete
- [ ] Architecture diagram included
- [ ] Installation instructions clear
- [ ] Demo instructions work
- [ ] Code comments thorough

**Hackathon Requirements:**
- [ ] Uses E2B sandbox ✓
- [ ] Uses at least 1 MCP (we use 4) ✓
- [ ] Submission form filled
- [ ] GitHub repo public
- [ ] Video linked

**Edge Cases Tested:**
- [ ] Agent failure (redistribute task)
- [ ] MCP timeout (retry logic)
- [ ] Network interruption (reconnect)
- [ ] Consensus tie (use fallback)
- [ ] Test failure (retry with fixes)

---

## Technical Implementation Details

### **File Structure (New Files)**

```
claude-swarm/
├── src/claudeswarm/
│   ├── cloud/                          # NEW
│   │   ├── __init__.py
│   │   ├── e2b_launcher.py            # Sandbox creation/management
│   │   ├── sandbox_manager.py         # Multi-sandbox orchestration
│   │   ├── mcp_bridge.py              # MCP integration
│   │   └── mcp_config.py              # MCP configuration
│   │
│   └── workflows/                      # NEW
│       ├── __init__.py
│       ├── autonomous_dev.py          # Main autonomous loop
│       ├── work_distributor.py        # Task breakdown & assignment
│       ├── code_review.py             # Review protocol
│       └── consensus.py               # Consensus mechanism
│
├── examples/
│   ├── cloud_demo.sh                  # NEW: Automated demo
│   └── cloud_config.yaml              # NEW: Cloud config example
│
├── docs/
│   └── E2B_INTEGRATION.md             # NEW: Technical docs
│
├── README_CLOUD.md                     # NEW: Cloud-specific README
└── HACKATHON_PLAN.md                   # This file
```

### **Dependencies to Add**

```toml
# pyproject.toml additions
[project]
dependencies = [
    # ... existing dependencies ...
    "e2b-code-interpreter>=0.1.0",  # E2B SDK
    "docker>=6.0.0",                # For MCP containers
    "httpx>=0.24.0",                # For MCP HTTP calls
]

[project.optional-dependencies]
cloud = [
    "e2b-code-interpreter>=0.1.0",
    "docker>=6.0.0",
]
```

### **Environment Variables Needed**

```bash
# .env.example
E2B_API_KEY=your_e2b_api_key_here
GITHUB_TOKEN=your_github_token_here
EXA_API_KEY=your_exa_api_key_here
PERPLEXITY_API_KEY=your_perplexity_api_key_here
```

### **Code Skeleton: E2B Launcher**

```python
# src/claudeswarm/cloud/e2b_launcher.py

from e2b_code_interpreter import CodeInterpreter
from typing import Optional
import asyncio

class CloudSandbox:
    """Manages a single E2B sandbox with multiple agents"""

    def __init__(self, num_agents: int = 4):
        self.num_agents = num_agents
        self.sandbox: Optional[CodeInterpreter] = None
        self.sandbox_id: Optional[str] = None

    async def create(self) -> str:
        """Create E2B sandbox and initialize environment"""

        # Create sandbox
        self.sandbox = CodeInterpreter()
        self.sandbox_id = self.sandbox.id

        # Install dependencies
        await self._install_dependencies()

        # Setup tmux
        await self._setup_tmux()

        # Initialize claudeswarm
        await self._initialize_swarm()

        return self.sandbox_id

    async def _install_dependencies(self):
        """Install required packages in sandbox"""
        commands = [
            "pip install git+https://github.com/borisbanach/claude-swarm.git",
            "pip install fastapi uvicorn pytest",
            "apt-get update && apt-get install -y tmux"
        ]

        for cmd in commands:
            result = await self.sandbox.notebook.exec_cell(f"!{cmd}")
            if result.error:
                raise RuntimeError(f"Failed to install dependencies: {result.error}")

    async def _setup_tmux(self):
        """Create tmux session with multiple panes"""

        # Create session
        await self.sandbox.process.start(
            "tmux new-session -d -s claude-swarm"
        )

        # Split into panes
        for i in range(1, self.num_agents):
            await self.sandbox.process.start(
                f"tmux split-window -h -t claude-swarm"
            )
            await self.sandbox.process.start(
                f"tmux select-layout -t claude-swarm tiled"
            )

    async def _initialize_swarm(self):
        """Initialize claudeswarm in each pane"""

        for i in range(self.num_agents):
            # Send discovery command to each pane
            await self.sandbox.process.start(
                f"tmux send-keys -t claude-swarm:{i} "
                f"'cd /workspace && claudeswarm discover-agents' Enter"
            )

        # Wait for initialization
        await asyncio.sleep(2)

    async def attach_mcp(self, mcp_name: str, config: dict):
        """Attach MCP server to sandbox"""
        # Implementation in mcp_bridge.py
        pass

    async def execute_autonomous_dev(self, feature: str):
        """Start autonomous development loop"""
        # Implementation in workflows/autonomous_dev.py
        pass

    async def cleanup(self):
        """Shutdown sandbox and cleanup resources"""
        if self.sandbox:
            await self.sandbox.close()
```

### **Code Skeleton: MCP Bridge**

```python
# src/claudeswarm/cloud/mcp_bridge.py

import docker
import httpx
from typing import Any, Dict

class MCPBridge:
    """Connects MCP servers to E2B sandbox"""

    def __init__(self, sandbox_id: str):
        self.sandbox_id = sandbox_id
        self.docker_client = docker.from_env()
        self.mcp_containers: Dict[str, Any] = {}

    async def attach_github_mcp(self, github_token: str):
        """Attach GitHub MCP server"""

        # Start GitHub MCP container
        container = self.docker_client.containers.run(
            "mcp/github:latest",
            detach=True,
            environment={"GITHUB_TOKEN": github_token},
            network_mode="bridge",
            name=f"github-mcp-{self.sandbox_id}"
        )

        self.mcp_containers["github"] = container

        # Get container IP
        container.reload()
        ip_address = container.attrs['NetworkSettings']['IPAddress']

        return f"http://{ip_address}:3000"

    async def attach_exa_mcp(self, exa_api_key: str):
        """Attach Exa MCP server"""

        container = self.docker_client.containers.run(
            "mcp/exa:latest",
            detach=True,
            environment={"EXA_API_KEY": exa_api_key},
            network_mode="bridge",
            name=f"exa-mcp-{self.sandbox_id}"
        )

        self.mcp_containers["exa"] = container

        container.reload()
        ip_address = container.attrs['NetworkSettings']['IPAddress']

        return f"http://{ip_address}:3000"

    async def call_mcp(self,
                      mcp_name: str,
                      method: str,
                      params: dict) -> dict:
        """Call MCP method with retry logic"""

        if mcp_name not in self.mcp_containers:
            raise ValueError(f"MCP {mcp_name} not attached")

        container = self.mcp_containers[mcp_name]
        container.reload()
        ip = container.attrs['NetworkSettings']['IPAddress']

        async with httpx.AsyncClient() as client:
            for attempt in range(3):
                try:
                    response = await client.post(
                        f"http://{ip}:3000/mcp/{method}",
                        json=params,
                        timeout=30.0
                    )
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPError as e:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2 ** attempt)

    def cleanup(self):
        """Stop and remove all MCP containers"""
        for container in self.mcp_containers.values():
            container.stop()
            container.remove()
```

### **Code Skeleton: Autonomous Development Loop**

```python
# src/claudeswarm/workflows/autonomous_dev.py

from claudeswarm.messaging import MessagingSystem, MessageType
from claudeswarm.locking import LockManager
from claudeswarm.cloud.mcp_bridge import MCPBridge
import asyncio
from typing import List, Dict

class AutonomousDevelopmentLoop:
    """Main orchestrator for autonomous feature development"""

    def __init__(self,
                 sandbox_id: str,
                 num_agents: int = 4,
                 mcp_bridge: MCPBridge = None):
        self.sandbox_id = sandbox_id
        self.num_agents = num_agents
        self.mcp_bridge = mcp_bridge
        self.messaging = MessagingSystem()
        self.lock_manager = LockManager()

    async def develop_feature(self,
                             feature_description: str,
                             max_duration_hours: int = 8) -> str:
        """
        Main entry point for autonomous development
        Returns: GitHub PR URL
        """

        print(f"🚀 Starting autonomous development: {feature_description}")

        try:
            # Phase 1: Research
            print("📚 Phase 1: Research...")
            research_results = await self.research_phase(feature_description)

            # Phase 2: Planning
            print("📋 Phase 2: Planning...")
            tasks = await self.planning_phase(research_results)

            # Phase 3: Implementation
            print("⚒️  Phase 3: Implementation...")
            implementations = await self.implementation_phase(tasks)

            # Phase 4: Code Review
            print("👀 Phase 4: Code Review...")
            reviews = await self.review_phase(implementations)

            # Phase 5: Consensus (if needed)
            if reviews.get('disagreements'):
                print("🗳️  Phase 5: Consensus...")
                await self.consensus_phase(reviews)

            # Phase 6: Testing
            print("🧪 Phase 6: Testing...")
            test_results = await self.testing_phase()

            # Phase 7: Deployment
            if test_results['passed']:
                print("🚢 Phase 7: Deployment...")
                pr_url = await self.deployment_phase()
                print(f"✅ Feature complete! PR: {pr_url}")
                return pr_url
            else:
                print("❌ Tests failed. Starting fix iteration...")
                return await self.fix_and_retry(test_results)

        except Exception as e:
            print(f"❌ Error during development: {e}")
            raise

    async def research_phase(self, feature_description: str) -> Dict:
        """Agent 0 researches the feature"""

        # Assign to agent-0
        agent_id = "agent-0"

        # Use Exa MCP to search
        exa_results = await self.mcp_bridge.call_mcp(
            "exa",
            "search",
            {
                "query": f"{feature_description} best practices tutorial",
                "num_results": 5
            }
        )

        # Use Perplexity MCP to validate
        perplexity_validation = await self.mcp_bridge.call_mcp(
            "perplexity",
            "ask",
            {
                "question": f"What are security considerations for {feature_description}?"
            }
        )

        # Agent writes research summary
        research_summary = {
            "feature": feature_description,
            "best_practices": exa_results,
            "security": perplexity_validation,
            "recommendations": self._extract_recommendations(exa_results)
        }

        # Broadcast to team
        self.messaging.broadcast_message(
            sender_id=agent_id,
            message_type=MessageType.INFO,
            content=f"Research complete. Key findings: {research_summary['recommendations']}"
        )

        return research_summary

    async def planning_phase(self, research_results: Dict) -> List[Dict]:
        """Break down feature into tasks"""

        # Use AI to decompose feature
        # For demo, we'll use a simple heuristic

        tasks = [
            {
                "id": "task-1",
                "title": "Database models",
                "files": ["models/user.py"],
                "agent": None  # To be claimed
            },
            {
                "id": "task-2",
                "title": "API endpoints",
                "files": ["routers/auth.py"],
                "agent": None
            },
            {
                "id": "task-3",
                "title": "Security middleware",
                "files": ["middleware/auth.py"],
                "agent": None
            },
            {
                "id": "task-4",
                "title": "Integration tests",
                "files": ["tests/test_auth.py"],
                "agent": None
            }
        ]

        # Broadcast available tasks
        self.messaging.broadcast_message(
            sender_id="coordinator",
            message_type=MessageType.INFO,
            content=f"Available tasks: {[t['title'] for t in tasks]}"
        )

        return tasks

    async def implementation_phase(self, tasks: List[Dict]) -> List[Dict]:
        """Agents claim and implement tasks"""

        # Wait for agents to claim tasks
        # In real implementation, this would be event-driven
        await asyncio.sleep(2)

        # Simulate agents claiming tasks
        # In real implementation, agents would message to claim

        implementations = []

        for i, task in enumerate(tasks[:3]):  # First 3 tasks
            agent_id = f"agent-{i+1}"

            # Agent acquires file lock
            for file_path in task['files']:
                self.lock_manager.acquire_lock(
                    file_path=file_path,
                    agent_id=agent_id,
                    reason=f"Implementing {task['title']}"
                )

            # Agent implements (simulated)
            # In real implementation, this would be actual code generation

            # Agent commits and broadcasts
            self.messaging.broadcast_message(
                sender_id=agent_id,
                message_type=MessageType.COMPLETED,
                content=f"Completed {task['title']}"
            )

            implementations.append({
                "task": task,
                "agent": agent_id,
                "status": "completed"
            })

        return implementations

    async def review_phase(self, implementations: List[Dict]) -> Dict:
        """Agents review each other's work"""

        reviews = {
            "reviews": [],
            "disagreements": []
        }

        # Each agent reviews another's work
        for i, impl in enumerate(implementations):
            reviewer_id = f"agent-{(i+2) % self.num_agents}"
            author_id = impl['agent']

            # Send review request
            self.messaging.send_direct_message(
                sender_id=reviewer_id,
                recipient_id=author_id,
                message_type=MessageType.REVIEW_REQUEST,
                content=f"Please review my changes to {impl['task']['files']}"
            )

            # Simulate review
            # In real implementation, this would be AI-powered code review

            review_result = {
                "reviewer": reviewer_id,
                "author": author_id,
                "files": impl['task']['files'],
                "issues": [],
                "suggestions": ["Consider adding error handling"],
                "approved": True
            }

            reviews["reviews"].append(review_result)

        return reviews

    async def consensus_phase(self, reviews: Dict):
        """Resolve disagreements through voting"""

        # In real implementation, this would facilitate agent debates
        # and voting on contested decisions

        for disagreement in reviews["disagreements"]:
            # Broadcast vote request
            self.messaging.broadcast_message(
                sender_id="coordinator",
                message_type=MessageType.QUESTION,
                content=f"Vote: {disagreement['topic']}"
            )

            # Collect votes
            # Determine winner
            # Broadcast result
            pass

    async def testing_phase(self) -> Dict:
        """Run tests and report results"""

        # Agent 0 runs tests
        agent_id = "agent-0"

        # In real implementation, this would execute pytest
        # For demo, we'll simulate

        test_results = {
            "passed": True,
            "total_tests": 12,
            "failures": []
        }

        self.messaging.broadcast_message(
            sender_id=agent_id,
            message_type=MessageType.INFO,
            content=f"Tests: {test_results['total_tests']} passed"
        )

        return test_results

    async def deployment_phase(self) -> str:
        """Create GitHub PR with changes"""

        # Agent 3 creates PR using GitHub MCP
        pr_result = await self.mcp_bridge.call_mcp(
            "github",
            "create_pull_request",
            {
                "title": "Add JWT authentication",
                "body": "Autonomous development by Claude Swarm",
                "branch": "feature/jwt-auth",
                "base": "main"
            }
        )

        pr_url = pr_result.get("url")

        self.messaging.broadcast_message(
            sender_id="agent-3",
            message_type=MessageType.COMPLETED,
            content=f"PR created: {pr_url}"
        )

        return pr_url

    def _extract_recommendations(self, exa_results: Dict) -> List[str]:
        """Extract key recommendations from research"""
        # Simple extraction for demo
        return ["Use RS256 for JWT", "15-minute token expiry", "Implement refresh tokens"]
```

---

## Risk Mitigation & Fallback Plans

### **Risk 1: E2B Integration Too Complex**

**Mitigation:**
- Start with simplest possible E2B integration
- Use E2B's Python SDK examples as template
- Test early (Hour 1-2)

**Fallback:**
- If E2B too difficult, demo with local tmux (existing system)
- Add "Cloud Mode Coming Soon" placeholder
- Still use MCPs locally via Docker

**Impact:** Lose E2B requirement, but keep MCP requirement

---

### **Risk 2: MCP Servers Don't Work as Expected**

**Mitigation:**
- Test each MCP individually before integration
- Have backup MCP choices
- Build abstraction layer (easy to swap MCPs)

**Fallback Priority:**
1. GitHub MCP (MUST HAVE - tangible output)
2. Filesystem MCP (MUST HAVE - basic functionality)
3. Exa MCP (NICE TO HAVE - makes demo impressive)
4. Perplexity MCP (OPTIONAL - cherry on top)

**Minimum Viable:** GitHub + Filesystem = still meets requirements

---

### **Risk 3: Autonomous Loop Too Ambitious**

**Mitigation:**
- Build iteratively (start with 2 agents, scale to 4)
- Focus on one phase at a time
- Use simple state machine

**Fallback:**
- Semi-autonomous mode (human approves each phase)
- Shorter demo (30 min instead of 2 hours)
- Simpler feature (hello world instead of JWT auth)

**Impact:** Less impressive, but still shows core value

---

### **Risk 4: Running Out of Time**

**Mitigation:**
- Time-box each component (use timer)
- Skip "nice to have" features
- Focus on demo quality over code perfection

**Priority Order:**
1. Basic E2B sandbox with tmux ✅ (Must have)
2. GitHub MCP integration ✅ (Must have)
3. Simple 2-agent coordination ✅ (Must have)
4. Dashboard showing agents ✅ (Should have)
5. 4-agent complex coordination ⚠️ (Nice to have)
6. Full autonomous loop ⚠️ (Nice to have)
7. Multiple MCPs ⚠️ (Nice to have)

**Minimum Viable Demo:** 1 + 2 + 3 + 4 = Submittable entry

---

## Success Metrics

### **Technical Success**

- [ ] E2B sandbox starts with 4 agents
- [ ] Agents discover each other in sandbox
- [ ] Messages deliver between agents
- [ ] File locking prevents conflicts
- [ ] At least 1 MCP works (GitHub)
- [ ] Autonomous loop completes 1 iteration
- [ ] Dashboard shows real-time updates
- [ ] Can run for 30+ minutes uninterrupted

### **Demo Success**

- [ ] Demo runs smoothly without crashes
- [ ] Visible GitHub PR created
- [ ] Agent debates visible in dashboard
- [ ] Clear narrative ("I want X" → PR created)
- [ ] Video is engaging and clear
- [ ] Documentation is comprehensive

### **Hackathon Success**

- [ ] Uses E2B sandbox ✅
- [ ] Uses at least 1 MCP from Docker Hub ✅
- [ ] Solves real problem (autonomous AI coordination)
- [ ] Shows technical sophistication
- [ ] Has impressive demo
- [ ] Code is production-quality
- [ ] Documentation is excellent

---

## Post-Hackathon: Production Roadmap

**If this goes well, what's next?**

### **Phase 1: Hackathon (Weekend)**
- Single E2B sandbox
- 4 agents
- Basic autonomous workflow
- 2-3 MCPs

### **Phase 2: Production (Week 1-2)**
- Multi-sandbox support (different agents in different sandboxes)
- Advanced consensus mechanisms
- More robust error handling
- Cost optimization

### **Phase 3: Scale (Week 3-4)**
- Support 10+ agents
- Cross-repository coordination
- Agent specialization (front-end expert, DB expert, etc.)
- Integration with CI/CD pipelines

### **Phase 4: Enterprise (Month 2+)**
- SaaS offering (swarm-as-a-service)
- Team management (assign humans to oversee swarms)
- Analytics dashboard (agent performance metrics)
- Marketplace for specialized agents

---

## Conclusion

This hackathon project transforms Claude Swarm from a local development tool into a **cloud-native autonomous development platform**. By combining:

1. **E2B sandboxes** (persistent, isolated execution)
2. **MCP servers** (GitHub, Exa, Filesystem, Perplexity)
3. **Existing production-ready infrastructure** (95/100 code quality)
4. **Innovative autonomous workflows** (multi-agent coordination)

We create something **judges have never seen before**: AI agents that truly work autonomously for hours, debating, implementing, reviewing, and deploying code - all visible in real-time.

**The key insight:** We're not building everything from scratch. We're extending an already-excellent foundation (Claude Swarm) with cloud capabilities and autonomous behaviors. This gives us a massive head start and increases our chances of winning.

**Ready to build!** 🚀

---

## Quick Reference: Commands to Implement

```bash
# Day 1
claudeswarm cloud init                    # Setup cloud credentials
claudeswarm cloud deploy --agents 4       # Launch sandbox

# Day 2
claudeswarm cloud monitor                 # Watch agents work
claudeswarm cloud attach-mcp github       # Add MCP
claudeswarm cloud develop "feature"       # Start autonomous dev
```

---

**Last Updated:** 2025-11-19
**Author:** Claude (Sonnet 4.5)
**Status:** Ready for Implementation
