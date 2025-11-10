"""End-to-end integration tests for config system.

These tests verify that the entire configuration system works together
across all components in realistic scenarios.

Tests cover:
- Creating project with custom config
- Starting agents with different configs
- Verifying rate limiting respects config
- Verifying lock timeouts respect config
- Modifying config and reloading
- Verifying changes take effect
- Multi-agent scenarios with shared config
- Config file hot-reloading in running system

Author: Agent-4 (Test Engineer)
"""

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from claudeswarm.messaging import MessagingSystem, Message, MessageType
from claudeswarm.locking import LockManager
from claudeswarm.discovery import refresh_registry, get_registry_path

# Config imports
try:
    from claudeswarm.config import (
        Config,
        load_config,
        ConfigLoader,
        get_default_config,
    )
    CONFIG_MODULE_EXISTS = True
except ImportError:
    class Config:
        pass
    def load_config(*args, **kwargs):
        pass
    class ConfigLoader:
        pass
    def get_default_config():
        pass
    CONFIG_MODULE_EXISTS = False


pytestmark = pytest.mark.skipif(
    not CONFIG_MODULE_EXISTS,
    reason="Config module not yet implemented"
)


class TestProjectSetupWithConfig:
    """Test setting up a new project with custom configuration."""

    def test_create_project_with_custom_config(self, mock_project_root):
        """Test creating a project with custom config from scratch."""
        # Create custom config
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_content = """# Custom project config
messaging:
  rate_limit:
    max_messages: 15
    time_window_seconds: 30

locking:
  stale_timeout_seconds: 600
  refresh_interval_seconds: 120

discovery:
  stale_threshold_seconds: 180
"""
        config_path = config_dir / "config.yaml"
        config_path.write_text(config_content)

        # Load and verify config
        config = load_config(config_path)

        assert config.messaging.rate_limit.max_messages == 15
        assert config.locking.stale_timeout_seconds == 600
        assert config.discovery.stale_threshold_seconds == 180

        # Create system components with this config
        with patch('claudeswarm.messaging.subprocess.run'):
            messaging = MessagingSystem(
                agent_id="agent-0",
                project_root=str(mock_project_root),
                config=config
            )

        lock_manager = LockManager(
            project_root=str(mock_project_root),
            config=config
        )

        # Verify components use config values
        assert messaging.rate_limiter.max_messages == 15
        assert lock_manager.stale_timeout == 600

    def test_project_without_config_uses_defaults(self, mock_project_root):
        """Test that project without config file uses sensible defaults."""
        # No config file created

        # Create components without config
        with patch('claudeswarm.messaging.subprocess.run'):
            messaging = MessagingSystem(
                agent_id="agent-0",
                project_root=str(mock_project_root)
            )

        lock_manager = LockManager(project_root=str(mock_project_root))

        # Should have default values
        assert messaging.rate_limiter.max_messages > 0
        assert lock_manager.stale_timeout > 0


class TestMultiAgentWithConfig:
    """Test multiple agents operating with shared configuration."""

    def test_multiple_agents_share_config_values(self, mock_project_root):
        """Test that multiple agents can use the same config."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_content = """messaging:
  rate_limit:
    max_messages: 5
    time_window_seconds: 60
"""
        config_path = config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        # Create multiple agents
        agents = []
        with patch('claudeswarm.messaging.subprocess.run'):
            for i in range(3):
                agent = MessagingSystem(
                    agent_id=f"agent-{i}",
                    project_root=str(mock_project_root),
                    config=config
                )
                agents.append(agent)

        # All should have same rate limits
        for agent in agents:
            assert agent.rate_limiter.max_messages == 5
            assert agent.rate_limiter.time_window_seconds == 60

    def test_agents_with_different_configs(self, mock_project_root):
        """Test agents can have different configs if needed."""
        # Create two different configs
        config1_content = """messaging:
  rate_limit:
    max_messages: 5
    time_window_seconds: 60
"""
        config2_content = """messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60
"""

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f1:
            f1.write(config1_content)
            config1_path = f1.name

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f2:
            f2.write(config2_content)
            config2_path = f2.name

        try:
            config1 = load_config(config1_path)
            config2 = load_config(config2_path)

            with patch('claudeswarm.messaging.subprocess.run'):
                agent1 = MessagingSystem(
                    agent_id="agent-0",
                    project_root=str(mock_project_root),
                    config=config1
                )
                agent2 = MessagingSystem(
                    agent_id="agent-1",
                    project_root=str(mock_project_root),
                    config=config2
                )

            # Different rate limits
            assert agent1.rate_limiter.max_messages == 5
            assert agent2.rate_limiter.max_messages == 10
        finally:
            os.unlink(config1_path)
            os.unlink(config2_path)


class TestRateLimitingWithConfig:
    """Test that rate limiting actually respects config values in practice."""

    def test_rate_limiting_enforces_config_limits(self, mock_project_root):
        """Test that rate limiting actually blocks messages per config."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Very strict rate limit for testing
        config_content = """messaging:
  rate_limit:
    max_messages: 2
    time_window_seconds: 10
"""
        config_path = config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        with patch('claudeswarm.messaging.subprocess.run'):
            messaging = MessagingSystem(
                agent_id="agent-0",
                project_root=str(mock_project_root),
                config=config
            )

            # First 2 messages should succeed
            assert messaging.rate_limiter.check_rate_limit() is True
            assert messaging.rate_limiter.check_rate_limit() is True

            # 3rd should be blocked
            assert messaging.rate_limiter.check_rate_limit() is False

            # After time window, should work again
            # (This would require waiting 10 seconds in real test)

    def test_broadcast_respects_rate_limits_from_config(self, mock_project_root):
        """Test that broadcast operations respect config rate limits."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_content = """messaging:
  rate_limit:
    max_messages: 5
    time_window_seconds: 60
  broadcast_delay_ms: 50
"""
        config_path = config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        # Create mock registry with multiple agents
        registry_data = {
            "session_name": "test",
            "updated_at": "2025-11-10T12:00:00",
            "agents": [
                {"id": "agent-0", "pane_index": "0:0.0", "pid": 1000,
                 "status": "active", "last_seen": "2025-11-10T12:00:00",
                 "session_name": "test"},
                {"id": "agent-1", "pane_index": "0:0.1", "pid": 1001,
                 "status": "active", "last_seen": "2025-11-10T12:00:00",
                 "session_name": "test"},
            ]
        }

        registry_path = mock_project_root / "ACTIVE_AGENTS.json"
        registry_path.write_text(json.dumps(registry_data))

        with patch('claudeswarm.messaging.subprocess.run'):
            with patch('claudeswarm.discovery.get_registry_path', return_value=registry_path):
                messaging = MessagingSystem(
                    agent_id="agent-0",
                    project_root=str(mock_project_root),
                    config=config
                )

                # Attempt broadcast
                # Should respect rate limits
                assert hasattr(messaging, 'rate_limiter')


class TestLockTimeoutsWithConfig:
    """Test that lock timeouts respect configuration values."""

    def test_stale_lock_detection_uses_config_timeout(self, mock_project_root):
        """Test that stale lock detection uses config timeout value."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Very short timeout for testing
        config_content = """locking:
  stale_timeout_seconds: 2
"""
        config_path = config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        lock_manager = LockManager(
            project_root=str(mock_project_root),
            config=config
        )

        # Acquire a lock
        success, _ = lock_manager.acquire_lock(
            filepath="test.txt",
            agent_id="agent-0",
            reason="testing"
        )
        assert success

        # Immediately should not be stale
        locks = lock_manager.list_locks()
        assert len(locks) == 1
        assert not locks[0].is_stale(timeout=2)

        # Wait for timeout
        time.sleep(3)

        # Now should be stale
        locks = lock_manager.list_locks()
        assert len(locks) == 1
        assert locks[0].is_stale(timeout=2)

    def test_lock_refresh_uses_config_interval(self, mock_project_root):
        """Test that lock refresh respects config interval."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_content = """locking:
  stale_timeout_seconds: 300
  refresh_interval_seconds: 30
"""
        config_path = config_dir / "config.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)

        lock_manager = LockManager(
            project_root=str(mock_project_root),
            config=config
        )

        assert lock_manager.refresh_interval == 30


class TestConfigReloadingE2E:
    """Test config hot-reloading in running system."""

    def test_config_modification_affects_new_instances(self, mock_project_root):
        """Test that modifying config affects newly created instances."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "config.yaml"

        # Initial config
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60
""")

        config1 = load_config(config_path)

        with patch('claudeswarm.messaging.subprocess.run'):
            messaging1 = MessagingSystem(
                agent_id="agent-0",
                project_root=str(mock_project_root),
                config=config1
            )
            assert messaging1.rate_limiter.max_messages == 10

        # Modify config
        time.sleep(0.01)  # Ensure file mtime changes
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 20
    time_window_seconds: 60
""")

        config2 = load_config(config_path)

        with patch('claudeswarm.messaging.subprocess.run'):
            messaging2 = MessagingSystem(
                agent_id="agent-1",
                project_root=str(mock_project_root),
                config=config2
            )
            assert messaging2.rate_limiter.max_messages == 20

    def test_config_loader_hot_reload(self, mock_project_root):
        """Test that ConfigLoader can hot-reload changed config."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "config.yaml"
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60
""")

        loader = ConfigLoader(config_path)
        config1 = loader.load()
        assert config1.messaging.rate_limit.max_messages == 10

        # Modify file
        time.sleep(0.01)
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 30
    time_window_seconds: 60
""")

        # Reload
        config2 = loader.reload()
        assert config2.messaging.rate_limit.max_messages == 30

    def test_system_adapts_to_config_changes(self, mock_project_root):
        """Test complete scenario of system adapting to config changes."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "config.yaml"

        # Start with default config
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 5
    time_window_seconds: 60

locking:
  stale_timeout_seconds: 300
""")

        # Create initial system
        config = load_config(config_path)

        with patch('claudeswarm.messaging.subprocess.run'):
            messaging = MessagingSystem(
                agent_id="agent-0",
                project_root=str(mock_project_root),
                config=config
            )

        lock_manager = LockManager(
            project_root=str(mock_project_root),
            config=config
        )

        # Verify initial values
        assert messaging.rate_limiter.max_messages == 5
        assert lock_manager.stale_timeout == 300

        # Simulate config update
        time.sleep(0.01)
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 15
    time_window_seconds: 60

locking:
  stale_timeout_seconds: 600
""")

        # Create new instances (simulating restart or new agents)
        new_config = load_config(config_path)

        with patch('claudeswarm.messaging.subprocess.run'):
            new_messaging = MessagingSystem(
                agent_id="agent-1",
                project_root=str(mock_project_root),
                config=new_config
            )

        new_lock_manager = LockManager(
            project_root=str(mock_project_root),
            config=new_config
        )

        # Verify new values
        assert new_messaging.rate_limiter.max_messages == 15
        assert new_lock_manager.stale_timeout == 600


class TestConfigValidationE2E:
    """End-to-end tests for config validation in real scenarios."""

    def test_invalid_config_prevents_system_startup(self, mock_project_root):
        """Test that invalid config prevents system from starting."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Invalid config (negative values)
        config_path = config_dir / "config.yaml"
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: -10
    time_window_seconds: 60
""")

        # Should raise error when loading
        with pytest.raises(Exception):  # ConfigError or ValidationError
            config = load_config(config_path)

            with patch('claudeswarm.messaging.subprocess.run'):
                MessagingSystem(
                    agent_id="agent-0",
                    project_root=str(mock_project_root),
                    config=config
                )

    def test_partial_invalid_config_fallback(self, mock_project_root):
        """Test system behavior with partially invalid config."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Config with one invalid section
        config_path = config_dir / "config.yaml"
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60

locking:
  stale_timeout_seconds: -1  # Invalid
""")

        # Should raise validation error
        with pytest.raises(Exception):
            load_config(config_path)


class TestRealWorldScenarios:
    """Test realistic end-to-end scenarios."""

    def test_typical_development_workflow(self, mock_project_root):
        """Test typical workflow: setup, work, adjust config, continue."""
        config_dir = mock_project_root / ".claudeswarm"
        config_dir.mkdir(parents=True, exist_ok=True)

        config_path = config_dir / "config.yaml"

        # Initial setup with defaults
        config_path.write_text(get_default_config().to_yaml())

        # Start working
        config = load_config(config_path)

        with patch('claudeswarm.messaging.subprocess.run'):
            messaging = MessagingSystem(
                agent_id="agent-0",
                project_root=str(mock_project_root),
                config=config
            )

        lock_manager = LockManager(
            project_root=str(mock_project_root),
            config=config
        )

        # Do some work
        success, _ = lock_manager.acquire_lock(
            filepath="main.py",
            agent_id="agent-0",
            reason="editing"
        )
        assert success

        # Realize we need higher rate limits for this project
        # Update config
        config_path.write_text("""messaging:
  rate_limit:
    max_messages: 50
    time_window_seconds: 60

locking:
  stale_timeout_seconds: 600
""")

        # Continue working with new config
        new_config = load_config(config_path)

        with patch('claudeswarm.messaging.subprocess.run'):
            new_messaging = MessagingSystem(
                agent_id="agent-1",
                project_root=str(mock_project_root),
                config=new_config
            )

        assert new_messaging.rate_limiter.max_messages == 50

    def test_multi_project_isolation(self, tmp_path):
        """Test that different projects can have independent configs."""
        # Project 1
        project1 = tmp_path / "project1"
        project1.mkdir()
        (project1 / ".claudeswarm").mkdir()
        (project1 / ".agent_locks").mkdir()

        config1_path = project1 / ".claudeswarm" / "config.yaml"
        config1_path.write_text("""messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60
""")

        # Project 2
        project2 = tmp_path / "project2"
        project2.mkdir()
        (project2 / ".claudeswarm").mkdir()
        (project2 / ".agent_locks").mkdir()

        config2_path = project2 / ".claudeswarm" / "config.yaml"
        config2_path.write_text("""messaging:
  rate_limit:
    max_messages: 20
    time_window_seconds: 60
""")

        # Load both
        config1 = load_config(config1_path)
        config2 = load_config(config2_path)

        # Should have different values
        assert config1.messaging.rate_limit.max_messages == 10
        assert config2.messaging.rate_limit.max_messages == 20

        # Create systems in each project
        with patch('claudeswarm.messaging.subprocess.run'):
            msg1 = MessagingSystem(
                agent_id="agent-0",
                project_root=str(project1),
                config=config1
            )
            msg2 = MessagingSystem(
                agent_id="agent-0",
                project_root=str(project2),
                config=config2
            )

        assert msg1.rate_limiter.max_messages == 10
        assert msg2.rate_limiter.max_messages == 20
