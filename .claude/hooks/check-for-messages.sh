#!/bin/bash
#
# Claude Swarm Message Checker Hook
#
# This hook automatically checks for new messages from other agents
# and injects them into the conversation context before each user prompt.
#
# Triggered by: UserPromptSubmit hook in Claude Code
# Output: Automatically injected into agent's conversation as additional context

set -euo pipefail

# Get current agent ID using whoami command
AGENT_ID=$(claudeswarm whoami 2>/dev/null | grep "Agent ID:" | awk '{print $3}' || echo "")

# Validate agent ID format
if [ -n "$AGENT_ID" ]; then
    if ! [[ "$AGENT_ID" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        exit 0
    fi
fi

# Exit silently if not in a tmux pane or no agent ID
if [ -z "$AGENT_ID" ]; then
  exit 0
fi

# Optional debug logging
if [ "${CLAUDESWARM_DEBUG:-0}" = "1" ]; then
    echo "[DEBUG] check-for-messages.sh executed for agent: $AGENT_ID" >&2
fi

# Check for messages (only show unread/recent ones)
# Limit to 3 most recent messages to avoid context bloat
# Add timeout to prevent hanging
MESSAGES=$(timeout 5s claudeswarm check-messages --limit 3 2>/dev/null || echo "")

# Only output if there are actual messages
# Use pattern matching instead of exact string comparison
if [ -n "$MESSAGES" ] && [[ ! "$MESSAGES" =~ ^No\ messages ]]; then
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo ""
  printf '%s\n' "$MESSAGES"
  echo ""
  echo "───────────────────────────────────────────────────────────────"
fi

exit 0
