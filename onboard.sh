#!/bin/bash
# Universal onboarding script for Claude Swarm
# Usage: ./onboard.sh /path/to/your/project

set -e

# Cleanup function for dashboard process
cleanup_dashboard() {
    if [ ! -z "$DASHBOARD_PID" ] && kill -0 "$DASHBOARD_PID" 2>/dev/null; then
        echo ""
        echo "Cleaning up dashboard process (PID: $DASHBOARD_PID)..."
        kill "$DASHBOARD_PID" 2>/dev/null || true
    fi
}

# Register cleanup on script exit
trap cleanup_dashboard EXIT INT TERM

if [ -z "$1" ]; then
    echo "Usage: ./onboard.sh /path/to/your/project"
    echo "Example: ./onboard.sh ~/work/aspire11/podcasts-chatbot"
    exit 1
fi

PROJECT_DIR="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🚀 Claude Swarm Onboarding"
echo "================================"
echo "Project: $PROJECT_DIR"
echo ""

# Navigate to script directory
cd "$SCRIPT_DIR"

# Activate venv
echo "1. Activating environment..."
if [ ! -f ".venv/bin/activate" ]; then
    echo "Error: Virtual environment not found at .venv/bin/activate"
    echo "Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -e ."
    exit 1
fi

source .venv/bin/activate

# Verify activation worked
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Error: Failed to activate virtual environment"
    exit 1
fi

# Discover agents
echo ""
echo "2. Discovering agents in project..."
if ! claudeswarm --project-root "$PROJECT_DIR" discover-agents; then
    echo "Error: Failed to discover agents"
    echo "Make sure tmux is running with Claude Code instances"
    exit 1
fi

# Wait a moment for discovery to complete
sleep 0.5

# Copy ACTIVE_AGENTS.json to project directory
if [ -f "ACTIVE_AGENTS.json" ]; then
    cp ACTIVE_AGENTS.json "$PROJECT_DIR/"
    echo "   ✓ Agent registry copied to project"
else
    echo "Warning: ACTIVE_AGENTS.json not found in script directory"
fi

# Get agent count (disable set -e temporarily for this check)
set +e
AGENT_COUNT=$(claudeswarm --project-root "$PROJECT_DIR" list-agents 2>/dev/null | grep -c "agent-")
set -e

# Default to 0 if grep returned nothing
if [ -z "$AGENT_COUNT" ]; then
    AGENT_COUNT=0
fi

if [ "$AGENT_COUNT" -eq "0" ]; then
    echo ""
    echo "❌ No agents found!"
    echo "Make sure Claude Code is running in tmux panes in: $PROJECT_DIR"
    exit 1
fi

echo ""
echo "Found $AGENT_COUNT agent(s)"

# Start dashboard in background (stop existing one first)
echo ""
echo "3. Starting dashboard..."
pkill -f "claudeswarm start-dashboard" 2>/dev/null || true
sleep 1

# Check if port 8080 is already in use
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "Warning: Port 8080 is already in use. Dashboard may fail to start."
    echo "Attempting to start anyway..."
fi

# Start dashboard in background
claudeswarm --project-root "$PROJECT_DIR" start-dashboard --no-browser &
DASHBOARD_PID=$!

# Wait and verify dashboard started successfully
sleep 2
if ! kill -0 "$DASHBOARD_PID" 2>/dev/null; then
    echo "Error: Dashboard failed to start"
    DASHBOARD_PID=""  # Clear PID so cleanup doesn't try to kill non-existent process
    exit 1
fi

echo "   ✓ Dashboard running (PID: $DASHBOARD_PID)"

# Run Python onboarding
echo ""
echo "4. Introducing agents to each other..."
if ! python3 "$SCRIPT_DIR/onboard_agents.py" "$PROJECT_DIR"; then
    echo "Error: Agent onboarding failed"
    exit 1
fi

echo ""
echo "================================"
echo "✅ Onboarding complete!"
echo "================================"
echo ""
echo "Dashboard: http://localhost:8080"
echo "Project: $PROJECT_DIR"
echo ""
echo "Next: The agents have been notified and can now coordinate!"
echo ""
echo "NOTE: Dashboard is running in background (PID: $DASHBOARD_PID)"
echo "      To stop it manually: kill $DASHBOARD_PID"
echo "      Or use: pkill -f 'claudeswarm start-dashboard'"
echo ""

# Don't let trap cleanup kill dashboard on success - unset trap
trap - EXIT INT TERM
