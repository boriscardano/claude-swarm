#!/usr/bin/env python3
"""Debug what's in the bashrc files."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def debug():
    """Check bashrc contents."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    tests = [
        ("cat /home/user/.bashrc", "Contents of /home/user/.bashrc"),
        ("cat /home/user/.bash_profile 2>/dev/null || echo 'Not found'", "Contents of /home/user/.bash_profile"),
        ("cat /home/user/.profile 2>/dev/null || echo 'Not found'", "Contents of /home/user/.profile"),
        ("su - user -c 'pwd'", "User's working directory"),
        ("su - user -c 'echo $HOME'", "User's HOME"),
        ("su - user -c 'bash -l -c \"env | grep CLAUDE\"'", "Env vars in login shell"),
    ]

    for cmd, desc in tests:
        print("=" * 70)
        print(f"{desc}")
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
    asyncio.run(debug())
