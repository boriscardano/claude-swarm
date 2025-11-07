#!/usr/bin/env python3
"""Demo script to showcase monitoring dashboard functionality.

This script creates sample log entries to demonstrate the monitoring dashboard.
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, 'src')

from claudeswarm.messaging import MessageType


def create_sample_logs():
    """Create sample log entries for demonstration."""
    log_file = Path("agent_messages.log")

    sample_messages = [
        {
            "timestamp": datetime.now().isoformat(),
            "sender": "agent-0",
            "msg_type": MessageType.INFO.value,
            "content": "Starting task: implement authentication module",
            "recipients": ["agent-1"],
            "msg_id": "msg-001"
        },
        {
            "timestamp": datetime.now().isoformat(),
            "sender": "agent-1",
            "msg_type": MessageType.QUESTION.value,
            "content": "Which authentication method should we use? OAuth2 or JWT?",
            "recipients": ["agent-0"],
            "msg_id": "msg-002"
        },
        {
            "timestamp": datetime.now().isoformat(),
            "sender": "agent-2",
            "msg_type": MessageType.BLOCKED.value,
            "content": "Cannot proceed - src/auth/config.py is locked by agent-0",
            "recipients": ["agent-0"],
            "msg_id": "msg-003"
        },
        {
            "timestamp": datetime.now().isoformat(),
            "sender": "agent-0",
            "msg_type": MessageType.REVIEW_REQUEST.value,
            "content": "Please review PR #42 - Add OAuth2 authentication",
            "recipients": ["agent-1", "agent-2"],
            "msg_id": "msg-004"
        },
        {
            "timestamp": datetime.now().isoformat(),
            "sender": "agent-1",
            "msg_type": MessageType.ACK.value,
            "content": "Acknowledged - will review PR #42",
            "recipients": ["agent-0"],
            "msg_id": "msg-005"
        },
        {
            "timestamp": datetime.now().isoformat(),
            "sender": "agent-0",
            "msg_type": MessageType.COMPLETED.value,
            "content": "OAuth2 authentication module complete and tested",
            "recipients": ["agent-1", "agent-2"],
            "msg_id": "msg-006"
        },
        {
            "timestamp": datetime.now().isoformat(),
            "sender": "agent-3",
            "msg_type": MessageType.CHALLENGE.value,
            "content": "I disagree with the OAuth2 approach - JWT would be more suitable",
            "recipients": ["agent-0"],
            "msg_id": "msg-007"
        }
    ]

    with open(log_file, 'w') as f:
        for msg in sample_messages:
            f.write(json.dumps(msg) + '\n')

    print(f"Created sample logs in {log_file}")
    print(f"Generated {len(sample_messages)} sample messages")


def print_color_demo():
    """Print a demo of color coding."""
    from claudeswarm.monitoring import ColorScheme

    print("\n" + "=" * 80)
    print("COLOR SCHEME DEMONSTRATION")
    print("=" * 80 + "\n")

    color_examples = [
        (ColorScheme.RED, "BLOCKED/ERROR", "Critical issues that need attention"),
        (ColorScheme.YELLOW, "QUESTION/ACK", "Questions and acknowledgments"),
        (ColorScheme.GREEN, "COMPLETED", "Successfully completed tasks"),
        (ColorScheme.BLUE, "INFO/REVIEW-REQUEST", "Information and review requests"),
        (ColorScheme.MAGENTA, "CHALLENGE/LOCK", "Challenges and lock operations"),
    ]

    for color, msg_type, description in color_examples:
        print(f"{color}[{msg_type}]{ColorScheme.RESET} {description}")

    print("\n" + "=" * 80 + "\n")


def print_usage():
    """Print usage instructions."""
    print("\n" + "=" * 80)
    print("MONITORING DASHBOARD USAGE")
    print("=" * 80 + "\n")

    print("To start the monitoring dashboard:\n")
    print("  1. In current terminal:")
    print("     $ claudeswarm start-monitoring --no-tmux\n")

    print("  2. In dedicated tmux pane:")
    print("     $ claudeswarm start-monitoring\n")

    print("  3. With filters:")
    print("     $ claudeswarm start-monitoring --filter-type BLOCKED")
    print("     $ claudeswarm start-monitoring --filter-agent agent-0\n")

    print("  4. As Python module:")
    print("     $ python -m claudeswarm.monitoring --no-tmux\n")

    print("Features:")
    print("  - Real-time log tailing (updates every 2 seconds)")
    print("  - Color-coded messages by type")
    print("  - Status sidebar showing:")
    print("    * Active agents count and list")
    print("    * Active file locks")
    print("    * Pending acknowledgments")
    print("  - Message filtering by type, agent, or time range")
    print("  - Last 20 messages displayed")
    print("  - Ctrl+C to exit\n")

    print("=" * 80 + "\n")


def main():
    """Main demo function."""
    print("\n" + "=" * 80)
    print("CLAUDE SWARM MONITORING DASHBOARD DEMO")
    print("=" * 80 + "\n")

    # Create sample logs
    create_sample_logs()

    # Show color demo
    print_color_demo()

    # Show usage
    print_usage()

    print("Sample log file created. You can now run:")
    print("  $ claudeswarm start-monitoring --no-tmux")
    print("\nto see the monitoring dashboard in action!")


if __name__ == '__main__':
    main()
