#!/bin/bash
#
# Claude Swarm Message Checker Hook
#
# This hook automatically checks for new messages from other agents
# and injects them into the conversation context before each user prompt.
#
# Triggered by: UserPromptSubmit hook in Claude Code
# Output: Automatically injected into agent's conversation as additional context

set -e

# Get current agent ID using whoami command
AGENT_ID=$(claudeswarm whoami 2>/dev/null | grep "Agent ID:" | awk '{print $3}' || echo "")

# Exit silently if not in a tmux pane or no agent ID
if [ -z "$AGENT_ID" ]; then
  exit 0
fi

# Check for messages (only show unread/recent ones)
# Limit to 3 most recent messages to avoid context bloat
MESSAGES=$(claudeswarm check-messages --limit 3 2>/dev/null || echo "")

# Only output if there are actual messages
if [ -n "$MESSAGES" ] && [ "$MESSAGES" != "No messages found for $AGENT_ID" ]; then
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo ""
  echo "$MESSAGES"
  echo ""
  echo "───────────────────────────────────────────────────────────────"
fi

exit 0
