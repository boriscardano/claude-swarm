#!/bin/bash
# Claude Swarm Message Checker Hook
# Checks for new messages and injects them into conversation

# Don't exit on errors - we handle them
set +e

# Try uv run first (dev mode), fall back to direct claudeswarm (installed)
MESSAGES=""
if command -v uv &> /dev/null; then
  MESSAGES=$(uv run claudeswarm check-messages --new-only --quiet --limit 5 2>&1) || true
fi

# Fall back to direct claudeswarm if uv failed or not available
if [ -z "$MESSAGES" ] && command -v claudeswarm &> /dev/null; then
  MESSAGES=$(claudeswarm check-messages --new-only --quiet --limit 5 2>&1) || true
fi

# Filter out error messages (keep only lines starting with [)
MESSAGES=$(echo "$MESSAGES" | grep '^\[' || true)

if [ -n "$MESSAGES" ]; then
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo ""
  printf '%s\n' "$MESSAGES"
  echo ""
  echo "Reply with: claudeswarm send-message <agent-id> INFO \"your message\""
  echo "───────────────────────────────────────────────────────────────"
fi
exit 0
