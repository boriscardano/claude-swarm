#!/bin/bash
# Universal onboarding script for Claude Swarm
# Usage: ./onboard.sh /path/to/your/project

set -e

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
source .venv/bin/activate

# Discover agents
echo ""
echo "2. Discovering agents in project..."
claudeswarm --project-root "$PROJECT_DIR" discover-agents

# Copy ACTIVE_AGENTS.json to project directory
if [ -f "ACTIVE_AGENTS.json" ]; then
    cp ACTIVE_AGENTS.json "$PROJECT_DIR/"
    echo "   ✓ Agent registry copied to project"
fi

# Get agent count
AGENT_COUNT=$(claudeswarm --project-root "$PROJECT_DIR" list-agents 2>/dev/null | grep -c "agent-" || echo "0")

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
claudeswarm --project-root "$PROJECT_DIR" start-dashboard --no-browser &
DASHBOARD_PID=$!
sleep 2
echo "   ✓ Dashboard running (PID: $DASHBOARD_PID)"

# Run Python onboarding
echo ""
echo "4. Introducing agents to each other..."
python3 "$SCRIPT_DIR/onboard_agents.py" "$PROJECT_DIR"

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
