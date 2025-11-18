#!/bin/bash
# Setup script for Claude Swarm agents working on podcasts-chatbot project

set -e

PROJECT_DIR="/Users/boris/work/aspire11/podcasts-chatbot"
SWARM_DIR="/Users/boris/work/aspire11/claude-swarm"

echo "🚀 Setting up Claude Swarm for podcasts-chatbot project..."
echo ""

# Navigate to project directory
cd "$PROJECT_DIR"

# Clean up old state
echo "1. Cleaning up old coordination state in $PROJECT_DIR..."
rm -f ACTIVE_AGENTS.json
mkdir -p .agent_locks
rm -f .agent_locks/*.lock 2>/dev/null || true
echo "   ✓ Cleaned up"

# Create tmux session
echo ""
echo "2. Creating tmux session 'podcasts'..."
tmux new-session -d -s podcasts -n agents -c "$PROJECT_DIR"

# Split into 2 panes vertically
echo "   ✓ Created session"
echo "   ✓ Splitting into 2 panes..."
tmux split-window -h -t podcasts:agents.0 -c "$PROJECT_DIR"

# Send setup commands to each pane
echo ""
echo "3. Setting up panes..."

# Pane 0 (Agent-0)
tmux send-keys -t podcasts:agents.0 "# This is Agent-0 - Start Claude Code to begin" C-m

# Pane 1 (Agent-1)
tmux send-keys -t podcasts:agents.1 "# This is Agent-1 - Start Claude Code to begin" C-m

echo "   ✓ Panes configured"

echo ""
echo "="*70
echo "✅ Setup complete!"
echo "="*70
echo ""
echo "PROJECT DIRECTORY: $PROJECT_DIR"
echo "TMUX SESSION: podcasts"
echo ""
echo "Next steps:"
echo ""
echo "1. Attach to the tmux session:"
echo "   tmux attach -t podcasts"
echo ""
echo "2. Start Claude Code in BOTH panes (manually)"
echo ""
echo "3. Then from ANYWHERE, run:"
echo "   cd $SWARM_DIR"
echo "   source .venv/bin/activate"
echo "   claudeswarm --project-root $PROJECT_DIR discover-agents"
echo ""
echo "4. Onboard the agents:"
echo "   python3 $SWARM_DIR/kickoff_podcast.py"
echo ""
echo "5. Give each agent the coordination instructions"
echo "   - See: $SWARM_DIR/PODCAST_AGENT0.txt"
echo "   - See: $SWARM_DIR/PODCAST_AGENT1.txt"
echo ""
echo "6. Monitor at: http://localhost:8080"
echo ""
