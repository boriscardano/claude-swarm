#!/usr/bin/env python3
"""Test Claude Code with --dangerously-skip-permissions flag."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def test():
    """Test claude with skip permissions."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    print("Testing: claude --dangerously-skip-permissions --print 'hello'")
    print("=" * 70)

    result = await asyncio.to_thread(
        sandbox.run_code,
        "!su - user -c 'bash -i -c \"claude --dangerously-skip-permissions --print \\\"hello\\\"\"'"
    )

    if hasattr(result, 'logs') and result.logs:
        if result.logs.stdout:
            print("STDOUT:")
            for line in result.logs.stdout:
                print(line.rstrip())
        if result.logs.stderr:
            print("STDERR:")
            for line in result.logs.stderr:
                print(line.rstrip())

    if result.error:
        print(f"ERROR: {result.error}")


if __name__ == "__main__":
    asyncio.run(test())
