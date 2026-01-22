#!/usr/bin/env python3
"""Add ANTHROPIC_AUTH_TOKEN to sandbox."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def add_auth_token():
    """Add ANTHROPIC_AUTH_TOKEN as alternative."""
    token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        print("❌ Token not found")
        return

    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"Connecting to sandbox: {sandbox_id}")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("Connected!\n")

    escaped_token = token.replace("'", "'\\''")

    # Try ANTHROPIC_AUTH_TOKEN instead
    commands = [
        f"echo 'export ANTHROPIC_AUTH_TOKEN=\"{escaped_token}\"' >> /home/user/.bashrc",
        f"echo 'export ANTHROPIC_AUTH_TOKEN=\"{escaped_token}\"' >> /home/user/.bash_profile",
        f"echo 'export ANTHROPIC_AUTH_TOKEN=\"{escaped_token}\"' >> /root/.bashrc",
    ]

    for cmd in commands:
        print(f"Running: {cmd[:80]}...")
        result = await asyncio.to_thread(sandbox.run_code, f"!{cmd}")
        if result.error:
            print(f"  Error: {result.error}")
        else:
            print("  ✓ Done")

    # Verify
    print("\nVerifying:")
    result = await asyncio.to_thread(
        sandbox.run_code,
        "!su - user -c 'source ~/.bashrc && env | grep ANTHROPIC_AUTH_TOKEN | head -c 80'"
    )
    if hasattr(result, 'logs') and result.logs and result.logs.stdout:
        for line in result.logs.stdout:
            print(f"  {line.rstrip()}...")

    print("\n✅ Try running claude again!")


if __name__ == "__main__":
    asyncio.run(add_auth_token())
