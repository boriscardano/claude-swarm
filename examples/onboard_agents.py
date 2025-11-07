#!/usr/bin/env python3
"""
Onboard Agents - Automated onboarding for Claude Swarm agents.

This script discovers all active agents and sends standardized onboarding
messages explaining the coordination system, commands, and protocol.

Usage:
    python examples/onboard_agents.py

    # Or make it executable
    chmod +x examples/onboard_agents.py
    ./examples/onboard_agents.py

Customize:
    You can modify the ONBOARDING_MESSAGES list below to customize
    the onboarding content for your team's needs.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from claudeswarm.discovery import refresh_registry, list_active_agents
from claudeswarm.messaging import broadcast_message, MessageType


# Customizable onboarding messages
ONBOARDING_MESSAGES = [
    "=== CLAUDE SWARM COORDINATION ACTIVE ===",
    "Multi-agent coordination is now available in this session.",
    "",
    "KEY PROTOCOL RULES:",
    "1. ALWAYS acquire file locks before editing (claudeswarm lock acquire --file <path> --reason <reason>)",
    "2. ALWAYS release locks immediately after editing (claudeswarm lock release --file <path>)",
    "3. Use specific message types when communicating (INFO, QUESTION, REVIEW-REQUEST, BLOCKED, etc.)",
    "4. Check COORDINATION.md for sprint goals and current work",
    "",
    "QUICK COMMAND REFERENCE:",
    "Discovery: claudeswarm discover-agents",
    "Send message: claudeswarm send-to-agent <agent-id> <TYPE> '<message>'",
    "Broadcast: claudeswarm broadcast-to-all <TYPE> '<message>'",
    "Lock file: claudeswarm lock acquire --file <path> --reason '<reason>'",
    "Release lock: claudeswarm lock release --file <path>",
    "List locks: claudeswarm lock list",
    "",
    "DOCUMENTATION: See AGENT_PROTOCOL.md, TUTORIAL.md, or docs/INTEGRATION_GUIDE.md",
    "",
    "Ready to coordinate! Use 'claudeswarm --help' for full command list.",
]


def onboard_agents(custom_messages=None):
    """
    Discover and onboard all active agents.

    Args:
        custom_messages: Optional list of custom messages to send instead of defaults

    Returns:
        int: Number of agents onboarded
    """
    print("=== Claude Swarm Agent Onboarding ===\n")

    # Step 1: Discover agents
    print("Step 1: Discovering active agents...")
    registry = refresh_registry()
    agents = list_active_agents()

    if not agents:
        print("❌ No agents discovered.")
        print("   Make sure Claude Code instances are running in tmux panes.")
        return 0

    print(f"✓ Found {len(agents)} active agent(s): {', '.join(a.id for a in agents)}")
    print()

    # Step 2: Send onboarding messages
    print("Step 2: Broadcasting onboarding messages...")

    messages = custom_messages or ONBOARDING_MESSAGES

    # Add agent list to messages
    agent_list_msg = f"ACTIVE AGENTS: {', '.join(a.id for a in agents)}"
    if agent_list_msg not in messages:
        # Insert before the last few messages
        insert_pos = len(messages) - 3 if len(messages) > 3 else len(messages)
        messages = messages[:insert_pos] + ["", agent_list_msg] + messages[insert_pos:]

    success_count = 0
    total_messages = 0

    for msg in messages:
        if not msg.strip():  # Skip empty messages
            continue

        total_messages += 1
        result = broadcast_message(
            sender_id="system",
            message_type=MessageType.INFO,
            content=msg,
            exclude_self=False
        )
        delivered = sum(result.values())
        success_count += delivered

        # Show progress with truncated message
        display_msg = msg[:60] + "..." if len(msg) > 60 else msg
        print(f"  ✓ [{total_messages}/{len([m for m in messages if m.strip()])}] {display_msg}")

    print()
    print(f"✓ Onboarding complete! Sent {total_messages} messages to {len(agents)} agent(s).")
    print()
    print("All agents have been notified about:")
    print("  • Coordination protocol rules")
    print("  • Available commands")
    print("  • How to send messages and acquire locks")
    print("  • Where to find documentation")
    print()
    print("🚀 Agents are now ready to coordinate!")

    return len(agents)


def main():
    """Main entry point for the script."""
    try:
        onboarded = onboard_agents()
        sys.exit(0 if onboarded > 0 else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Onboarding interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error during onboarding: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
