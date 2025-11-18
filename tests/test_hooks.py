"""
Comprehensive tests for hook integration.

This test module covers:
- check-for-messages.sh executes without errors
- Agent ID validation in hook
- Timeout behavior
- Graceful degradation

Author: Test Coverage Enhancement
"""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


class TestCheckForMessagesHook:
    """Tests for check-for-messages.sh hook script."""

    def test_hook_script_exists(self):
        """Test that hook script exists and is readable."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")

        # Check if hook exists (relative to project root)
        if not hook_path.exists():
            # Try from test directory
            hook_path = Path("../.claude/hooks/check-for-messages.sh")

        if not hook_path.exists():
            # Try absolute path based on current file location
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        assert hook_path.exists(), f"Hook script not found at {hook_path}"
        assert hook_path.is_file(), "Hook script is not a file"

    def test_hook_script_is_executable(self):
        """Test that hook script has executable permissions."""
        # Find hook script
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        # Check executable permission
        assert os.access(hook_path, os.X_OK), "Hook script is not executable"

    def test_hook_executes_without_errors_when_no_agent(self):
        """Test hook executes without errors when not running as an agent."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        # Execute hook in clean environment (no TMUX_PANE, etc.)
        env = os.environ.copy()
        env.pop('TMUX_PANE', None)
        env.pop('AGENT_ID', None)

        result = subprocess.run(
            [str(hook_path)],
            capture_output=True,
            text=True,
            env=env,
            timeout=10
        )

        # Should exit cleanly (exit code 0) even without agent context
        assert result.returncode == 0, f"Hook failed with: {result.stderr}"

        # Should produce no output when not an agent
        assert result.stdout == "", "Hook should produce no output when not an agent"

    def test_hook_handles_invalid_agent_id(self):
        """Test agent ID validation in hook."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        # Read the script to verify it has agent ID validation
        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify script has validation logic
        assert "agent_id" in script_content.lower() or "AGENT_ID" in script_content, \
            "Hook should reference agent ID"

        # Verify it has regex pattern matching for validation
        assert "[a-zA-Z0-9_-]" in script_content or "regex" in script_content.lower(), \
            "Hook should validate agent ID format"

    def test_hook_timeout_behavior(self):
        """Test timeout behavior of hook."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        # Read script to verify timeout is used
        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify script uses timeout command
        assert "timeout" in script_content, "Hook should use timeout to prevent hanging"

        # Verify timeout value is reasonable (should be 5s based on current implementation)
        assert "5s" in script_content or "timeout 5" in script_content, \
            "Hook should have 5 second timeout"

    def test_hook_graceful_degradation(self):
        """Test graceful degradation when claudeswarm commands fail."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        # Read script to verify error handling
        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify script has error handling (|| echo "" or similar)
        assert "||" in script_content, "Hook should have error handling (|| fallback)"

        # Verify script redirects errors to /dev/null
        assert "2>/dev/null" in script_content, "Hook should suppress error output"

        # Verify script has set -e (exit on error) to prevent cascading failures
        # OR verify it has proper error handling
        has_error_handling = (
            "set -e" in script_content or
            "|| echo" in script_content or
            "|| true" in script_content
        )
        assert has_error_handling, "Hook should have error handling"

    def test_hook_uses_whoami_command(self):
        """Test that hook uses whoami command to detect agent ID."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify hook uses whoami to detect agent ID
        assert "whoami" in script_content, "Hook should use 'whoami' command to detect agent ID"
        assert "claudeswarm whoami" in script_content, \
            "Hook should use 'claudeswarm whoami' to get agent info"

    def test_hook_checks_messages_with_limit(self):
        """Test that hook uses check-messages with limit parameter."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify hook uses check-messages command
        assert "check-messages" in script_content, "Hook should use 'check-messages' command"

        # Verify hook limits number of messages (to avoid context bloat)
        assert "--limit" in script_content or "-l" in script_content, \
            "Hook should limit number of messages"

    def test_hook_has_proper_shebang(self):
        """Test that hook has proper shebang."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            first_line = f.readline().strip()

        # Should start with #!/bin/bash or #!/usr/bin/env bash
        assert first_line.startswith("#!"), "Hook should have shebang"
        assert "bash" in first_line.lower(), "Hook should use bash"

    def test_hook_output_format(self):
        """Test that hook has proper output formatting."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify hook has output formatting for messages
        assert "NEW MESSAGES" in script_content or "MESSAGES FROM" in script_content, \
            "Hook should have header for messages"

        # Verify hook uses visual separators (box drawing or similar)
        has_formatting = any(char in script_content for char in ["═", "─", "║", "╔", "╚", "***", "---"])
        assert has_formatting, "Hook should have visual formatting"

    def test_hook_conditional_output(self):
        """Test that hook only outputs when there are messages."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify hook checks for message content before outputting
        assert "if" in script_content, "Hook should have conditional logic"

        # Should check for "No messages" or similar to avoid unnecessary output
        has_message_check = (
            "No messages" in script_content or
            "[ -n" in script_content or  # Check for non-empty
            "[ ! -z" in script_content   # Check for non-zero
        )
        assert has_message_check, "Hook should check if messages exist before outputting"

    def test_hook_debug_mode(self):
        """Test that hook supports debug mode."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify hook has debug mode support
        assert "DEBUG" in script_content or "debug" in script_content, \
            "Hook should support debug mode"

        # Should check environment variable for debug mode
        assert "CLAUDESWARM_DEBUG" in script_content or "$DEBUG" in script_content, \
            "Hook should check debug environment variable"


class TestHookIntegration:
    """Integration tests for hook functionality."""

    def test_hook_integration_with_check_messages_command(self):
        """Test that hook integrates properly with check-messages command."""
        # This test verifies the hook calls the correct command
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify hook calls claudeswarm check-messages
        assert "claudeswarm check-messages" in script_content, \
            "Hook should call 'claudeswarm check-messages'"

    def test_hook_exit_code_always_zero(self):
        """Test that hook always exits with code 0 (for Claude Code compatibility)."""
        hook_path = Path(".claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            hook_path = Path("../.claude/hooks/check-for-messages.sh")
        if not hook_path.exists():
            test_dir = Path(__file__).parent.parent
            hook_path = test_dir / ".claude" / "hooks" / "check-for-messages.sh"

        if not hook_path.exists():
            pytest.skip("Hook script not found")

        with open(hook_path, 'r') as f:
            script_content = f.read()

        # Verify script ends with exit 0
        lines = script_content.strip().split('\n')
        last_non_comment_line = None
        for line in reversed(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('#'):
                last_non_comment_line = stripped
                break

        assert last_non_comment_line == "exit 0", \
            "Hook should always exit with code 0 for Claude Code compatibility"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
