#!/bin/bash
# Demo setup script for Claude Swarm
# Creates an 8-pane tmux session to demonstrate multi-agent coordination

set -e

# Configuration
SESSION_NAME="claude-swarm-demo"
WINDOW_NAME="agents"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# Color codes for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper function for colored output
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    log_error "tmux is not installed. Please install tmux first."
    exit 1
fi

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    log_warning "Session '$SESSION_NAME' already exists."
    read -p "Do you want to kill it and create a new one? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        tmux kill-session -t "$SESSION_NAME"
        log_info "Killed existing session"
    else
        log_info "Attaching to existing session..."
        tmux attach-session -t "$SESSION_NAME"
        exit 0
    fi
fi

log_info "Creating tmux session: $SESSION_NAME"

# Create new session with first window
tmux new-session -d -s "$SESSION_NAME" -n "$WINDOW_NAME"

# Split window into 8 panes (2x4 grid)
# First split horizontally into 2 rows
tmux split-window -h -t "$SESSION_NAME:0"

# Split each half vertically into 4 panes
tmux split-window -v -t "$SESSION_NAME:0.0"
tmux split-window -v -t "$SESSION_NAME:0.0"
tmux split-window -v -t "$SESSION_NAME:0.2"

tmux split-window -v -t "$SESSION_NAME:0.4"
tmux split-window -v -t "$SESSION_NAME:0.4"
tmux split-window -v -t "$SESSION_NAME:0.6"

# Rearrange panes into a nice 2x4 grid
tmux select-layout -t "$SESSION_NAME:0" tiled

# Set working directory for all panes
for i in {0..7}; do
    tmux send-keys -t "$SESSION_NAME:0.$i" "cd $PROJECT_ROOT" C-m
done

# Clear all panes
for i in {0..7}; do
    tmux send-keys -t "$SESSION_NAME:0.$i" "clear" C-m
done

# Add identifying labels to each pane
tmux send-keys -t "$SESSION_NAME:0.0" "echo -e '${GREEN}[Agent 0 - Coordinator]${NC}'" C-m
tmux send-keys -t "$SESSION_NAME:0.1" "echo -e '${BLUE}[Agent 1 - Developer]${NC}'" C-m
tmux send-keys -t "$SESSION_NAME:0.2" "echo -e '${BLUE}[Agent 2 - Developer]${NC}'" C-m
tmux send-keys -t "$SESSION_NAME:0.3" "echo -e '${YELLOW}[Agent 3 - Reviewer]${NC}'" C-m
tmux send-keys -t "$SESSION_NAME:0.4" "echo -e '${BLUE}[Agent 4 - Developer]${NC}'" C-m
tmux send-keys -t "$SESSION_NAME:0.5" "echo -e '${BLUE}[Agent 5 - Developer]${NC}'" C-m
tmux send-keys -t "$SESSION_NAME:0.6" "echo -e '${YELLOW}[Agent 6 - Reviewer]${NC}'" C-m
tmux send-keys -t "$SESSION_NAME:0.7" "echo -e '${RED}[Agent 7 - Monitor]${NC}'" C-m

# Optional: Add demo commands to each pane
cat << 'EOF' > /tmp/demo_commands.txt
=== Claude Swarm Demo Commands ===

Agent Discovery:
  claudeswarm discover-agents

Send Message:
  claudeswarm send-to-agent agent-1 INFO "Hello!"

Broadcast:
  claudeswarm broadcast-to-all INFO "Team announcement"

Acquire Lock:
  claudeswarm lock acquire --file src/example.py --reason "Working on feature"

Release Lock:
  claudeswarm lock release --file src/example.py

List Locks:
  claudeswarm list-all-locks

Start Monitoring:
  claudeswarm start-monitoring

=== Demo Scenarios ===

Scenario 1: Basic Coordination
1. Agent 0: Discover agents
2. Agent 0: Broadcast task assignment
3. Agents 1-2: Send ACK
4. Agent 1: Acquire lock, work, release
5. Agent 2: Acquire lock, review

Scenario 2: Code Review
1. Agent 3: Lock file, make changes
2. Agent 3: Request review from Agent 1
3. Agent 1: Lock file, review, provide feedback
4. Agent 3: Address feedback
5. Agent 1: Approve

Scenario 3: Lock Conflict
1. Agent 1: Lock file
2. Agent 2: Try to lock same file (fails)
3. Agent 2: Send BLOCKED message
4. Agent 1: Finish work, release lock
5. Agent 2: Acquire lock

Press Ctrl+B then ? for tmux help
EOF

# Display demo commands in Agent 0 pane
tmux send-keys -t "$SESSION_NAME:0.0" "cat /tmp/demo_commands.txt" C-m

# Set up Agent 7 as monitor (if monitoring is implemented)
tmux send-keys -t "$SESSION_NAME:0.7" "echo 'Monitor pane - run: claudeswarm start-monitoring'" C-m

# Set pane titles (tmux 3.0+)
if tmux -V | awk '{print $2}' | awk -F. '{exit ($1 < 3)}' 2>/dev/null; then
    tmux select-pane -t "$SESSION_NAME:0.0" -T "Agent-0-Coordinator"
    tmux select-pane -t "$SESSION_NAME:0.1" -T "Agent-1-Developer"
    tmux select-pane -t "$SESSION_NAME:0.2" -T "Agent-2-Developer"
    tmux select-pane -t "$SESSION_NAME:0.3" -T "Agent-3-Reviewer"
    tmux select-pane -t "$SESSION_NAME:0.4" -T "Agent-4-Developer"
    tmux select-pane -t "$SESSION_NAME:0.5" -T "Agent-5-Developer"
    tmux select-pane -t "$SESSION_NAME:0.6" -T "Agent-6-Reviewer"
    tmux select-pane -t "$SESSION_NAME:0.7" -T "Agent-7-Monitor"
fi

# Select first pane
tmux select-pane -t "$SESSION_NAME:0.0"

log_success "Demo session created successfully!"
log_info ""
log_info "Session layout:"
log_info "  +----------------+----------------+"
log_info "  | Agent 0        | Agent 4        |"
log_info "  | Coordinator    | Developer      |"
log_info "  +----------------+----------------+"
log_info "  | Agent 1        | Agent 5        |"
log_info "  | Developer      | Developer      |"
log_info "  +----------------+----------------+"
log_info "  | Agent 2        | Agent 6        |"
log_info "  | Developer      | Reviewer       |"
log_info "  +----------------+----------------+"
log_info "  | Agent 3        | Agent 7        |"
log_info "  | Reviewer       | Monitor        |"
log_info "  +----------------+----------------+"
log_info ""
log_info "Tmux commands:"
log_info "  Ctrl+B then arrow keys - Navigate between panes"
log_info "  Ctrl+B then [ - Enter scroll mode (q to exit)"
log_info "  Ctrl+B then ? - Show all keybindings"
log_info "  Ctrl+B then d - Detach from session"
log_info ""
log_info "Attaching to session..."
sleep 2

# Attach to the session
tmux attach-session -t "$SESSION_NAME"
