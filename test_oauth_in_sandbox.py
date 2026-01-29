#!/usr/bin/env python3
"""Test that ANTHROPIC_AUTH_TOKEN is in the E2B sandbox environment."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def test():
    """Test OAuth token in sandbox."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    # Test 1: Check if ANTHROPIC_AUTH_TOKEN exists in .bashrc
    print("=" * 70)
    print("Test 1: Checking for ANTHROPIC_AUTH_TOKEN in .bashrc")
    print("=" * 70)

    result = await asyncio.to_thread(
        sandbox.run_code,
        "!grep ANTHROPIC /home/user/.bashrc"
    )

    if hasattr(result, 'logs') and result.logs:
        if result.logs.stdout:
            for line in result.logs.stdout:
                # Mask the token value for security
                if "ANTHROPIC_AUTH_TOKEN" in line:
                    print("✓ ANTHROPIC_AUTH_TOKEN is set (value hidden for security)")
                else:
                    print(line.rstrip())
        if result.logs.stderr:
            for line in result.logs.stderr:
                print(f"STDERR: {line.rstrip()}")

    if result.error:
        print(f"ERROR: {result.error}")

    # Test 2: Try running claude --version
    print("\n" + "=" * 70)
    print("Test 2: Running 'claude --version'")
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

    if result.error:
        print(f"ERROR: {result.error}")

    # Test 3: Try running claude --print 'hello'
    print("\n" + "=" * 70)
    print("Test 3: Running 'claude --print hello' (should not ask for auth)")
    print("=" * 70)

    result = await asyncio.to_thread(
        sandbox.run_code,
        "!su - user -c 'bash -i -c \"claude --print \\\"Hello from E2B!\\\"\"'"
    )

    if hasattr(result, 'logs') and result.logs:
        if result.logs.stdout:
            print("STDOUT:")
            for line in result.logs.stdout:
                print(f"  {line.rstrip()}")
        if result.logs.stderr:
            print("STDERR:")
            for line in result.logs.stderr:
                print(f"  {line.rstrip()}")

    if result.error:
        print(f"ERROR: {result.error}")

    print("\n" + "=" * 70)
    print("Tests complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test())
