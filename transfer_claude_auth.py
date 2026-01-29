#!/usr/bin/env python3
"""Transfer Claude Code authentication from local to E2B sandbox."""
import asyncio
import os
import json
import base64
from pathlib import Path
from e2b_code_interpreter import Sandbox


async def transfer_auth():
    """Transfer local Claude Code auth to E2B sandbox."""
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"📦 Transferring Claude Code authentication to sandbox: {sandbox_id}\n")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("✓ Connected to sandbox\n")

    # Get local Claude directory
    claude_dir = Path.home() / ".claude"

    # Files/directories to transfer
    items_to_transfer = [
        "settings.json",
        "settings.local.json",
        "statsig",  # This directory contains authentication cache
    ]

    for item in items_to_transfer:
        local_path = claude_dir / item
        if not local_path.exists():
            print(f"⚠️  Skipping {item} (not found locally)")
            continue

        if local_path.is_file():
            # Read and transfer file
            print(f"📤 Transferring {item}...")
            with open(local_path, 'r') as f:
                content = f.read()

            # Write to sandbox (both root and user)
            for user_home in ["/root", "/home/user"]:
                remote_path = f"{user_home}/.claude/{item}"
                # Escape single quotes in content for shell
                escaped_content = content.replace("'", "'\\''")
                result = await asyncio.to_thread(
                    sandbox.run_code,
                    f"!mkdir -p {user_home}/.claude && echo '{escaped_content}' > {remote_path}"
                )
                if result.error:
                    print(f"  ❌ Error writing to {remote_path}: {result.error}")
                else:
                    print(f"  ✓ Wrote to {remote_path}")

        elif local_path.is_dir():
            # Transfer directory recursively
            print(f"📂 Transferring directory {item}/...")
            for file_path in local_path.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(claude_dir)
                    print(f"  📤 {rel_path}")

                    with open(file_path, 'r') as f:
                        content = f.read()

                    for user_home in ["/root", "/home/user"]:
                        remote_path = f"{user_home}/.claude/{rel_path}"
                        remote_dir = os.path.dirname(remote_path)
                        escaped_content = content.replace("'", "'\\''")

                        result = await asyncio.to_thread(
                            sandbox.run_code,
                            f"!mkdir -p {remote_dir} && echo '{escaped_content}' > {remote_path}"
                        )
                        if result.error:
                            print(f"    ❌ Error: {result.error}")

    # Fix ownership for user
    print("\n🔧 Fixing file ownership...")
    result = await asyncio.to_thread(
        sandbox.run_code,
        "!chown -R user:user /home/user/.claude"
    )
    if result.error:
        print(f"❌ Error fixing ownership: {result.error}")
    else:
        print("✓ Ownership fixed")

    print("\n✅ Authentication transfer complete!")
    print("\nNow try running: claudeswarm cloud monitor")
    print("Then in a pane, run: claude --print 'Hello from E2B!'")


if __name__ == "__main__":
    asyncio.run(transfer_auth())
