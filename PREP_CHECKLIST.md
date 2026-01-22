# E2B Hackathon Preparation Checklist

## Overview
This checklist tracks all preparation work needed before the hackathon weekend. Each agent should use this to coordinate their prep work and ensure we're ready to hit the ground running.

---

## Pre-Hackathon Tasks

### File Structure & Scaffolding
- [ ] Create `src/claudeswarm/cloud/` directory
- [ ] Create `src/claudeswarm/cloud/__init__.py`
- [ ] Create `src/claudeswarm/cloud/types.py` (agent-4)
- [ ] Create `src/claudeswarm/cloud/e2b_launcher.py` skeleton (agent-3)
- [ ] Create `src/claudeswarm/cloud/sandbox_manager.py` skeleton (agent-3)
- [ ] Create `src/claudeswarm/cloud/mcp_bridge.py` skeleton (agent-4)
- [ ] Create `src/claudeswarm/cloud/mcp_config.py` skeleton (agent-5)
- [ ] Create `src/claudeswarm/workflows/` directory
- [ ] Create `src/claudeswarm/workflows/__init__.py`
- [ ] Create `src/claudeswarm/workflows/autonomous_dev.py` skeleton (agent-1)
- [ ] Create `src/claudeswarm/workflows/work_distributor.py` skeleton (agent-1)
- [ ] Create `src/claudeswarm/workflows/code_review.py` skeleton (agent-1)
- [ ] Create `src/claudeswarm/workflows/consensus.py` skeleton (agent-1)

### Documentation
- [ ] Create `README_CLOUD.md` outline
- [ ] Create `docs/E2B_INTEGRATION.md` technical spec
- [ ] Create `docs/MCP_INTEGRATION.md` technical spec (agent-5)
- [ ] Create `docs/SSE_ENDPOINTS.md` dashboard API spec (agent-5)
- [ ] Create `.env.example` template (agent-1)
- [ ] Document interface contracts between components

### Research & Planning
- [ ] Research E2B Python SDK examples (agent-3)
- [ ] Research E2B tmux support and persistence (agent-3)
- [ ] Research GitHub MCP Docker image availability (agent-4)
- [ ] Research Filesystem MCP Docker image availability (agent-4)
- [ ] Research Exa MCP API documentation (agent-5)
- [ ] Research Perplexity MCP API documentation (agent-5)
- [ ] Define MCPResponse, MCPError, MCPConfig types (agent-4)
- [ ] Design consensus voting algorithm (agent-1)

### Dependencies
- [ ] Add E2B SDK to pyproject.toml
- [ ] Add Docker SDK to pyproject.toml
- [ ] Add httpx to pyproject.toml (for MCP calls)
- [ ] Test that dependencies install correctly
- [ ] Create optional dependencies group `[cloud]`

### Code Skeletons
- [ ] Write CloudSandbox class skeleton with method signatures (agent-3)
- [ ] Write MCPBridge class skeleton with method signatures (agent-4)
- [ ] Write Exa MCP config class skeleton (agent-5)
- [ ] Write Perplexity MCP config class skeleton (agent-5)
- [ ] Write AutonomousDevelopmentLoop class skeleton (agent-1)
- [ ] Add cloud commands to CLI (stub implementations)

### Testing Setup
- [ ] Create `tests/cloud/` directory
- [ ] Create test stubs for E2B launcher
- [ ] Create test stubs for MCP bridge
- [ ] Create test stubs for autonomous workflows
- [ ] Document manual testing procedure

---

## Credentials & API Keys Needed

### Required for Hackathon
1. **E2B API Key**
   - URL: https://e2b.dev/docs/getting-started
   - Purpose: Create and manage sandboxes
   - Priority: CRITICAL

2. **GitHub Personal Access Token**
   - URL: https://github.com/settings/tokens
   - Scopes needed: `repo`, `workflow`
   - Purpose: GitHub MCP for commits and PRs
   - Priority: CRITICAL

### Nice to Have
3. **Exa API Key**
   - URL: https://exa.ai
   - Purpose: Research and web search MCP
   - Priority: HIGH (makes demo impressive)

4. **Perplexity API Key**
   - URL: https://perplexity.ai
   - Purpose: Fact-checking and validation MCP
   - Priority: MEDIUM (optional enhancement)

### Configuration
- [ ] Create `.env.example` with all required keys
- [ ] Add `.env` to `.gitignore` (verify it's there)
- [ ] Document how to load credentials in code
- [ ] Test credential loading from environment

---

## Hackathon Weekend Timeline

### Day 1 (Saturday) - 8 Hours

#### Hour 1-2: E2B Sandbox Launcher (agent-3)
- [ ] Implement CloudSandbox.create()
- [ ] Implement dependency installation
- [ ] Implement tmux session creation
- [ ] Implement claudeswarm initialization
- [ ] Test: Can create and connect to sandbox
- [ ] Test: Tmux session works correctly

#### Hour 3-4: MCP Integration (agent-4 & agent-5)
**agent-4:**
- [ ] Implement MCPBridge core class
- [ ] Implement attach_github_mcp()
- [ ] Implement attach_filesystem_mcp()
- [ ] Implement call_mcp() with retry logic
- [ ] Test: Can start GitHub MCP container
- [ ] Test: Can create test repo via GitHub MCP

**agent-5:**
- [ ] Implement Exa MCP configuration
- [ ] Implement Perplexity MCP configuration
- [ ] Implement attach_exa_mcp()
- [ ] Implement attach_perplexity_mcp()
- [ ] Test: Can perform Exa search
- [ ] Test: Can query Perplexity

#### Hour 5-6: Autonomous Workflow Engine (agent-1)
- [ ] Implement WorkDistributor.decompose_feature()
- [ ] Implement WorkDistributor.broadcast_available_tasks()
- [ ] Implement CodeReviewProtocol.request_review()
- [ ] Implement CodeReviewProtocol.submit_review()
- [ ] Implement ConsensusEngine.initiate_vote()
- [ ] Test: Can break down feature into tasks
- [ ] Test: Agents can claim tasks

#### Hour 7-8: CLI Integration (ALL)
- [ ] Implement `claudeswarm cloud deploy`
- [ ] Implement `claudeswarm cloud status`
- [ ] Implement `claudeswarm cloud monitor`
- [ ] Adapt discovery.py for E2B agents
- [ ] Test: CLI commands work end-to-end

### Day 2 (Sunday) - 8 Hours

#### Hour 9-10: Enhanced Monitoring Dashboard (agent-5 + ALL)
- [ ] Add SSE endpoint `/api/cloud/sandbox-status`
- [ ] Add SSE endpoint `/api/cloud/agent-conversations`
- [ ] Add SSE endpoint `/api/cloud/mcp-calls`
- [ ] Update frontend to display cloud data
- [ ] Add agent conversation threading view
- [ ] Add MCP call log view
- [ ] Test: Dashboard updates in real-time
- [ ] Test: Conversation threading works

#### Hour 11-12: Autonomous Development Loop (agent-1)
- [ ] Implement research_phase()
- [ ] Implement planning_phase()
- [ ] Implement implementation_phase()
- [ ] Implement review_phase()
- [ ] Implement consensus_phase()
- [ ] Implement testing_phase()
- [ ] Implement deployment_phase()
- [ ] Test: Loop completes one iteration

#### Hour 13-14: Demo Scenario (ALL)
- [ ] Create demo FastAPI starter repo
- [ ] Test autonomous JWT auth feature development
- [ ] Verify agents debate and reach consensus
- [ ] Verify GitHub PR is created
- [ ] Verify all tests pass
- [ ] Time the demo (should be ~2 hours)
- [ ] Document any issues

#### Hour 15: Documentation & Video (ALL)
- [ ] Write README_CLOUD.md
- [ ] Write docs/E2B_INTEGRATION.md
- [ ] Create demo script
- [ ] Record demo video (3 minutes)
- [ ] Capture screenshots
- [ ] Test installation instructions

#### Hour 16: Final Testing & Submission (ALL)
- [ ] Run through full demo 3x
- [ ] Test all edge cases
- [ ] Verify all requirements met
- [ ] Fill out hackathon submission form
- [ ] Upload video
- [ ] Make repo public
- [ ] Submit!

---

## Interface Contracts

### Between agent-4 (MCPBridge) and agent-5 (MCP Configs)

**MCPBridge exposes:**
```python
class MCPBridge:
    async def call_mcp(self, mcp_name: str, method: str, params: dict) -> MCPResponse
    async def attach_mcp(self, mcp_name: str, config: MCPConfig) -> str
    def cleanup(self) -> None
```

**MCP Config modules provide:**
```python
class ExaMCPConfig(MCPConfig):
    docker_image: str
    environment: dict[str, str]
    available_methods: list[str]

class PerplexityMCPConfig(MCPConfig):
    docker_image: str
    environment: dict[str, str]
    available_methods: list[str]
```

### Between agent-3 (E2B Launcher) and agent-4 (MCP Bridge)

**E2B Launcher exposes:**
```python
class CloudSandbox:
    sandbox_id: str
    async def create() -> str
    async def attach_mcp(mcp_name: str, config: dict) -> None
    async def execute_command(cmd: str) -> str
```

**MCP Bridge needs:**
- sandbox_id for network connectivity
- Access to sandbox filesystem for mounting

### Between agent-1 (Workflows) and agent-4/5 (MCP)

**Workflows need:**
```python
# Research via Exa
mcp_bridge.call_mcp("exa", "search", {"query": "...", "num_results": 5})

# Validation via Perplexity
mcp_bridge.call_mcp("perplexity", "ask", {"question": "..."})

# GitHub operations
mcp_bridge.call_mcp("github", "create_pull_request", {...})
```

---

## Testing Checklist

### Before Hackathon Starts
- [ ] All dependencies install correctly
- [ ] E2B API key works (test with simple sandbox)
- [ ] GitHub token has correct permissions
- [ ] All file skeletons have correct imports
- [ ] No syntax errors in any skeleton code
- [ ] CLI stubs run without crashing

### During Development
- [ ] E2B sandbox starts successfully
- [ ] Tmux session created with 4 panes
- [ ] Agents can discover each other in sandbox
- [ ] Messages deliver between agents
- [ ] File locks work in E2B environment
- [ ] GitHub MCP connects and works
- [ ] Filesystem MCP connects and works
- [ ] Exa MCP connects and works
- [ ] Dashboard shows real-time updates
- [ ] Autonomous loop runs without errors

### Before Submission
- [ ] Full demo runs 3x successfully
- [ ] Video is under 3 minutes
- [ ] README is clear and complete
- [ ] All code is commented
- [ ] No TODOs or FIXMEs in code
- [ ] No credentials committed
- [ ] All tests pass

---

## Risk Mitigation

### If E2B Integration Fails
**Fallback:** Demo with local tmux (existing system works)
**Impact:** Lose E2B requirement but keep MCP requirement

### If MCP Servers Don't Work
**Priority:**
1. GitHub MCP (MUST HAVE)
2. Filesystem MCP (MUST HAVE)
3. Exa MCP (NICE TO HAVE)
4. Perplexity MCP (OPTIONAL)

**Minimum Viable:** GitHub + Filesystem = meets requirements

### If Running Out of Time
**Core Requirements (Must Have):**
1. Basic E2B sandbox with tmux
2. GitHub MCP integration
3. Simple 2-agent coordination
4. Dashboard showing agents

**Nice to Have (Skip if needed):**
1. 4-agent complex coordination
2. Full autonomous loop
3. Multiple MCPs
4. Fancy dashboard features

---

## Communication Protocol

### Daily Check-ins
- Morning: What are you working on today?
- Evening: What did you complete? Any blockers?

### Blocked Protocol
1. Send BLOCKED message with description
2. Tag relevant agent if you need their help
3. Continue on other tasks if possible
4. Don't wait more than 30 min before asking for help

### File Locking for Prep Work
- ALWAYS acquire file lock before editing shared files
- ALWAYS release lock immediately after
- If lock is held >5 min, send message to holder

---

## Success Criteria

### Minimum Viable Demo
- [ ] E2B sandbox starts with 4 agents
- [ ] Agents discover each other
- [ ] Messages deliver between agents
- [ ] At least 1 MCP works (GitHub)
- [ ] Can create GitHub PR
- [ ] Dashboard shows agents

### Target Demo
- [ ] All of above +
- [ ] 4 MCPs working (GitHub, Filesystem, Exa, Perplexity)
- [ ] Agents autonomously research and implement
- [ ] Code review debates visible
- [ ] Consensus mechanism works
- [ ] Runs for 30+ minutes autonomously

### Stretch Goals
- [ ] All of above +
- [ ] Runs for 2+ hours autonomously
- [ ] Multiple feature implementations
- [ ] Advanced consensus algorithms
- [ ] Beautiful dashboard UI

---

**Last Updated:** 2025-11-19 by agent-5
**Status:** Ready for prep work
**Next Action:** All agents start on assigned prep tasks
