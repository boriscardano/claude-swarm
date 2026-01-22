#!/usr/bin/env python3
"""Add OAuth token to current sandbox manually."""
import asyncio
import os
from e2b_code_interpreter import Sandbox


async def fix_sandbox():
    """Add OAuth token to the current sandbox."""
    # Get token from local environment
    token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        print("❌ CLAUDE_CODE_OAUTH_TOKEN not found in local environment!")
        print("   Run: source ~/.zshrc")
        return

    print(f"✓ Found OAuth token (length: {len(token)} chars)")

    # Get current sandbox ID
    cache_file = os.path.expanduser("~/.claudeswarm/last_sandbox_id")
    with open(cache_file) as f:
        sandbox_id = f.read().strip()

    print(f"\n🔌 Connecting to sandbox: {sandbox_id}")
    sandbox = await asyncio.to_thread(Sandbox.connect, sandbox_id)
    print("✓ Connected!\n")

    # Escape the token for shell
    escaped_token = token.replace("'", "'\\''")
    export_cmd = f"export CLAUDE_CODE_OAUTH_TOKEN='{escaped_token}'"

    commands = [
        # Add token to /home/user/.bashrc (user's shell)
        (f"echo '{export_cmd}' >> /home/user/.bashrc", "Add to user .bashrc"),
        # Add token to /home/user/.bash_profile
        (f"echo '{export_cmd}' >> /home/user/.bash_profile", "Add to user .bash_profile"),
        # Add token to /home/user/.profile
        (f"echo '{export_cmd}' >> /home/user/.profile", "Add to user .profile"),
        # Also add to root (for root shells)
        (f"echo '{export_cmd}' >> /root/.bashrc", "Add to root .bashrc"),
        (f"echo '{export_cmd}' >> /root/.bash_profile", "Add to root .bash_profile"),
        # Create config files
        ("mkdir -p /home/user/.claude", "Create user .claude dir"),
        ("mkdir -p /home/user/.config/claude-code", "Create user config dir"),
        ('echo \'{"hasCompletedOnboarding": true}\' > /home/user/.claude.json', "Create user .claude.json"),
        ('echo \'{"hasCompletedOnboarding": true}\' > /home/user/.config/claude-code/config.json', "Create user config.json"),
        # Also for root
        ("mkdir -p /root/.claude", "Create root .claude dir"),
        ('echo \'{"hasCompletedOnboarding": true}\' > /root/.claude.json', "Create root .claude.json"),
    ]

    for cmd, desc in commands:
        print(f"📝 {desc}...")
        result = await asyncio.to_thread(sandbox.run_code, f"!{cmd}")
        if result.error:
            print(f"   ⚠️  Error: {result.error}")
        else:
            print(f"   ✓ Done")

    # Verify
    print("\n🔍 Verifying configuration...")
    verify_result = await asyncio.to_thread(
        sandbox.run_code,
        "!su - user -c 'source ~/.bashrc && env | grep CLAUDE_CODE_OAUTH_TOKEN | head -c 80'"
    )
    if hasattr(verify_result, 'logs') and verify_result.logs and verify_result.logs.stdout:
        for line in verify_result.logs.stdout:
            print(f"   ✓ Token in user environment: {line.rstrip()}...")
    else:
        print("   ⚠️  Token not found in user environment")

    print("\n✅ Sandbox configuration complete!")
    print(f"   Sandbox ID: {sandbox_id}")
    print("\nNow connect with: claudeswarm cloud shell")
    print("Then run: claude")


if __name__ == "__main__":
    asyncio.run(fix_sandbox())
