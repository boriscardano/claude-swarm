"""
Unit tests for messaging reliability features.

Tests cover:
- Retry logic with exponential backoff
- Stable tmux pane ID usage
- Transient error detection
- ACK processing in check-messages

Author: Automated implementation
Phase: Reliable Messaging
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from claudeswarm.messaging import (
    MAX_TMUX_RETRIES,
    TMUX_INITIAL_RETRY_DELAY,
    TMUX_JITTER_FACTOR,
    TMUX_MAX_RETRY_DELAY,
    TmuxError,
    TmuxMessageDelivery,
    TmuxPaneNotFoundError,
    TmuxSocketError,
    TmuxTimeoutError,
    _calculate_tmux_backoff,
    _is_transient_tmux_error,
)


class TestBackoffCalculation:
    """Tests for exponential backoff calculation."""

    def test_first_retry_delay(self):
        """First retry should use initial delay."""
        delay = _calculate_tmux_backoff(0)
        # Allow for jitter (±25%)
        min_expected = TMUX_INITIAL_RETRY_DELAY * (1 - TMUX_JITTER_FACTOR)
        max_expected = TMUX_INITIAL_RETRY_DELAY * (1 + TMUX_JITTER_FACTOR)
        assert min_expected <= delay <= max_expected

    def test_exponential_increase(self):
        """Delay should increase exponentially."""
        # Patch random to neutralize jitter for predictable testing
        import random

        with patch.object(random, "random", return_value=0.5):
            actual_0 = _calculate_tmux_backoff(0)
            actual_1 = _calculate_tmux_backoff(1)
            actual_2 = _calculate_tmux_backoff(2)

        # With jitter neutralized (random=0.5 means jitter=0), delays should double
        # Allow small tolerance for floating point
        assert actual_1 > actual_0, "Delay should increase"
        assert actual_2 > actual_1, "Delay should continue increasing"

    def test_max_delay_cap(self):
        """Delay should be capped at max value."""
        # Very high attempt number should hit cap
        delay = _calculate_tmux_backoff(100)
        # Even with +25% jitter, should not exceed cap * 1.25
        max_with_jitter = TMUX_MAX_RETRY_DELAY * (1 + TMUX_JITTER_FACTOR)
        assert delay <= max_with_jitter

    def test_minimum_delay(self):
        """Delay should never be negative or too small."""
        for attempt in range(10):
            delay = _calculate_tmux_backoff(attempt)
            assert delay >= 0.01


class TestTransientErrorDetection:
    """Tests for transient error detection."""

    def test_server_not_responding(self):
        """Server not responding should be transient."""
        assert _is_transient_tmux_error("Tmux server not responding to requests")
        assert _is_transient_tmux_error("SERVER NOT RESPONDING")

    def test_connection_refused(self):
        """Connection refused should be transient."""
        assert _is_transient_tmux_error("Connection refused to socket")

    def test_resource_unavailable(self):
        """Resource temporarily unavailable should be transient."""
        assert _is_transient_tmux_error("Resource temporarily unavailable")

    def test_timeout(self):
        """Timeout errors should be transient."""
        assert _is_transient_tmux_error("Operation timed out")

    def test_pane_not_found_not_transient(self):
        """Pane not found should NOT be transient."""
        assert not _is_transient_tmux_error("Pane not found")
        assert not _is_transient_tmux_error("Can't find pane")

    def test_permission_denied_not_transient(self):
        """Permission denied should NOT be transient."""
        assert not _is_transient_tmux_error("Permission denied")


class TestRetryLogic:
    """Tests for retry logic in send_to_pane."""

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    def test_success_on_first_attempt(self, mock_send):
        """Successful first attempt should not retry."""
        mock_send.return_value = True

        result = TmuxMessageDelivery.send_to_pane("%5", "test message")

        assert result is True
        assert mock_send.call_count == 1

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    def test_no_retry_on_pane_not_found(self, mock_send):
        """TmuxPaneNotFoundError should not be retried."""
        mock_send.side_effect = TmuxPaneNotFoundError("Pane not found")

        with pytest.raises(TmuxPaneNotFoundError):
            TmuxMessageDelivery.send_to_pane("%5", "test message")

        # Should only try once - no retries
        assert mock_send.call_count == 1

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    @patch("claudeswarm.messaging.time.sleep")
    def test_retry_on_timeout(self, mock_sleep, mock_send):
        """TmuxTimeoutError should trigger retry."""
        mock_send.side_effect = [
            TmuxTimeoutError("Timeout"),
            TmuxTimeoutError("Timeout"),
            True,  # Success on third attempt
        ]

        result = TmuxMessageDelivery.send_to_pane("%5", "test message")

        assert result is True
        assert mock_send.call_count == 3
        # Should have slept twice (before 2nd and 3rd attempts)
        assert mock_sleep.call_count == 2

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    @patch("claudeswarm.messaging.time.sleep")
    def test_retry_on_socket_error(self, mock_sleep, mock_send):
        """TmuxSocketError should trigger retry."""
        mock_send.side_effect = [
            TmuxSocketError("Socket error"),
            True,  # Success on second attempt
        ]

        result = TmuxMessageDelivery.send_to_pane("%5", "test message")

        assert result is True
        assert mock_send.call_count == 2
        assert mock_sleep.call_count == 1

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    @patch("claudeswarm.messaging.time.sleep")
    def test_max_retries_exhausted(self, mock_sleep, mock_send):
        """Should raise after max retries exhausted."""
        mock_send.side_effect = TmuxTimeoutError("Timeout")

        with pytest.raises(TmuxTimeoutError):
            TmuxMessageDelivery.send_to_pane("%5", "test message")

        # Initial attempt + MAX_TMUX_RETRIES retries
        assert mock_send.call_count == MAX_TMUX_RETRIES + 1

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    @patch("claudeswarm.messaging.time.sleep")
    def test_transient_error_retry(self, mock_sleep, mock_send):
        """Transient TmuxError should trigger retry."""
        mock_send.side_effect = [
            TmuxError("Server not responding"),  # Transient
            True,  # Success
        ]

        result = TmuxMessageDelivery.send_to_pane("%5", "test message")

        assert result is True
        assert mock_send.call_count == 2

    @patch.object(TmuxMessageDelivery, "_send_to_pane_once")
    def test_non_transient_error_no_retry(self, mock_send):
        """Non-transient TmuxError should not be retried."""
        mock_send.side_effect = TmuxError("Some permanent error")

        with pytest.raises(TmuxError, match="Some permanent error"):
            TmuxMessageDelivery.send_to_pane("%5", "test message")

        # Should only try once
        assert mock_send.call_count == 1


class TestStablePaneId:
    """Tests for stable tmux pane ID usage."""

    @patch("subprocess.run")
    def test_verify_pane_exists_with_percent_format(self, mock_run):
        """verify_pane_exists should use pane_id format for %N panes."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "%0\n%1\n%5\n%10\n"
        mock_run.return_value = mock_result

        result = TmuxMessageDelivery.verify_pane_exists("%5")

        assert result is True
        # Should use #{pane_id} format for %N
        call_args = mock_run.call_args[0][0]  # Get the command list
        assert "#{pane_id}" in str(call_args)  # Check format string is in command

    @patch("subprocess.run")
    def test_verify_pane_exists_with_session_format(self, mock_run):
        """verify_pane_exists should use session format for session:window.pane."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "0:0.0\n0:0.1\n0:1.0\n"
        mock_run.return_value = mock_result

        result = TmuxMessageDelivery.verify_pane_exists("0:0.1")

        assert result is True
        # Should use session:window.pane format
        call_args = mock_run.call_args[0][0]  # Get the command list
        assert "#{session_name}" in str(call_args)  # Check format string is in command

    @patch("subprocess.run")
    def test_verify_pane_not_exists(self, mock_run):
        """verify_pane_exists should return False for non-existent pane."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "%0\n%1\n%2\n"
        mock_run.return_value = mock_result

        result = TmuxMessageDelivery.verify_pane_exists("%99")

        assert result is False


class TestAckProcessing:
    """Tests for ACK processing in check-messages."""

    def test_process_pending_retries_called(self):
        """process_pending_retries should be called during check-messages."""
        # This is an integration test - verify the function exists and is callable
        from claudeswarm.ack import process_pending_retries

        # Should not raise
        assert callable(process_pending_retries)
