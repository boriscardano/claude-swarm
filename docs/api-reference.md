# API Reference

Comprehensive API documentation for Claude Swarm modules and functions.

---

## Table of Contents

1. [Discovery Module](#discovery-module)
2. [Messaging Module](#messaging-module)
3. [Locking Module](#locking-module)
4. [ACK Module](#ack-module)
5. [Monitoring Module](#monitoring-module)
6. [Coordination Module](#coordination-module)
7. [CLI Commands](#cli-commands)

---

## Discovery Module

**Module:** `claudeswarm.discovery`

The discovery system identifies and tracks Claude Code agents running in tmux panes.

### Classes

#### `Agent`

Represents a discovered Claude Code agent.

```python
@dataclass
class Agent:
    id: str              # Unique agent identifier (e.g., "agent-0")
    pane_index: str      # tmux pane identifier (e.g., "session:0.1")
    pid: int             # Process ID
    status: str          # "active", "stale", or "dead"
    last_seen: str       # ISO 8601 timestamp
    session_name: str    # tmux session name
```

**Methods:**

- `to_dict() -> Dict`: Convert to dictionary for JSON serialization
- `from_dict(data: Dict) -> Agent`: Create Agent from dictionary

---

#### `AgentRegistry`

Registry of all discovered agents.

```python
@dataclass
class AgentRegistry:
    session_name: str    # tmux session name
    updated_at: str      # ISO 8601 timestamp
    agents: List[Agent]  # List of agents
```

**Methods:**

- `to_dict() -> Dict`: Convert to dictionary
- `from_dict(data: Dict) -> AgentRegistry`: Create from dictionary

---

### Functions

#### `discover_agents()`

Discover active Claude Code agents in tmux panes.

```python
def discover_agents(
    session_name: Optional[str] = None,
    stale_threshold: int = 60
) -> AgentRegistry
```

**Parameters:**
- `session_name` (Optional[str]): Filter by tmux session (None = all sessions)
- `stale_threshold` (int): Seconds after which agent is considered stale (default: 60)

**Returns:**
- `AgentRegistry`: Registry containing all discovered agents

**Raises:**
- `RuntimeError`: If tmux is not running or discovery fails

**Example:**

```python
from claudeswarm.discovery import discover_agents

# Discover all agents
registry = discover_agents()
print(f"Found {len(registry.agents)} agents")

# Discover in specific session
registry = discover_agents(session_name="myproject")
```

---

#### `refresh_registry()`

Refresh the agent registry file (ACTIVE_AGENTS.json).

```python
def refresh_registry(stale_threshold: int = 60) -> AgentRegistry
```

**Parameters:**
- `stale_threshold` (int): Seconds for stale detection (default: 60)

**Returns:**
- `AgentRegistry`: Updated registry (also saved to disk)

**Example:**

```python
from claudeswarm.discovery import refresh_registry

registry = refresh_registry()
# ACTIVE_AGENTS.json is now updated
```

---

#### `get_agent_by_id()`

Look up an agent by ID from the registry.

```python
def get_agent_by_id(agent_id: str) -> Optional[Agent]
```

**Parameters:**
- `agent_id` (str): Agent identifier (e.g., "agent-0")

**Returns:**
- `Agent` if found, `None` otherwise

**Example:**

```python
from claudeswarm.discovery import get_agent_by_id

agent = get_agent_by_id("agent-1")
if agent:
    print(f"Agent {agent.id} in pane {agent.pane_index}")
```

---

#### `list_active_agents()`

Get list of all active agents.

```python
def list_active_agents() -> List[Agent]
```

**Returns:**
- `List[Agent]`: Agents with status "active"

**Example:**

```python
from claudeswarm.discovery import list_active_agents

for agent in list_active_agents():
    print(f"{agent.id}: {agent.pane_index}")
```

---

## Messaging Module

**Module:** `claudeswarm.messaging`

The messaging system enables communication between agents via tmux send-keys.

### Enums

#### `MessageType`

Types of messages that can be sent.

```python
class MessageType(Enum):
    QUESTION = "QUESTION"              # Request information
    REVIEW_REQUEST = "REVIEW-REQUEST"  # Request code review
    BLOCKED = "BLOCKED"                # Indicate blockage
    COMPLETED = "COMPLETED"            # Announce completion
    CHALLENGE = "CHALLENGE"            # Challenge a decision
    INFO = "INFO"                      # Share information
    ACK = "ACK"                        # Acknowledge receipt
```

---

### Classes

#### `Message`

Represents a message sent between agents.

```python
@dataclass
class Message:
    sender_id: str           # Sending agent ID
    timestamp: datetime      # When message was created
    msg_type: MessageType    # Type of message
    content: str             # Message content
    recipients: List[str]    # List of recipient agent IDs
    msg_id: str              # Unique UUID for tracking
```

**Methods:**

- `to_dict() -> dict`: Convert to dictionary
- `from_dict(data: dict) -> Message`: Create from dictionary
- `format_for_display() -> str`: Format for terminal display

**Example:**

```python
from claudeswarm.messaging import Message, MessageType
from datetime import datetime

msg = Message(
    sender_id="agent-0",
    timestamp=datetime.now(),
    msg_type=MessageType.INFO,
    content="Task completed",
    recipients=["agent-1"]
)

print(msg.format_for_display())
# Output: [agent-0][2025-11-07 14:30:15][INFO]: Task completed
```

---

#### `MessagingSystem`

Main messaging coordinator.

```python
class MessagingSystem:
    def __init__(
        self,
        log_file: Path = None,
        rate_limit_messages: int = 10,
        rate_limit_window: int = 60
    )
```

**Parameters:**
- `log_file` (Path): Path to message log file
- `rate_limit_messages` (int): Max messages per agent per window (default: 10)
- `rate_limit_window` (int): Rate limit window in seconds (default: 60)

**Methods:**

##### `send_message()`

Send a direct message to a specific agent.

```python
def send_message(
    self,
    sender_id: str,
    recipient_id: str,
    msg_type: MessageType,
    content: str
) -> Optional[Message]
```

**Returns:**
- `Message` if successful, `None` if failed

---

##### `broadcast_message()`

Broadcast a message to all active agents.

```python
def broadcast_message(
    self,
    sender_id: str,
    msg_type: MessageType,
    content: str,
    exclude_self: bool = True
) -> Dict[str, bool]
```

**Returns:**
- `Dict[str, bool]`: Maps recipient_id to delivery success status

---

### Functions

#### `send_message()`

Module-level convenience function to send a message.

```python
def send_message(
    sender_id: str,
    recipient_id: str,
    message_type: MessageType,
    content: str
) -> Optional[Message]
```

**Example:**

```python
from claudeswarm.messaging import send_message, MessageType

msg = send_message(
    sender_id="agent-0",
    recipient_id="agent-1",
    message_type=MessageType.QUESTION,
    content="What's the status?"
)

if msg:
    print(f"Message sent: {msg.msg_id}")
```

---

#### `broadcast_message()`

Module-level convenience function to broadcast.

```python
def broadcast_message(
    sender_id: str,
    message_type: MessageType,
    content: str,
    exclude_self: bool = True
) -> Dict[str, bool]
```

**Example:**

```python
from claudeswarm.messaging import broadcast_message, MessageType

results = broadcast_message(
    sender_id="agent-0",
    message_type=MessageType.INFO,
    content="Sprint starting - check COORDINATION.md"
)

success_count = sum(1 for success in results.values() if success)
print(f"Delivered to {success_count}/{len(results)} agents")
```

---

## Locking Module

**Module:** `claudeswarm.locking`

The locking system prevents concurrent file editing conflicts.

### Classes

#### `FileLock`

Represents an active file lock.

```python
@dataclass
class FileLock:
    agent_id: str      # Agent holding the lock
    filepath: str      # Path to locked file
    locked_at: float   # Unix timestamp
    reason: str        # Human-readable reason
```

**Methods:**

- `is_stale(timeout: int = 300) -> bool`: Check if lock is stale
- `age_seconds() -> float`: Get lock age in seconds
- `to_dict() -> dict`: Convert to dictionary
- `from_dict(data: dict) -> FileLock`: Create from dictionary

---

#### `LockConflict`

Represents a failed lock acquisition.

```python
@dataclass
class LockConflict:
    filepath: str           # Path that couldn't be locked
    current_holder: str     # Agent ID holding the lock
    locked_at: datetime     # When lock was acquired
    reason: str             # Why file is locked
```

---

#### `LockManager`

Manages file locks for agent coordination.

```python
class LockManager:
    def __init__(
        self,
        lock_dir: str = ".agent_locks",
        project_root: Optional[Path] = None
    )
```

**Parameters:**
- `lock_dir` (str): Directory for lock files (default: ".agent_locks")
- `project_root` (Path): Project root (default: current directory)

**Methods:**

##### `acquire_lock()`

Acquire a lock on a file.

```python
def acquire_lock(
    self,
    filepath: str,
    agent_id: str,
    reason: str = "",
    timeout: int = 300
) -> tuple[bool, Optional[LockConflict]]
```

**Parameters:**
- `filepath` (str): Path to lock (can be glob pattern like "src/**/*.py")
- `agent_id` (str): Agent acquiring the lock
- `reason` (str): Explanation for the lock
- `timeout` (int): Stale lock timeout in seconds (default: 300)

**Returns:**
- `(True, None)` if lock acquired successfully
- `(False, LockConflict)` if lock held by another agent

**Example:**

```python
from claudeswarm.locking import LockManager

lm = LockManager()

success, conflict = lm.acquire_lock(
    filepath="src/auth.py",
    agent_id="agent-1",
    reason="Implementing OAuth"
)

if success:
    print("Lock acquired!")
    # Do work...
    lm.release_lock("src/auth.py", "agent-1")
else:
    print(f"Conflict: {conflict.current_holder} has lock")
```

---

##### `release_lock()`

Release a lock on a file.

```python
def release_lock(
    self,
    filepath: str,
    agent_id: str
) -> bool
```

**Returns:**
- `True` if released, `False` if lock doesn't exist or owned by another agent

---

##### `who_has_lock()`

Check who currently holds a lock.

```python
def who_has_lock(
    self,
    filepath: str
) -> Optional[FileLock]
```

**Returns:**
- `FileLock` if file is locked, `None` otherwise (stale locks auto-cleaned)

---

##### `list_all_locks()`

List all active locks.

```python
def list_all_locks(
    self,
    include_stale: bool = False
) -> list[FileLock]
```

**Returns:**
- `List[FileLock]`: All active (and optionally stale) locks

---

##### `cleanup_stale_locks()`

Clean up all stale locks.

```python
def cleanup_stale_locks(
    self,
    timeout: int = 300
) -> int
```

**Returns:**
- `int`: Number of locks cleaned up

---

##### `cleanup_agent_locks()`

Clean up all locks held by a specific agent.

```python
def cleanup_agent_locks(
    self,
    agent_id: str
) -> int
```

**Returns:**
- `int`: Number of locks cleaned up

---

## ACK Module

**Module:** `claudeswarm.ack`

The acknowledgment system ensures critical messages are received.

### Classes

#### `PendingAck`

Represents a message awaiting acknowledgment.

```python
@dataclass
class PendingAck:
    msg_id: str           # Message identifier
    sender_id: str        # Sending agent
    recipient_id: str     # Expected acknowledger
    message: dict         # Original message (as dict)
    sent_at: str          # ISO timestamp
    retry_count: int      # Number of retries
    next_retry_at: str    # ISO timestamp for next retry
```

---

#### `AckSystem`

Main acknowledgment system.

```python
class AckSystem:
    MAX_RETRIES = 3
    RETRY_DELAYS = [30, 60, 120]  # Exponential backoff

    def __init__(self, pending_file: Path | None = None)
```

**Methods:**

##### `send_with_ack()`

Send a message that requires acknowledgment.

```python
def send_with_ack(
    self,
    sender_id: str,
    recipient_id: str,
    msg_type: MessageType,
    content: str,
    timeout: int = 30
) -> str | None
```

**Returns:**
- `str`: Message ID for tracking, or `None` if send failed

**Example:**

```python
from claudeswarm.ack import send_with_ack
from claudeswarm.messaging import MessageType

msg_id = send_with_ack(
    sender_id="agent-2",
    recipient_id="agent-1",
    msg_type=MessageType.BLOCKED,
    content="Need auth.py to proceed"
)

print(f"Sent message {msg_id}, waiting for ACK...")
```

---

##### `receive_ack()`

Process received acknowledgment.

```python
def receive_ack(
    self,
    msg_id: str,
    agent_id: str
) -> bool
```

**Returns:**
- `bool`: True if ACK matched and removed, False if not found

---

##### `check_pending_acks()`

Check for messages awaiting acknowledgment.

```python
def check_pending_acks(
    self,
    agent_id: str | None = None
) -> list[PendingAck]
```

**Returns:**
- `list[PendingAck]`: Pending acknowledgments (optionally filtered by agent)

---

##### `process_retries()`

Process pending ACKs and retry/escalate as needed.

```python
def process_retries(self) -> int
```

**Returns:**
- `int`: Number of messages processed

---

### Functions

#### `send_with_ack()`

Module-level function to send with acknowledgment.

```python
def send_with_ack(
    sender_id: str,
    recipient_id: str,
    msg_type: MessageType,
    content: str,
    timeout: int = 30
) -> str | None
```

---

#### `acknowledge_message()`

Acknowledge receipt of a message.

```python
def acknowledge_message(
    msg_id: str,
    agent_id: str
) -> bool
```

**Example:**

```python
from claudeswarm.ack import acknowledge_message

# When you receive a [REQUIRES-ACK] message
success = acknowledge_message(
    msg_id="abc-123-def-456",
    agent_id="agent-1"
)
```

---

## Monitoring Module

**Module:** `claudeswarm.monitoring`

The monitoring system provides real-time visibility into agent activity.

### Classes

#### `MonitoringState`

Current state of the monitoring dashboard.

```python
@dataclass
class MonitoringState:
    active_agents: list[Agent]        # Currently active agents
    active_locks: list[FileLock]      # Currently held locks
    pending_acks: list[PendingAck]    # Messages awaiting ACK
    recent_messages: deque[Message]   # Last 100 messages
```

---

#### `MessageFilter`

Filter criteria for message display.

```python
@dataclass
class MessageFilter:
    msg_types: Optional[Set[MessageType]]              # Filter by type
    agent_ids: Optional[Set[str]]                      # Filter by agent
    time_range: Optional[Tuple[datetime, datetime]]    # Filter by time
```

**Methods:**

- `matches(message: Message) -> bool`: Check if message matches filter

---

#### `Monitor`

Main monitoring dashboard implementation.

```python
class Monitor:
    def __init__(
        self,
        log_path: Path = Path("./agent_messages.log"),
        refresh_interval: float = 2.0,
        message_filter: Optional[MessageFilter] = None
    )
```

**Methods:**

##### `get_status()`

Get current monitoring state.

```python
def get_status(self) -> MonitoringState
```

---

##### `run_dashboard()`

Run the monitoring dashboard main loop.

```python
def run_dashboard(self) -> None
```

Continuously updates display until interrupted (Ctrl+C).

---

### Functions

#### `start_monitoring()`

Start the monitoring dashboard.

```python
def start_monitoring(
    filter_type: Optional[str] = None,
    filter_agent: Optional[str] = None,
    use_tmux: bool = True
) -> None
```

**Parameters:**
- `filter_type` (str): Filter to specific message type
- `filter_agent` (str): Filter to specific agent ID
- `use_tmux` (bool): Create dedicated tmux pane (default: True)

**Example:**

```python
from claudeswarm.monitoring import start_monitoring

# Start monitoring in tmux pane
start_monitoring()

# Filter to only BLOCKED messages
start_monitoring(filter_type="BLOCKED")

# Monitor specific agent
start_monitoring(filter_agent="agent-3")
```

---

## Coordination Module

**Module:** `claudeswarm.coordination`

The coordination module manages the shared COORDINATION.md file.

### Classes

#### `CoordinationFile`

Manages COORDINATION.md with atomic updates and locking.

```python
class CoordinationFile:
    def __init__(
        self,
        project_root: Optional[Path] = None,
        agent_id: Optional[str] = None,
        lock_manager: Optional[LockManager] = None
    )
```

**Methods:**

##### `init_file()`

Initialize a new COORDINATION.md file.

```python
def init_file(
    self,
    project_name: str = "Project",
    force: bool = False
) -> bool
```

---

##### `get_section()`

Get content of a specific section.

```python
def get_section(
    self,
    section_name: str
) -> Optional[str]
```

---

##### `update_section()`

Update a specific section atomically with locking.

```python
def update_section(
    self,
    section_name: str,
    new_content: str,
    reason: str = "updating section"
) -> bool
```

---

##### `append_to_section()`

Append a line to a section atomically.

```python
def append_to_section(
    self,
    section_name: str,
    line: str,
    reason: str = "appending"
) -> bool
```

---

### Functions

#### `init_coordination_file()`

Initialize COORDINATION.md.

```python
def init_coordination_file(
    project_name: str = "Project",
    force: bool = False,
    project_root: Optional[Path] = None
) -> bool
```

**Example:**

```python
from claudeswarm.coordination import init_coordination_file

init_coordination_file(project_name="MyProject")
```

---

#### `get_current_work()`

Get list of items in Current Work section.

```python
def get_current_work(
    project_root: Optional[Path] = None
) -> list[str]
```

**Returns:**
- `list[str]`: Table rows of current work items

---

#### `add_current_work()`

Add a new work item.

```python
def add_current_work(
    agent: str,
    task: str,
    status: str = "In Progress",
    agent_id: Optional[str] = None,
    project_root: Optional[Path] = None
) -> bool
```

**Example:**

```python
from claudeswarm.coordination import add_current_work

add_current_work(
    agent="agent-1",
    task="Implement JWT authentication",
    status="In Progress",
    agent_id="agent-1"
)
```

---

#### `add_blocked_item()`

Add a blocked item.

```python
def add_blocked_item(
    task: str,
    reason: str,
    agent: str,
    agent_id: Optional[str] = None,
    project_root: Optional[Path] = None
) -> bool
```

---

## CLI Commands

**Entry Point:** `claudeswarm` command

### Global Options

```bash
claudeswarm --project-root PATH <command> [options]
```

- `--project-root PATH`: Project root directory (default: current directory)

---

### Commands

#### `discover-agents`

Discover active Claude Code agents in tmux.

```bash
claudeswarm discover-agents [--watch] [--interval SECONDS] [--json] [--stale-threshold SECONDS]
```

**Options:**
- `--watch`: Continuously monitor for agents
- `--interval SECONDS`: Refresh interval for watch mode (default: 30)
- `--json`: Output in JSON format
- `--stale-threshold SECONDS`: Stale detection threshold (default: 60)

**Example:**

```bash
# Single discovery
claudeswarm discover-agents

# Continuous monitoring
claudeswarm discover-agents --watch

# JSON output
claudeswarm discover-agents --json
```

---

#### `list-agents`

List active agents from registry.

```bash
claudeswarm list-agents [--json]
```

---

#### `acquire-file-lock`

Acquire a lock on a file.

```bash
claudeswarm acquire-file-lock FILEPATH AGENT_ID [REASON]
```

**Example:**

```bash
claudeswarm acquire-file-lock src/auth.py agent-1 "Implementing OAuth"
```

---

#### `release-file-lock`

Release a lock on a file.

```bash
claudeswarm release-file-lock FILEPATH AGENT_ID
```

---

#### `who-has-lock`

Check who has a lock on a file.

```bash
claudeswarm who-has-lock FILEPATH [--json]
```

---

#### `list-all-locks`

List all active locks.

```bash
claudeswarm list-all-locks [--include-stale] [--json]
```

---

#### `cleanup-stale-locks`

Clean up stale locks.

```bash
claudeswarm cleanup-stale-locks
```

---

#### `start-monitoring`

Start the monitoring dashboard.

```bash
claudeswarm start-monitoring [--filter-type TYPE] [--filter-agent AGENT_ID] [--no-tmux]
```

**Options:**
- `--filter-type TYPE`: Filter to specific message type
- `--filter-agent AGENT_ID`: Filter to specific agent
- `--no-tmux`: Run in current terminal instead of tmux pane

**Example:**

```bash
# Start monitoring
claudeswarm start-monitoring

# Filter to BLOCKED messages
claudeswarm start-monitoring --filter-type BLOCKED

# Monitor specific agent
claudeswarm start-monitoring --filter-agent agent-2
```

---

## Error Handling

All modules follow consistent error handling patterns:

### Exception Hierarchy

```
Exception
├── DiscoveryError (claudeswarm.discovery)
│   ├── TmuxNotRunningError
│   ├── TmuxPermissionError
│   └── RegistryLockError
├── ValidationError (claudeswarm.validators)
├── FileLockError (claudeswarm.file_lock)
│   └── FileLockTimeout
├── RuntimeError (built-in)
├── FileNotFoundError (built-in)
└── ValueError (built-in)
```

### Common Exceptions

#### DiscoveryError

Base exception for discovery system errors.

**Example:**

```python
from claudeswarm.discovery import discover_agents, TmuxNotRunningError, RegistryLockError

try:
    registry = discover_agents()
except TmuxNotRunningError as e:
    print(f"Error: tmux is not running - {e}")
    # Handle: prompt user to start tmux
except RegistryLockError as e:
    print(f"Error: registry file is locked - {e}")
    # Handle: retry after a delay
except Exception as e:
    print(f"Unexpected discovery error: {e}")
```

#### ValidationError

Raised for invalid input parameters.

**Example:**

```python
from claudeswarm.locking import LockManager
from claudeswarm.validators import ValidationError

lm = LockManager()

try:
    success, conflict = lm.acquire_lock(
        filepath="src/auth.py",
        agent_id="",  # Invalid: empty agent ID
        reason="Testing"
    )
except ValidationError as e:
    print(f"Invalid input: {e}")
    # Handle: prompt user for valid agent ID
```

#### FileLockTimeout

Raised when file lock cannot be acquired within timeout.

**Example:**

```python
from claudeswarm.file_lock import FileLock, FileLockTimeout
from pathlib import Path

try:
    with FileLock(Path("ACTIVE_AGENTS.json"), timeout=2.0):
        # Critical section: access shared file
        pass
except FileLockTimeout as e:
    print(f"Could not acquire lock: {e}")
    # Handle: retry or skip operation
```

### RuntimeError

Raised when system requirements aren't met:
- tmux is not running
- tmux is not installed
- Discovery fails

### FileNotFoundError

Raised when expected files don't exist:
- Agent registry not found
- Coordination file not found
- Lock directory missing

### ValueError

Raised for invalid input:
- Empty agent IDs
- Invalid message types
- Invalid section names

---

## Common Patterns

This section demonstrates common usage patterns for coordinating agents.

### Send Message and Wait for ACK

Send a message that requires acknowledgment, then check for response:

```python
from claudeswarm.ack import send_with_ack, AckSystem
from claudeswarm.messaging import MessageType
import time

# Send message that requires ACK
msg_id = send_with_ack(
    sender_id="agent-2",
    recipient_id="agent-1",
    msg_type=MessageType.BLOCKED,
    content="Need auth.py to proceed"
)

if not msg_id:
    print("Failed to send message")
else:
    # Wait for acknowledgment (system will retry automatically)
    ack_system = AckSystem()
    max_wait = 180  # 3 minutes
    start_time = time.time()

    while time.time() - start_time < max_wait:
        pending = ack_system.check_pending_acks(agent_id="agent-2")
        if not any(p.msg_id == msg_id for p in pending):
            print("Message acknowledged!")
            break
        time.sleep(5)  # Check every 5 seconds
    else:
        print("Timeout waiting for acknowledgment")
```

### Lock-Modify-Release Pattern

Safely acquire a lock, modify files, then release:

```python
from claudeswarm.locking import LockManager
from pathlib import Path

lm = LockManager()
agent_id = "agent-1"
filepath = "src/auth.py"

# Acquire lock
success, conflict = lm.acquire_lock(
    filepath=filepath,
    agent_id=agent_id,
    reason="Implementing OAuth"
)

if not success:
    print(f"Cannot proceed: {conflict.current_holder} has lock")
    print(f"Reason: {conflict.reason}")
    # Wait or handle conflict
else:
    try:
        # Critical section: modify file
        content = Path(filepath).read_text()
        # ... make changes ...
        Path(filepath).write_text(content)
        print("Changes saved successfully")
    except Exception as e:
        print(f"Error during modification: {e}")
        # Handle error, but still release lock
    finally:
        # Always release lock, even on error
        lm.release_lock(filepath, agent_id)
        print("Lock released")
```

### Broadcast with Timeout

Broadcast a message and track delivery status:

```python
from claudeswarm.messaging import broadcast_message, MessageType
import time

# Send broadcast
results = broadcast_message(
    sender_id="agent-0",
    message_type=MessageType.INFO,
    content="Sprint starting - check COORDINATION.md"
)

# Check delivery results
total_agents = len(results)
successful = sum(1 for success in results.values() if success)
failed = [agent_id for agent_id, success in results.items() if not success]

print(f"Broadcast delivered to {successful}/{total_agents} agents")

if failed:
    print(f"Failed deliveries: {', '.join(failed)}")
    # Optionally retry failed deliveries
    time.sleep(5)
    for agent_id in failed:
        from claudeswarm.messaging import send_message
        send_message(
            sender_id="agent-0",
            recipient_id=agent_id,
            message_type=MessageType.INFO,
            content="Sprint starting - check COORDINATION.md"
        )
```

### Retry with Exponential Backoff

Retry an operation with increasing delays:

```python
from claudeswarm.locking import LockManager
import time

def acquire_lock_with_retry(lm, filepath, agent_id, max_retries=5):
    """Acquire lock with exponential backoff retry."""
    delays = [1, 2, 5, 10, 30]  # seconds

    for attempt in range(max_retries):
        success, conflict = lm.acquire_lock(
            filepath=filepath,
            agent_id=agent_id,
            reason="Processing with retry"
        )

        if success:
            return True, None

        if attempt < max_retries - 1:
            delay = delays[attempt]
            print(f"Lock held by {conflict.current_holder}, "
                  f"retrying in {delay}s... (attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
        else:
            print(f"Failed to acquire lock after {max_retries} attempts")
            return False, conflict

    return False, None

# Usage
lm = LockManager()
success, conflict = acquire_lock_with_retry(
    lm,
    filepath="src/database.py",
    agent_id="agent-3"
)

if success:
    try:
        # Do work
        pass
    finally:
        lm.release_lock("src/database.py", "agent-3")
```

---

## Best Practices

### Rate Limiting

Messages are rate-limited to 10 per agent per minute. If exceeded:

```python
# Returns None
msg = send_message(...)
if msg is None:
    print("Rate limit exceeded, wait before retrying")
```

### Lock Management

Always use try-finally or context managers:

```python
from claudeswarm.locking import LockManager

lm = LockManager()
success, conflict = lm.acquire_lock("file.py", "agent-1", "editing")

if success:
    try:
        # Do work...
        pass
    finally:
        lm.release_lock("file.py", "agent-1")
```

### ACK Messages

Use ACKs for critical coordination:

```python
from claudeswarm.ack import send_with_ack
from claudeswarm.messaging import MessageType

# Send with ACK requirement
msg_id = send_with_ack(
    sender_id="agent-2",
    recipient_id="agent-1",
    msg_type=MessageType.BLOCKED,
    content="Critical: Need auth.py immediately"
)

# System will retry 3 times, then escalate to all agents
```

---

## Programmatic Configuration

Claude Swarm can be configured programmatically using the `config` module.

### Loading Configuration

```python
from claudeswarm.config import get_config, ConfigManager

# Get current configuration (loads from .claudeswarm.yaml if exists)
config = get_config()

# Access configuration values
print(f"Rate limit: {config.rate_limiting.messages_per_minute} msg/min")
print(f"Stale timeout: {config.locking.stale_timeout}s")
print(f"Stale threshold: {config.discovery.stale_threshold}s")
```

### Modifying Configuration at Runtime

```python
from claudeswarm.config import ConfigManager

# Create config manager
config_mgr = ConfigManager()

# Update rate limiting
config_mgr.config.rate_limiting.messages_per_minute = 20
config_mgr.config.rate_limiting.window_seconds = 60

# Update locking settings
config_mgr.config.locking.stale_timeout = 600  # 10 minutes
config_mgr.config.locking.auto_cleanup = True

# Save to file
config_mgr.save(".claudeswarm.yaml")
```

### Creating Configuration from Scratch

```python
from claudeswarm.config import (
    Config,
    RateLimitingConfig,
    LockingConfig,
    DiscoveryConfig,
    OnboardingConfig
)

# Create custom configuration
config = Config(
    rate_limiting=RateLimitingConfig(
        messages_per_minute=15,
        window_seconds=60
    ),
    locking=LockingConfig(
        stale_timeout=300,
        auto_cleanup=False
    ),
    discovery=DiscoveryConfig(
        stale_threshold=90,
        auto_refresh_interval=None,
        enable_cross_project_coordination=False
    ),
    onboarding=OnboardingConfig(
        enabled=True,
        auto_onboard=False
    )
)

# Save to file
from claudeswarm.config import ConfigManager
config_mgr = ConfigManager(config=config)
config_mgr.save(".claudeswarm.yaml")
```

### Configuration Validation

```python
from claudeswarm.config import ConfigManager

config_mgr = ConfigManager.from_file(".claudeswarm.yaml")

# Validate configuration
try:
    config_mgr.validate()
    print("Configuration is valid")
except ValueError as e:
    print(f"Invalid configuration: {e}")
```

### Environment-Specific Configuration

```python
from claudeswarm.config import ConfigManager
from pathlib import Path

# Development configuration
dev_config = ConfigManager.from_file("configs/dev.yaml")

# Production configuration
prod_config = ConfigManager.from_file("configs/prod.yaml")

# Use appropriate config based on environment
import os
if os.getenv("ENV") == "production":
    config = prod_config.config
else:
    config = dev_config.config

# Access configuration
print(f"Using config: {config.rate_limiting.messages_per_minute} msg/min")
```

### Configuration Schema

All configuration values with their types and defaults:

```python
@dataclass
class RateLimitingConfig:
    messages_per_minute: int = 10
    window_seconds: int = 60

@dataclass
class LockingConfig:
    stale_timeout: int = 300
    auto_cleanup: bool = False

@dataclass
class DiscoveryConfig:
    stale_threshold: int = 60
    auto_refresh_interval: Optional[int] = None
    enable_cross_project_coordination: bool = False

@dataclass
class OnboardingConfig:
    enabled: bool = True
    auto_onboard: bool = False

@dataclass
class Config:
    rate_limiting: RateLimitingConfig
    locking: LockingConfig
    discovery: DiscoveryConfig
    onboarding: OnboardingConfig
```

---

## Version Information

**Current Version:** 0.1.0

For updates and changelog, see the [GitHub repository](https://github.com/yourusername/claude-swarm).

---

**Last Updated:** 2025-11-18
