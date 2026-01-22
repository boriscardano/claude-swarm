#!/usr/bin/env python3
"""Test Claude Code authentication in E2B sandbox."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def test_claude_auth():
    """Test if Claude Code uses OAuth token automatically."""
    # Get sandbox ID
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"🔌 Connecting to sandbox: {sandbox_id}")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("✓ Connected!\n")

    # Test 1: Check if OAuth token is set in environment
    print("=" * 60)
    print("Test 1: Check if CLAUDE_CODE_OAUTH_TOKEN is set")
    print("=" * 60)
    result = await asyncio.to_thread(
        sandbox.run_code,
        "!bash -c 'source ~/.bashrc && env | grep CLAUDE_CODE_OAUTH_TOKEN | head -c 80'"
    )
    if hasattr(result, 'logs') and result.logs and result.logs.stdout:
        for line in result.logs.stdout:
            print(line.rstrip())
    else:
        print("Token not found in environment!")

    # Test 2: Check config.json
    print("\n" + "=" * 60)
    print("Test 2: Check Claude Code config")
    print("=" * 60)
    result = await asyncio.to_thread(
        sandbox.run_code,
        "!cat /root/.config/claude-code/config.json"
    )
    if hasattr(result, 'logs') and result.logs and result.logs.stdout:
        for line in result.logs.stdout:
            print(line.rstrip())

    # Test 3: Run claude --version
    print("\n" + "=" * 60)
    print("Test 3: claude --version (should work without prompts)")
    print("=" * 60)
    result = await asyncio.to_thread(
        sandbox.run_code,
        "!bash -c 'source ~/.bashrc && claude --version'"
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

    print("\n✅ Tests complete!")


if __name__ == "__main__":
    asyncio.run(test_claude_auth())
