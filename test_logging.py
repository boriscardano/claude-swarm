#!/usr/bin/env python3
"""Test script to demonstrate agent discovery logging.

This script enables debug logging and runs agent discovery to show
all the detailed logging output about project filtering.
"""

import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Configure logging to show debug messages
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:%(name)s:%(message)s'
)

from claudeswarm.discovery import discover_agents

def main():
    """Run agent discovery with debug logging enabled."""
    print("=" * 70)
    print("Agent Discovery with Debug Logging")
    print("=" * 70)
    print()

    try:
        registry = discover_agents()

        print()
        print("=" * 70)
        print("Discovery Summary")
        print("=" * 70)
        print(f"Total agents: {len(registry.agents)}")
        print(f"Active agents: {len([a for a in registry.agents if a.status == 'active'])}")
        print(f"Stale agents: {len([a for a in registry.agents if a.status == 'stale'])}")
        print()

        if registry.agents:
            print("Discovered Agents:")
            for agent in registry.agents:
                print(f"  - {agent.id}: {agent.pane_index} (PID: {agent.pid}, Status: {agent.status})")
        else:
            print("No agents discovered")

    except Exception as e:
        print(f"Error during discovery: {e}", file=sys.stderr)
        return 1

    return 0

if __name__ == "__main__":
    sys.exit(main())
