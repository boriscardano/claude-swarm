# Claude Swarm - Implementation Plan

**Version**: 1.0
**Date**: 2025-11-07
**Target**: Multi-agent coordination system for Claude Code instances

---

## Executive Summary

This plan outlines the complete implementation of Claude Swarm, a tmux-based coordination system enabling multiple Claude Code agents to work together on shared projects. The system will be built by **5+ agents working in parallel**, implementing 7 core features across 3 phases.

**Key Goals:**
- Enable 8+ Claude Code agents to coordinate without human intervention
- Prevent file conflicts through distributed locking
- Provide reliable messaging and acknowledgment systems
- Offer real-time monitoring and visibility
- Create a reusable protocol for agent coordination

---

## Technology Stack

### Core Technologies
- **Python 3.12+** - Main implementation language
- **uv** - Fast Python package manager (replaces pip/poetry)
- **tmux 3.0+** - Terminal multiplexer for agent isolation
- **JSON** - Data serialization
- **Markdown** - Documentation and coordination files

### Python Dependencies (via uv)
```toml
[project.dependencies]
# Core functionality - no external deps needed for MVP
# Python stdlib provides: subprocess, json, pathlib, datetime, logging

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
]
```

### Development Tools
- **uv** - Package management and virtual environments
- **pytest** - Testing framework
- **black** - Code formatting
- **ruff** - Fast Python linter
- **mypy** - Static type checking
- **pre-commit** - Git hooks (optional)

---

## Project Structure (Target)

```
claude-swarm/
├── .git/
├── .gitignore
├── .python-version          # 3.12
├── pyproject.toml           # uv-managed dependencies
├── uv.lock                  # Lock file for reproducible builds
├── README.md                # Project overview
├── IMPLEMENTATION_PLAN.md   # This file
├── AGENT_PROTOCOL.md        # Instructions for Claude Code agents
├── CONTRIBUTING.md          # Contribution guidelines
├── LICENSE                  # MIT License
├── src/
│   └── claudeswarm/
│       ├── __init__.py      # Package initialization
│       ├── discovery.py     # Agent discovery system
│       ├── messaging.py     # Message sending/receiving
│       ├── locking.py       # File lock management
│       ├── ack.py           # Acknowledgment system
│       ├── monitoring.py    # Log aggregation & dashboard
│       ├── coordination.py  # Shared coordination file management
│       ├── cli.py           # Command-line interface
│       └── utils.py         # Common utilities
├── bin/
│   ├── discover-agents      # Bash wrapper
│   ├── send-to-agent        # Bash wrapper
│   ├── broadcast-to-all     # Bash wrapper
│   ├── acquire-file-lock    # Bash wrapper
│   ├── release-file-lock    # Bash wrapper
│   ├── who-has-lock         # Bash wrapper
│   ├── send-with-ack        # Bash wrapper
│   └── start-monitoring     # Bash wrapper
├── tests/
│   ├── __init__.py
│   ├── test_discovery.py
│   ├── test_messaging.py
│   ├── test_locking.py
│   ├── test_ack.py
│   ├── test_coordination.py
│   └── integration/
│       ├── __init__.py
│       ├── test_multi_agent.py
│       ├── test_code_review.py
│       └── test_blocking_escalation.py
├── examples/
│   ├── demo_setup.sh        # Sets up demo tmux session
│   ├── sample_coordination/
│   └── tutorials/
└── docs/
    ├── getting-started.md
    ├── architecture.md
    ├── protocol.md
    ├── api-reference.md
    └── troubleshooting.md
```

---

## Implementation Phases

### Phase 0: Project Setup (Foundation)
**Duration**: 1 day
**Agents**: 1 agent (Agent-Setup)

#### Tasks
1. **Configure uv package management**
   - Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Initialize project: `uv init` (already done)
   - Configure pyproject.toml with proper metadata
   - Add dev dependencies
   - Create uv.lock file

2. **Create Python package structure**
   - Create `src/claudeswarm/` directory
   - Add `__init__.py` files
   - Create empty module files
   - Setup `__version__` in `__init__.py`

3. **Setup development tooling**
   - Configure black (line length 100)
   - Configure ruff (select rules)
   - Configure mypy (strict mode)
   - Add pytest configuration
   - Create pre-commit config (optional)

4. **Create bin/ directory with script templates**
   - Create all 8 bash wrapper scripts
   - Make them executable
   - Add proper shebang and error handling
   - Add help text to each script

5. **Initialize documentation structure**
   - Create docs/ directory
   - Create examples/ directory
   - Create tests/ directory with __init__.py

**Deliverables:**
- ✅ Proper Python package structure
- ✅ uv configured with dependencies
- ✅ Development tools configured
- ✅ Bin scripts created (empty but ready)
- ✅ Directory structure complete

**Testing:**
- `uv sync` works without errors
- `uv run python -c "import claudeswarm"` succeeds
- All bin scripts are executable
- `uv run pytest` finds test directory

---

### Phase 1: Core Coordination Features (Foundation)
**Duration**: 3-4 days
**Agents**: 3 agents in parallel

---

#### Agent 1: Agent Discovery System
**Module**: `src/claudeswarm/discovery.py`
**Priority**: Critical (blocks messaging)

##### Tasks
1. **Implement tmux session detection**
   - Use `subprocess` to call `tmux list-panes -a -F '#{session_name}:#{window_index}:#{pane_index}:#{pane_pid}:#{pane_current_command}'`
   - Parse output into structured data
   - Handle cases where tmux isn't running
   - Error handling for permission issues

2. **Implement Claude Code process identification**
   - Filter processes by command name patterns
   - Support multiple Claude Code invocation patterns
   - Detect `claude` or `claude-code` processes
   - Get process metadata (PID, start time)

3. **Implement agent registry generation**
   - Create `ACTIVE_AGENTS.json` format
   - Include: agent ID, pane index, PID, status, last_seen timestamp
   - Write atomically (tmp file + rename)
   - Handle concurrent writes gracefully

4. **Implement registry refresh mechanism**
   - Auto-discover every 30 seconds (optional background mode)
   - Mark stale agents (not seen in 60 seconds)
   - Remove dead agents from registry
   - Preserve agent IDs when possible

5. **Create CLI command**
   - `discover-agents` - trigger discovery manually
   - `discover-agents --watch` - continuous mode
   - `discover-agents --json` - output to stdout

**Data Structures:**
```python
@dataclass
class Agent:
    id: str              # agent-0, agent-1, etc.
    pane_index: str      # tmux pane identifier
    pid: int             # process ID
    status: str          # active, stale, dead
    last_seen: datetime
    session_name: str

@dataclass
class AgentRegistry:
    session_name: str
    updated_at: datetime
    agents: List[Agent]
```

**Testing Requirements:**
- Unit tests: tmux output parsing, agent ID generation
- Integration test: detect 3 mock tmux panes
- Test stale agent removal
- Test registry file format validation
- Test concurrent discovery calls

**Dependencies:** None (can start immediately)

---

#### Agent 2: Messaging System
**Module**: `src/claudeswarm/messaging.py`
**Priority**: Critical (enables all coordination)

##### Tasks
1. **Implement message format and validation**
   - Define MessageType enum (QUESTION, REVIEW-REQUEST, BLOCKED, COMPLETED, etc.)
   - Create Message dataclass with sender, timestamp, type, content
   - Implement message serialization/deserialization
   - Add message validation rules

2. **Implement tmux send-keys integration**
   - Use `tmux send-keys` to deliver messages
   - Proper escaping for special characters (quotes, newlines, etc.)
   - Handle delivery failures gracefully
   - Retry mechanism for transient failures

3. **Implement direct messaging (point-to-point)**
   - `send_message(target_pane, message_type, content)`
   - Look up target pane from agent registry
   - Format message with header: `[AGENT-X][timestamp][TYPE]: content`
   - Log to `agent_messages.log`
   - Return delivery confirmation

4. **Implement broadcast messaging**
   - `broadcast_message(message_type, content, exclude_self=True)`
   - Send to all agents in registry except sender
   - Parallel delivery to multiple panes
   - Track delivery success/failure per recipient
   - Aggregate results

5. **Implement message logging**
   - Structured logging to `agent_messages.log`
   - Include: timestamp, sender, recipients, type, content, delivery status
   - Rotate logs when they exceed 10MB
   - JSON format for easy parsing

6. **Implement rate limiting**
   - Max 10 messages per agent per minute
   - Track message counts per agent
   - Reject messages exceeding rate limit
   - Reset counters every minute

7. **Create CLI commands**
   - `send-to-agent <target> <type> <message>`
   - `broadcast-to-all <type> <message>`

**Data Structures:**
```python
class MessageType(Enum):
    QUESTION = "QUESTION"
    REVIEW_REQUEST = "REVIEW-REQUEST"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CHALLENGE = "CHALLENGE"
    INFO = "INFO"
    ACK = "ACK"

@dataclass
class Message:
    sender_id: str
    timestamp: datetime
    msg_type: MessageType
    content: str
    recipients: List[str]
    msg_id: str  # UUID for tracking
```

**Testing Requirements:**
- Unit tests: message formatting, escaping, validation
- Mock tmux send-keys, verify correct commands generated
- Test rate limiting with rapid message sending
- Test broadcast to multiple recipients
- Test special character handling (quotes, newlines, etc.)
- Integration test: send message between 2 mock panes

**Dependencies:**
- Needs `discovery.py` for agent registry lookup
- **Coordination Point**: Agent 2 waits for Agent 1's registry structure

---

#### Agent 3: File Locking System
**Module**: `src/claudeswarm/locking.py`
**Priority**: Critical (prevents conflicts)

##### Tasks
1. **Implement lock file structure**
   - Create `.agent_locks/` directory
   - Lock file naming: hash(filepath) → `src_auth_py.lock`
   - Lock file format: JSON with agent_id, filepath, locked_at, reason
   - Atomic lock file creation (exclusive mode)

2. **Implement lock acquisition**
   - `acquire_lock(filepath, agent_id, reason, timeout=30)`
   - Check if lock already exists
   - If exists, check if stale (>5 minutes old)
   - If stale, auto-release and acquire
   - If active, return conflict with lock holder info
   - Write lock file atomically

3. **Implement lock release**
   - `release_lock(filepath, agent_id)`
   - Verify agent owns the lock
   - Remove lock file
   - Log release event
   - Handle already-released gracefully

4. **Implement lock querying**
   - `who_has_lock(filepath)` - return current lock holder
   - `list_all_locks()` - return all active locks
   - `check_lock_status(filepath)` - detailed lock info

5. **Implement stale lock cleanup**
   - Background task to scan for stale locks
   - Locks older than 5 minutes → auto-release
   - Log cleanup actions
   - Run every 60 seconds (optional daemon mode)

6. **Implement glob pattern locking**
   - Support locking patterns like `src/**/*.py`
   - Check if new lock conflicts with existing patterns
   - Use `fnmatch` for pattern matching

7. **Create CLI commands**
   - `acquire-file-lock <filepath> <agent_id> [reason]`
   - `release-file-lock <filepath> <agent_id>`
   - `who-has-lock <filepath>`
   - `list-all-locks`

**Data Structures:**
```python
@dataclass
class FileLock:
    agent_id: str
    filepath: str
    locked_at: float  # Unix timestamp
    reason: str

@dataclass
class LockConflict:
    filepath: str
    current_holder: str
    locked_at: datetime
    reason: str
```

**Testing Requirements:**
- Unit tests: lock acquisition, release, conflict detection
- Test stale lock detection and cleanup
- Test concurrent lock attempts (race condition simulation)
- Test glob pattern matching
- Test lock file corruption handling
- Integration test: 2 agents competing for same file

**Dependencies:** None (can start immediately)

---

### Phase 2: Advanced Features
**Duration**: 3-4 days
**Agents**: 3 agents in parallel

---

#### Agent 4: Acknowledgment System
**Module**: `src/claudeswarm/ack.py`
**Priority**: High (reliability)

##### Tasks
1. **Implement ACK message tracking**
   - Create `PENDING_ACKS.json` structure
   - Track messages requiring acknowledgment
   - Store: msg_id, sender, recipient, sent_at, retry_count
   - Atomic updates to tracking file

2. **Implement send-with-ack**
   - `send_with_ack(target, msg_type, content, timeout=30)`
   - Generate unique message ID
   - Send message with [REQUIRES-ACK] flag
   - Add to pending ACKs tracking
   - Return immediately (non-blocking)

3. **Implement ACK reception**
   - Listen for [ACK-{msg_id}] messages
   - Match ACK to pending entry
   - Remove from pending list
   - Log acknowledgment received
   - Notify sender if callback provided

4. **Implement retry mechanism**
   - Background task checking pending ACKs
   - If timeout exceeded (30s), retry sending
   - Max 3 retry attempts
   - Exponential backoff: 30s, 60s, 120s
   - After max retries, escalate

5. **Implement escalation**
   - After max retries, broadcast to all agents
   - Message format: [UNACKNOWLEDGED] original message
   - Request any agent to help
   - Log escalation event

6. **Create CLI commands**
   - `send-with-ack <target> <type> <message>`
   - `send-ack <msg_id> <agent_id>`
   - `check-pending-acks [agent_id]`

**Data Structures:**
```python
@dataclass
class PendingAck:
    msg_id: str
    sender_id: str
    recipient_id: str
    message: Message
    sent_at: datetime
    retry_count: int
    next_retry_at: datetime
```

**Testing Requirements:**
- Unit tests: ACK tracking, retry logic, timeout calculation
- Mock message delivery, verify retries occur
- Test escalation after max retries
- Test ACK matching and removal
- Integration test: send with ACK, receive ACK, verify removal

**Dependencies:**
- Needs `messaging.py` for sending messages
- **Coordination Point**: Agent 4 waits for Agent 2's messaging system

---

#### Agent 5: Monitoring Dashboard
**Module**: `src/claudeswarm/monitoring.py`
**Priority**: Medium (visibility)

##### Tasks
1. **Implement log file monitoring**
   - Tail `agent_messages.log` continuously
   - Parse log entries in real-time
   - Buffer last 100 messages in memory
   - Handle log rotation gracefully

2. **Implement message filtering**
   - Filter by message type
   - Filter by agent ID (sender or recipient)
   - Filter by time range
   - Support multiple filters simultaneously

3. **Implement color coding**
   - ANSI color codes for terminal output
   - RED: BLOCKED, ERROR
   - YELLOW: QUESTION, REQUIRES-ACK
   - GREEN: COMPLETED, ACK
   - BLUE: INFO, REVIEW-REQUEST
   - MAGENTA: Lock operations

4. **Implement status sidebar**
   - Show active agent count (from registry)
   - Show active locks count and list
   - Show pending ACKs count
   - Auto-refresh every 2 seconds

5. **Implement tmux pane integration**
   - Launch monitoring in dedicated tmux pane
   - Auto-create pane if not exists
   - Proper pane layout configuration
   - Handle monitoring pane closure gracefully

6. **Create CLI commands**
   - `start-monitoring` - launch monitoring pane
   - `start-monitoring --filter-type BLOCKED` - filtered view
   - `start-monitoring --filter-agent agent-3` - agent-specific view

**Data Structures:**
```python
@dataclass
class MonitoringState:
    active_agents: List[Agent]
    active_locks: List[FileLock]
    pending_acks: List[PendingAck]
    recent_messages: deque[Message]  # Last 100

class MessageFilter:
    msg_types: Optional[Set[MessageType]]
    agent_ids: Optional[Set[str]]
    time_range: Optional[Tuple[datetime, datetime]]
```

**Testing Requirements:**
- Unit tests: log parsing, filtering, color coding
- Mock log file, verify tailing works
- Test filter combinations
- Test status sidebar updates
- Manual test: verify colors appear correctly in terminal

**Dependencies:**
- Needs `discovery.py` for agent count
- Needs `locking.py` for lock status
- Needs `ack.py` for pending ACKs count
- **Coordination Point**: Agent 5 integrates outputs from Agents 1, 3, 4

---

#### Agent 1 (Returns): Shared Coordination File
**Module**: `src/claudeswarm/coordination.py`
**Priority**: Medium (team coordination)

##### Tasks
1. **Implement COORDINATION.md template**
   - Define sections: Sprint Goals, Current Work, Blocked, Code Review Queue, Decisions
   - Create template generator
   - Initialize empty coordination file
   - Section markers for easy parsing

2. **Implement section-based editing**
   - Parse COORDINATION.md into sections
   - Allow updates to specific sections only
   - Preserve other sections during update
   - Markdown formatting preservation

3. **Implement lock integration**
   - Must acquire lock before editing COORDINATION.md
   - Auto-release after update
   - Handle lock conflicts gracefully
   - Timeout for lock acquisition: 10 seconds

4. **Implement atomic updates**
   - Read current content
   - Apply changes to specific section
   - Write back atomically (tmp file + rename)
   - Retry on conflict

5. **Implement query functions**
   - `get_current_work()` - what's in progress
   - `get_blocked_items()` - blocked tasks
   - `get_review_queue()` - pending reviews
   - `get_decisions()` - decisions made

6. **Create CLI commands**
   - `update-coordination <section> <content>`
   - `query-coordination <section>`
   - `init-coordination` - create template

**Testing Requirements:**
- Unit tests: template generation, section parsing, atomic updates
- Test concurrent updates to different sections
- Test lock integration
- Integration test: multiple agents updating different sections

**Dependencies:**
- Needs `locking.py` for file locking
- **Coordination Point**: Agent 1 reuses lock system from Agent 3

---

### Phase 3: Documentation & Testing
**Duration**: 2-3 days
**Agents**: 2-3 agents in parallel

---

#### Agent 2 (Returns): Protocol Documentation
**Files**: `AGENT_PROTOCOL.md`, `docs/protocol.md`, `docs/getting-started.md`
**Priority**: High (enables agent usage)

##### Tasks
1. **Write AGENT_PROTOCOL.md**
   - Getting Started section
   - Communication Rules (message types reference)
   - File Locking Protocol (critical: never edit without lock)
   - Acknowledgment Requirements
   - Coordination Patterns (common workflows)
   - Best Practices (dos and don'ts)
   - Examples (real coordination scenarios)
   - Troubleshooting (common issues)

2. **Write docs/getting-started.md**
   - Installation instructions (uv-based)
   - First-time setup
   - Quick start tutorial
   - Example: 2-agent coordination task
   - Configuration options
   - Troubleshooting guide

3. **Write docs/architecture.md**
   - System design overview
   - Component interaction diagrams (ASCII art)
   - Message flow diagrams
   - Lock acquisition flowchart
   - Extension points

4. **Write docs/api-reference.md**
   - All CLI commands documented
   - All Python APIs documented
   - Parameters, return values, examples
   - Error handling

5. **Update README.md**
   - Project description
   - Quick start (one-liner install)
   - Architecture overview
   - Link to detailed docs
   - Contributing guidelines
   - License information

**Testing Requirements:**
- Have another human review for clarity
- Test instructions by following them exactly
- Verify all code examples work
- Check all links

**Dependencies:**
- Needs all features implemented (Agents 1-5)
- **Coordination Point**: Agent 2 waits for all Phase 1 & 2 completions

---

#### Agent 3 (Returns): Integration Tests
**Files**: `tests/integration/`, example scripts
**Priority**: High (quality assurance)

##### Tasks
1. **Write integration test framework**
   - Helper functions to create mock tmux sessions
   - Helper to launch mock Claude Code instances
   - Utilities to verify message delivery
   - Utilities to verify lock state
   - Test cleanup functions

2. **Test Scenario 1: Basic Coordination**
   - Create 3 mock agents
   - Agent 0 discovers others
   - Agent 0 broadcasts task
   - Agents acknowledge
   - Agent 1 acquires lock, works, releases
   - Agent 2 acquires lock, reviews
   - Verify: messages delivered, no conflicts, monitoring shows activity

3. **Test Scenario 2: Code Review Workflow**
   - Agent 3 requests review
   - Agent 1 acknowledges, acquires lock
   - Agent 1 reviews, provides feedback
   - Agent 3 addresses feedback
   - Agent 1 approves
   - Verify: proper ACKs, lock transitions, coordination file updated

4. **Test Scenario 3: Blocking & Escalation**
   - Agent 2 sends ACK-required message to Agent 5
   - Agent 5 doesn't respond (simulate hang)
   - System retries 3 times
   - System escalates to broadcast
   - Agent 4 responds
   - Verify: retries occurred, escalation worked, alternate agent helped

5. **Test Scenario 4: Stale Lock Recovery**
   - Agent 7 acquires lock
   - Simulate crash (kill process)
   - Wait 5 minutes (or mock time)
   - Agent 3 tries to acquire lock
   - System detects stale lock, auto-releases
   - Agent 3 successfully acquires
   - Verify: stale detection, auto-cleanup, successful acquisition

6. **Create demo setup script**
   - `examples/demo_setup.sh` - creates 8-pane tmux session
   - Launches Claude Code in each pane (optional)
   - Shows example coordination task
   - Automated demo walkthrough

**Testing Requirements:**
- All integration tests pass
- Tests run in CI/CD (GitHub Actions)
- Code coverage > 80%
- No flaky tests

**Dependencies:**
- Needs all features implemented
- **Coordination Point**: Agent 3 tests everything from Agents 1-5

---

#### Agent 6 (Optional): Examples & Tutorials
**Files**: `examples/`, tutorial scripts
**Priority**: Low (nice-to-have)

##### Tasks
1. **Create example projects**
   - `examples/sample_coordination/` - simple web app example
   - Show agents building features in parallel
   - Include COORDINATION.md snapshots
   - Include message logs

2. **Create tutorial scripts**
   - `examples/tutorials/01_discovery.sh` - discovery walkthrough
   - `examples/tutorials/02_messaging.sh` - messaging demo
   - `examples/tutorials/03_locking.sh` - locking demo
   - Interactive tutorials with explanations

**Dependencies:**
- Needs all features implemented

---

## Multi-Agent Coordination Strategy

### High-Level Overview

**Phase 1** - 3 agents work in parallel on independent features:
- **Agent 1**: Discovery system (no dependencies)
- **Agent 2**: Messaging system (depends on discovery structure)
- **Agent 3**: Locking system (no dependencies)

**Phase 2** - 3 agents work in parallel:
- **Agent 4**: ACK system (depends on messaging)
- **Agent 5**: Monitoring (integrates discovery, locking, ACK)
- **Agent 1** (returns): Coordination file (depends on locking)

**Phase 3** - 2-3 agents work in parallel:
- **Agent 2** (returns): Documentation (depends on all features)
- **Agent 3** (returns): Integration tests (depends on all features)
- **Agent 6** (optional): Examples (depends on all features)

### Detailed Agent Coordination

#### Phase 1 Coordination

**Agent 1 (Discovery)** - Start immediately
- Day 1 morning: Implement tmux detection and parsing
- Day 1 afternoon: Implement registry generation
- Day 2 morning: Implement refresh mechanism and CLI
- Day 2 afternoon: Write unit tests
- **Handoff**: Publish `AgentRegistry` data structure to shared location (or code comment)

**Agent 2 (Messaging)** - Start immediately, wait for structure
- Day 1 morning: Implement message format and validation (independent)
- Day 1 afternoon: Implement tmux send-keys integration (independent)
- **WAIT**: Need `AgentRegistry` structure from Agent 1
- Day 2 morning: Integrate with discovery, implement direct messaging
- Day 2 afternoon: Implement broadcast and rate limiting
- Day 3 morning: Write unit tests and CLI

**Agent 3 (Locking)** - Start immediately
- Day 1 morning: Implement lock file structure and atomic operations
- Day 1 afternoon: Implement lock acquisition and release
- Day 2 morning: Implement querying and stale cleanup
- Day 2 afternoon: Implement glob patterns and CLI
- Day 3 morning: Write unit tests

**Coordination Points:**
- **Daily sync**: Brief message exchange about progress
- **Agent 2 depends on Agent 1**: Agent 1 commits registry structure by end of Day 1
- **No blocking**: Agent 2 can work on message formatting while waiting

---

#### Phase 2 Coordination

**Agent 4 (ACK)** - Starts after Agent 2 completes
- **WAIT**: Need completed `messaging.py`
- Day 4 morning: Implement ACK tracking and send-with-ack
- Day 4 afternoon: Implement retry mechanism
- Day 5 morning: Implement escalation and CLI
- Day 5 afternoon: Write unit tests

**Agent 5 (Monitoring)** - Starts when components available
- Day 4 morning: Implement log monitoring and filtering (independent)
- Day 4 afternoon: Implement color coding and tmux integration (independent)
- **WAIT**: Need discovery, locking, ACK for status sidebar
- Day 5 morning: Integrate status sidebar with other components
- Day 5 afternoon: Test and polish

**Agent 1 (returns) (Coordination File)** - Starts after Agent 3 completes
- **WAIT**: Need completed `locking.py`
- Day 4 morning: Implement template and section parsing
- Day 4 afternoon: Implement lock integration and atomic updates
- Day 5 morning: Implement query functions and CLI
- Day 5 afternoon: Write unit tests

**Coordination Points:**
- **Agent 4 blocked** until Agent 2 done (estimated Day 3 afternoon)
- **Agent 1 (return) blocked** until Agent 3 done (estimated Day 3 morning)
- **Agent 5** can work independently until Day 5, then integrates
- **Sync**: Mid-phase check-in to verify APIs compatible

---

#### Phase 3 Coordination

**Agent 2 (returns) (Documentation)** - Starts when all features done
- **WAIT**: All Phase 1 & 2 features complete
- Day 6-7: Write all documentation files
- Test all examples
- Review for clarity

**Agent 3 (returns) (Integration Tests)** - Starts when all features done
- **WAIT**: All Phase 1 & 2 features complete
- Day 6: Write test framework and Scenario 1-2
- Day 7: Write Scenario 3-4, create demo setup
- Run full test suite

**Agent 6 (optional) (Examples)** - Starts when all features done
- Day 7-8: Create example projects and tutorials

**Coordination Points:**
- **Both blocked** until all Phase 1 & 2 complete (estimated end of Day 5)
- **Parallel work**: Agents 2 & 3 work simultaneously, no dependencies
- **Final review**: All agents review complete system together

---

### Coordination Tools for Development

During development, agents should:

1. **Use this plan** as shared coordination document
2. **Update status** in this file (add checkmarks to completed tasks)
3. **Communicate blockers** explicitly ("Agent 2: BLOCKED on Agent 1 registry structure")
4. **Define interfaces early** (data structures, function signatures)
5. **Commit frequently** to avoid conflicts
6. **Write API docs** in docstrings as you code
7. **Run tests** before marking tasks complete

---

## Testing Strategy

### Unit Tests (per module)
- **discovery.py**: tmux parsing, agent ID generation, registry updates
- **messaging.py**: message formatting, escaping, rate limiting, broadcast
- **locking.py**: lock acquisition, conflict detection, stale cleanup, glob matching
- **ack.py**: ACK tracking, retry logic, timeout calculation, escalation
- **coordination.py**: section parsing, atomic updates, lock integration
- **monitoring.py**: log parsing, filtering, color coding

### Integration Tests
- **test_multi_agent.py**: Basic 3-agent coordination
- **test_code_review.py**: Code review workflow
- **test_blocking_escalation.py**: Blocking and escalation
- **test_stale_lock_recovery.py**: Stale lock detection

### Manual Testing
- Demo with real tmux session and Claude Code instances
- Verify colors in monitoring pane
- Test with 8 agents simultaneously
- Load testing: 100+ messages/minute

### CI/CD
- GitHub Actions workflow
- Run tests on push and PR
- Code coverage reporting
- Linting with ruff and black

---

## Success Criteria

### Functional Requirements
- ✅ 8 Claude Code agents can discover each other automatically
- ✅ Messages delivered reliably via tmux send-keys
- ✅ File locks prevent conflicts (zero conflicts in testing)
- ✅ ACK system ensures critical messages received
- ✅ Stale locks auto-recover
- ✅ Monitoring provides real-time visibility
- ✅ Agents can follow AGENT_PROTOCOL.md successfully

### Performance Targets
- Message delivery: < 100ms
- Lock acquisition: < 1 second (when available)
- Agent discovery: < 2 seconds
- No message loss
- Handle 100+ messages/minute across 8 agents

### Quality Metrics
- Code coverage > 80%
- All integration tests pass
- Documentation complete and clear
- No critical bugs in first release

---

## Timeline Estimate

| Phase | Duration | Agents | Key Deliverables |
|-------|----------|--------|------------------|
| Phase 0: Setup | 0.5-1 day | 1 | Project structure, uv config, dev tools |
| Phase 1: Core | 3-4 days | 3 | Discovery, Messaging, Locking |
| Phase 2: Advanced | 3-4 days | 3 | ACK, Monitoring, Coordination File |
| Phase 3: Docs/Tests | 2-3 days | 2-3 | Documentation, Integration tests |
| **Total** | **8-12 days** | **5-6** | **Complete system** |

**Note**: Timeline assumes agents work in parallel where possible. Sequential approach would take 15-20 days.

---

## Risk Mitigation

### Risk 1: Agent 2 blocked on Agent 1
**Mitigation**: Agent 1 publishes data structures early (end of Day 1). Agent 2 works on independent parts first.

### Risk 2: Integration issues in Phase 2
**Mitigation**: Define clear APIs in Phase 1. Agents write comprehensive docstrings. Mid-phase sync meeting.

### Risk 3: Testing reveals critical bugs
**Mitigation**: Unit tests throughout development. Early integration testing. Buffer time in Phase 3.

### Risk 4: tmux behavior varies across systems
**Mitigation**: Test on multiple tmux versions. Document required tmux version. Graceful error handling.

### Risk 5: Performance issues with 8+ agents
**Mitigation**: Rate limiting built in. Efficient message delivery. Load testing before release.

---

## Future Enhancements (Post-MVP)

These features are out of scope for initial implementation but valuable for future versions:

1. **Web-based monitoring dashboard** - Replace tmux monitoring pane
2. **Agent role specialization** - Backend, frontend, testing, review roles
3. **Hierarchical coordination** - Lead agent + worker agents
4. **Conflict resolution strategies** - Automatic merge conflict handling
5. **Learning from past patterns** - ML-based coordination optimization
6. **Git integration** - Auto-commit, PR creation, review workflows
7. **Slack/Discord notifications** - External visibility
8. **Performance analytics** - Metrics on agent efficiency
9. **Non-tmux support** - Support screen, zellij, or standalone mode
10. **Cloud deployment** - Distributed agents across machines

---

## Appendix A: uv Quick Reference

### Common uv Commands
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Initialize project
uv init

# Sync dependencies from pyproject.toml
uv sync

# Add dependency
uv add pytest

# Add dev dependency
uv add --dev black

# Run command in venv
uv run python -m claudeswarm.cli

# Run tests
uv run pytest

# Build package
uv build

# Update dependencies
uv lock --upgrade
```

---

## Appendix B: Agent Communication Protocol

### Message Format
```
[AGENT-{id}][YYYY-MM-DD HH:MM:SS][TYPE]: message content
```

### Message Types
- **QUESTION**: Ask for information or clarification
- **REVIEW-REQUEST**: Request code review
- **BLOCKED**: Indicate work is blocked
- **COMPLETED**: Announce task completion
- **CHALLENGE**: Challenge a decision or approach
- **INFO**: Share information
- **ACK**: Acknowledge message receipt

### Example Messages
```
[AGENT-1][2025-11-07 14:30:15][QUESTION]: What database schema are we using?
[AGENT-2][2025-11-07 14:30:30][INFO]: Using PostgreSQL with SQLAlchemy ORM
[AGENT-1][2025-11-07 14:30:45][ACK]: Thanks, proceeding with Postgres models
[AGENT-3][2025-11-07 14:31:00][REVIEW-REQUEST]: Please review PR #12 - auth middleware
[AGENT-4][2025-11-07 14:31:15][BLOCKED][REQUIRES-ACK]: Need auth.py from Agent-1 to proceed
```

---

## Appendix C: File Lock Protocol

### Lock Acquisition Flow
1. Agent wants to edit `src/auth.py`
2. Agent calls `acquire-file-lock src/auth.py agent-2 "implementing JWT"`
3. System checks `.agent_locks/src_auth_py.lock`
4. If not exists → create lock, return success
5. If exists and stale (>5 min) → remove old lock, create new lock, return success
6. If exists and active → return conflict with holder info
7. If conflict → agent messages lock holder: "When will you be done with auth.py?"

### Lock Release Flow
1. Agent done editing `src/auth.py`
2. Agent calls `release-file-lock src/auth.py agent-2`
3. System verifies agent-2 owns lock
4. System removes `.agent_locks/src_auth_py.lock`
5. System broadcasts: `[AGENT-2][timestamp][INFO]: Released lock on src/auth.py`

### Critical Rule
**NEVER edit a file without acquiring its lock first.** This is the most important rule in the protocol.

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-07 | Agent-Setup | Initial comprehensive plan |

---

**End of Implementation Plan**
