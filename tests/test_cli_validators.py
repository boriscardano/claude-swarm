"""Tests for CLI validators and helper functions."""

import argparse
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claudeswarm.cli import _get_safe_editor, _require_agent_id, positive_int


class TestPositiveInt:
    """Tests for positive_int type validator."""

    def test_valid_positive_integer(self):
        """Test valid positive integer."""
        assert positive_int("1") == 1
        assert positive_int("100") == 100
        assert positive_int("999999") == 999999

    def test_zero_raises_error(self):
        """Test that zero raises an error."""
        with pytest.raises(argparse.ArgumentTypeError, match="must be a positive integer"):
            positive_int("0")

    def test_negative_raises_error(self):
        """Test that negative numbers raise an error."""
        with pytest.raises(argparse.ArgumentTypeError, match="must be a positive integer"):
            positive_int("-1")
        with pytest.raises(argparse.ArgumentTypeError, match="must be a positive integer"):
            positive_int("-100")

    def test_invalid_string_raises_error(self):
        """Test that non-numeric strings raise an error."""
        with pytest.raises(argparse.ArgumentTypeError, match="not a valid integer"):
            positive_int("abc")
        with pytest.raises(argparse.ArgumentTypeError, match="not a valid integer"):
            positive_int("1.5")
        with pytest.raises(argparse.ArgumentTypeError, match="not a valid integer"):
            positive_int("")


class TestRequireAgentId:
    """Tests for _require_agent_id helper function."""

    def test_explicit_agent_id(self):
        """Test with explicitly provided agent ID."""
        args = argparse.Namespace(agent_id="test-agent")
        result = _require_agent_id(args)
        assert result == "test-agent"

    def test_auto_detect_success(self):
        """Test auto-detection when agent is found."""
        args = argparse.Namespace(agent_id=None)

        with patch("claudeswarm.cli._detect_current_agent") as mock_detect:
            mock_detect.return_value = ("detected-agent", {"id": "detected-agent"})
            result = _require_agent_id(args)
            assert result == "detected-agent"

    def test_auto_detect_failure(self):
        """Test auto-detection when agent is not found."""
        args = argparse.Namespace(agent_id=None)

        with patch("claudeswarm.cli._detect_current_agent") as mock_detect:
            mock_detect.return_value = (None, None)

            with pytest.raises(SystemExit) as exc_info:
                _require_agent_id(args)

            assert exc_info.value.code == 1

    def test_custom_arg_name(self):
        """Test with custom argument name."""
        args = argparse.Namespace(sender_id="custom-agent")
        result = _require_agent_id(args, arg_name="sender_id")
        assert result == "custom-agent"

    def test_validation_error(self):
        """Test that validation errors are caught."""
        args = argparse.Namespace(agent_id="invalid agent with spaces!")

        with pytest.raises(SystemExit) as exc_info:
            _require_agent_id(args)

        assert exc_info.value.code == 1


class TestGetSafeEditor:
    """Tests for _get_safe_editor function."""

    def test_valid_editor_in_path(self):
        """Test with valid EDITOR in PATH."""
        with patch.dict(os.environ, {"EDITOR": "vim"}, clear=False):
            with patch("shutil.which") as mock_which:
                mock_which.return_value = "/usr/bin/vim"
                with patch("os.access") as mock_access:
                    mock_access.return_value = True

                    result = _get_safe_editor()
                    assert result == "/usr/bin/vim"

    def test_editor_with_metacharacters_rejected(self):
        """Test that EDITOR with shell metacharacters is rejected."""
        dangerous_editors = [
            "vim; rm -rf /",
            "vim && malicious",
            "vim | cat /etc/passwd",
            "vim `whoami`",
            "vim $USER",
            'vim "test"',
        ]

        for dangerous in dangerous_editors:
            with patch.dict(os.environ, {"EDITOR": dangerous}, clear=False):
                with patch("shutil.which") as mock_which:
                    mock_which.return_value = "vim"

                    result = _get_safe_editor()
                    # Should fallback to safe editor, not use the dangerous one
                    assert result != dangerous

    def test_editor_not_in_path(self):
        """Test with EDITOR not in PATH."""
        with patch.dict(os.environ, {"EDITOR": "nonexistent-editor"}, clear=False):
            with patch("shutil.which") as mock_which:
                # First call for the invalid editor returns None
                # Subsequent calls for fallbacks return valid paths
                def which_side_effect(cmd):
                    if cmd == "nonexistent-editor":
                        return None
                    elif cmd == "vim":
                        return "/usr/bin/vim"
                    return None

                mock_which.side_effect = which_side_effect

                with patch("os.access") as mock_access:
                    mock_access.return_value = True

                    result = _get_safe_editor()
                    # Should fallback to vim
                    assert result == "vim"

    def test_editor_not_executable(self):
        """Test with EDITOR that exists but is not executable."""
        with patch.dict(os.environ, {"EDITOR": "vim"}, clear=False):
            with patch("shutil.which") as mock_which:

                def which_side_effect(cmd):
                    if cmd == "vim":
                        return "/usr/bin/vim"
                    elif cmd == "vi":
                        return "/usr/bin/vi"
                    return None

                mock_which.side_effect = which_side_effect

                with patch("os.access") as mock_access:

                    def access_side_effect(path, mode):
                        # vim is not executable, vi is
                        if path == "/usr/bin/vim":
                            return False
                        elif path == "/usr/bin/vi":
                            return True
                        return False

                    mock_access.side_effect = access_side_effect

                    result = _get_safe_editor()
                    # Should fallback to vi
                    assert result == "vi"

    def test_no_editor_found(self):
        """Test when no editor is found."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("shutil.which") as mock_which:
                mock_which.return_value = None

                result = _get_safe_editor()
                assert result is None

    def test_fallback_to_default_editors(self):
        """Test fallback to default editors when EDITOR is not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("shutil.which") as mock_which:

                def which_side_effect(cmd):
                    # Only nano is available
                    if cmd == "nano":
                        return "/usr/bin/nano"
                    return None

                mock_which.side_effect = which_side_effect

                with patch("os.access") as mock_access:
                    mock_access.return_value = True

                    result = _get_safe_editor()
                    assert result == "nano"
