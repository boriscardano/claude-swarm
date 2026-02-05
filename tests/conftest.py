"""Pytest configuration and shared fixtures for claudeswarm tests.

This module provides test fixtures for configuration testing including:
- Temporary config files (YAML, TOML)
- Mock config objects
- Temporary directories
- Config validation helpers
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def reset_backend_singleton():
    """Reset the backend singleton before each test.

    This prevents backend state from leaking between tests,
    especially when tests manipulate TMUX/TMUX_PANE env vars.
    """
    from claudeswarm.backend import reset_backend

    reset_backend()
    yield
    reset_backend()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary directory for config files.

    Returns:
        Path: Path to temporary directory
    """
    config_dir = tmp_path / ".claudeswarm"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


@pytest.fixture
def sample_yaml_config():
    """Provide a sample YAML config string.

    Returns:
        str: Valid YAML configuration
    """
    return """# Claude Swarm Configuration
rate_limiting:
  messages_per_minute: 10
  window_seconds: 60

locking:
  stale_timeout: 300
  auto_cleanup: false
  default_reason: "working"

discovery:
  stale_threshold: 120
  auto_refresh_interval: 30

onboarding:
  enabled: true
  auto_onboard: false
"""


@pytest.fixture
def sample_toml_config():
    """Provide a sample TOML config string.

    Returns:
        str: Valid TOML configuration
    """
    return """# Claude Swarm Configuration

[rate_limiting]
messages_per_minute = 10
window_seconds = 60

[locking]
stale_timeout = 300
auto_cleanup = false
default_reason = "working"

[discovery]
stale_threshold = 120
auto_refresh_interval = 30

[onboarding]
enabled = true
auto_onboard = false
"""


@pytest.fixture
def invalid_yaml_config():
    """Provide an invalid YAML config string.

    Returns:
        str: Invalid YAML (syntax error)
    """
    return """# Invalid YAML
rate_limiting:
  messages_per_minute: 10
  - invalid_list_item
  window_seconds: 60
"""


@pytest.fixture
def invalid_values_config():
    """Provide a config with invalid values.

    Returns:
        str: YAML with semantically invalid values
    """
    return """rate_limiting:
  messages_per_minute: -10
  window_seconds: 0

locking:
  stale_timeout: -1
"""


@pytest.fixture
def partial_config():
    """Provide a partial config (missing some sections).

    Returns:
        str: YAML with only some sections defined
    """
    return """rate_limiting:
  messages_per_minute: 20
"""


@pytest.fixture
def config_dict():
    """Provide a config as a Python dict.

    Returns:
        dict: Configuration dictionary
    """
    return {
        "rate_limiting": {"messages_per_minute": 10, "window_seconds": 60},
        "locking": {"stale_timeout": 300, "auto_cleanup": False, "default_reason": "working"},
        "discovery": {"stale_threshold": 120, "auto_refresh_interval": 30},
        "onboarding": {"enabled": True, "auto_onboard": False},
    }


@pytest.fixture
def write_yaml_config(temp_config_dir):
    """Factory fixture to write YAML config files.

    Returns:
        callable: Function that writes config and returns path
    """

    def _write_config(content: str, filename: str = "config.yaml") -> Path:
        config_path = temp_config_dir / filename
        config_path.write_text(content)
        return config_path

    return _write_config


@pytest.fixture
def write_toml_config(temp_config_dir):
    """Factory fixture to write TOML config files.

    Returns:
        callable: Function that writes config and returns path
    """

    def _write_config(content: str, filename: str = "config.toml") -> Path:
        config_path = temp_config_dir / filename
        config_path.write_text(content)
        return config_path

    return _write_config


@pytest.fixture
def mock_config():
    """Provide a mock config object.

    Returns:
        Mock: Mock config with common attributes
    """
    config = Mock()
    config.rate_limiting = Mock()
    config.rate_limiting.messages_per_minute = 10
    config.rate_limiting.window_seconds = 60

    config.locking = Mock()
    config.locking.stale_timeout = 300
    config.locking.auto_cleanup = False
    config.locking.default_reason = "working"

    config.discovery = Mock()
    config.discovery.stale_threshold = 120
    config.discovery.auto_refresh_interval = 30

    config.onboarding = Mock()
    config.onboarding.enabled = True
    config.onboarding.auto_onboard = False

    return config


@pytest.fixture
def mock_editor():
    """Mock the EDITOR environment variable.

    Yields:
        str: Path to mock editor script
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write('#!/bin/sh\necho "Mock editor called with: $@"\n')
        f.flush()
        editor_path = f.name

    os.chmod(editor_path, 0o755)
    old_editor = os.environ.get("EDITOR")
    os.environ["EDITOR"] = editor_path

    try:
        yield editor_path
    finally:
        if old_editor:
            os.environ["EDITOR"] = old_editor
        else:
            os.environ.pop("EDITOR", None)
        try:
            os.unlink(editor_path)
        except OSError:
            pass


@pytest.fixture
def mock_project_root(tmp_path):
    """Create a mock project root with necessary directories.

    Returns:
        Path: Path to mock project root
    """
    project_root = tmp_path / "test_project"
    project_root.mkdir(parents=True, exist_ok=True)

    # Create expected directories
    (project_root / ".agent_locks").mkdir(exist_ok=True)
    (project_root / ".claudeswarm").mkdir(exist_ok=True)

    return project_root


@pytest.fixture
def capture_subprocess():
    """Fixture to capture subprocess calls.

    Yields:
        list: List that will contain all subprocess call arguments
    """
    calls = []

    def mock_run(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        result = Mock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    import subprocess

    original_run = subprocess.run
    subprocess.run = mock_run

    try:
        yield calls
    finally:
        subprocess.run = original_run
