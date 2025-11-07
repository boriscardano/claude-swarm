#!/bin/bash
# Automated demo walkthrough for Claude Swarm
# Demonstrates key features with automated commands

set -e

SESSION_NAME="claude-swarm-demo"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Helper to send commands to specific pane
send_to_agent() {
    local agent_num=$1
    local command=$2
    local description=$3

    echo -e "${BLUE}[$description]${NC} Agent $agent_num: $command"
    tmux send-keys -t "$SESSION_NAME:0.$agent_num" "$command" C-m
    sleep 1
}

# Helper to display message in pane
show_message() {
    local agent_num=$1
    local message=$2

    tmux send-keys -t "$SESSION_NAME:0.$agent_num" "echo -e '${GREEN}>>> $message${NC}'" C-m
    sleep 0.5
}

echo -e "${GREEN}=== Claude Swarm Automated Demo ===${NC}"
echo ""
echo "This demo will walk through key features:"
echo "1. Agent Discovery"
echo "2. Message Broadcasting"
echo "3. File Locking"
echo "4. Code Review Workflow"
echo ""
read -p "Press Enter to start demo..."

# Check if session exists
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "Creating demo session..."
    "$PROJECT_ROOT/examples/demo_setup.sh"
    sleep 2
fi

echo ""
echo -e "${YELLOW}Phase 1: Agent Discovery${NC}"
echo "---------------------------------------"
sleep 2

# Agent 0 discovers other agents
show_message 0 "Phase 1: Discovering active agents..."
send_to_agent 0 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.discovery import refresh_registry, list_active_agents
registry = refresh_registry()
agents = list_active_agents()
print(f'\\nDiscovered {len(agents)} active agents:')
for agent in agents:
    print(f'  - {agent.id} (pane: {agent.pane_index})')
\"" "Discovery"

sleep 3

echo ""
echo -e "${YELLOW}Phase 2: Message Broadcasting${NC}"
echo "---------------------------------------"
sleep 2

# Agent 0 broadcasts task
show_message 0 "Broadcasting task assignment to all agents..."
send_to_agent 0 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.messaging import broadcast_message, MessageType
result = broadcast_message(
    sender_id='agent-0',
    message_type=MessageType.INFO,
    content='Starting new sprint - please check COORDINATION.md for assignments',
    exclude_self=True
)
print(f'\\nBroadcast result: {result}')
\"" "Broadcast"

sleep 3

# Agents acknowledge
show_message 1 "Acknowledging broadcast..."
send_to_agent 1 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.messaging import send_message, MessageType
send_message('agent-1', 'agent-0', MessageType.ACK, 'Acknowledged - ready to start')
print('ACK sent to Agent 0')
\"" "ACK"

sleep 2

show_message 2 "Acknowledging broadcast..."
send_to_agent 2 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.messaging import send_message, MessageType
send_message('agent-2', 'agent-0', MessageType.ACK, 'Acknowledged - reviewing tasks')
print('ACK sent to Agent 0')
\"" "ACK"

sleep 3

echo ""
echo -e "${YELLOW}Phase 3: File Locking${NC}"
echo "---------------------------------------"
sleep 2

# Create test file
show_message 1 "Creating test file..."
send_to_agent 1 "mkdir -p src && echo '# Test file' > src/feature.py" "Create File"
sleep 1

# Agent 1 acquires lock
show_message 1 "Acquiring lock on src/feature.py..."
send_to_agent 1 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
success, conflict = lm.acquire_lock('src/feature.py', 'agent-1', 'Implementing feature')
if success:
    print('✓ Lock acquired successfully')
else:
    print(f'✗ Lock conflict: {conflict}')
\"" "Lock Acquire"

sleep 2

# Agent 2 tries to acquire same lock
show_message 2 "Attempting to lock same file (should fail)..."
send_to_agent 2 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
success, conflict = lm.acquire_lock('src/feature.py', 'agent-2', 'Trying to edit')
if success:
    print('✓ Lock acquired')
else:
    print(f'✗ Lock held by {conflict.current_holder}')
    print(f'  Reason: {conflict.reason}')
\"" "Lock Conflict"

sleep 3

# Agent 2 sends blocked message
show_message 2 "Sending BLOCKED message to Agent 1..."
send_to_agent 2 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.messaging import send_message, MessageType
send_message('agent-2', 'agent-1', MessageType.BLOCKED, 'Waiting for src/feature.py lock')
print('BLOCKED message sent')
\"" "Blocked Message"

sleep 2

# Agent 1 finishes and releases lock
show_message 1 "Finishing work and releasing lock..."
send_to_agent 1 "echo 'def new_feature(): pass' >> src/feature.py" "Edit File"
sleep 1

send_to_agent 1 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
success = lm.release_lock('src/feature.py', 'agent-1')
if success:
    print('✓ Lock released')
\"" "Lock Release"

sleep 2

# Agent 2 acquires lock
show_message 2 "Acquiring lock (should succeed now)..."
send_to_agent 2 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
success, conflict = lm.acquire_lock('src/feature.py', 'agent-2', 'Code review')
if success:
    print('✓ Lock acquired for review')
\"" "Lock Acquire"

sleep 3

echo ""
echo -e "${YELLOW}Phase 4: Code Review Workflow${NC}"
echo "---------------------------------------"
sleep 2

# Agent 2 reviews and sends feedback
show_message 2 "Reviewing code..."
send_to_agent 2 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.messaging import send_message, MessageType
send_message('agent-2', 'agent-1', MessageType.REVIEW_REQUEST, 'Review feedback: Add docstring and type hints')
print('Review feedback sent')
\"" "Review Feedback"

sleep 2

# Agent 2 releases lock
send_to_agent 2 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
lm.release_lock('src/feature.py', 'agent-2')
print('✓ Lock released')
\"" "Lock Release"

sleep 2

# Agent 1 addresses feedback
show_message 1 "Addressing review feedback..."
send_to_agent 1 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
lm.acquire_lock('src/feature.py', 'agent-1', 'Addressing feedback')
print('✓ Lock acquired')
\"" "Lock Acquire"

sleep 1

send_to_agent 1 "echo 'def new_feature() -> None:\\n    \"\"\"New feature implementation.\"\"\"\\n    pass' > src/feature.py" "Update File"
sleep 1

send_to_agent 1 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
lm.release_lock('src/feature.py', 'agent-1')
print('✓ Changes committed, lock released')
\"" "Lock Release"

sleep 2

# Final approval
show_message 2 "Final review..."
send_to_agent 2 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.messaging import send_message, MessageType
send_message('agent-2', 'agent-1', MessageType.COMPLETED, 'APPROVED: src/feature.py looks great!')
print('Approval sent')
\"" "Approval"

sleep 3

echo ""
echo -e "${YELLOW}Phase 5: Monitoring${NC}"
echo "---------------------------------------"
sleep 2

# Show current locks
show_message 7 "Checking current lock status..."
send_to_agent 7 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.locking import LockManager
lm = LockManager()
locks = lm.list_all_locks()
print(f'\\nActive locks: {len(locks)}')
for lock in locks:
    print(f'  - {lock.filepath} locked by {lock.agent_id}')
    print(f'    Reason: {lock.reason}')
\"" "Lock Status"

sleep 3

# Show active agents
show_message 7 "Checking active agents..."
send_to_agent 7 "cd $PROJECT_ROOT && python -c \"
from claudeswarm.discovery import list_active_agents
agents = list_active_agents()
print(f'\\nActive agents: {len(agents)}')
for agent in agents:
    print(f'  - {agent.id} ({agent.status})')
\"" "Agent Status"

sleep 3

echo ""
echo -e "${GREEN}=== Demo Complete ===${NC}"
echo ""
echo "The demo has shown:"
echo "  ✓ Agent discovery and registry"
echo "  ✓ Message broadcasting and ACKs"
echo "  ✓ File locking and conflict detection"
echo "  ✓ Code review workflow"
echo "  ✓ Monitoring and status checking"
echo ""
echo "You can now experiment with the commands in each pane."
echo "See Agent 0 pane for available commands."
echo ""
echo "To detach from session: Ctrl+B then d"
echo "To re-attach: tmux attach-session -t $SESSION_NAME"
echo "To kill session: tmux kill-session -t $SESSION_NAME"
