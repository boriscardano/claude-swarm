"""Configuration system for Claude Swarm.

This module provides a comprehensive configuration system that:
- Defines configuration schema using dataclasses
- Supports loading from YAML and TOML files
- Provides sensible defaults for all settings
- Validates configuration values
- Implements thread-safe singleton pattern
- Supports configuration reload

Configuration files are searched in the following order:
1. Explicit path provided to load_config()
2. .claudeswarm.yaml in project root
3. .claudeswarm.toml in project root
4. Default values

Example configuration (.claudeswarm.yaml):
    rate_limiting:
      messages_per_minute: 20
      window_seconds: 60

    locking:
      stale_timeout: 300
      auto_cleanup: true
      default_reason: "working"

    discovery:
      stale_threshold: 60
      auto_refresh_interval: 30
      enable_cross_project_coordination: false

    onboarding:
      enabled: true
      auto_onboard: false

Example configuration (.claudeswarm.toml):
    [rate_limiting]
    messages_per_minute = 20
    window_seconds = 60

    [locking]
    stale_timeout = 300
    auto_cleanup = true
    default_reason = "working"

    [discovery]
    stale_threshold = 60
    auto_refresh_interval = 30
    enable_cross_project_coordination = false

    [onboarding]
    enabled = true
    auto_onboard = false
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Conditional imports for file format support
try:
    import tomllib  # Python 3.11+

    HAS_TOML = True
except ImportError:
    try:
        import tomli as tomllib  # Fallback for Python 3.10

        HAS_TOML = True
    except ImportError:
        HAS_TOML = False

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# YAML DoS prevention limits
MAX_CONFIG_FILE_SIZE_BYTES = 1 * 1024 * 1024  # 1MB
MAX_YAML_NESTING_DEPTH = 10

__all__ = [
    "RateLimitConfig",
    "LockingConfig",
    "DiscoveryConfig",
    "OnboardingConfig",
    "DashboardConfig",
    "BackendConfig",
    "ClaudeSwarmConfig",
    "load_config",
    "get_config",
    "reload_config",
    "ConfigValidationError",
]


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""

    pass


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting in the messaging system.

    Attributes:
        messages_per_minute: Maximum number of messages an agent can send per window
        window_seconds: Time window for rate limiting in seconds
    """

    messages_per_minute: int = 10
    window_seconds: int = 60

    def validate(self) -> None:
        """Validate rate limit configuration.

        Raises:
            ConfigValidationError: If validation fails
        """
        if self.messages_per_minute <= 0:
            raise ConfigValidationError(
                f"messages_per_minute must be > 0, got {self.messages_per_minute}"
            )
        if self.window_seconds <= 0:
            raise ConfigValidationError(f"window_seconds must be > 0, got {self.window_seconds}")
        if self.messages_per_minute > 1000:
            raise ConfigValidationError(
                f"messages_per_minute too high (max 1000), got {self.messages_per_minute}"
            )
        if self.window_seconds > 3600:
            raise ConfigValidationError(
                f"window_seconds too high (max 3600), got {self.window_seconds}"
            )


@dataclass
class LockingConfig:
    """Configuration for distributed file locking.

    Attributes:
        stale_timeout: Seconds after which a lock is considered stale
        auto_cleanup: Whether to automatically clean up stale locks
        default_reason: Default reason string for lock acquisition
    """

    stale_timeout: int = 300
    auto_cleanup: bool = False
    default_reason: str = "working"

    def validate(self) -> None:
        """Validate locking configuration.

        Raises:
            ConfigValidationError: If validation fails
        """
        if self.stale_timeout <= 0:
            raise ConfigValidationError(f"stale_timeout must be > 0, got {self.stale_timeout}")
        if self.stale_timeout < 60:
            raise ConfigValidationError(
                f"stale_timeout too low (min 60s for safety), got {self.stale_timeout}"
            )
        if self.stale_timeout > 86400:
            raise ConfigValidationError(
                f"stale_timeout too high (max 24h), got {self.stale_timeout}"
            )
        if not self.default_reason or not self.default_reason.strip():
            raise ConfigValidationError("default_reason cannot be empty")
        if len(self.default_reason) > 100:
            raise ConfigValidationError(
                f"default_reason too long (max 100 chars), got {len(self.default_reason)}"
            )


@dataclass
class DiscoveryConfig:
    """Configuration for agent discovery system.

    Attributes:
        stale_threshold: Seconds after which an agent is considered stale
        auto_refresh_interval: Automatic refresh interval in seconds (None = disabled)
        enable_cross_project_coordination: Whether to enable cross-project agent discovery.
            When False (default), only agents in the same project directory are discovered.
            When True, agents from all projects are visible, which may have security
            implications in multi-tenant or shared environments. Use with caution.
    """

    stale_threshold: int = 60
    auto_refresh_interval: int | None = None
    enable_cross_project_coordination: bool = False

    def validate(self) -> None:
        """Validate discovery configuration.

        Raises:
            ConfigValidationError: If validation fails
        """
        if self.stale_threshold <= 0:
            raise ConfigValidationError(f"stale_threshold must be > 0, got {self.stale_threshold}")
        if self.stale_threshold < 10:
            raise ConfigValidationError(
                f"stale_threshold too low (min 10s), got {self.stale_threshold}"
            )
        if self.stale_threshold > 3600:
            raise ConfigValidationError(
                f"stale_threshold too high (max 1h), got {self.stale_threshold}"
            )
        if self.auto_refresh_interval is not None:
            if self.auto_refresh_interval <= 0:
                raise ConfigValidationError(
                    f"auto_refresh_interval must be > 0, got {self.auto_refresh_interval}"
                )
            if self.auto_refresh_interval < 5:
                raise ConfigValidationError(
                    f"auto_refresh_interval too low (min 5s), got {self.auto_refresh_interval}"
                )


@dataclass
class OnboardingConfig:
    """Configuration for agent onboarding system.

    Attributes:
        enabled: Whether onboarding is enabled
        custom_messages: Optional list of custom onboarding messages
        auto_onboard: Whether to automatically onboard new agents
    """

    enabled: bool = True
    custom_messages: list[str] | None = None
    auto_onboard: bool = False

    def validate(self) -> None:
        """Validate onboarding configuration.

        Raises:
            ConfigValidationError: If validation fails
        """
        if self.custom_messages is not None:
            if not isinstance(self.custom_messages, list):
                raise ConfigValidationError(
                    f"custom_messages must be a list, got {type(self.custom_messages)}"
                )
            if len(self.custom_messages) > 100:
                raise ConfigValidationError(
                    f"Too many custom messages (max 100), got {len(self.custom_messages)}"
                )
            for i, msg in enumerate(self.custom_messages):
                if not isinstance(msg, str):
                    raise ConfigValidationError(
                        f"custom_messages[{i}] must be a string, got {type(msg)}"
                    )
                if len(msg) > 1000:
                    raise ConfigValidationError(
                        f"custom_messages[{i}] too long (max 1000 chars), got {len(msg)}"
                    )


@dataclass
class DashboardConfig:
    """Configuration for web dashboard.

    Attributes:
        enabled: Whether dashboard is available
        port: Default port for dashboard server
        host: Default host to bind to
        auto_open_browser: Whether to open browser automatically
        refresh_interval: Data refresh interval in seconds
    """

    enabled: bool = True
    port: int = 8080
    host: str = "localhost"
    auto_open_browser: bool = True
    refresh_interval: int = 1  # seconds

    def validate(self) -> None:
        """Validate dashboard configuration.

        Raises:
            ConfigValidationError: If validation fails
        """
        if self.port < 1024 or self.port > 65535:
            raise ConfigValidationError(f"port must be between 1024-65535, got {self.port}")
        if self.refresh_interval < 1:
            raise ConfigValidationError(
                f"refresh_interval must be >= 1, got {self.refresh_interval}"
            )
        if not isinstance(self.host, str) or not self.host.strip():
            raise ConfigValidationError("host cannot be empty")


@dataclass
class BackendConfig:
    """Configuration for terminal backend.

    Attributes:
        provider: Backend provider to use ("auto", "tmux", "process")
        message_poll_interval: Interval in seconds for polling file-based messages
    """

    provider: str = "auto"
    message_poll_interval: int = 5

    def validate(self) -> None:
        """Validate backend configuration.

        Raises:
            ConfigValidationError: If validation fails
        """
        valid_providers = ("auto", "tmux", "process")
        if self.provider.lower() not in valid_providers:
            raise ConfigValidationError(
                f"backend.provider must be one of {valid_providers}, got '{self.provider}'"
            )
        if self.message_poll_interval < 1:
            raise ConfigValidationError(
                f"message_poll_interval must be >= 1, got {self.message_poll_interval}"
            )
        if self.message_poll_interval > 300:
            raise ConfigValidationError(
                f"message_poll_interval too high (max 300s), got {self.message_poll_interval}"
            )


@dataclass
class ClaudeSwarmConfig:
    """Complete configuration for Claude Swarm.

    Attributes:
        rate_limiting: Rate limiting configuration
        locking: File locking configuration
        discovery: Agent discovery configuration
        onboarding: Onboarding configuration
        dashboard: Dashboard configuration
        backend: Terminal backend configuration
        project_root: Project root directory (None = auto-detect)
    """

    rate_limiting: RateLimitConfig = field(default_factory=RateLimitConfig)
    locking: LockingConfig = field(default_factory=LockingConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    onboarding: OnboardingConfig = field(default_factory=OnboardingConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    backend: BackendConfig = field(default_factory=BackendConfig)
    project_root: Path | None = None

    def validate(self) -> None:
        """Validate all configuration sections.

        Raises:
            ConfigValidationError: If any validation fails
        """
        self.rate_limiting.validate()
        self.locking.validate()
        self.discovery.validate()
        self.onboarding.validate()
        self.dashboard.validate()
        self.backend.validate()

        if self.project_root is not None:
            if not isinstance(self.project_root, (Path, str)):
                raise ConfigValidationError(
                    f"project_root must be a Path or str, got {type(self.project_root)}"
                )
            project_path = Path(self.project_root)
            if not project_path.exists():
                raise ConfigValidationError(f"project_root does not exist: {project_path}")
            if not project_path.is_dir():
                raise ConfigValidationError(f"project_root is not a directory: {project_path}")

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation of configuration
        """
        result = {
            "rate_limiting": asdict(self.rate_limiting),
            "locking": asdict(self.locking),
            "discovery": asdict(self.discovery),
            "onboarding": asdict(self.onboarding),
            "dashboard": asdict(self.dashboard),
            "backend": asdict(self.backend),
        }
        if self.project_root is not None:
            result["project_root"] = str(self.project_root)
        return result


def _check_yaml_nesting_depth(
    obj: Any, current_depth: int = 0, max_depth: int = MAX_YAML_NESTING_DEPTH
) -> None:
    """Check that YAML object doesn't exceed maximum nesting depth.

    Prevents DoS attacks via deeply nested structures.

    Args:
        obj: Object to check (typically from yaml.safe_load)
        current_depth: Current depth in the object tree
        max_depth: Maximum allowed depth

    Raises:
        ConfigValidationError: If nesting depth exceeds max_depth
    """
    if current_depth > max_depth:
        raise ConfigValidationError(f"YAML nesting depth exceeds maximum of {max_depth} levels")

    if isinstance(obj, dict):
        for value in obj.values():
            _check_yaml_nesting_depth(value, current_depth + 1, max_depth)
    elif isinstance(obj, list):
        for item in obj:
            _check_yaml_nesting_depth(item, current_depth + 1, max_depth)


def _find_config_file(start_path: Path | None = None) -> Path | None:
    """Find configuration file in project directory.

    Searches for .claudeswarm.yaml or .claudeswarm.toml in the current
    directory and parent directories.

    Args:
        start_path: Starting directory for search (None = current directory)

    Returns:
        Path to configuration file if found, None otherwise
    """
    search_path = start_path or Path.cwd()

    # Search up the directory tree
    for directory in [search_path] + list(search_path.parents):
        # Try YAML first
        if HAS_YAML:
            yaml_path = directory / ".claudeswarm.yaml"
            if yaml_path.is_file():
                return yaml_path

        # Try TOML
        if HAS_TOML:
            toml_path = directory / ".claudeswarm.toml"
            if toml_path.is_file():
                return toml_path

    return None


def _load_yaml_config(path: Path) -> dict[str, Any]:
    """Load configuration from YAML file.

    Args:
        path: Path to YAML configuration file

    Returns:
        Parsed configuration dictionary

    Raises:
        ConfigValidationError: If YAML parsing fails or YAML not available
    """
    if not HAS_YAML:
        raise ConfigValidationError(
            "YAML support not available. Install pyyaml: pip install pyyaml"
        )

    # Check file size to prevent large file DoS attacks
    try:
        file_size = path.stat().st_size
        if file_size > MAX_CONFIG_FILE_SIZE_BYTES:
            raise ConfigValidationError(
                f"Configuration file too large: {file_size} bytes "
                f"(max {MAX_CONFIG_FILE_SIZE_BYTES} bytes)"
            )
    except OSError as e:
        raise ConfigValidationError(f"Failed to check file size for {path}: {e}") from e

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

            # Validate nesting depth to prevent deeply nested structure DoS attacks
            if data is not None:
                _check_yaml_nesting_depth(data)

            return data if data is not None else {}
    except yaml.YAMLError as e:
        raise ConfigValidationError(f"Failed to parse YAML file {path}: {e}") from e
    except ConfigValidationError:
        # Re-raise our own validation errors
        raise
    except Exception as e:
        raise ConfigValidationError(f"Failed to load YAML file {path}: {e}") from e


def _load_toml_config(path: Path) -> dict[str, Any]:
    """Load configuration from TOML file.

    Args:
        path: Path to TOML configuration file

    Returns:
        Parsed configuration dictionary

    Raises:
        ConfigValidationError: If TOML parsing fails or TOML not available
    """
    if not HAS_TOML:
        raise ConfigValidationError(
            "TOML support not available. Requires Python 3.11+ or install tomli: pip install tomli"
        )

    # Check file size to prevent large file DoS attacks (same as YAML)
    try:
        file_size = path.stat().st_size
        if file_size > MAX_CONFIG_FILE_SIZE_BYTES:
            raise ConfigValidationError(
                f"Configuration file too large: {file_size} bytes "
                f"(max {MAX_CONFIG_FILE_SIZE_BYTES} bytes)"
            )
    except OSError as e:
        raise ConfigValidationError(f"Failed to check file size for {path}: {e}") from e

    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except Exception as e:
        raise ConfigValidationError(f"Failed to load TOML file {path}: {e}") from e


def _merge_config_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge configuration dictionaries.

    Args:
        base: Base configuration dictionary
        override: Override configuration dictionary

    Returns:
        Merged configuration dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_config_dict(result[key], value)
        else:
            result[key] = value

    return result


def _dict_to_config(data: dict[str, Any]) -> ClaudeSwarmConfig:
    """Convert dictionary to ClaudeSwarmConfig.

    Args:
        data: Configuration dictionary

    Returns:
        ClaudeSwarmConfig instance

    Raises:
        ConfigValidationError: If conversion fails
    """
    try:
        # Extract rate limiting config
        rate_limiting_data = data.get("rate_limiting", {})
        rate_limiting = RateLimitConfig(
            messages_per_minute=rate_limiting_data.get("messages_per_minute", 10),
            window_seconds=rate_limiting_data.get("window_seconds", 60),
        )

        # Extract locking config
        locking_data = data.get("locking", {})
        locking = LockingConfig(
            stale_timeout=locking_data.get("stale_timeout", 300),
            auto_cleanup=locking_data.get("auto_cleanup", False),
            default_reason=locking_data.get("default_reason", "working"),
        )

        # Extract discovery config
        discovery_data = data.get("discovery", {})
        discovery = DiscoveryConfig(
            stale_threshold=discovery_data.get("stale_threshold", 60),
            auto_refresh_interval=discovery_data.get("auto_refresh_interval"),
            enable_cross_project_coordination=discovery_data.get(
                "enable_cross_project_coordination", False
            ),
        )

        # Extract onboarding config
        onboarding_data = data.get("onboarding", {})
        onboarding = OnboardingConfig(
            enabled=onboarding_data.get("enabled", True),
            custom_messages=onboarding_data.get("custom_messages"),
            auto_onboard=onboarding_data.get("auto_onboard", False),
        )

        # Extract dashboard config
        dashboard_data = data.get("dashboard", {})
        dashboard = DashboardConfig(
            enabled=dashboard_data.get("enabled", True),
            port=dashboard_data.get("port", 8080),
            host=dashboard_data.get("host", "localhost"),
            auto_open_browser=dashboard_data.get("auto_open_browser", True),
            refresh_interval=dashboard_data.get("refresh_interval", 1),
        )

        # Extract backend config
        backend_data = data.get("backend", {})
        backend = BackendConfig(
            provider=backend_data.get("provider", "auto"),
            message_poll_interval=backend_data.get("message_poll_interval", 5),
        )

        # Extract project root
        project_root = None
        if "project_root" in data and data["project_root"] is not None:
            project_root = Path(data["project_root"])

        return ClaudeSwarmConfig(
            rate_limiting=rate_limiting,
            locking=locking,
            discovery=discovery,
            onboarding=onboarding,
            dashboard=dashboard,
            backend=backend,
            project_root=project_root,
        )
    except Exception as e:
        raise ConfigValidationError(f"Failed to convert dictionary to config: {e}") from e


def load_config(config_path: Path | None = None) -> ClaudeSwarmConfig:
    """Load configuration from file or use defaults.

    Configuration loading order:
    1. If config_path provided, load from that file
    2. Otherwise, search for .claudeswarm.yaml or .claudeswarm.toml
    3. If no file found, use defaults

    Args:
        config_path: Optional explicit path to configuration file

    Returns:
        Loaded and validated configuration

    Raises:
        ConfigValidationError: If configuration is invalid
    """
    # Start with default configuration
    config_dict: dict[str, Any] = {}

    # Determine which file to load
    file_to_load: Path | None = None

    if config_path is not None:
        # Explicit path provided
        file_to_load = Path(config_path)
        if not file_to_load.exists():
            raise ConfigValidationError(f"Configuration file not found: {file_to_load}")
    else:
        # Search for configuration file
        file_to_load = _find_config_file()

    # Load configuration if file found
    if file_to_load is not None:
        suffix = file_to_load.suffix.lower()

        if suffix in (".yaml", ".yml"):
            config_dict = _load_yaml_config(file_to_load)
        elif suffix == ".toml":
            config_dict = _load_toml_config(file_to_load)
        else:
            raise ConfigValidationError(
                f"Unsupported configuration file format: {suffix}. "
                "Supported formats: .yaml, .yml, .toml"
            )

    # Convert to ClaudeSwarmConfig
    config = _dict_to_config(config_dict)

    # Validate configuration
    config.validate()

    return config


# Global configuration singleton
_config_instance: ClaudeSwarmConfig | None = None
_config_lock = threading.Lock()


def get_config() -> ClaudeSwarmConfig:
    """Get singleton configuration instance.

    Lazy-loads configuration on first access. Thread-safe.

    Returns:
        Singleton configuration instance
    """
    global _config_instance

    if _config_instance is None:
        with _config_lock:
            # Double-check pattern
            if _config_instance is None:
                _config_instance = load_config()

    return _config_instance


def reload_config(config_path: Path | None = None) -> ClaudeSwarmConfig:
    """Force reload configuration from disk.

    Thread-safe. Useful for testing or when configuration file changes.

    Args:
        config_path: Optional explicit path to configuration file

    Returns:
        Newly loaded configuration instance

    Raises:
        ConfigValidationError: If configuration is invalid
    """
    global _config_instance

    with _config_lock:
        _config_instance = load_config(config_path)
        return _config_instance
