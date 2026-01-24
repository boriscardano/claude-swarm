"""Tests for configuration system.

This module contains comprehensive tests for the configuration loading,
validation, and management system.
"""

import tempfile
from pathlib import Path
from typing import Any

import pytest

from claudeswarm.config import (
    MAX_CONFIG_FILE_SIZE_BYTES,
    MAX_YAML_NESTING_DEPTH,
    ClaudeSwarmConfig,
    ConfigValidationError,
    DiscoveryConfig,
    LockingConfig,
    OnboardingConfig,
    RateLimitConfig,
    _check_yaml_nesting_depth,
    _dict_to_config,
    _find_config_file,
    _merge_config_dict,
    get_config,
    load_config,
    reload_config,
)


class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = RateLimitConfig()
        assert config.messages_per_minute == 10
        assert config.window_seconds == 60

    def test_custom_values(self) -> None:
        """Test creating config with custom values."""
        config = RateLimitConfig(messages_per_minute=20, window_seconds=120)
        assert config.messages_per_minute == 20
        assert config.window_seconds == 120

    def test_validation_success(self) -> None:
        """Test validation passes for valid values."""
        config = RateLimitConfig(messages_per_minute=10, window_seconds=60)
        config.validate()  # Should not raise

    def test_validation_messages_per_minute_zero(self) -> None:
        """Test validation fails for zero messages_per_minute."""
        config = RateLimitConfig(messages_per_minute=0, window_seconds=60)
        with pytest.raises(ConfigValidationError, match="messages_per_minute must be > 0"):
            config.validate()

    def test_validation_messages_per_minute_negative(self) -> None:
        """Test validation fails for negative messages_per_minute."""
        config = RateLimitConfig(messages_per_minute=-1, window_seconds=60)
        with pytest.raises(ConfigValidationError, match="messages_per_minute must be > 0"):
            config.validate()

    def test_validation_messages_per_minute_too_high(self) -> None:
        """Test validation fails for too high messages_per_minute."""
        config = RateLimitConfig(messages_per_minute=1001, window_seconds=60)
        with pytest.raises(ConfigValidationError, match="messages_per_minute too high"):
            config.validate()

    def test_validation_window_seconds_zero(self) -> None:
        """Test validation fails for zero window_seconds."""
        config = RateLimitConfig(messages_per_minute=10, window_seconds=0)
        with pytest.raises(ConfigValidationError, match="window_seconds must be > 0"):
            config.validate()

    def test_validation_window_seconds_negative(self) -> None:
        """Test validation fails for negative window_seconds."""
        config = RateLimitConfig(messages_per_minute=10, window_seconds=-1)
        with pytest.raises(ConfigValidationError, match="window_seconds must be > 0"):
            config.validate()

    def test_validation_window_seconds_too_high(self) -> None:
        """Test validation fails for too high window_seconds."""
        config = RateLimitConfig(messages_per_minute=10, window_seconds=3601)
        with pytest.raises(ConfigValidationError, match="window_seconds too high"):
            config.validate()


class TestLockingConfig:
    """Tests for LockingConfig."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = LockingConfig()
        assert config.stale_timeout == 300
        assert config.auto_cleanup is False
        assert config.default_reason == "working"

    def test_custom_values(self) -> None:
        """Test creating config with custom values."""
        config = LockingConfig(stale_timeout=600, auto_cleanup=True, default_reason="testing")
        assert config.stale_timeout == 600
        assert config.auto_cleanup is True
        assert config.default_reason == "testing"

    def test_validation_success(self) -> None:
        """Test validation passes for valid values."""
        config = LockingConfig(stale_timeout=300, auto_cleanup=False, default_reason="work")
        config.validate()  # Should not raise

    def test_validation_stale_timeout_zero(self) -> None:
        """Test validation fails for zero stale_timeout."""
        config = LockingConfig(stale_timeout=0)
        with pytest.raises(ConfigValidationError, match="stale_timeout must be > 0"):
            config.validate()

    def test_validation_stale_timeout_too_low(self) -> None:
        """Test validation fails for too low stale_timeout."""
        config = LockingConfig(stale_timeout=59)
        with pytest.raises(ConfigValidationError, match="stale_timeout too low"):
            config.validate()

    def test_validation_stale_timeout_too_high(self) -> None:
        """Test validation fails for too high stale_timeout."""
        config = LockingConfig(stale_timeout=86401)
        with pytest.raises(ConfigValidationError, match="stale_timeout too high"):
            config.validate()

    def test_validation_default_reason_empty(self) -> None:
        """Test validation fails for empty default_reason."""
        config = LockingConfig(default_reason="")
        with pytest.raises(ConfigValidationError, match="default_reason cannot be empty"):
            config.validate()

    def test_validation_default_reason_whitespace(self) -> None:
        """Test validation fails for whitespace-only default_reason."""
        config = LockingConfig(default_reason="   ")
        with pytest.raises(ConfigValidationError, match="default_reason cannot be empty"):
            config.validate()

    def test_validation_default_reason_too_long(self) -> None:
        """Test validation fails for too long default_reason."""
        config = LockingConfig(default_reason="x" * 101)
        with pytest.raises(ConfigValidationError, match="default_reason too long"):
            config.validate()


class TestDiscoveryConfig:
    """Tests for DiscoveryConfig."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = DiscoveryConfig()
        assert config.stale_threshold == 60
        assert config.auto_refresh_interval is None

    def test_custom_values(self) -> None:
        """Test creating config with custom values."""
        config = DiscoveryConfig(stale_threshold=120, auto_refresh_interval=30)
        assert config.stale_threshold == 120
        assert config.auto_refresh_interval == 30

    def test_validation_success(self) -> None:
        """Test validation passes for valid values."""
        config = DiscoveryConfig(stale_threshold=60, auto_refresh_interval=30)
        config.validate()  # Should not raise

    def test_validation_success_no_refresh_interval(self) -> None:
        """Test validation passes when auto_refresh_interval is None."""
        config = DiscoveryConfig(stale_threshold=60, auto_refresh_interval=None)
        config.validate()  # Should not raise

    def test_validation_stale_threshold_zero(self) -> None:
        """Test validation fails for zero stale_threshold."""
        config = DiscoveryConfig(stale_threshold=0)
        with pytest.raises(ConfigValidationError, match="stale_threshold must be > 0"):
            config.validate()

    def test_validation_stale_threshold_too_low(self) -> None:
        """Test validation fails for too low stale_threshold."""
        config = DiscoveryConfig(stale_threshold=9)
        with pytest.raises(ConfigValidationError, match="stale_threshold too low"):
            config.validate()

    def test_validation_stale_threshold_too_high(self) -> None:
        """Test validation fails for too high stale_threshold."""
        config = DiscoveryConfig(stale_threshold=3601)
        with pytest.raises(ConfigValidationError, match="stale_threshold too high"):
            config.validate()

    def test_validation_refresh_interval_zero(self) -> None:
        """Test validation fails for zero auto_refresh_interval."""
        config = DiscoveryConfig(stale_threshold=60, auto_refresh_interval=0)
        with pytest.raises(ConfigValidationError, match="auto_refresh_interval must be > 0"):
            config.validate()

    def test_validation_refresh_interval_too_low(self) -> None:
        """Test validation fails for too low auto_refresh_interval."""
        config = DiscoveryConfig(stale_threshold=60, auto_refresh_interval=4)
        with pytest.raises(ConfigValidationError, match="auto_refresh_interval too low"):
            config.validate()


class TestOnboardingConfig:
    """Tests for OnboardingConfig."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = OnboardingConfig()
        assert config.enabled is True
        assert config.custom_messages is None
        assert config.auto_onboard is False

    def test_custom_values(self) -> None:
        """Test creating config with custom values."""
        messages = ["Hello", "World"]
        config = OnboardingConfig(enabled=False, custom_messages=messages, auto_onboard=True)
        assert config.enabled is False
        assert config.custom_messages == messages
        assert config.auto_onboard is True

    def test_validation_success(self) -> None:
        """Test validation passes for valid values."""
        config = OnboardingConfig(
            enabled=True, custom_messages=["msg1", "msg2"], auto_onboard=False
        )
        config.validate()  # Should not raise

    def test_validation_success_no_messages(self) -> None:
        """Test validation passes when custom_messages is None."""
        config = OnboardingConfig(enabled=True, custom_messages=None)
        config.validate()  # Should not raise

    def test_validation_messages_not_list(self) -> None:
        """Test validation fails for non-list custom_messages."""
        config = OnboardingConfig(custom_messages="not a list")  # type: ignore
        with pytest.raises(ConfigValidationError, match="custom_messages must be a list"):
            config.validate()

    def test_validation_too_many_messages(self) -> None:
        """Test validation fails for too many custom_messages."""
        config = OnboardingConfig(custom_messages=["msg"] * 101)
        with pytest.raises(ConfigValidationError, match="Too many custom messages"):
            config.validate()

    def test_validation_message_not_string(self) -> None:
        """Test validation fails for non-string message."""
        config = OnboardingConfig(custom_messages=["good", 123, "also good"])  # type: ignore
        with pytest.raises(ConfigValidationError, match="custom_messages\\[1\\] must be a string"):
            config.validate()

    def test_validation_message_too_long(self) -> None:
        """Test validation fails for too long message."""
        config = OnboardingConfig(custom_messages=["x" * 1001])
        with pytest.raises(ConfigValidationError, match="custom_messages\\[0\\] too long"):
            config.validate()


class TestClaudeSwarmConfig:
    """Tests for ClaudeSwarmConfig."""

    def test_default_values(self) -> None:
        """Test that default values are set correctly."""
        config = ClaudeSwarmConfig()
        assert isinstance(config.rate_limiting, RateLimitConfig)
        assert isinstance(config.locking, LockingConfig)
        assert isinstance(config.discovery, DiscoveryConfig)
        assert isinstance(config.onboarding, OnboardingConfig)
        assert config.project_root is None

    def test_custom_values(self) -> None:
        """Test creating config with custom values."""
        rate_limiting = RateLimitConfig(messages_per_minute=20, window_seconds=120)
        locking = LockingConfig(stale_timeout=600)
        discovery = DiscoveryConfig(stale_threshold=90)
        onboarding = OnboardingConfig(enabled=False)
        project_root = Path("/tmp")

        config = ClaudeSwarmConfig(
            rate_limiting=rate_limiting,
            locking=locking,
            discovery=discovery,
            onboarding=onboarding,
            project_root=project_root,
        )

        assert config.rate_limiting.messages_per_minute == 20
        assert config.locking.stale_timeout == 600
        assert config.discovery.stale_threshold == 90
        assert config.onboarding.enabled is False
        assert config.project_root == project_root

    def test_validation_success(self) -> None:
        """Test validation passes for valid config."""
        config = ClaudeSwarmConfig()
        config.validate()  # Should not raise

    def test_validation_invalid_subsection(self) -> None:
        """Test validation fails when subsection is invalid."""
        config = ClaudeSwarmConfig()
        config.rate_limiting.messages_per_minute = 0
        with pytest.raises(ConfigValidationError):
            config.validate()

    def test_validation_project_root_not_exists(self) -> None:
        """Test validation fails when project_root doesn't exist."""
        config = ClaudeSwarmConfig(project_root=Path("/nonexistent/path"))
        with pytest.raises(ConfigValidationError, match="project_root does not exist"):
            config.validate()

    def test_validation_project_root_not_directory(self) -> None:
        """Test validation fails when project_root is not a directory."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            config = ClaudeSwarmConfig(project_root=tmp_path)
            with pytest.raises(ConfigValidationError, match="project_root is not a directory"):
                config.validate()
        finally:
            tmp_path.unlink()

    def test_to_dict(self) -> None:
        """Test converting config to dictionary."""
        config = ClaudeSwarmConfig()
        config_dict = config.to_dict()

        assert "rate_limiting" in config_dict
        assert "locking" in config_dict
        assert "discovery" in config_dict
        assert "onboarding" in config_dict
        assert config_dict["rate_limiting"]["messages_per_minute"] == 10
        assert config_dict["locking"]["stale_timeout"] == 300

    def test_to_dict_with_project_root(self) -> None:
        """Test to_dict includes project_root when set."""
        config = ClaudeSwarmConfig(project_root=Path("/tmp"))
        config_dict = config.to_dict()
        assert "project_root" in config_dict
        assert config_dict["project_root"] == "/tmp"


class TestDictToConfig:
    """Tests for _dict_to_config function."""

    def test_empty_dict(self) -> None:
        """Test converting empty dict uses defaults."""
        config = _dict_to_config({})
        assert config.rate_limiting.messages_per_minute == 10
        assert config.locking.stale_timeout == 300
        assert config.discovery.stale_threshold == 60
        assert config.onboarding.enabled is True

    def test_partial_dict(self) -> None:
        """Test converting partial dict merges with defaults."""
        data = {"rate_limiting": {"messages_per_minute": 20}}
        config = _dict_to_config(data)
        assert config.rate_limiting.messages_per_minute == 20
        assert config.rate_limiting.window_seconds == 60  # Default
        assert config.locking.stale_timeout == 300  # Default

    def test_full_dict(self) -> None:
        """Test converting full dict."""
        data = {
            "rate_limiting": {"messages_per_minute": 20, "window_seconds": 120},
            "locking": {
                "stale_timeout": 600,
                "auto_cleanup": True,
                "default_reason": "testing",
            },
            "discovery": {"stale_threshold": 90, "auto_refresh_interval": 30},
            "onboarding": {
                "enabled": False,
                "custom_messages": ["msg1"],
                "auto_onboard": True,
            },
            "project_root": "/tmp",
        }
        config = _dict_to_config(data)
        assert config.rate_limiting.messages_per_minute == 20
        assert config.locking.stale_timeout == 600
        assert config.discovery.stale_threshold == 90
        assert config.onboarding.enabled is False
        assert config.project_root == Path("/tmp")


class TestMergeConfigDict:
    """Tests for _merge_config_dict function."""

    def test_merge_empty_dicts(self) -> None:
        """Test merging two empty dicts."""
        result = _merge_config_dict({}, {})
        assert result == {}

    def test_merge_with_empty_override(self) -> None:
        """Test merging with empty override keeps base."""
        base = {"a": 1, "b": 2}
        result = _merge_config_dict(base, {})
        assert result == {"a": 1, "b": 2}

    def test_merge_with_empty_base(self) -> None:
        """Test merging with empty base uses override."""
        override = {"a": 1, "b": 2}
        result = _merge_config_dict({}, override)
        assert result == {"a": 1, "b": 2}

    def test_merge_flat_dicts(self) -> None:
        """Test merging flat dictionaries."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _merge_config_dict(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_nested_dicts(self) -> None:
        """Test merging nested dictionaries."""
        base = {"section": {"a": 1, "b": 2}}
        override = {"section": {"b": 3, "c": 4}}
        result = _merge_config_dict(base, override)
        assert result == {"section": {"a": 1, "b": 3, "c": 4}}

    def test_merge_deep_nested(self) -> None:
        """Test merging deeply nested dictionaries."""
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"d": 3, "e": 4}}}
        result = _merge_config_dict(base, override)
        assert result == {"a": {"b": {"c": 1, "d": 3, "e": 4}}}


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_defaults_no_file(self) -> None:
        """Test loading defaults when no config file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Change to temp directory with no config file
            original_cwd = Path.cwd()
            try:
                import os

                os.chdir(tmpdir)
                config = load_config()
                assert config.rate_limiting.messages_per_minute == 10
                assert config.locking.stale_timeout == 300
            finally:
                os.chdir(original_cwd)

    def test_load_nonexistent_file(self) -> None:
        """Test loading nonexistent file raises error."""
        with pytest.raises(ConfigValidationError, match="Configuration file not found"):
            load_config(Path("/nonexistent/config.yaml"))

    def test_load_unsupported_format(self) -> None:
        """Test loading unsupported format raises error."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with pytest.raises(
                ConfigValidationError, match="Unsupported configuration file format"
            ):
                load_config(tmp_path)
        finally:
            tmp_path.unlink()

    def test_validation_on_load(self) -> None:
        """Test that validation is performed on load."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            # Write invalid config (messages_per_minute = 0)
            tmp.write("rate_limiting:\n  messages_per_minute: 0\n")
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            # Need to check if YAML is available
            try:
                import yaml

                with pytest.raises(ConfigValidationError, match="messages_per_minute must be > 0"):
                    load_config(tmp_path)
            except ImportError:
                pytest.skip("YAML not available")
        finally:
            tmp_path.unlink()


class TestFindConfigFile:
    """Tests for _find_config_file function."""

    def test_no_config_file(self) -> None:
        """Test returns None when no config file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _find_config_file(Path(tmpdir))
            assert result is None

    def test_finds_yaml_in_current_dir(self) -> None:
        """Test finds .claudeswarm.yaml in current directory."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            config_file = tmppath / ".claudeswarm.yaml"
            config_file.touch()

            result = _find_config_file(tmppath)
            assert result == config_file

    def test_finds_toml_in_current_dir(self) -> None:
        """Test finds .claudeswarm.toml in current directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            config_file = tmppath / ".claudeswarm.toml"
            config_file.touch()

            result = _find_config_file(tmppath)
            # Only if TOML support is available
            if result is not None:
                assert result == config_file

    def test_finds_config_in_parent_dir(self) -> None:
        """Test finds config in parent directory."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            config_file = tmppath / ".claudeswarm.yaml"
            config_file.touch()

            subdir = tmppath / "subdir"
            subdir.mkdir()

            result = _find_config_file(subdir)
            assert result == config_file

    def test_prefers_yaml_over_toml(self) -> None:
        """Test prefers YAML when both exist."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            yaml_file = tmppath / ".claudeswarm.yaml"
            toml_file = tmppath / ".claudeswarm.toml"
            yaml_file.touch()
            toml_file.touch()

            result = _find_config_file(tmppath)
            # YAML should be preferred if available
            assert result == yaml_file


class TestSingletonConfig:
    """Tests for singleton configuration functions."""

    def test_get_config_returns_instance(self) -> None:
        """Test get_config returns a config instance."""
        # Reset singleton for test
        import claudeswarm.config as config_module

        config_module._config_instance = None

        config = get_config()
        assert isinstance(config, ClaudeSwarmConfig)

    def test_get_config_returns_same_instance(self) -> None:
        """Test get_config returns the same instance on repeated calls."""
        # Reset singleton for test
        import claudeswarm.config as config_module

        config_module._config_instance = None

        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_reload_config_creates_new_instance(self) -> None:
        """Test reload_config creates a new instance."""
        # Reset singleton for test
        import claudeswarm.config as config_module

        config_module._config_instance = None

        config1 = get_config()
        config2 = reload_config()

        # Different instances
        assert config1 is not config2
        # But both are valid configs
        assert isinstance(config1, ClaudeSwarmConfig)
        assert isinstance(config2, ClaudeSwarmConfig)

    def test_reload_config_updates_singleton(self) -> None:
        """Test reload_config updates the singleton."""
        # Reset singleton for test
        import claudeswarm.config as config_module

        config_module._config_instance = None

        reload_config()
        config1 = get_config()
        reload_config()
        config2 = get_config()

        # After reload, get_config returns the new instance
        assert config1 is not config2


class TestYAMLNestingDepth:
    """Tests for YAML nesting depth validation."""

    def test_check_yaml_nesting_depth_flat_dict(self) -> None:
        """Test that flat dictionaries pass validation."""
        obj = {"a": 1, "b": 2, "c": 3}
        _check_yaml_nesting_depth(obj)  # Should not raise

    def test_check_yaml_nesting_depth_flat_list(self) -> None:
        """Test that flat lists pass validation."""
        obj = [1, 2, 3, 4, 5]
        _check_yaml_nesting_depth(obj)  # Should not raise

    def test_check_yaml_nesting_depth_nested_within_limit(self) -> None:
        """Test that nesting within limit passes validation."""
        obj = {"a": {"b": {"c": {"d": 1}}}}
        _check_yaml_nesting_depth(obj)  # Should not raise

    def test_check_yaml_nesting_depth_exactly_at_limit(self) -> None:
        """Test that nesting exactly at limit passes validation."""
        # Build nested structure with depth = MAX_YAML_NESTING_DEPTH
        obj: Any = {"value": 1}
        for _ in range(MAX_YAML_NESTING_DEPTH - 1):
            obj = {"nested": obj}

        _check_yaml_nesting_depth(obj)  # Should not raise

    def test_check_yaml_nesting_depth_exceeds_limit(self) -> None:
        """Test that nesting exceeding limit raises error."""
        # Build nested structure with depth = MAX_YAML_NESTING_DEPTH + 1
        obj: Any = {"value": 1}
        for _ in range(MAX_YAML_NESTING_DEPTH):
            obj = {"nested": obj}

        with pytest.raises(ConfigValidationError, match="YAML nesting depth exceeds maximum"):
            _check_yaml_nesting_depth(obj)

    def test_check_yaml_nesting_depth_list_nesting(self) -> None:
        """Test that nested lists are validated."""
        # Build deeply nested list structure
        obj: Any = [1]
        for _ in range(MAX_YAML_NESTING_DEPTH):
            obj = [obj]

        with pytest.raises(ConfigValidationError, match="YAML nesting depth exceeds maximum"):
            _check_yaml_nesting_depth(obj)

    def test_check_yaml_nesting_depth_mixed_nesting(self) -> None:
        """Test that mixed dict/list nesting is validated."""
        # Build deeply nested mixed structure
        obj: Any = {"value": 1}
        for i in range(MAX_YAML_NESTING_DEPTH):
            if i % 2 == 0:
                obj = {"nested": obj}
            else:
                obj = [obj]

        with pytest.raises(ConfigValidationError, match="YAML nesting depth exceeds maximum"):
            _check_yaml_nesting_depth(obj)

    def test_check_yaml_nesting_depth_custom_limit(self) -> None:
        """Test that custom depth limit can be specified."""
        obj = {"a": {"b": {"c": 1}}}

        # Should pass with higher limit
        _check_yaml_nesting_depth(obj, max_depth=5)

        # Should fail with lower limit
        with pytest.raises(ConfigValidationError, match="YAML nesting depth exceeds maximum of 2"):
            _check_yaml_nesting_depth(obj, max_depth=2)

    def test_check_yaml_nesting_depth_primitives(self) -> None:
        """Test that primitive values pass validation."""
        _check_yaml_nesting_depth(42)
        _check_yaml_nesting_depth("string")
        _check_yaml_nesting_depth(True)
        _check_yaml_nesting_depth(None)
        _check_yaml_nesting_depth(3.14)


class TestYAMLFileSizeLimit:
    """Tests for YAML file size limit validation."""

    def test_load_yaml_config_normal_size(self) -> None:
        """Test that normal-sized YAML files load successfully."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            # Write a small config (< 1KB)
            tmp.write("rate_limiting:\n  messages_per_minute: 20\n")
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            config = load_config(tmp_path)
            assert config.rate_limiting.messages_per_minute == 20
        finally:
            tmp_path.unlink()

    def test_load_yaml_config_large_file_rejected(self) -> None:
        """Test that files exceeding size limit are rejected."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            # Write a file larger than MAX_CONFIG_FILE_SIZE_BYTES
            # Create a large YAML with many entries
            tmp.write("large_data:\n")
            # Write enough data to exceed 1MB
            chunk = "  " + "x" * 100 + ": value\n"
            chunks_needed = (MAX_CONFIG_FILE_SIZE_BYTES // len(chunk)) + 1
            for i in range(chunks_needed):
                tmp.write(f"  key{i}: {'x' * 1000}\n")
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            # Verify file is actually too large
            assert tmp_path.stat().st_size > MAX_CONFIG_FILE_SIZE_BYTES

            with pytest.raises(ConfigValidationError, match="Configuration file too large"):
                load_config(tmp_path)
        finally:
            tmp_path.unlink()

    def test_load_yaml_config_exactly_at_limit(self) -> None:
        """Test that files exactly at the size limit are accepted."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            # Write a file exactly at MAX_CONFIG_FILE_SIZE_BYTES
            # Start with minimal valid YAML
            content = "rate_limiting:\n  messages_per_minute: 20\n"
            # Pad with comments to reach the limit
            current_size = len(content.encode("utf-8"))
            padding_needed = MAX_CONFIG_FILE_SIZE_BYTES - current_size - 10  # Leave some margin
            if padding_needed > 0:
                content += "# " + "x" * (padding_needed - 2) + "\n"
            tmp.write(content)
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            # Verify file is close to limit but not over
            file_size = tmp_path.stat().st_size
            assert file_size <= MAX_CONFIG_FILE_SIZE_BYTES
            assert file_size > MAX_CONFIG_FILE_SIZE_BYTES - 1000  # Close to limit

            config = load_config(tmp_path)
            assert config.rate_limiting.messages_per_minute == 20
        finally:
            tmp_path.unlink()


class TestYAMLNestingDepthIntegration:
    """Integration tests for YAML nesting depth in config loading."""

    def test_load_yaml_config_normal_nesting(self) -> None:
        """Test that normal config nesting loads successfully."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            tmp.write(
                """
rate_limiting:
  messages_per_minute: 20
  window_seconds: 60

locking:
  stale_timeout: 300
  auto_cleanup: true
  default_reason: "working"

discovery:
  stale_threshold: 60
"""
            )
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            config = load_config(tmp_path)
            assert config.rate_limiting.messages_per_minute == 20
            assert config.locking.stale_timeout == 300
        finally:
            tmp_path.unlink()

    def test_load_yaml_config_deep_nesting_rejected(self) -> None:
        """Test that deeply nested YAML is rejected."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            # Create a deeply nested structure that exceeds MAX_YAML_NESTING_DEPTH
            content = "a:\n"
            indent = "  "
            for i in range(MAX_YAML_NESTING_DEPTH + 2):
                content += indent * (i + 1) + f"level{i}:\n"
            content += indent * (MAX_YAML_NESTING_DEPTH + 3) + "value: 1\n"

            tmp.write(content)
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            with pytest.raises(ConfigValidationError, match="YAML nesting depth exceeds maximum"):
                load_config(tmp_path)
        finally:
            tmp_path.unlink()

    def test_load_yaml_config_deep_list_nesting_rejected(self) -> None:
        """Test that deeply nested lists in YAML are rejected."""
        try:
            import yaml
        except ImportError:
            pytest.skip("YAML not available")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tmp:
            # Create a deeply nested list structure
            content = "data:\n"
            indent = "  "
            for i in range(MAX_YAML_NESTING_DEPTH + 2):
                content += indent * (i + 1) + "-\n"
            content += indent * (MAX_YAML_NESTING_DEPTH + 3) + "- value\n"

            tmp.write(content)
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            with pytest.raises(ConfigValidationError, match="YAML nesting depth exceeds maximum"):
                load_config(tmp_path)
        finally:
            tmp_path.unlink()
