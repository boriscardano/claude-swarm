#!/usr/bin/env python3
"""Debug Claude Code authentication in E2B."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def debug():
    """Debug authentication."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    # Check what's in the config files
    tests = [
        ("Root .bashrc", "!cat /root/.bashrc | tail -5"),
        ("User .bashrc", "!cat /home/user/.bashrc | tail -5"),
        ("Root .claude.json", "!cat /root/.claude.json 2>&1"),
        ("User .claude.json", "!cat /home/user/.claude.json 2>&1"),
        ("Root config", "!cat /root/.config/claude-code/config.json 2>&1"),
        ("User config", "!cat /home/user/.config/claude-code/config.json 2>&1"),
        ("Env in bash -i", "!su - user -c 'bash -i -c \"env | grep ANTHROPIC\"'"),
    ]

    for name, cmd in tests:
        print("=" * 70)
        print(f"{name}")
        print("=" * 70)
        result = await asyncio.to_thread(sandbox.run_code, cmd)
        if hasattr(result, 'logs') and result.logs:
            if result.logs.stdout:
                for line in result.logs.stdout:
                    if "ANTHROPIC_AUTH_TOKEN" in line:
                        print("ANTHROPIC_AUTH_TOKEN=*** (hidden)")
                    else:
                        print(line.rstrip())
            if result.logs.stderr:
                for line in result.logs.stderr:
                    print(f"STDERR: {line.rstrip()}")
        print()


if __name__ == "__main__":
    asyncio.run(debug())
