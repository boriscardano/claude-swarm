#!/bin/bash
# Setup script for Claude Swarm with 2 agents

set -e

echo "🚀 Setting up Claude Swarm with 2 agents..."
echo ""

# Navigate to project directory (script directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Clean up old state
echo "1. Cleaning up old state..."
rm -f ACTIVE_AGENTS.json
rm -f .agent_locks/*.lock 2>/dev/null || true
echo "   ✓ Cleaned up"

# Create tmux session
echo ""
echo "2. Creating tmux session 'claude-swarm'..."
tmux new-session -d -s claude-swarm -n agents

# Split into 2 panes vertically
echo "   ✓ Created session"
echo "   ✓ Splitting into 2 panes..."
tmux split-window -h -t claude-swarm:agents

# Set pane titles (for reference)
tmux select-pane -t claude-swarm:agents.0 -T "Agent-0"
tmux select-pane -t claude-swarm:agents.1 -T "Agent-1"

# Send setup commands to each pane
echo ""
echo "3. Setting up panes..."

# Pane 0 (Agent-0)
tmux send-keys -t claude-swarm:agents.0 "cd $PROJECT_DIR" C-m
tmux send-keys -t claude-swarm:agents.0 "# Agent-0 Ready - Start Claude Code here"

# Pane 1 (Agent-1)
tmux send-keys -t claude-swarm:agents.1 "cd $PROJECT_DIR" C-m
tmux send-keys -t claude-swarm:agents.1 "# Agent-1 Ready - Start Claude Code here"

echo "   ✓ Panes configured"

echo ""
echo "="*70
echo "✅ Setup complete!"
echo "="*70
echo ""
echo "Next steps:"
echo ""
echo "1. Attach to the tmux session:"
echo "   tmux attach -t claude-swarm"
echo ""
echo "2. In EACH pane, start Claude Code (not shown here - start manually)"
echo ""
echo "3. Once both agents are running, run from outside tmux:"
echo "   cd $PROJECT_DIR"
echo "   source .venv/bin/activate"
echo "   claudeswarm discover-agents"
echo ""
echo "4. Then onboard the agents:"
echo "   python3 kickoff_coordination.py"
echo ""
echo "5. Give each agent these instructions:"
echo "   - Agent-0: See instructions in AGENT0_INSTRUCTIONS.txt"
echo "   - Agent-1: See instructions in AGENT1_INSTRUCTIONS.txt"
echo ""
echo "6. Monitor at: http://localhost:8080"
echo ""
