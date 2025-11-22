#!/bin/bash
#
# Start the collaborative development demo in tmux
#
# This script automatically sends the demo command to each tmux pane
# Usage: ./start_demo.sh [repo-url] [feature-description]
#
# Example:
#   ./start_demo.sh https://github.com/user/repo "Add dark mode support"
#

set -euo pipefail

REPO_URL="${1:-https://github.com/anthropics/claude-code}"
FEATURE="${2:-Add collaborative development workflow}"
SESSION_NAME="${3:-claude-swarm}"

echo "🚀 Starting collaborative development demo"
echo "   Repo: $REPO_URL"
echo "   Feature: $FEATURE"
echo "   Session: $SESSION_NAME"
echo

# Check if tmux session exists
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "❌ Error: tmux session '$SESSION_NAME' not found"
    echo "   Please deploy first: claudeswarm cloud deploy --agents 4"
    exit 1
fi

# Get number of panes
NUM_PANES=$(tmux list-panes -t "$SESSION_NAME" | wc -l)
echo "✓ Found $NUM_PANES panes in session '$SESSION_NAME'"

# Send commands to each pane
for (( i=0; i<NUM_PANES; i++ )); do
    echo "📝 Sending command to pane $i..."

    # Construct the demo command
    CMD="python /workspace/claude-swarm/examples/hackathon_demo/run_demo.py --agent $i --repo '$REPO_URL' --feature '$FEATURE'"

    # Send to tmux pane
    tmux send-keys -t "$SESSION_NAME.$i" "$CMD" C-m

    sleep 0.5
done

echo
echo "✅ Demo started in all panes!"
echo
echo "To monitor:"
echo "  tmux attach -t $SESSION_NAME"
echo
echo "To navigate:"
echo "  Ctrl+b + arrow keys    = Switch panes"
echo "  Ctrl+b + z             = Zoom/unzoom pane"
echo "  Ctrl+b + [             = Scroll mode (q to exit)"
