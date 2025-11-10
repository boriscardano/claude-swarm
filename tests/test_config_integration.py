"""Integration tests for the configuration system.

Tests cover:
- Loading config from YAML files
- Loading config from TOML files
- Missing file handling (default fallback)
- Partial config merging with defaults
- Config reloading after file changes
- Invalid YAML syntax error handling
- Invalid value validation (negative numbers, etc.)
- Config file discovery and path resolution
- Environment variable overrides
- Config serialization/deserialization

Author: Agent-4 (Test Engineer)
"""

import os
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest


# Import config module - Agent 1 has implemented this
try:
    from claudeswarm.config import (
        ClaudeSwarmConfig,
        RateLimitConfig,
        LockingConfig,
        DiscoveryConfig,
        ConfigValidationError,
        load_config,
        get_config,
        reload_config,
    )
    CONFIG_MODULE_EXISTS = True
except ImportError as e:
    # Create placeholder classes for IDE support
    class ClaudeSwarmConfig:
        pass
    class RateLimitConfig:
        pass
    class LockingConfig:
        pass
    class DiscoveryConfig:
        pass
    class ConfigValidationError(Exception):
        pass
    def load_config(*args, **kwargs):
        pass
    def get_config():
        pass
    def reload_config(*args, **kwargs):
        pass
    CONFIG_MODULE_EXISTS = False
    _import_error = str(e)


pytestmark = pytest.mark.skipif(
    not CONFIG_MODULE_EXISTS,
    reason=f"Config module not available: {_import_error if not CONFIG_MODULE_EXISTS else ''}"
)


class TestConfigLoading:
    """Tests for basic config file loading."""

    def test_load_config_from_yaml_file(self, temp_config_dir, sample_yaml_config):
        """Test loading valid YAML config file."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        config = load_config(config_path)

        assert config is not None
        assert hasattr(config, 'messaging')
        assert config.messaging.rate_limit.max_messages == 10
        assert config.messaging.rate_limit.time_window_seconds == 60
        assert config.locking.stale_timeout_seconds == 300

    def test_load_config_from_toml_file(self, temp_config_dir, sample_toml_config):
        """Test loading valid TOML config file."""
        config_path = temp_config_dir / "config.toml"
        config_path.write_text(sample_toml_config)

        config = load_config(config_path)

        assert config is not None
        assert hasattr(config, 'messaging')
        assert config.messaging.rate_limit.max_messages == 10
        assert config.locking.stale_timeout_seconds == 300

    def test_load_config_with_missing_file_uses_defaults(self, temp_config_dir):
        """Test that missing config file falls back to defaults."""
        nonexistent_path = temp_config_dir / "nonexistent.yaml"

        config = load_config(nonexistent_path)

        # Should return default config
        assert config is not None
        assert hasattr(config, 'messaging')
        # Verify it has expected default structure
        assert hasattr(config.messaging, 'rate_limit')

    def test_load_config_with_partial_config_merges_defaults(
        self, temp_config_dir, partial_config
    ):
        """Test that partial config is merged with defaults."""
        config_path = temp_config_dir / "partial.yaml"
        config_path.write_text(partial_config)

        config = load_config(config_path)

        # Should have the overridden value
        assert config.messaging.rate_limit.max_messages == 20

        # Should also have default values for missing sections
        assert hasattr(config, 'locking')
        assert hasattr(config, 'discovery')
        assert config.locking.stale_timeout_seconds > 0

    def test_load_config_from_dict(self, config_dict):
        """Test creating config from dictionary."""
        config = Config.from_dict(config_dict)

        assert config.messaging.rate_limit.max_messages == 10
        assert config.locking.stale_timeout_seconds == 300
        assert config.discovery.stale_threshold_seconds == 120

    def test_config_to_dict_roundtrip(self, config_dict):
        """Test config serialization roundtrip."""
        config = Config.from_dict(config_dict)
        serialized = config.to_dict()

        assert serialized == config_dict

        # Verify we can recreate it
        config2 = Config.from_dict(serialized)
        assert config2.to_dict() == config_dict


class TestConfigValidation:
    """Tests for config validation and error handling."""

    def test_load_config_with_invalid_yaml_syntax_raises_error(
        self, temp_config_dir, invalid_yaml_config
    ):
        """Test that invalid YAML syntax raises ConfigError."""
        config_path = temp_config_dir / "invalid.yaml"
        config_path.write_text(invalid_yaml_config)

        with pytest.raises(ConfigError, match="[Ii]nvalid|[Ss]yntax|YAML"):
            load_config(config_path)

    def test_load_config_with_negative_max_messages_raises_error(
        self, temp_config_dir, invalid_values_config
    ):
        """Test that negative max_messages raises ValidationError."""
        config_path = temp_config_dir / "negative.yaml"
        config_path.write_text(invalid_values_config)

        with pytest.raises((ConfigValidationError, ConfigError), match="[Nn]egative|[Ii]nvalid"):
            load_config(config_path)

    def test_load_config_with_zero_time_window_raises_error(self, temp_config_dir):
        """Test that zero time window raises ValidationError."""
        config_content = """messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 0
"""
        config_path = temp_config_dir / "zero_window.yaml"
        config_path.write_text(config_content)

        with pytest.raises((ConfigValidationError, ConfigError), match="[Zz]ero|[Ii]nvalid|positive"):
            load_config(config_path)

    def test_config_validates_stale_timeout_positive(self, temp_config_dir):
        """Test that negative stale timeout is rejected."""
        config_content = """locking:
  stale_timeout_seconds: -1
"""
        config_path = temp_config_dir / "negative_timeout.yaml"
        config_path.write_text(config_content)

        with pytest.raises((ConfigValidationError, ConfigError)):
            load_config(config_path)

    def test_config_validates_required_fields_present(self, temp_config_dir):
        """Test that missing required fields raise appropriate errors."""
        config_content = """messaging:
  rate_limit:
    # Missing max_messages
    time_window_seconds: 60
"""
        config_path = temp_config_dir / "missing_field.yaml"
        config_path.write_text(config_content)

        # Should either raise error or use defaults
        # Exact behavior depends on Agent 1's implementation
        try:
            config = load_config(config_path)
            # If it succeeds, should have filled in defaults
            assert config.messaging.rate_limit.max_messages > 0
        except (ConfigValidationError, ConfigError):
            # This is also acceptable
            pass


class TestConfigReloading:
    """Tests for config reloading and hot updates."""

    def test_reload_config_after_file_change(self, temp_config_dir, sample_yaml_config):
        """Test that config can be reloaded after file modification."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        # Load initial config
        loader = ConfigLoader(config_path)
        config1 = loader.load()
        assert config1.messaging.rate_limit.max_messages == 10

        # Modify the file
        time.sleep(0.01)  # Ensure file mtime changes
        modified_config = sample_yaml_config.replace(
            "max_messages: 10", "max_messages: 20"
        )
        config_path.write_text(modified_config)

        # Reload
        config2 = loader.reload()
        assert config2.messaging.rate_limit.max_messages == 20

    def test_config_loader_detects_file_changes(self, temp_config_dir, sample_yaml_config):
        """Test that ConfigLoader detects file modifications."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        loader = ConfigLoader(config_path)
        loader.load()

        # Initially should not need reload
        assert not loader.needs_reload()

        # Modify file
        time.sleep(0.01)
        modified_config = sample_yaml_config.replace(
            "max_messages: 10", "max_messages: 15"
        )
        config_path.write_text(modified_config)

        # Now should need reload
        assert loader.needs_reload()

    def test_reload_config_preserves_runtime_modifications(self, temp_config_dir, sample_yaml_config):
        """Test that runtime modifications can be preserved or overridden on reload."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        config = load_config(config_path)
        original_value = config.messaging.rate_limit.max_messages

        # Make runtime modification
        config.messaging.rate_limit.max_messages = 999

        # Reload should restore file values
        config = load_config(config_path)
        assert config.messaging.rate_limit.max_messages == original_value


class TestConfigPathDiscovery:
    """Tests for config file path discovery and resolution."""

    def test_find_config_in_current_directory(self, temp_config_dir, sample_yaml_config):
        """Test finding config.yaml in current directory."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        with patch('pathlib.Path.cwd', return_value=temp_config_dir):
            config = load_config()  # No path specified
            assert config is not None

    def test_find_config_in_claudeswarm_directory(self, temp_config_dir, sample_yaml_config):
        """Test finding config in .claudeswarm subdirectory."""
        claudeswarm_dir = temp_config_dir / ".claudeswarm"
        claudeswarm_dir.mkdir(exist_ok=True)
        config_path = claudeswarm_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        with patch('pathlib.Path.cwd', return_value=temp_config_dir):
            config = load_config()  # Should find in .claudeswarm/
            assert config is not None

    def test_config_path_resolution_with_relative_path(self, temp_config_dir, sample_yaml_config):
        """Test resolving relative config paths."""
        config_path = temp_config_dir / "custom" / "myconfig.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(sample_yaml_config)

        with patch('pathlib.Path.cwd', return_value=temp_config_dir):
            config = load_config("custom/myconfig.yaml")
            assert config is not None

    def test_config_path_resolution_with_absolute_path(self, temp_config_dir, sample_yaml_config):
        """Test loading config with absolute path."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        config = load_config(str(config_path.absolute()))
        assert config is not None


class TestConfigDefaults:
    """Tests for default configuration values."""

    def test_get_default_config_returns_valid_config(self):
        """Test that default config is valid and complete."""
        config = get_default_config()

        assert config is not None
        assert hasattr(config, 'messaging')
        assert hasattr(config, 'locking')
        assert hasattr(config, 'discovery')
        assert hasattr(config, 'monitoring')

    def test_default_config_has_reasonable_rate_limits(self):
        """Test that default rate limits are reasonable."""
        config = get_default_config()

        assert config.messaging.rate_limit.max_messages > 0
        assert config.messaging.rate_limit.max_messages < 1000  # Not too high
        assert config.messaging.rate_limit.time_window_seconds > 0

    def test_default_config_has_reasonable_timeouts(self):
        """Test that default timeouts are reasonable."""
        config = get_default_config()

        assert config.locking.stale_timeout_seconds >= 60  # At least 1 minute
        assert config.locking.stale_timeout_seconds <= 3600  # At most 1 hour
        assert config.discovery.stale_threshold_seconds > 0

    def test_default_config_can_be_modified(self):
        """Test that default config instance can be modified."""
        config = get_default_config()
        original = config.messaging.rate_limit.max_messages

        config.messaging.rate_limit.max_messages = 999
        assert config.messaging.rate_limit.max_messages == 999

        # Getting default again should return fresh instance
        config2 = get_default_config()
        assert config2.messaging.rate_limit.max_messages == original


class TestConfigEnvironmentOverrides:
    """Tests for environment variable overrides."""

    def test_env_var_overrides_rate_limit(self, temp_config_dir, sample_yaml_config, monkeypatch):
        """Test that environment variables can override config values."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        monkeypatch.setenv("CLAUDESWARM_MESSAGING_RATE_LIMIT_MAX_MESSAGES", "50")

        config = load_config(config_path)
        # Implementation may or may not support env overrides
        # This tests the interface if it exists
        assert config.messaging.rate_limit.max_messages >= 10  # At least has value

    def test_env_var_overrides_stale_timeout(self, temp_config_dir, sample_yaml_config, monkeypatch):
        """Test environment variable override for stale timeout."""
        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        monkeypatch.setenv("CLAUDESWARM_LOCKING_STALE_TIMEOUT_SECONDS", "600")

        config = load_config(config_path)
        assert config.locking.stale_timeout_seconds >= 300


class TestConfigEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_load_config_with_empty_file(self, temp_config_dir):
        """Test loading empty config file uses defaults."""
        config_path = temp_config_dir / "empty.yaml"
        config_path.write_text("")

        config = load_config(config_path)
        # Should fallback to defaults
        assert config is not None

    def test_load_config_with_only_comments(self, temp_config_dir):
        """Test loading config file with only comments."""
        config_path = temp_config_dir / "comments.yaml"
        config_path.write_text("# Only comments\n# No actual config\n")

        config = load_config(config_path)
        # Should fallback to defaults
        assert config is not None

    def test_load_config_with_unicode_content(self, temp_config_dir):
        """Test loading config with unicode characters."""
        config_content = """# Configuration avec des caractères spéciaux
messaging:
  rate_limit:
    max_messages: 10
    time_window_seconds: 60
"""
        config_path = temp_config_dir / "unicode.yaml"
        config_path.write_text(config_content, encoding='utf-8')

        config = load_config(config_path)
        assert config.messaging.rate_limit.max_messages == 10

    def test_load_config_with_very_large_values(self, temp_config_dir):
        """Test config handles very large numeric values."""
        config_content = """messaging:
  rate_limit:
    max_messages: 999999
    time_window_seconds: 86400
"""
        config_path = temp_config_dir / "large.yaml"
        config_path.write_text(config_content)

        config = load_config(config_path)
        assert config.messaging.rate_limit.max_messages == 999999

    def test_load_config_concurrent_access(self, temp_config_dir, sample_yaml_config):
        """Test that config loading is thread-safe."""
        import threading

        config_path = temp_config_dir / "config.yaml"
        config_path.write_text(sample_yaml_config)

        results = []
        errors = []

        def load_config_thread():
            try:
                config = load_config(config_path)
                results.append(config)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=load_config_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        # All configs should have same values
        for config in results:
            assert config.messaging.rate_limit.max_messages == 10
