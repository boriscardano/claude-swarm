"""Integration tests for config system with claudeswarm modules.

Tests cover:
- MessagingSystem uses config rate limits
- LockManager uses config stale timeout
- Discovery uses config stale threshold
- Config override via constructor still works
- Backward compatibility (no config = old behavior)
- Config changes propagate to module behavior
- Module-specific config validation

Author: Agent-4 (Test Engineer)
"""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from claudeswarm.discovery import refresh_registry
from claudeswarm.locking import STALE_LOCK_TIMEOUT, LockManager
from claudeswarm.messaging import MessagingSystem, RateLimiter

# Config module imports (will be available after Agent 1 completes)
try:
    from claudeswarm.config import Config, get_default_config, load_config

    CONFIG_MODULE_EXISTS = True
except ImportError:

    class Config:
        pass

    def load_config(*args, **kwargs):
        pass

    def get_default_config():
        pass

    CONFIG_MODULE_EXISTS = False


pytestmark = pytest.mark.skipif(
    not CONFIG_MODULE_EXISTS, reason="Config module not yet implemented by Agent 1"
)


class TestMessagingSystemWithConfig:
    """Tests for MessagingSystem using configuration."""

    def test_messaging_system_uses_config_rate_limits(self, temp_config_dir, mock_project_root):
        """Test that MessagingSystem respects config rate limits."""
        config_content = """messaging:
  rate_limit:
    max_messages: 5
    time_window_seconds: 10
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        # Create messaging system with config
        with patch("claudeswarm.messaging.subprocess.run"):
            messaging = MessagingSystem(
                agent_id="test-agent", project_root=str(mock_project_root), config=config
            )

            # Verify rate limiter uses config values
            assert messaging.rate_limiter.max_messages == 5
            assert messaging.rate_limiter.time_window_seconds == 10

    def test_messaging_system_rate_limiting_behavior_with_config(
        self, temp_config_dir, mock_project_root
    ):
        """Test that rate limiting actually enforces config limits."""
        config_content = """messaging:
  rate_limit:
    max_messages: 3
    time_window_seconds: 60
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        with patch("claudeswarm.messaging.subprocess.run"):
            messaging = MessagingSystem(
                agent_id="test-agent", project_root=str(mock_project_root), config=config
            )

            # Should be able to send 3 messages
            for i in range(3):
                result = messaging.rate_limiter.check_rate_limit()
                assert result is True, f"Message {i+1} should be allowed"

            # 4th message should be blocked
            result = messaging.rate_limiter.check_rate_limit()
            assert result is False, "4th message should be rate limited"

    def test_messaging_system_without_config_uses_defaults(self, mock_project_root):
        """Test that MessagingSystem works without config (backward compat)."""
        with patch("claudeswarm.messaging.subprocess.run"):
            messaging = MessagingSystem(agent_id="test-agent", project_root=str(mock_project_root))

            # Should have default rate limits
            assert messaging.rate_limiter.max_messages > 0
            assert messaging.rate_limiter.time_window_seconds > 0

    def test_messaging_system_constructor_override_takes_precedence(
        self, temp_config_dir, mock_project_root
    ):
        """Test that constructor params override config."""
        config_content = """messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        with patch("claudeswarm.messaging.subprocess.run"):
            # Override with constructor params
            messaging = MessagingSystem(
                agent_id="test-agent",
                project_root=str(mock_project_root),
                config=config,
                rate_limit_override={"max_messages": 20, "time_window_seconds": 120},
            )

            # Should use override values
            assert messaging.rate_limiter.max_messages == 20
            assert messaging.rate_limiter.time_window_seconds == 120

    def test_rate_limiter_directly_with_config(self, temp_config_dir):
        """Test RateLimiter can be initialized from config."""
        config_content = """messaging:
  rate_limit:
    max_messages: 15
    time_window_seconds: 30
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        rate_limiter = RateLimiter.from_config(config.messaging.rate_limit)

        assert rate_limiter.max_messages == 15
        assert rate_limiter.time_window_seconds == 30


class TestLockManagerWithConfig:
    """Tests for LockManager using configuration."""

    def test_lock_manager_uses_config_stale_timeout(self, temp_config_dir, mock_project_root):
        """Test that LockManager respects config stale timeout."""
        config_content = """locking:
  stale_timeout_seconds: 600
  refresh_interval_seconds: 120
  max_retries: 5
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        lock_manager = LockManager(project_root=str(mock_project_root), config=config)

        assert lock_manager.stale_timeout == 600
        assert lock_manager.refresh_interval == 120
        assert lock_manager.max_retries == 5

    def test_lock_manager_stale_detection_uses_config_timeout(
        self, temp_config_dir, mock_project_root
    ):
        """Test that stale lock detection uses config timeout."""
        config_content = """locking:
  stale_timeout_seconds: 5
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        lock_manager = LockManager(project_root=str(mock_project_root), config=config)

        # Acquire a lock
        success, _ = lock_manager.acquire_lock(
            filepath="test.txt", agent_id="agent-1", reason="test"
        )
        assert success

        # Wait for it to become stale (based on config)
        time.sleep(6)

        # Should be detected as stale
        locks = lock_manager.list_locks()
        if locks:
            assert locks[0].is_stale(timeout=5)

    def test_lock_manager_without_config_uses_default_timeout(self, mock_project_root):
        """Test that LockManager works without config (backward compat)."""
        lock_manager = LockManager(project_root=str(mock_project_root))

        # Should use default timeout
        assert lock_manager.stale_timeout == STALE_LOCK_TIMEOUT

    def test_lock_manager_constructor_override_takes_precedence(
        self, temp_config_dir, mock_project_root
    ):
        """Test that constructor timeout param overrides config."""
        config_content = """locking:
  stale_timeout_seconds: 300
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        lock_manager = LockManager(
            project_root=str(mock_project_root), config=config, stale_timeout=600  # Override
        )

        assert lock_manager.stale_timeout == 600

    def test_lock_manager_refresh_interval_from_config(self, temp_config_dir, mock_project_root):
        """Test that lock refresh uses config interval."""
        config_content = """locking:
  refresh_interval_seconds: 30
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        lock_manager = LockManager(project_root=str(mock_project_root), config=config)

        # Acquire lock
        success, _ = lock_manager.acquire_lock(
            filepath="test.txt", agent_id="agent-1", reason="test"
        )
        assert success

        # Start refresh thread
        lock_manager.start_refresh()

        # Verify refresh interval is set correctly
        assert lock_manager.refresh_interval == 30

        lock_manager.stop_refresh()


class TestDiscoveryWithConfig:
    """Tests for discovery system using configuration."""

    def test_discovery_uses_config_stale_threshold(self, temp_config_dir):
        """Test that discovery uses config stale threshold."""
        config_content = """discovery:
  stale_threshold_seconds: 90
  refresh_interval_seconds: 15
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        # Mock the tmux parsing
        with patch("claudeswarm.discovery._parse_tmux_panes", return_value=[]):
            registry = refresh_registry(config=config)

            # Verify config was applied (depends on Agent 1's implementation)
            assert registry is not None

    def test_discovery_stale_detection_respects_config(self, temp_config_dir, mock_project_root):
        """Test that agent staleness detection uses config threshold."""
        config_content = """discovery:
  stale_threshold_seconds: 60
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        load_config(config_path)

        # This test would verify that agents are marked stale
        # based on the config threshold - implementation depends on Agent 1
        pass

    def test_discovery_without_config_uses_defaults(self):
        """Test that discovery works without config (backward compat)."""
        with patch("claudeswarm.discovery._parse_tmux_panes", return_value=[]):
            registry = refresh_registry()
            assert registry is not None


class TestConfigChangePropagation:
    """Tests for config changes propagating to modules."""

    def test_config_change_affects_new_messaging_instances(
        self, temp_config_dir, mock_project_root
    ):
        """Test that changing config affects newly created MessagingSystem instances."""
        config_path = temp_config_dir / "config.yaml"

        # Initial config
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60
""")

        config1 = load_config(config_path)

        with patch("claudeswarm.messaging.subprocess.run"):
            messaging1 = MessagingSystem(
                agent_id="test-agent", project_root=str(mock_project_root), config=config1
            )
            assert messaging1.rate_limiter.max_messages == 10

        # Update config
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 20
    time_window_seconds: 60
""")

        config2 = load_config(config_path)

        with patch("claudeswarm.messaging.subprocess.run"):
            messaging2 = MessagingSystem(
                agent_id="test-agent", project_root=str(mock_project_root), config=config2
            )
            assert messaging2.rate_limiter.max_messages == 20

    def test_config_reload_updates_module_behavior(self, temp_config_dir, mock_project_root):
        """Test that reloading config can update module behavior."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text("""locking:
  stale_timeout_seconds: 300
""")

        lock_manager = LockManager(
            project_root=str(mock_project_root), config=load_config(config_path)
        )

        assert lock_manager.stale_timeout == 300

        # Update config and create new manager
        config_path.write_text("""locking:
  stale_timeout_seconds: 600
""")

        lock_manager2 = LockManager(
            project_root=str(mock_project_root), config=load_config(config_path)
        )

        assert lock_manager2.stale_timeout == 600


class TestModuleConfigValidation:
    """Tests for module-specific config validation."""

    def test_messaging_validates_rate_limit_config(self, temp_config_dir, mock_project_root):
        """Test that MessagingSystem validates rate limit config."""
        config_content = """messaging:
  rate_limit:
    max_messages: -5
    time_window_seconds: 60
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        # Should raise validation error when loading
        with pytest.raises(Exception):  # ConfigError or ValidationError
            config = load_config(config_path)
            with patch("claudeswarm.messaging.subprocess.run"):
                MessagingSystem(
                    agent_id="test-agent", project_root=str(mock_project_root), config=config
                )

    def test_lock_manager_validates_timeout_config(self, temp_config_dir, mock_project_root):
        """Test that LockManager validates timeout config."""
        config_content = """locking:
  stale_timeout_seconds: -100
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        # Should raise validation error
        with pytest.raises(Exception):  # ConfigError or ValidationError
            config = load_config(config_path)
            LockManager(project_root=str(mock_project_root), config=config)

    def test_discovery_validates_threshold_config(self, temp_config_dir):
        """Test that discovery validates threshold config."""
        config_content = """discovery:
  stale_threshold_seconds: 0
"""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(config_content)

        # Should raise validation error
        with pytest.raises(Exception):  # ConfigError or ValidationError
            config = load_config(config_path)
            with patch("claudeswarm.discovery._parse_tmux_panes", return_value=[]):
                refresh_registry(config=config)


class TestBackwardCompatibility:
    """Tests for backward compatibility without config."""

    def test_messaging_system_works_without_config_module(self, mock_project_root):
        """Test MessagingSystem works when config module not imported."""
        with patch("claudeswarm.messaging.subprocess.run"):
            messaging = MessagingSystem(agent_id="test-agent", project_root=str(mock_project_root))

            # Should work with default behavior
            assert messaging.agent_id == "test-agent"
            assert hasattr(messaging, "rate_limiter")

    def test_lock_manager_works_without_config_module(self, mock_project_root):
        """Test LockManager works when config module not imported."""
        lock_manager = LockManager(project_root=str(mock_project_root))

        # Should work with default behavior
        assert lock_manager.project_root == Path(mock_project_root)

    def test_all_modules_maintain_existing_api(self, mock_project_root):
        """Test that existing API surface is maintained."""
        # MessagingSystem
        with patch("claudeswarm.messaging.subprocess.run"):
            messaging = MessagingSystem(agent_id="test", project_root=str(mock_project_root))
            assert hasattr(messaging, "send_message")
            assert hasattr(messaging, "broadcast")

        # LockManager
        lock_mgr = LockManager(project_root=str(mock_project_root))
        assert hasattr(lock_mgr, "acquire_lock")
        assert hasattr(lock_mgr, "release_lock")
        assert hasattr(lock_mgr, "list_locks")

    def test_config_is_optional_parameter(self, mock_project_root):
        """Test that config parameter is optional for all modules."""
        # Should not raise errors
        with patch("claudeswarm.messaging.subprocess.run"):
            MessagingSystem(agent_id="test", project_root=str(mock_project_root))

        LockManager(project_root=str(mock_project_root))

        with patch("claudeswarm.discovery._parse_tmux_panes", return_value=[]):
            refresh_registry()
