#!/bin/bash
#
# Simple Demo: Show Multi-Agent Coordination
#
# This script demonstrates the CORE innovation: agents coordinating via messages
# Perfect for a 2-minute video where you want to show something that ACTUALLY WORKS
#
# Usage: ./simple_demo.sh
#

set -euo pipefail

SESSION_NAME="${1:-claude-swarm}"

echo "🎬 Claude Swarm - Multi-Agent Coordination Demo"
echo "================================================"
echo

# Check if tmux session exists
if ! tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "❌ Error: tmux session '$SESSION_NAME' not found"
    echo "   Please deploy first: claudeswarm cloud deploy --agents 4"
    exit 1
fi

echo "✅ Found tmux session: $SESSION_NAME"
echo

# Pane 0: Project Manager - Discovers agents and broadcasts tasks
echo "📝 Pane 0 (Project Manager): Discovering agents and broadcasting task..."
tmux send-keys -t "$SESSION_NAME.0" "clear" C-m
sleep 0.5
tmux send-keys -t "$SESSION_NAME.0" "echo '🧑‍💼 Project Manager: Discovering team...'" C-m
sleep 0.5
tmux send-keys -t "$SESSION_NAME.0" "claudeswarm discover-agents" C-m
sleep 2
tmux send-keys -t "$SESSION_NAME.0" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME.0" "echo '📢 Broadcasting task to team...'" C-m
sleep 0.5
tmux send-keys -t "$SESSION_NAME.0" "claudeswarm broadcast-message --message '{\"type\":\"task\",\"action\":\"implement_feature\",\"feature\":\"Add dark mode\",\"assigned_by\":\"PM\"}'" C-m
sleep 2

# Pane 1: Backend Developer - Checks messages and responds
echo "📝 Pane 1 (Backend Developer): Checking for tasks..."
tmux send-keys -t "$SESSION_NAME.1" "clear" C-m
sleep 0.5
tmux send-keys -t "$SESSION_NAME.1" "echo '⚙️  Backend Developer: Waiting for assignment...'" C-m
sleep 1
tmux send-keys -t "$SESSION_NAME.1" "claudeswarm check-messages" C-m
sleep 2
tmux send-keys -t "$SESSION_NAME.1" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME.1" "echo '✅ Task received: Implementing backend logic...'" C-m
sleep 1
tmux send-keys -t "$SESSION_NAME.1" "claudeswarm broadcast-message --message '{\"type\":\"status\",\"agent\":\"backend\",\"status\":\"Working on dark mode API\"}'" C-m
sleep 2

# Pane 2: Frontend Developer - Checks messages and responds
echo "📝 Pane 2 (Frontend Developer): Checking for tasks..."
tmux send-keys -t "$SESSION_NAME.2" "clear" C-m
sleep 0.5
tmux send-keys -t "$SESSION_NAME.2" "echo '🎨 Frontend Developer: Waiting for assignment...'" C-m
sleep 1
tmux send-keys -t "$SESSION_NAME.2" "claudeswarm check-messages" C-m
sleep 2
tmux send-keys -t "$SESSION_NAME.2" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME.2" "echo '✅ Task received: Creating theme toggle UI...'" C-m
sleep 1
tmux send-keys -t "$SESSION_NAME.2" "claudeswarm broadcast-message --message '{\"type\":\"status\",\"agent\":\"frontend\",\"status\":\"Working on theme switcher\"}'" C-m
sleep 2

# Pane 3: QA Engineer - Checks messages
echo "📝 Pane 3 (QA Engineer): Monitoring team progress..."
tmux send-keys -t "$SESSION_NAME.3" "clear" C-m
sleep 0.5
tmux send-keys -t "$SESSION_NAME.3" "echo '🧪 QA Engineer: Monitoring team messages...'" C-m
sleep 1
tmux send-keys -t "$SESSION_NAME.3" "claudeswarm check-messages" C-m
sleep 2
tmux send-keys -t "$SESSION_NAME.3" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME.3" "echo '📊 Team Status: 2 agents working on dark mode feature'" C-m
sleep 1

# Show final status in pane 0
sleep 1
tmux send-keys -t "$SESSION_NAME.0" "echo ''" C-m
tmux send-keys -t "$SESSION_NAME.0" "echo '✅ All agents coordinated successfully!'" C-m
tmux send-keys -t "$SESSION_NAME.0" "claudeswarm list-agents" C-m

echo
echo "✅ Demo complete!"
echo
echo "To view the agents working:"
echo "  tmux attach -t $SESSION_NAME"
echo
echo "Navigate between panes:"
echo "  Ctrl+b + arrow keys"
echo
