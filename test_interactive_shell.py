#!/usr/bin/env python3
"""Test token in actual interactive shell."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def test():
    """Test in interactive bash."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    # Test in an INTERACTIVE bash shell (not -c)
    print("Testing ANTHROPIC_AUTH_TOKEN in interactive bash:")
    print("=" * 70)

    # The key is to use bash -i (interactive) and source .bashrc explicitly
    result = await asyncio.to_thread(
        sandbox.run_code,
        "!su - user -c 'bash -i -c \"env | grep ANTHROPIC\"'"
    )

    if hasattr(result, 'logs') and result.logs and result.logs.stdout:
        for line in result.logs.stdout:
            print(line.rstrip())
    else:
        print("No output")

    print("\n" + "=" * 70)
    print("Testing claude --version with ANTHROPIC_AUTH_TOKEN:")
    print("=" * 70)

    result = await asyncio.to_thread(
        sandbox.run_code,
        "!su - user -c 'bash -i -c \"claude --version\"'"
    )

    if hasattr(result, 'logs') and result.logs:
        if result.logs.stdout:
            for line in result.logs.stdout:
                print(line.rstrip())
        if result.logs.stderr:
            for line in result.logs.stderr:
                print(f"STDERR: {line.rstrip()}")


if __name__ == "__main__":
    asyncio.run(test())
