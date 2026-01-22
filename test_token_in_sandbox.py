#!/usr/bin/env python3
"""Check OAuth token in E2B sandbox."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def check_token():
    """Check if token is accessible in sandbox."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    tests = [
        ("env | grep CLAUDE", "Check environment for CLAUDE vars (no sourcing)"),
        ("bash -c 'env | grep CLAUDE'", "Check in bash subshell"),
        ("bash -l -c 'env | grep CLAUDE'", "Check in login shell (should source .bash_profile)"),
        ("bash -c 'source ~/.bashrc && env | grep CLAUDE'", "Check with explicit source of .bashrc"),
        ("cat ~/.bashrc | grep CLAUDE", "Check if token is in .bashrc"),
        ("cat ~/.bash_profile | grep CLAUDE", "Check if token is in .bash_profile"),
        ("cat ~/.claude.json 2>/dev/null || echo 'File not found'", "Check ~/.claude.json"),
        ("cat ~/.config/claude-code/config.json 2>/dev/null || echo 'File not found'", "Check config.json"),
    ]

    for cmd, desc in tests:
        print("=" * 70)
        print(f"Test: {desc}")
        print(f"Command: {cmd}")
        print("=" * 70)
        result = await asyncio.to_thread(sandbox.run_code, f"!{cmd}")

        if hasattr(result, 'logs') and result.logs:
            if result.logs.stdout:
                for line in result.logs.stdout:
                    print(line.rstrip())
            if result.logs.stderr:
                print("STDERR:", result.logs.stderr)
        if result.error:
            print(f"ERROR: {result.error}")
        print()


if __name__ == "__main__":
    asyncio.run(check_token())
