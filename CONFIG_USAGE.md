# Configuration System Usage Guide

The Claude Swarm configuration system provides centralized, type-safe configuration management for all components.

## Quick Start

### Using Default Configuration

The simplest way to use Claude Swarm is with default settings:

```python
from claudeswarm.config import get_config

config = get_config()
print(f"Rate limit: {config.rate_limiting.messages_per_minute}")
```

### Creating a Configuration File

Create `.claudeswarm.yaml` or `.claudeswarm.toml` in your project root:

**YAML Format (.claudeswarm.yaml):**
```yaml
rate_limiting:
  messages_per_minute: 20
  window_seconds: 60

locking:
  stale_timeout: 600
  auto_cleanup: true
  default_reason: "working"

discovery:
  stale_threshold: 90
  auto_refresh_interval: 30

onboarding:
  enabled: true
  custom_messages:
    - "Welcome to the team!"
    - "Check out COORDINATION.md"
  auto_onboard: false
```

**TOML Format (.claudeswarm.toml):**
```toml
[rate_limiting]
messages_per_minute = 20
window_seconds = 60

[locking]
stale_timeout = 600
auto_cleanup = true
default_reason = "working"

[discovery]
stale_threshold = 90
auto_refresh_interval = 30

[onboarding]
enabled = true
custom_messages = ["Welcome to the team!", "Check out COORDINATION.md"]
auto_onboard = false
```

## Configuration Options

### Rate Limiting (`rate_limiting`)

Controls message rate limiting to prevent spam:

- `messages_per_minute` (int, default: 10): Maximum messages per agent per window
  - Range: 1-1000
- `window_seconds` (int, default: 60): Time window for rate limiting
  - Range: 1-3600

### Locking (`locking`)

Controls distributed file locking behavior:

- `stale_timeout` (int, default: 300): Seconds before a lock is considered stale
  - Range: 60-86400 (1 minute to 24 hours)
- `auto_cleanup` (bool, default: false): Automatically clean up stale locks
- `default_reason` (str, default: "working"): Default reason for lock acquisition
  - Max length: 100 characters

### Discovery (`discovery`)

Controls agent discovery and registry:

- `stale_threshold` (int, default: 60): Seconds before agent is considered stale
  - Range: 10-3600
- `auto_refresh_interval` (int, optional): Automatic refresh interval in seconds
  - If null/unset, auto-refresh is disabled
  - Minimum: 5 seconds

### Onboarding (`onboarding`)

Controls agent onboarding system:

- `enabled` (bool, default: true): Whether onboarding is enabled
- `custom_messages` (list[str], optional): Custom onboarding messages
  - Max 100 messages
  - Each message max 1000 characters
- `auto_onboard` (bool, default: false): Automatically onboard new agents

### Project Root (`project_root`)

Optional project root directory path:

- If unset, automatically detected from current working directory
- Must be a valid, existing directory

## API Usage

### Loading Configuration

```python
from claudeswarm.config import load_config
from pathlib import Path

# Load from default location or use defaults
config = load_config()

# Load from specific file
config = load_config(Path("custom_config.yaml"))
```

### Singleton Pattern

For application-wide configuration:

```python
from claudeswarm.config import get_config

# First call loads and caches
config = get_config()

# Subsequent calls return same instance
config2 = get_config()
assert config is config2
```

### Reloading Configuration

Useful for testing or hot-reload scenarios:

```python
from claudeswarm.config import reload_config

# Force reload from disk
config = reload_config()
```

### Validation

Configuration is automatically validated on load, but you can also validate manually:

```python
from claudeswarm.config import ClaudeSwarmConfig, ConfigValidationError

config = ClaudeSwarmConfig()
config.rate_limiting.messages_per_minute = 0  # Invalid

try:
    config.validate()
except ConfigValidationError as e:
    print(f"Validation failed: {e}")
```

### Converting to Dictionary

Useful for serialization or debugging:

```python
config = get_config()
config_dict = config.to_dict()
print(config_dict)
```

## File Format Support

The configuration system supports multiple formats:

### YAML (.yaml, .yml)
- Requires: `pip install pyyaml`
- Recommended for readability
- Preferred format when both available

### TOML (.toml)
- Requires: Python 3.11+ or `pip install tomli`
- Native support in Python 3.11+
- Good for version control

## Configuration File Discovery

The system searches for configuration files in this order:

1. Explicit path provided to `load_config(path)`
2. `.claudeswarm.yaml` in current directory
3. `.claudeswarm.toml` in current directory
4. Parent directories (walking up the tree)
5. Default values if no file found

## Error Handling

### Configuration Validation Errors

```python
from claudeswarm.config import ConfigValidationError

try:
    config = load_config()
except ConfigValidationError as e:
    print(f"Invalid configuration: {e}")
```

Common validation errors:
- Values out of range (e.g., negative timeouts)
- Empty required fields
- Invalid file paths
- Type mismatches

## Best Practices

1. **Use Configuration Files**: Don't hardcode settings in your code
2. **Version Control**: Check in `.claudeswarm.yaml.example`, not actual config
3. **Validate Early**: Let configuration load fail at startup, not during runtime
4. **Use Singleton**: Call `get_config()` instead of `load_config()` repeatedly
5. **Document Changes**: Comment your configuration file thoroughly

## Examples

### Development Configuration

For rapid development with relaxed limits:

```yaml
rate_limiting:
  messages_per_minute: 50
  window_seconds: 60

locking:
  stale_timeout: 120
  auto_cleanup: true

discovery:
  stale_threshold: 30
  auto_refresh_interval: 10
```

### Production Configuration

For stable production with strict controls:

```yaml
rate_limiting:
  messages_per_minute: 10
  window_seconds: 60

locking:
  stale_timeout: 600
  auto_cleanup: false

discovery:
  stale_threshold: 120
  auto_refresh_interval: 60
```

### Testing Configuration

For unit/integration tests:

```python
from claudeswarm.config import ClaudeSwarmConfig, RateLimitConfig

# Create test config programmatically
config = ClaudeSwarmConfig(
    rate_limiting=RateLimitConfig(
        messages_per_minute=100,
        window_seconds=10
    )
)
```

## Integration with Other Modules

The configuration system is designed to be used by all Claude Swarm modules:

```python
from claudeswarm.config import get_config

# In messaging.py
config = get_config()
rate_limiter = RateLimiter(
    max_messages=config.rate_limiting.messages_per_minute,
    window_seconds=config.rate_limiting.window_seconds
)

# In locking.py
STALE_LOCK_TIMEOUT = get_config().locking.stale_timeout

# In discovery.py
registry = discover_agents(
    stale_threshold=get_config().discovery.stale_threshold
)
```

## Thread Safety

The singleton pattern is thread-safe using double-checked locking:

```python
# Safe to call from multiple threads
config = get_config()
```

The configuration object itself is immutable after creation, making it safe to share across threads.
