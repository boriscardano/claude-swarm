#!/usr/bin/env python3
"""Test Claude Code /login in E2B sandbox."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def test_login():
    """Test interactive login."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    print("=" * 70)
    print("Attempting: claude /login")
    print("=" * 70)
    print()

    # Try to run claude /login and capture the output
    result = await asyncio.to_thread(
        sandbox.run_code,
        "!su - user -c 'bash -i -c \"claude /login\"'",
        timeout=30  # 30 second timeout
    )

    if hasattr(result, 'logs') and result.logs:
        if result.logs.stdout:
            print("STDOUT:")
            for line in result.logs.stdout:
                print(f"  {line.rstrip()}")
        if result.logs.stderr:
            print("\nSTDERR:")
            for line in result.logs.stderr:
                print(f"  {line.rstrip()}")

    if result.error:
        print(f"\nERROR: {result.error}")

    print("\n" + "=" * 70)
    print("If you see a URL above, you may be able to access it!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_login())
