#!/usr/bin/env python3
"""
Test E2B sandbox to diagnose tmux installation issues.
"""

import asyncio
import os
from e2b_code_interpreter import Sandbox


async def test_tmux_installation():
    """Test tmux installation and apt-get in E2B."""
    # Get sandbox ID from cache
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    if not os.path.exists(cache_file):
        print("❌ No cached sandbox found. Run 'claudeswarm cloud deploy' first.")
        return

    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"🔌 Connecting to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("✓ Connected!\n")

    tests = [
        # Check if we have root/sudo access
        ("whoami", "Check current user"),
        ("id", "Check user ID and groups"),

        # Check if tmux exists
        ("which tmux", "Find tmux location"),
        ("ls -la /usr/bin/tmux", "Check /usr/bin/tmux"),
        ("find /usr -name tmux 2>/dev/null", "Search for tmux anywhere"),

        # Test apt-get access
        ("apt-get --version", "Check apt-get version"),
        ("apt-cache search tmux", "Search for tmux in apt"),

        # Try to install tmux manually
        ("apt-get update 2>&1 | head -20", "Try apt-get update (first 20 lines)"),
        ("apt-get install -y tmux 2>&1 | head -30", "Try installing tmux (first 30 lines)"),

        # Check if it worked
        ("which tmux", "Check if tmux is now available"),
    ]

    for cmd, desc in tests:
        print("=" * 60)
        print(f"Test: {desc}")
        print(f"Command: {cmd}")
        print("=" * 60)

        result = await asyncio.to_thread(sandbox.run_code, f"!{cmd}")
        print_result(result)
        print()

    print("=" * 60)
    print("✓ Tests complete!")
    print("=" * 60)


def print_result(result):
    """Print command result in a structured way."""
    if hasattr(result, 'logs') and result.logs:
        if result.logs.stdout:
            print("STDOUT:")
            for line in result.logs.stdout:
                print(f"  {line.rstrip()}")
        if result.logs.stderr:
            print("STDERR:")
            for line in result.logs.stderr:
                print(f"  {line.rstrip()}")

    if hasattr(result, 'text') and result.text:
        print("TEXT:")
        print(f"  {result.text}")

    if hasattr(result, 'error') and result.error:
        print("ERROR:")
        print(f"  {result.error}")

    if hasattr(result, 'exit_code'):
        print(f"EXIT CODE: {result.exit_code}")


if __name__ == "__main__":
    asyncio.run(test_tmux_installation())
