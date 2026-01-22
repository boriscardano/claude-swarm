#!/usr/bin/env python3
"""Fix permissions on current sandbox."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def fix():
    """Fix permissions."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    commands = [
        "chown -R user:user /home/user/.claude",
        "chown -R user:user /home/user/.config/claude-code",
        "ls -la /home/user/.claude",
        "ls -la /home/user/.config/claude-code",
    ]

    for cmd in commands:
        print(f"Running: {cmd}")
        result = await asyncio.to_thread(sandbox.run_code, f"!{cmd}")
        if hasattr(result, 'logs') and result.logs and result.logs.stdout:
            for line in result.logs.stdout:
                print(f"  {line.rstrip()}")
        if result.error:
            print(f"  Error: {result.error}")
        print()

    print("✅ Permissions fixed! Try running 'claude' again.")


if __name__ == "__main__":
    asyncio.run(fix())
