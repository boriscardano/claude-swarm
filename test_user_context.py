#!/usr/bin/env python3
"""Check user context in E2B sandbox."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def check_users():
    """Check which users exist and where token should be."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    tests = [
        ("whoami", "Current user when using run_code"),
        ("echo $HOME", "Home directory"),
        ("ls -la /root/.bashrc", "Check root's .bashrc exists"),
        ("ls -la /home/user/.bashrc 2>&1", "Check user's .bashrc exists"),
        ("cat /root/.bashrc | grep CLAUDE || echo 'Not in root bashrc'", "Token in root .bashrc?"),
        ("cat /home/user/.bashrc 2>/dev/null | grep CLAUDE || echo 'Not in user bashrc'", "Token in user .bashrc?"),
        ("su - user -c 'whoami'", "User when running as user"),
        ("su - user -c 'echo $HOME'", "User's home directory"),
        ("su - user -c 'env | grep CLAUDE || echo No token'", "Token in user environment?"),
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
                for line in result.logs.stderr:
                    print(f"STDERR: {line.rstrip()}")
        if result.error:
            print(f"ERROR: {result.error}")
        print()


if __name__ == "__main__":
    asyncio.run(check_users())
