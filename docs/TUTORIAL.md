# Claude Swarm Tutorial: Zero to Hero

Welcome to the Claude Swarm tutorial! This guide will teach you how to coordinate multiple Claude Code agents to work together on the same codebase. By the end, you'll be able to run a team of AI agents that communicate, avoid conflicts, and collaborate like a real development team.

**Target Audience:** Claude Code users who want to scale their productivity with multi-agent coordination.

**Time to Complete:** 30-45 minutes

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start (5 Minutes)](#quick-start-5-minutes)
3. [Core Concepts Tutorial](#core-concepts-tutorial)
4. [Real-World Scenario: Building a Feature Together](#real-world-scenario-building-a-feature-together)
5. [Common Workflows](#common-workflows)
6. [Monitoring and Debugging](#monitoring-and-debugging)
7. [Advanced Usage](#advanced-usage)
8. [Tips and Best Practices](#tips-and-best-practices)

---

## Prerequisites

Before you begin, ensure you have:

### Required Software

1. **tmux 3.0+** - Terminal multiplexer for agent isolation
   ```bash
   # macOS
   brew install tmux

   # Ubuntu/Debian
   sudo apt-get install tmux

   # Verify installation
   tmux -V  # Should show: tmux 3.x or later
   ```

2. **Python 3.12+** - Runtime environment
   ```bash
   python3 --version  # Should show: Python 3.12.x or later
   ```

3. **uv** - Fast Python package manager
   ```bash
   # Install uv
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Verify installation
   uv --version
   ```

4. **Claude Code** - Multiple instances (2+ recommended to start)
   ```bash
   # Verify Claude Code is installed
   which claude
   ```

### Basic tmux Knowledge

If you're new to tmux, here are the essential commands you'll need:

| Command | Description |
|---------|-------------|
| `tmux new -s myproject` | Create a new session named "myproject" |
| `Ctrl+b "` | Split pane horizontally |
| `Ctrl+b %` | Split pane vertically |
| `Ctrl+b arrow-keys` | Navigate between panes |
| `Ctrl+b [` | Enter scroll mode (press `q` to exit) |
| `Ctrl+b d` | Detach from session (keeps running) |
| `tmux attach -t myproject` | Reattach to detached session |
| `tmux kill-session -t myproject` | Kill entire session |

Don't worry if this seems overwhelming - we'll guide you through each step!

---

## Quick Start (5 Minutes)

Let's get your first multi-agent system running in 5 minutes.

### Step 1: Install Claude Swarm

```bash
# Clone the repository
git clone https://github.com/yourusername/claude-swarm.git
cd claude-swarm

# Install dependencies
uv sync --all-extras

# Verify installation
uv run claudeswarm --help
```

Expected output:
```
Usage: claudeswarm [OPTIONS] COMMAND [ARGS]...

  Claude Swarm - Multi-agent coordination for Claude Code

Commands:
  discover          Discover active agents
  send-to-agent     Send a message to a specific agent
  broadcast-to-all  Broadcast message to all agents
  ...
```

### Step 2: Create Your First Multi-Agent Session

```bash
# Start a new tmux session
tmux new -s tutorial

# Split into 3 panes (we'll start small)
# Press: Ctrl+b "  (split horizontally)
# Press: Ctrl+b "  (split horizontally again)
```

You should now see 3 panes stacked vertically.

### Step 3: Launch Claude Code Agents

In each pane, launch Claude Code:

```bash
# Pane 1 (Top)
claude

# Pane 2 (Middle) - Navigate with: Ctrl+b down-arrow
claude

# Pane 3 (Bottom) - Navigate with: Ctrl+b down-arrow
claude
```

You now have 3 Claude Code agents running!

### Step 4: Discover Your Agents

In the **top pane**, run:

```bash
uv run claudeswarm discover
```

Expected output:
```
=== Agent Discovery [2025-11-07T10:30:00+00:00] ===
Session: tutorial
Total agents: 3

  ✓ agent-0       | tutorial:0.0     | PID: 12345   | active
  ✓ agent-1       | tutorial:0.1     | PID: 12346   | active
  ✓ agent-2       | tutorial:0.2     | PID: 12347   | active

Registry saved to: ACTIVE_AGENTS.json
```

Congratulations! Your agents can now see each other.

### Step 5: Onboard All Agents

Now that agents are discovered, they need to know about the coordination system. Run the automated onboarding command:

```bash
uv run claudeswarm onboard
```

Expected output:
```
=== Claude Swarm Agent Onboarding ===

Step 1: Discovering active agents...
Found 3 active agent(s): agent-0, agent-1, agent-2

Step 2: Broadcasting onboarding messages...

Onboarding complete! Messages delivered to 3 agent(s).

All agents have been notified about:
  - Coordination protocol rules
  - Available commands
  - How to send messages and acquire locks
  - Where to find documentation

Agents are now ready to coordinate!
```

**Check your other panes** - each agent received onboarding messages explaining:
- How the coordination system works
- Key protocol rules (always lock files before editing)
- Essential commands
- Where to find documentation

This single command prepares all agents to work together!

### Step 6: Send Your First Message

In **Pane 1** (agent-0), send a message to agent-1:

```bash
uv run claudeswarm send-to-agent agent-1 INFO "Hello from agent-0!"
```

**Switch to Pane 2** (Ctrl+b down-arrow) and you should see:
```
[agent-0][2025-11-07 10:35:00][INFO]: Hello from agent-0!
```

### Step 7: Broadcast to Everyone

In **Pane 1** (agent-0), broadcast to all agents:

```bash
uv run claudeswarm broadcast-to-all INFO "Team meeting at 3pm!"
```

**Switch to Panes 2 and 3** - both should receive the message (agent-0 won't receive it since it excludes itself by default).

### Step 8: Test File Locking

In **Pane 1** (agent-0), acquire a lock:

```bash
uv run claudeswarm lock acquire --file test.txt --reason "writing documentation"
```

Output:
```
Lock acquired on: test.txt
  Agent: agent-0
  Reason: writing documentation
```

Now in **Pane 2** (agent-1), try to acquire the same lock:

```bash
uv run claudeswarm lock acquire --file test.txt --reason "fixing typos"
```

Output:
```
Lock conflict on: test.txt
  Currently held by: agent-0
  Locked at: 2025-11-07 10:40:00 UTC
  Age: 15.3 seconds
  Reason: writing documentation
```

**Success!** You've prevented a file conflict. Now release the lock in Pane 1:

```bash
uv run claudeswarm lock release --file test.txt
```

And try again in Pane 2:

```bash
uv run claudeswarm lock acquire --file test.txt --reason "fixing typos"
```

Output:
```
Lock acquired on: test.txt
  Agent: agent-1
  Reason: fixing typos
```

**Congratulations!** You've completed the quick start. Your agents can now:
- Discover each other
- Receive automated onboarding
- Send messages
- Coordinate file access

---

## Core Concepts Tutorial

Now let's dive deeper into each coordination mechanism.

### Concept 1: Agent Discovery

**What it is:** The system that detects which Claude Code instances are running in your tmux session.

**Why it matters:** Agents need to know about each other before they can communicate.

**How it works:**
1. Scans all tmux panes in your session
2. Identifies processes that match Claude Code patterns
3. Assigns unique IDs (agent-0, agent-1, etc.)
4. Saves registry to `ACTIVE_AGENTS.json`

**Hands-On Example:**

```bash
# Run discovery
uv run claudeswarm discover

# View the registry file
cat ACTIVE_AGENTS.json
```

Example output:
```json
{
  "session_name": "tutorial",
  "updated_at": "2025-11-07T10:30:00+00:00",
  "agents": [
    {
      "id": "agent-0",
      "pane_index": "tutorial:0.0",
      "pid": 12345,
      "status": "active",
      "last_seen": "2025-11-07T10:30:00+00:00"
    },
    {
      "id": "agent-1",
      "pane_index": "tutorial:0.1",
      "pid": 12346,
      "status": "active",
      "last_seen": "2025-11-07T10:30:00+00:00"
    }
  ]
}
```

**Key Points:**
- Run `discover` whenever you add/remove agents
- Agent IDs are stable within a session
- Agents not seen for 60 seconds are marked as "stale"

---

### Concept 2: Messaging Between Agents

**What it is:** A communication system that lets agents send messages to each other via tmux.

**Why it matters:** Agents need to ask questions, report status, and coordinate work.

**Message Types:**

| Type | Purpose | Example Use Case |
|------|---------|------------------|
| **INFO** | Share information | "Starting work on auth module" |
| **QUESTION** | Ask for help | "What database are we using?" |
| **REVIEW-REQUEST** | Request code review | "Please review PR #42" |
| **BLOCKED** | Report blockage | "Waiting for API schema" |
| **COMPLETED** | Announce completion | "Feature XYZ is done" |
| **CHALLENGE** | Disagree respectfully | "I think we should use Postgres instead" |
| **ACK** | Acknowledge receipt | "Got it, thanks!" |

**Hands-On Example:**

**Scenario:** Agent-1 needs help from Agent-2.

In **Pane 2** (agent-1):
```bash
uv run claudeswarm send-to-agent agent-2 QUESTION "What database schema should I use for user authentication?"
```

In **Pane 3** (agent-2), you'll see:
```
[agent-1][2025-11-07 11:00:00][QUESTION]: What database schema should I use for user authentication?
```

Now reply from **Pane 3** (agent-2):
```bash
uv run claudeswarm send-to-agent agent-1 INFO "Use the schema in docs/database.md - users table with email, password_hash, and created_at fields"
```

**Pane 2** receives:
```
[agent-2][2025-11-07 11:00:15][INFO]: Use the schema in docs/database.md - users table with email, password_hash, and created_at fields
```

**Best Practices:**
- Use specific message types (not just INFO for everything)
- Keep messages concise and actionable
- Limit to 10 messages per minute (rate limiting)
- Use broadcast sparingly (only for team-wide info)

---

### Concept 3: File Locking

**What it is:** A distributed locking system that prevents multiple agents from editing the same file simultaneously.

**Why it matters:** Without locks, agents will create merge conflicts and overwrite each other's work.

**The Golden Rule:** **NEVER edit a file without acquiring its lock first.**

**How Locks Work:**

```
                                    ┌─────────────────┐
                                    │  Lock Available │
                                    └────────┬────────┘
                                             │
                          ┌──────────────────┴──────────────────┐
                          │                                     │
                    Agent-1 requests                     Agent-2 requests
                    ┌──────▼──────┐                     ┌──────▼──────┐
                    │ Lock Granted│                     │Lock Conflict│
                    └──────┬──────┘                     └──────┬──────┘
                           │                                   │
                    ┌──────▼──────┐                    ┌──────▼──────┐
                    │  Edit File  │                    │ Ask Agent-1 │
                    └──────┬──────┘                    │  for ETA    │
                           │                           └─────────────┘
                    ┌──────▼──────┐
                    │Release Lock │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Now Agent-2│
                    │  can acquire│
                    └─────────────┘
```

**Hands-On Example:**

**Scenario:** Two agents want to edit the same file.

In **Pane 1** (agent-0), create a file and lock it:
```bash
echo "# Authentication Module" > src/auth.py
uv run claudeswarm lock acquire --file src/auth.py --reason "implementing login function"
```

Edit the file:
```bash
cat >> src/auth.py << 'EOF'

def login(username, password):
    """Authenticate user and return token."""
    # TODO: Implement
    pass
EOF
```

Meanwhile, in **Pane 2** (agent-1), try to lock the same file:
```bash
uv run claudeswarm lock acquire --file src/auth.py --reason "adding logout function"
```

Output:
```
Lock conflict on: src/auth.py
  Currently held by: agent-0
  Locked at: 2025-11-07 11:15:00 UTC
  Age: 45.2 seconds
  Reason: implementing login function
```

Agent-1 should now **ask agent-0 for ETA**:
```bash
uv run claudeswarm send-to-agent agent-0 QUESTION "How long until you finish with src/auth.py? I need to add logout function."
```

In **Pane 1**, respond:
```bash
uv run claudeswarm send-to-agent agent-1 INFO "2 more minutes, then it's all yours"
```

After finishing, **release the lock in Pane 1**:
```bash
uv run claudeswarm lock release --file src/auth.py
uv run claudeswarm send-to-agent agent-1 INFO "src/auth.py is now available"
```

Now in **Pane 2**, acquire and edit:
```bash
uv run claudeswarm lock acquire --file src/auth.py --reason "adding logout function"

cat >> src/auth.py << 'EOF'

def logout(token):
    """Invalidate user token."""
    # TODO: Implement
    pass
EOF

uv run claudeswarm lock release --file src/auth.py
```

**Success!** Both agents edited the file safely without conflicts.

**Advanced: Glob Pattern Locking**

You can lock multiple files at once:

```bash
# Lock all Python files in src/auth/
uv run claudeswarm lock acquire --file "src/auth/*.py" --reason "refactoring auth module"

# Lock all test files
uv run claudeswarm lock acquire --file "tests/**/*_test.py" --reason "updating test suite"
```

**Warning:** Glob locks conflict symmetrically. If you hold `src/auth/*.py`, no one can lock `src/auth/login.py`.

---

### Concept 4: Acknowledgments (ACKs)

**What it is:** A reliability mechanism that ensures critical messages are received.

**Why it matters:** Some messages are too important to risk being missed (e.g., "I'm blocked and can't proceed").

**How it works:**
1. Sender sends message with ACK requirement
2. System tracks pending acknowledgment
3. If no ACK within timeout (30s), retry
4. After 3 retries, escalate to ALL agents

**When to use ACKs:**
- **BLOCKED** messages (always)
- Critical coordination changes
- Task handoffs between agents
- Security or deployment alerts

**Hands-On Example:**

**Note:** As of current implementation, ACKs are partially implemented. The messaging system supports ACK message types, but automatic retry/escalation is in the `ack.py` module.

For now, you can manually send ACKs:

In **Pane 1** (agent-0):
```bash
uv run claudeswarm send-to-agent agent-1 BLOCKED "Cannot proceed without database schema - PLEASE ACKNOWLEDGE"
```

In **Pane 2** (agent-1):
```bash
# Acknowledge receipt
uv run claudeswarm send-to-agent agent-0 ACK "Acknowledged - sending schema now"

# Send the needed information
uv run claudeswarm send-to-agent agent-0 INFO "Database schema: users(id, email, password_hash, created_at)"
```

**Future Enhancement:** The `send-with-ack` command will automate the retry/escalation process.

---

### Concept 5: Coordination File

**What it is:** A shared `COORDINATION.md` file that serves as a team workspace.

**Why it matters:** Provides a single source of truth for sprint goals, current work, blockers, and decisions.

**Structure:**

```markdown
# Coordination File

## Sprint Goals
- Goal 1: Build authentication system
- Goal 2: Add user dashboard

## Current Work
| Agent | Task | Status | Started |
|-------|------|--------|---------|
| agent-1 | JWT implementation | In Progress | 2025-11-07 |
| agent-2 | Login UI | In Progress | 2025-11-07 |

## Blocked Items
- **Database migration**: Waiting for approval (Agent: agent-1)

## Code Review Queue
- **PR #42**: JWT implementation (Author: agent-1, Reviewer: agent-2)

## Decisions
- **[2025-11-07]** Use PostgreSQL for production database
```

**Hands-On Example:**

Initialize the coordination file:
```bash
uv run claudeswarm coordination init
```

View the file:
```bash
cat COORDINATION.md
```

Update a section (Python API):
```python
from claudeswarm.coordination import update_section

update_section(
    section="Current Work",
    content="""| Agent | Task | Status | Started |
|-------|------|--------|---------|
| agent-0 | API endpoints | In Progress | 2025-11-07 |
| agent-1 | Database models | In Progress | 2025-11-07 |"""
)
```

**Important:** The coordination file uses locking too! You must acquire a lock before editing it.

---

## Real-World Scenario: Building a Feature Together

Let's put it all together with a realistic scenario: Building a user authentication feature with 3 agents.

### The Team

- **Agent-0 (Backend):** Implements API endpoints
- **Agent-1 (Database):** Creates database models
- **Agent-2 (Tests):** Writes integration tests

### The Goal

Build a complete authentication system with:
1. User registration endpoint
2. Login endpoint
3. Database models
4. Integration tests

### Setup

Make sure you have 3 panes with Claude Code running, then discover agents:

```bash
uv run claudeswarm discover
```

### Phase 1: Planning and Coordination

**Agent-0 (Coordinator) - Pane 1:**

```bash
# Initialize coordination file
uv run claudeswarm coordination init

# Announce the sprint goal
uv run claudeswarm broadcast-to-all INFO "New sprint: Build user authentication system. Check COORDINATION.md for tasks."

# Update coordination file with tasks
# (In a real scenario, Agent-0 would edit COORDINATION.md with task assignments)
```

**Agent-1 and Agent-2 - Panes 2 and 3:**

```bash
# Both acknowledge
uv run claudeswarm send-to-agent agent-0 ACK "Ready to start"
```

### Phase 2: Parallel Development

**Agent-1 (Database) - Pane 2:**

```bash
# Lock database model file
uv run claudeswarm lock acquire --file "src/models/user.py" --reason "creating user model"

# Create database model
mkdir -p src/models
cat > src/models/user.py << 'EOF'
"""User database model."""
from datetime import datetime

class User:
    """User model for authentication."""

    def __init__(self, email: str, password_hash: str):
        self.id = None
        self.email = email
        self.password_hash = password_hash
        self.created_at = datetime.utcnow()

    def save(self):
        """Save user to database."""
        # TODO: Implement database save
        pass

    @staticmethod
    def find_by_email(email: str):
        """Find user by email."""
        # TODO: Implement database query
        pass
EOF

# Release lock
uv run claudeswarm lock release --file "src/models/user.py"

# Announce completion
uv run claudeswarm broadcast-to-all COMPLETED "User model complete - ready for API integration"
```

**Agent-0 (Backend) - Pane 1:**

While Agent-1 works on the model, Agent-0 can start the API structure:

```bash
# Lock API file
uv run claudeswarm lock acquire --file "src/api/auth.py" --reason "implementing auth endpoints"

# Create API endpoints
mkdir -p src/api
cat > src/api/auth.py << 'EOF'
"""Authentication API endpoints."""

def register_user(email: str, password: str):
    """Register a new user.

    Args:
        email: User email address
        password: Plain text password (will be hashed)

    Returns:
        dict: Success message with user ID
    """
    # TODO: Import User model once available
    # TODO: Hash password
    # TODO: Create and save user
    return {"message": "User registered", "user_id": "placeholder"}

def login_user(email: str, password: str):
    """Authenticate user and generate token.

    Args:
        email: User email address
        password: Plain text password

    Returns:
        dict: Authentication token
    """
    # TODO: Import User model once available
    # TODO: Verify password
    # TODO: Generate JWT token
    return {"token": "placeholder"}
EOF

# Release lock
uv run claudeswarm lock release --file "src/api/auth.py"
```

Now wait for Agent-1's completion message, then integrate:

```bash
# Wait for: [agent-1][timestamp][COMPLETED]: User model complete - ready for API integration

# Acknowledge
uv run claudeswarm send-to-agent agent-1 ACK "Received - integrating now"

# Lock both files to integrate
uv run claudeswarm lock acquire --file "src/api/auth.py" --reason "integrating with user model"

# Update auth.py to import and use User model
cat > src/api/auth.py << 'EOF'
"""Authentication API endpoints."""
from src.models.user import User
import hashlib

def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(email: str, password: str):
    """Register a new user."""
    password_hash = hash_password(password)
    user = User(email=email, password_hash=password_hash)
    user.save()
    return {"message": "User registered", "user_id": user.id}

def login_user(email: str, password: str):
    """Authenticate user and generate token."""
    user = User.find_by_email(email)
    if user and user.password_hash == hash_password(password):
        # Generate token (simplified)
        token = f"token_{user.id}"
        return {"token": token}
    return {"error": "Invalid credentials"}
EOF

# Release lock
uv run claudeswarm lock release --file "src/api/auth.py"

# Announce completion
uv run claudeswarm broadcast-to-all COMPLETED "Auth API endpoints complete - ready for testing"
```

**Agent-2 (Tests) - Pane 3:**

Agent-2 waits for both completions, then writes tests:

```bash
# Wait for: [agent-0][timestamp][COMPLETED]: Auth API endpoints complete - ready for testing

# Acknowledge
uv run claudeswarm send-to-agent agent-0 ACK "Starting integration tests"

# Lock test file
uv run claudeswarm lock acquire --file "tests/test_auth.py" --reason "writing integration tests"

# Create integration tests
mkdir -p tests
cat > tests/test_auth.py << 'EOF'
"""Integration tests for authentication system."""
from src.api.auth import register_user, login_user

def test_user_registration():
    """Test user can register."""
    result = register_user("test@example.com", "password123")
    assert "user_id" in result
    assert result["message"] == "User registered"

def test_user_login():
    """Test user can login after registration."""
    # Register user
    register_user("login@example.com", "password123")

    # Login
    result = login_user("login@example.com", "password123")
    assert "token" in result

def test_invalid_login():
    """Test login fails with wrong password."""
    # Register user
    register_user("fail@example.com", "password123")

    # Try wrong password
    result = login_user("fail@example.com", "wrongpassword")
    assert "error" in result
EOF

# Release lock
uv run claudeswarm lock release --file "tests/test_auth.py"

# Run tests (this might fail without a real database, but demonstrates the workflow)
# pytest tests/test_auth.py

# Announce completion
uv run claudeswarm broadcast-to-all COMPLETED "Integration tests complete - auth system ready for review"
```

### Phase 3: Code Review

**Agent-0 (Coordinator) - Pane 1:**

```bash
# Request review from agents
uv run claudeswarm send-to-agent agent-1 REVIEW-REQUEST "Please review src/api/auth.py"
uv run claudeswarm send-to-agent agent-2 REVIEW-REQUEST "Please review src/models/user.py"
```

**Agent-1 (Reviewer) - Pane 2:**

```bash
# Acknowledge review request
uv run claudeswarm send-to-agent agent-0 ACK "Starting review of auth.py"

# Lock file for review
uv run claudeswarm lock acquire --file "src/api/auth.py" --reason "code review"

# Review the code
cat src/api/auth.py

# Provide feedback
uv run claudeswarm send-to-agent agent-0 REVIEW-REQUEST "auth.py looks good, but please add error handling for duplicate emails"

# Release lock
uv run claudeswarm lock release --file "src/api/auth.py"
```

**Agent-0 (Addresses Feedback) - Pane 1:**

```bash
# Acknowledge feedback
uv run claudeswarm send-to-agent agent-1 ACK "Will add error handling"

# Lock and update
uv run claudeswarm lock acquire --file "src/api/auth.py" --reason "adding error handling"

# Add try-except for duplicate emails (simplified)
# ... edit file ...

# Release lock
uv run claudeswarm lock release --file "src/api/auth.py"

# Notify reviewer
uv run claudeswarm send-to-agent agent-1 COMPLETED "Error handling added - please re-review"
```

**Agent-1 (Final Approval) - Pane 2:**

```bash
# Lock for final review
uv run claudeswarm lock acquire --file "src/api/auth.py" --reason "final review"

# Check changes
cat src/api/auth.py

# Release lock
uv run claudeswarm lock release --file "src/api/auth.py"

# Approve
uv run claudeswarm send-to-agent agent-0 COMPLETED "APPROVED - auth.py ready to merge"
```

### Phase 4: Wrap Up

**Agent-0 (Coordinator) - Pane 1:**

```bash
# Announce feature completion
uv run claudeswarm broadcast-to-all COMPLETED "User authentication feature COMPLETE - all tests passing, code reviewed, ready to merge"

# Update coordination file
# Mark sprint goal as complete in COORDINATION.md
```

**Congratulations!** You've successfully coordinated 3 agents to build a complete feature:
- Backend API (Agent-0)
- Database models (Agent-1)
- Integration tests (Agent-2)
- Code review cycle
- Zero file conflicts

---

## Common Workflows

Here are patterns you'll use frequently.

### Workflow 1: Code Review

**Participants:** Implementer (agent-1), Reviewer (agent-2)

```bash
# Agent-1: Complete work and request review
uv run claudeswarm lock release --file src/feature.py
uv run claudeswarm send-to-agent agent-2 REVIEW-REQUEST "Please review src/feature.py - implements XYZ feature"

# Agent-2: Acknowledge and review
uv run claudeswarm send-to-agent agent-1 ACK "Starting review"
uv run claudeswarm lock acquire --file src/feature.py --reason "code review"
# ... review code ...
uv run claudeswarm send-to-agent agent-1 REVIEW-REQUEST "Please add docstrings and type hints"
uv run claudeswarm lock release --file src/feature.py

# Agent-1: Address feedback
uv run claudeswarm send-to-agent agent-2 ACK "Addressing feedback"
uv run claudeswarm lock acquire --file src/feature.py --reason "addressing review feedback"
# ... make changes ...
uv run claudeswarm lock release --file src/feature.py
uv run claudeswarm send-to-agent agent-2 COMPLETED "Feedback addressed"

# Agent-2: Final approval
uv run claudeswarm send-to-agent agent-1 COMPLETED "APPROVED - ready to merge"
```

### Workflow 2: Parallel Feature Development

**Participants:** 3+ agents working on different parts

```bash
# Agent-0 (Coordinator): Assign tasks
uv run claudeswarm send-to-agent agent-1 INFO "Task: Implement user registration (src/auth/register.py)"
uv run claudeswarm send-to-agent agent-2 INFO "Task: Implement user login (src/auth/login.py)"
uv run claudeswarm send-to-agent agent-3 INFO "Task: Write tests (tests/test_auth.py)"

# Each agent: Acknowledge and proceed
uv run claudeswarm send-to-agent agent-0 ACK "Starting on registration"
uv run claudeswarm lock acquire --file "src/auth/register.py" --reason "implementing registration"
# ... work ...
uv run claudeswarm lock release --file "src/auth/register.py"
uv run claudeswarm send-to-agent agent-0 COMPLETED "Registration complete"

# Repeat for each agent - no conflicts because different files!
```

### Workflow 3: Handling Blockers

**Participants:** Blocked agent (agent-1), Blocking agent (agent-2)

```bash
# Agent-1: Report blocker
uv run claudeswarm send-to-agent agent-2 BLOCKED "Cannot proceed without API schema definition - please send ASAP"

# Agent-2: Acknowledge and unblock
uv run claudeswarm send-to-agent agent-1 ACK "Sending schema now"
uv run claudeswarm send-to-agent agent-1 INFO "API schema: POST /users {email, password} -> {user_id, token}"

# Agent-1: Acknowledge unblock
uv run claudeswarm send-to-agent agent-2 ACK "Thanks! Proceeding now"
```

### Workflow 4: Team Decision Making

**Participants:** All agents

```bash
# Agent-0: Propose decision
uv run claudeswarm broadcast-to-all CHALLENGE "Proposal: Use PostgreSQL instead of SQLite. Opinions?"

# Agents vote/comment
uv run claudeswarm send-to-agent agent-0 INFO "Agree - Postgres has better performance"
uv run claudeswarm send-to-agent agent-0 CHALLENGE "Disagree - SQLite is simpler for our use case"
uv run claudeswarm send-to-agent agent-0 INFO "Agree - We'll need Postgres features eventually"

# Agent-0: Make final decision
uv run claudeswarm broadcast-to-all INFO "DECISION: Using PostgreSQL. Rationale: Better scalability and we'll need advanced features"

# Update COORDINATION.md
# Add to Decisions section: [2025-11-07] Use PostgreSQL: Better scalability and feature set
```

---

## Monitoring and Debugging

### View Message Log

All messages are logged to `agent_messages.log`:

```bash
# View recent messages
tail -20 agent_messages.log

# Follow in real-time
tail -f agent_messages.log

# Search for specific message type
grep "BLOCKED" agent_messages.log

# Pretty-print JSON log
tail -f agent_messages.log | jq .
```

### Check Agent Registry

```bash
# View active agents
cat ACTIVE_AGENTS.json

# Pretty-print
cat ACTIVE_AGENTS.json | jq .

# Check specific agent
cat ACTIVE_AGENTS.json | jq '.agents[] | select(.id == "agent-1")'
```

### Monitor File Locks

```bash
# List all active locks
uv run claudeswarm lock list

# Check specific file
uv run claudeswarm lock who --file src/auth.py

# View lock files directly
ls -la .agent_locks/

# View lock file contents
cat .agent_locks/src_auth_py.lock | jq .
```

### Debug Message Delivery

If messages aren't appearing:

```bash
# 1. Verify agents are discovered
uv run claudeswarm discover

# 2. Check tmux session
echo $TMUX  # Should output session info
tmux list-panes -a  # Should show your panes

# 3. Test send-keys directly
tmux send-keys -t tutorial:0.1 'echo "Test message"' Enter

# 4. Check message log for errors
tail -f agent_messages.log | grep -i error
```

### Cleanup Stale Locks

If locks are stuck:

```bash
# Clean up locks older than 5 minutes
uv run claudeswarm cleanup-stale-locks

# Force remove all locks (use with caution!)
rm -rf .agent_locks/*
```

### Troubleshooting Common Issues

**Issue: "No agents discovered"**

Solution:
```bash
# Verify tmux is running
tmux list-sessions

# Verify Claude Code processes
ps aux | grep claude

# Try manual discovery
uv run claudeswarm discover --verbose
```

**Issue: "Rate limit exceeded"**

Solution:
```bash
# Wait 60 seconds
sleep 60

# Or batch your messages
uv run claudeswarm broadcast-to-all INFO "Status: Feature A done, Feature B in progress, Feature C blocked on API"
```

**Issue: "Lock conflict on every file"**

Solution:
```bash
# Check for glob pattern locks
uv run claudeswarm lock list

# Someone might have locked **/*.py or similar
# Ask them to release or wait for timeout
```

---

## Advanced Usage

### Custom Coordination Patterns

You can build custom workflows using the Python API:

```python
# custom_workflow.py
from claudeswarm.discovery import refresh_registry
from claudeswarm.messaging import send_message, MessageType
from claudeswarm.locking import LockManager

def distributed_code_review(files, reviewers):
    """Assign files to reviewers for parallel review."""
    lm = LockManager()

    for file, reviewer in zip(files, reviewers):
        # Assign review task
        send_message(
            sender_id="agent-0",
            recipient_id=reviewer,
            message_type=MessageType.REVIEW_REQUEST,
            content=f"Please review {file}"
        )

        # Lock file for reviewer
        lm.acquire_lock(file, reviewer, "code review assignment")

# Use it
distributed_code_review(
    files=["src/auth.py", "src/db.py", "src/api.py"],
    reviewers=["agent-1", "agent-2", "agent-3"]
)
```

### Integration with CI/CD

You can use Claude Swarm in automated pipelines:

```yaml
# .github/workflows/multi-agent-test.yml
name: Multi-Agent Testing

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Setup tmux
        run: sudo apt-get install tmux
      - name: Run multi-agent tests
        run: |
          tmux new-session -d -s ci
          # Launch agents and run tests
          uv run pytest tests/integration/
```

### Scaling to 8+ Agents

For larger teams:

```bash
# Create 8-pane layout
./examples/demo_setup.sh

# Or manually with custom layout
tmux new -s large-team
tmux split-window -h
tmux split-window -v
tmux split-window -v
# ... continue until you have 8+ panes

# Assign roles
# Pane 0: Coordinator
# Panes 1-4: Backend developers
# Panes 5-6: Frontend developers
# Pane 7: Test engineer
# Pane 8: DevOps/monitoring
```

**Best practices for large teams:**
1. Designate a coordinator agent (agent-0)
2. Use broadcast sparingly (direct messages preferred)
3. Use glob locks for module-level work
4. Update COORDINATION.md frequently
5. Run monitoring in dedicated pane

---

## Tips and Best Practices

### When to Use ACKs

Use acknowledgment-required messages when:
- Blocking another agent's work
- Critical security/deployment information
- Task handoffs with dependencies
- Coordination changes affecting everyone

Don't use ACKs for:
- Routine status updates
- Questions with no urgency
- FYI information

### How to Avoid Deadlocks

**Deadlock scenario:**
```
Agent-1 holds lock on A, wants lock on B
Agent-2 holds lock on B, wants lock on A
Both wait forever
```

**Prevention strategies:**
1. **Lock ordering:** Always acquire locks in alphabetical order
   ```bash
   # Good
   uv run claudeswarm lock acquire --file src/a.py
   uv run claudeswarm lock acquire --file src/b.py

   # Bad (if another agent locks b then a)
   uv run claudeswarm lock acquire --file src/b.py
   uv run claudeswarm lock acquire --file src/a.py
   ```

2. **Use glob locks:** Lock related files together
   ```bash
   uv run claudeswarm lock acquire --file "src/module/*.py" --reason "refactoring module"
   ```

3. **Communicate before locking:** Ask if someone else needs related files
   ```bash
   uv run claudeswarm broadcast-to-all QUESTION "Planning to lock src/auth/* for refactor. Anyone need those files?"
   ```

4. **Release quickly:** Don't hold locks while thinking or testing

### Effective Coordination File Usage

**Update after major milestones:**
```bash
# After completing a feature
# Add to "Decisions" section

# When blocked
# Add to "Blocked Items" section immediately

# When starting work
# Update "Current Work" section
```

**Keep it current:**
- Remove completed tasks
- Update status daily
- Archive old decisions (move to DECISIONS_ARCHIVE.md)

**Use it for standups:**
```bash
# Each agent reviews COORDINATION.md
cat COORDINATION.md

# Update their status
# Agent-1: Changed "JWT implementation" from "In Progress" to "Complete"
```

### Message Hygiene

**Good messages:**
```bash
uv run claudeswarm send-to-agent agent-1 REVIEW-REQUEST "Please review PR #42 - adds JWT authentication. Focus on security of token generation."

uv run claudeswarm send-to-agent agent-2 BLOCKED "Cannot proceed with user dashboard until API endpoints are deployed to staging"
```

**Bad messages:**
```bash
uv run claudeswarm send-to-agent agent-1 INFO "hey"

uv run claudeswarm broadcast-to-all INFO "working on stuff"
```

**Tips:**
- Be specific and actionable
- Include context (file names, PR numbers, etc.)
- Use correct message type
- Keep under 200 characters when possible

### Lock Management

**Good lock reasons:**
```bash
uv run claudeswarm lock acquire --file src/auth.py --reason "implementing JWT token validation"
uv run claudeswarm lock acquire --file "tests/*.py" --reason "updating tests for new API"
```

**Bad lock reasons:**
```bash
uv run claudeswarm lock acquire --file src/auth.py --reason "working"
uv run claudeswarm lock acquire --file src/auth.py --reason "stuff"
```

**Remember:**
- Lock just before editing
- Release immediately after editing
- Never hold lock while waiting/thinking
- Always provide descriptive reason

---

## What's Next?

You've completed the tutorial! You now know how to:
- Set up multi-agent coordination with tmux
- Use agent discovery and messaging
- Coordinate file access with locks
- Build features with multiple agents
- Handle code reviews and blockers
- Monitor and debug the system

### Next Steps

1. **Try the automated demo:**
   ```bash
   ./examples/demo_walkthrough.sh
   ```

2. **Read the detailed protocol:**
   - [AGENT_PROTOCOL.md](/Users/boris/work/aspire11/claude-swarm/AGENT_PROTOCOL.md) - Complete coordination rules
   - [docs/architecture.md](/Users/boris/work/aspire11/claude-swarm/docs/architecture.md) - System design
   - [docs/api-reference.md](/Users/boris/work/aspire11/claude-swarm/docs/api-reference.md) - API documentation

3. **Run integration tests:**
   ```bash
   pytest tests/integration/
   ```

4. **Build your own workflow:**
   - Start with 2-3 agents
   - Build a real feature
   - Scale up to 4-8 agents
   - Create custom coordination patterns

5. **Join the community:**
   - Share your workflows
   - Report bugs
   - Contribute improvements

---

## Quick Reference Card

### Essential Commands

```bash
# Discovery & Onboarding
uv run claudeswarm discover                                # Find all agents
uv run claudeswarm onboard                                 # Onboard all agents

# Messaging
uv run claudeswarm send-to-agent <agent-id> <TYPE> "<message>"
uv run claudeswarm broadcast-to-all <TYPE> "<message>"

# Locking
uv run claudeswarm lock acquire --file <path> --reason "<reason>"
uv run claudeswarm lock release --file <path>
uv run claudeswarm lock list
uv run claudeswarm lock who --file <path>

# Maintenance
uv run claudeswarm cleanup-stale-locks
```

### Message Types Quick Guide

- **INFO** - Status updates
- **QUESTION** - Need help/information
- **REVIEW-REQUEST** - Request code review
- **BLOCKED** - Cannot proceed (use with ACK)
- **COMPLETED** - Task done
- **CHALLENGE** - Disagree politely
- **ACK** - Acknowledge receipt

### Setup Workflow

```
Discover → Onboard → Coordinate
```

### Lock Workflow

```
Check → Acquire → Edit → Release → Announce
```

### The Golden Rules

1. **ALWAYS** acquire lock before editing
2. **ALWAYS** release lock after editing
3. **ALWAYS** communicate blockers immediately
4. **NEVER** edit without a lock
5. **NEVER** hold lock while idle

---

**Happy coordinating!** May your agents work together seamlessly and your merge conflicts be zero.

For questions, issues, or contributions, see the main [README.md](/Users/boris/work/aspire11/claude-swarm/README.md).
