#!/usr/bin/env python3
"""Get Claude Code credentials from macOS Keychain for E2B deployment."""
import subprocess
import json
import sys


def get_claude_credentials():
    """
    Extract Claude Code OAuth credentials from macOS Keychain.

    On macOS, Claude Code stores credentials in Keychain, not in files.
    We need to extract them to transfer to E2B sandbox.
    """
    print("🔍 Searching for Claude Code credentials in macOS Keychain...")

    try:
        # Try to find Claude Code OAuth entries in Keychain
        result = subprocess.run(
            ['security', 'find-generic-password', '-s', 'claude-code', '-w'],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            password = result.stdout.strip()
            print(f"✓ Found Claude Code credentials (length: {len(password)} chars)")
            return password
        else:
            print("❌ No Claude Code credentials found in Keychain")
            print("\nTo get credentials:")
            print("1. Run 'claude' locally and login")
            print("2. Run this script again")
            return None

    except Exception as e:
        print(f"❌ Error accessing Keychain: {e}")
        print("\nAlternative: You may need to manually export credentials")
        return None


if __name__ == "__main__":
    creds = get_claude_credentials()
    if creds:
        print("\n✅ Credentials retrieved successfully")
        print("These can be used for E2B deployment")
    else:
        print("\n⚠️  Could not retrieve credentials")
        sys.exit(1)
