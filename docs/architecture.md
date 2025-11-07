# Claude Swarm Architecture

This document provides a comprehensive overview of the Claude Swarm system design, component interactions, and architectural patterns.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Components](#core-components)
3. [Component Interaction Diagrams](#component-interaction-diagrams)
4. [Message Flow](#message-flow)
5. [Lock Acquisition Flow](#lock-acquisition-flow)
6. [Data Structures](#data-structures)
7. [Extension Points](#extension-points)

---

## System Overview

Claude Swarm is a **tmux-based coordination system** that enables multiple Claude Code agents to work together on shared projects without conflicts.

### Key Design Principles

1. **No Central Server** - Fully distributed, peer-to-peer coordination
2. **tmux as Transport** - Use tmux send-keys for reliable message delivery
3. **File-Based State** - JSON files for agent registry and locks
4. **Atomic Operations** - Prevent race conditions with atomic file writes
5. **Self-Healing** - Automatic stale lock cleanup and agent status updates
6. **Zero Dependencies** - Pure Python stdlib, no external packages needed

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TMUX SESSION                              │
│                                                                   │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐    │
│  │  Pane 0        │  │  Pane 1        │  │  Pane 2        │    │
│  │  agent-0       │  │  agent-1       │  │  agent-2       │    │
│  │  (coordinator) │  │  (backend)     │  │  (frontend)    │    │
│  └────────┬───────┘  └────────┬───────┘  └────────┬───────┘    │
│           │                   │                   │              │
└───────────┼───────────────────┼───────────────────┼──────────────┘
            │                   │                   │
            │ tmux send-keys    │ tmux send-keys    │ tmux send-keys
            ├───────────────────┼───────────────────┤
            │                   │                   │
            ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLAUDE SWARM LAYER                            │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Discovery System (discovery.py)                          │  │
│  │  • Scans tmux panes for Claude Code processes            │  │
│  │  • Maintains ACTIVE_AGENTS.json registry                 │  │
│  │  • Detects stale agents (not seen in 60s)                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Messaging System (messaging.py)                          │  │
│  │  • Send direct messages (agent → agent)                   │  │
│  │  • Broadcast messages (agent → all)                       │  │
│  │  • Rate limiting (10 msg/min)                             │  │
│  │  • Message logging to agent_messages.log                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  File Locking System (locking.py)                         │  │
│  │  • Acquire/release exclusive file locks                   │  │
│  │  • Glob pattern support (src/**/*.py)                     │  │
│  │  • Stale lock detection (5 min timeout)                   │  │
│  │  • Conflict resolution                                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ACK System (ack.py)                                       │  │
│  │  • Track messages requiring acknowledgment                │  │
│  │  • Retry with exponential backoff                         │  │
│  │  • Escalate to broadcast after 3 retries                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Monitoring System (monitoring.py)                        │  │
│  │  • Real-time log tailing                                  │  │
│  │  • Color-coded message display                            │  │
│  │  • Status sidebar (agents, locks, ACKs)                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FILE SYSTEM                                 │
│                                                                   │
│  • ACTIVE_AGENTS.json         - Agent registry                   │
│  • agent_messages.log          - Message log (JSON lines)        │
│  • .agent_locks/*.lock         - Lock files (one per file)       │
│  • PENDING_ACKS.json           - Pending acknowledgments         │
│  • COORDINATION.md (optional)  - Shared coordination file        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Discovery System (`discovery.py`)

**Purpose:** Maintain real-time awareness of active agents.

**How it works:**
1. Runs `tmux list-panes -a` to get all panes
2. Filters panes running `claude` or `claude-code` processes
3. Assigns stable agent IDs (agent-0, agent-1, etc.)
4. Writes registry to `ACTIVE_AGENTS.json` atomically
5. Marks agents not seen in 60s as "stale"

**Key Functions:**
- `discover_agents()` - Discover agents and return registry
- `refresh_registry()` - Discover and save to file
- `get_agent_by_id()` - Look up agent by ID
- `list_active_agents()` - Get all active agents

**Data Flow:**
```
tmux list-panes -a
       │
       ▼
Parse pane info
       │
       ▼
Filter Claude Code processes
       │
       ▼
Assign agent IDs
       │
       ▼
AgentRegistry object
       │
       ▼
ACTIVE_AGENTS.json (atomic write)
```

---

### 2. Messaging System (`messaging.py`)

**Purpose:** Enable reliable communication between agents.

**Message Types:**
- `QUESTION` - Request information
- `REVIEW-REQUEST` - Request code review
- `BLOCKED` - Indicate blockage
- `COMPLETED` - Announce completion
- `CHALLENGE` - Challenge a decision
- `INFO` - Share information
- `ACK` - Acknowledge receipt

**Key Components:**
- `Message` - Data class for messages
- `MessagingSystem` - Main messaging coordinator
- `TmuxMessageDelivery` - tmux send-keys integration
- `MessageLogger` - JSON log writer
- `RateLimiter` - Enforce 10 msg/min limit

**How Messages are Sent:**
```
send_message(sender, recipient, type, content)
       │
       ▼
Check rate limit (10/min)
       │
       ▼
Look up recipient pane in registry
       │
       ▼
Format message: [sender][timestamp][type]: content
       │
       ▼
Escape for tmux (quotes, newlines)
       │
       ▼
tmux send-keys -t <pane> 'echo "message"' Enter
       │
       ▼
Log to agent_messages.log (JSON)
```

---

### 3. File Locking System (`locking.py`)

**Purpose:** Prevent concurrent file editing conflicts.

**Lock Storage:**
- Directory: `.agent_locks/`
- Filename: `SHA256(filepath).lock`
- Format: JSON with agent_id, filepath, locked_at, reason

**Key Components:**
- `LockManager` - Main lock coordinator
- `FileLock` - Data class for lock info
- `LockConflict` - Data class for conflicts

**Lock Lifecycle:**
```
acquire_lock(filepath, agent_id, reason)
       │
       ▼
Hash filepath → lock filename
       │
       ▼
Check if lock file exists
       │
       ├─► No: Create lock (exclusive mode) → Success
       │
       └─► Yes: Read lock file
               │
               ├─► Same agent? → Refresh timestamp → Success
               │
               ├─► Stale (>5 min)? → Delete old → Create new → Success
               │
               └─► Active by other? → Return LockConflict
```

**Glob Pattern Matching:**
```
Lock request: src/auth/jwt.py
Existing locks:
  - src/auth/*.py (agent-1) ← CONFLICT! (fnmatch)
  - src/models/*.py (agent-2) ← No conflict
```

---

### 4. ACK System (`ack.py`)

**Purpose:** Ensure critical messages are received and acknowledged.

**Workflow:**
```
send_with_ack(target, msg_type, content, timeout=30)
       │
       ▼
Generate unique msg_id (UUID)
       │
       ▼
Send message with [REQUIRES-ACK] flag
       │
       ▼
Add to PENDING_ACKS.json
       │
       ▼
Wait for ACK response...
       │
       ├─► ACK received → Remove from pending → Done
       │
       └─► Timeout (30s) → Retry #1
                            │
                            └─► Timeout (60s) → Retry #2
                                                │
                                                └─► Timeout (120s) → Retry #3
                                                                     │
                                                                     └─► Escalate to broadcast
```

**Retry Strategy:**
- Retry 1: 30 seconds (original timeout)
- Retry 2: 60 seconds (2x backoff)
- Retry 3: 120 seconds (4x backoff)
- Escalation: Broadcast to ALL agents

---

### 5. Monitoring System (`monitoring.py`)

**Purpose:** Provide real-time visibility into agent activity.

**Components:**
- Log file tailing (`agent_messages.log`)
- Message filtering (by type, agent, time)
- Color coding (RED=BLOCKED, GREEN=COMPLETED, etc.)
- Status sidebar (agent count, lock count, pending ACKs)

**Display Layout:**
```
┌─────────────────────────────────────────────────────────────────┐
│  CLAUDE SWARM MONITOR                         [Session: myproj] │
├─────────────────────────────────────────────────────────────────┤
│  STATUS                                                          │
│  • Active Agents: 3                                              │
│  • Active Locks: 2 (src/auth.py, tests/test_auth.py)           │
│  • Pending ACKs: 1                                               │
├─────────────────────────────────────────────────────────────────┤
│  MESSAGES (last 100)                                             │
│                                                                   │
│  [agent-0][14:30:00][INFO]: Starting JWT implementation         │
│  [agent-1][14:30:15][ACK]: Acknowledged                         │
│  [agent-2][14:30:30][BLOCKED]: Need auth.py to proceed          │  ← RED
│  [agent-0][14:30:45][INFO]: Will release auth.py in 5 min       │
│  [agent-2][14:31:00][ACK]: Thanks                               │
│  [agent-0][14:35:00][COMPLETED]: JWT implementation done        │  ← GREEN
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Interaction Diagrams

### Agent Discovery Sequence

```
Agent-0                Discovery System           ACTIVE_AGENTS.json
   │                          │                            │
   │  run discover_agents()   │                            │
   ├─────────────────────────►│                            │
   │                          │                            │
   │                          │  tmux list-panes -a        │
   │                          ├────────────┐               │
   │                          │            │               │
   │                          │◄───────────┘               │
   │                          │  parse output              │
   │                          │                            │
   │                          │  filter Claude processes   │
   │                          │                            │
   │                          │  load existing registry    │
   │                          ├───────────────────────────►│
   │                          │         (read)             │
   │                          │◄───────────────────────────┤
   │                          │                            │
   │                          │  merge & update IDs        │
   │                          │                            │
   │                          │  write registry (atomic)   │
   │                          ├───────────────────────────►│
   │                          │         (tmp + rename)     │
   │                          │                            │
   │  ◄───────────────────────┤                            │
   │     AgentRegistry         │                            │
   │                          │                            │
```

---

### Message Sending Sequence

```
Agent-0        MessagingSystem      AgentRegistry     Agent-1 (tmux pane)
   │                 │                    │                    │
   │  send_message() │                    │                    │
   ├────────────────►│                    │                    │
   │                 │                    │                    │
   │                 │  check rate limit  │                    │
   │                 ├──────────┐         │                    │
   │                 │          │         │                    │
   │                 │◄─────────┘         │                    │
   │                 │                    │                    │
   │                 │  lookup recipient  │                    │
   │                 ├───────────────────►│                    │
   │                 │◄───────────────────┤                    │
   │                 │   (pane_index)     │                    │
   │                 │                    │                    │
   │                 │  format message    │                    │
   │                 │  escape for tmux   │                    │
   │                 │                    │                    │
   │                 │  tmux send-keys    │                    │
   │                 ├────────────────────────────────────────►│
   │                 │                    │                    │
   │                 │  log message       │                    │
   │                 ├──────────┐         │                    │
   │                 │          │         │   [message shown]  │
   │                 │◄─────────┘         │                    │
   │                 │                    │                    │
   │  ◄──────────────┤                    │                    │
   │    Message obj  │                    │                    │
```

---

### Lock Acquisition Sequence

```
Agent-1          LockManager       .agent_locks/          Agent-2
   │                  │                  │                    │
   │  acquire_lock()  │                  │                    │
   ├─────────────────►│                  │                    │
   │                  │                  │                    │
   │                  │  hash(filepath)  │                    │
   │                  │                  │                    │
   │                  │  check lock file │                    │
   │                  ├─────────────────►│                    │
   │                  │◄─────────────────┤                    │
   │                  │  (exists?)       │                    │
   │                  │                  │                    │
   │                  ├──────┐           │                    │
   │                  │ No?  │           │                    │
   │                  │◄─────┘           │                    │
   │                  │                  │                    │
   │                  │  create lock     │                    │
   │                  │  (exclusive)     │                    │
   │                  ├─────────────────►│                    │
   │                  │                  │                    │
   │  ◄───────────────┤                  │                    │
   │    (True, None)  │                  │                    │
   │                  │                  │                    │
   │  [editing file]  │                  │                    │
   │                  │                  │                    │
   │                  │                  │  acquire_lock()    │
   │                  │◄─────────────────┼────────────────────┤
   │                  │                  │                    │
   │                  │  check lock file │                    │
   │                  ├─────────────────►│                    │
   │                  │◄─────────────────┤                    │
   │                  │  (exists!)       │                    │
   │                  │                  │                    │
   │                  │  read lock       │                    │
   │                  │  (owned by A-1)  │                    │
   │                  │                  │                    │
   │                  ├──────────────────┼───────────────────►│
   │                  │  (False, Conflict)                    │
   │                  │                  │                    │
```

---

## Message Flow

### Broadcast Message Flow

```
Agent-0 broadcasts "Feature complete"
       │
       ▼
┌─────────────────────────────────────────┐
│  MessagingSystem                         │
│  • Load ACTIVE_AGENTS.json              │
│  • Get all agents except sender         │
│  • Format message once                  │
│  • Send to each agent in parallel       │
└─────────────────────────────────────────┘
       │
       ├────────────────┬────────────────┐
       │                │                │
       ▼                ▼                ▼
   Agent-1          Agent-2          Agent-3
   (receives)       (receives)       (receives)
```

---

### ACK Message Flow

```
Agent-2                          Agent-1
   │                                │
   │  [BLOCKED][REQUIRES-ACK]       │
   ├───────────────────────────────►│
   │  "Need auth.py to proceed"     │
   │                                │
   │  Add to PENDING_ACKS.json      │
   │                                │
   │                                │  [reads message]
   │                                │
   │         [ACK] "Releasing       │
   │         auth.py in 2 min"      │
   │◄───────────────────────────────┤
   │                                │
   │  Remove from PENDING_ACKS      │
   │                                │
   │                                │  [releases lock]
   │                                │
   │  [acquires lock on auth.py]    │
   │                                │
```

---

## Lock Acquisition Flow

### Happy Path (No Conflict)

```
┌──────────────────────────────────────────────────┐
│  Agent wants to edit src/auth.py                 │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│  Check: .agent_locks/{hash}.lock exists?         │
└──────────────┬───────────────────────────────────┘
               │
               ▼ No
┌──────────────────────────────────────────────────┐
│  Create lock file (exclusive mode)                │
│  Content: {agent_id, filepath, locked_at, reason}│
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│  SUCCESS - Agent can edit file                    │
└──────────────────────────────────────────────────┘
```

---

### Conflict Resolution Path

```
┌──────────────────────────────────────────────────┐
│  Agent-2 wants to edit src/auth.py              │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│  Check: .agent_locks/{hash}.lock exists?         │
└──────────────┬───────────────────────────────────┘
               │
               ▼ Yes
┌──────────────────────────────────────────────────┐
│  Read lock file                                   │
│  - agent_id: agent-1                             │
│  - locked_at: 120 seconds ago                    │
│  - reason: "implementing JWT"                    │
└──────────────┬───────────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────────┐
│  Check: Is lock stale (>5 minutes)?              │
└──────────────┬───────────────────────────────────┘
               │
               ├─► Yes: Delete lock → Retry acquire → SUCCESS
               │
               └─► No: Return LockConflict
                      │
                      ▼
               ┌────────────────────────────────────┐
               │  Agent-2 sends message to Agent-1:  │
               │  "When will you finish auth.py?"    │
               └────────────────────────────────────┘
```

---

## Data Structures

### Agent Registry Format (`ACTIVE_AGENTS.json`)

```json
{
  "session_name": "myproject",
  "updated_at": "2025-11-07T10:30:00+00:00",
  "agents": [
    {
      "id": "agent-0",
      "pane_index": "myproject:0.0",
      "pid": 12345,
      "status": "active",
      "last_seen": "2025-11-07T10:30:00+00:00",
      "session_name": "myproject"
    },
    {
      "id": "agent-1",
      "pane_index": "myproject:0.1",
      "pid": 12346,
      "status": "active",
      "last_seen": "2025-11-07T10:30:00+00:00",
      "session_name": "myproject"
    }
  ]
}
```

---

### Lock File Format (`.agent_locks/{hash}.lock`)

```json
{
  "agent_id": "agent-1",
  "filepath": "src/auth.py",
  "locked_at": 1699360200.123456,
  "reason": "implementing JWT authentication"
}
```

---

### Message Log Format (`agent_messages.log`)

Each line is a JSON object:

```json
{
  "timestamp": "2025-11-07T10:30:15+00:00",
  "msg_id": "abc-123-def-456",
  "sender": "agent-0",
  "recipients": ["agent-1"],
  "msg_type": "QUESTION",
  "content": "What database schema are we using?",
  "delivery_status": {"agent-1": true},
  "success_count": 1,
  "failure_count": 0
}
```

---

### Pending ACKs Format (`PENDING_ACKS.json`)

```json
{
  "pending": [
    {
      "msg_id": "xyz-789-abc",
      "sender_id": "agent-2",
      "recipient_id": "agent-1",
      "message": {
        "sender_id": "agent-2",
        "timestamp": "2025-11-07T10:35:00+00:00",
        "msg_type": "BLOCKED",
        "content": "Need auth.py to proceed",
        "recipients": ["agent-1"],
        "msg_id": "xyz-789-abc"
      },
      "sent_at": "2025-11-07T10:35:00+00:00",
      "retry_count": 0,
      "next_retry_at": "2025-11-07T10:35:30+00:00"
    }
  ]
}
```

---

## Extension Points

### 1. Custom Message Types

Add new message types by extending `MessageType` enum:

```python
# In messaging.py
class MessageType(Enum):
    # ... existing types ...
    DEPLOYMENT = "DEPLOYMENT"
    SECURITY_ALERT = "SECURITY-ALERT"
```

---

### 2. Custom Lock Strategies

Implement alternative locking strategies:

```python
# Custom lock manager with priorities
class PriorityLockManager(LockManager):
    def acquire_lock(self, filepath, agent_id, reason, priority=0):
        # Higher priority agents can preempt lower priority locks
        existing_lock = self._read_lock(self._get_lock_path(filepath))
        if existing_lock and self._get_priority(agent_id) > priority:
            # Preempt existing lock
            self._notify_preemption(existing_lock.agent_id)
            # ... acquire lock ...
```

---

### 3. Custom Coordination Patterns

Implement coordination patterns as reusable modules:

```python
# patterns/code_review.py
def code_review_workflow(reviewer_id, implementer_id, files):
    """Orchestrate a code review between two agents."""
    # 1. Reviewer acquires locks
    # 2. Reviewer sends feedback
    # 3. Implementer makes changes
    # 4. Reviewer approves
    # 5. Release locks
```

---

### 4. Alternative Transports

Replace tmux send-keys with other transports:

```python
# transports/websocket.py
class WebSocketMessageDelivery:
    def send_to_pane(self, pane_id, message):
        # Send via WebSocket instead of tmux
        ws = websocket.create_connection(f"ws://localhost:8080/{pane_id}")
        ws.send(message)
        ws.close()
```

---

### 5. Monitoring Plugins

Add custom monitoring displays:

```python
# monitoring/dashboard.py
class CustomDashboard:
    def display(self, state):
        # Custom visualization of agent activity
        # E.g., web dashboard, Grafana integration, etc.
```

---

## Performance Considerations

### Scalability

- **Agents:** Tested up to 8 agents, designed for 4-12 agents
- **Messages:** Rate limited to 10/min per agent
- **Locks:** O(1) lock lookup (hash-based filenames)
- **Discovery:** O(n) pane scanning, runs every 30s

### Bottlenecks

1. **tmux send-keys latency:** ~50-100ms per message
2. **File I/O:** Atomic writes require temp file + rename
3. **Registry updates:** Single writer, safe but not concurrent

### Optimization Strategies

1. **Batch messages:** Combine multiple updates into one broadcast
2. **Cache registry:** Read once, use multiple times
3. **Lazy lock cleanup:** Only clean stale locks on conflict
4. **Async operations:** Use background threads for monitoring

---

## Security Considerations

### Trust Model

- **Trusted environment:** All agents are trusted (same user, same machine)
- **No authentication:** Agents identified by process only
- **No encryption:** Messages sent in plain text via tmux

### Potential Issues

1. **Lock hijacking:** Any agent can release any lock (mitigation: log all operations)
2. **Message spoofing:** Agents can impersonate others (mitigation: trust model)
3. **DoS via rate limit:** Malicious agent could spam messages (mitigation: rate limiting)

---

## Future Architecture Enhancements

1. **Distributed mode:** Agents on different machines (requires network transport)
2. **Persistent storage:** Database instead of JSON files
3. **Event bus:** Pub/sub pattern for message delivery
4. **Hierarchical coordination:** Lead agent + worker agents
5. **Conflict resolution:** Automatic merge conflict handling
6. **Time-travel debugging:** Replay message history

---

For more details, see:
- **[API Reference](api-reference.md)** - Detailed API documentation
- **[Protocol Specification](protocol.md)** - Technical protocol details
- **[Getting Started](getting-started.md)** - Practical usage guide
