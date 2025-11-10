# Claude Swarm CLI Usage

Quick reference for Claude Swarm command-line interface.

## Configuration Commands

### `claudeswarm config init`

Create a default configuration file.

```bash
# Create .claudeswarm.yaml with defaults
claudeswarm config init

# Create with custom name
claudeswarm config init -o my-config.yaml

# Create TOML format
claudeswarm config init -o .claudeswarm.toml

# Overwrite existing file
claudeswarm config init --force
```

**Options:**
- `-o, --output PATH` - Output path (default: .claudeswarm.yaml)
- `-f, --force` - Overwrite existing file

**Exit codes:**
- 0: Success
- 1: Error (file exists without --force, write error, etc.)

---

### `claudeswarm config show`

Display current configuration.

```bash
# Show current config (searches for file)
claudeswarm config show

# Show specific file
claudeswarm config show --file custom-config.yaml

# Output as JSON
claudeswarm config show --json
```

**Options:**
- `--file PATH` - Path to config file (default: search for .claudeswarm.yaml)
- `--json` - Output as JSON instead of human-readable format

**Exit codes:**
- 0: Success
- 1: Error loading config

**Output:**
```
Configuration source: /path/to/.claudeswarm.yaml

rate_limiting:
  messages_per_minute: 10
  window_seconds: 60

locking:
  stale_timeout: 300
  auto_cleanup: false
  default_reason: working

...
```

---

### `claudeswarm config validate`

Validate configuration file syntax and values.

```bash
# Validate default config file
claudeswarm config validate

# Validate specific file
claudeswarm config validate --file custom-config.yaml
```

**Options:**
- `--file PATH` - Path to config file (default: search for .claudeswarm.yaml)

**Exit codes:**
- 0: Configuration is valid
- 1: Validation failed

**Output (valid):**
```
Validating: /path/to/.claudeswarm.yaml

✓ Syntax: Valid
✓ Values: Valid

Config file is valid: /path/to/.claudeswarm.yaml
```

**Output (invalid):**
```
Validating: /path/to/.claudeswarm.yaml

✓ Syntax: Valid
✗ Values: Invalid

Validation errors:
  - rate_limiting.messages_per_minute must be > 0
  - locking.stale_timeout must be >= 60
```

---

### `claudeswarm config edit`

Open configuration file in editor.

```bash
# Edit default config file (uses $EDITOR)
claudeswarm config edit

# Edit specific file
claudeswarm config edit --file custom-config.yaml
```

**Options:**
- `--file PATH` - Path to config file (default: search for .claudeswarm.yaml)

**Behavior:**
- Uses `$EDITOR` environment variable
- Falls back to vim, vi, nano, or emacs (in that order)
- Creates file if it doesn't exist
- Prompts to validate after saving

**Exit codes:**
- 0: Editor exited successfully
- 1: No editor found or edit failed

**Environment variables:**
- `EDITOR` - Preferred text editor (e.g., `export EDITOR=vim`)

---

## Configuration File Format

### YAML Format (.claudeswarm.yaml)

```yaml
rate_limiting:
  messages_per_minute: 10
  window_seconds: 60

locking:
  stale_timeout: 300
  auto_cleanup: false
  default_reason: "working"

discovery:
  stale_threshold: 60
  auto_refresh_interval: null

onboarding:
  enabled: true
  custom_messages: null
  auto_onboard: false

project_root: null
```

### TOML Format (.claudeswarm.toml)

```toml
[rate_limiting]
messages_per_minute = 10
window_seconds = 60

[locking]
stale_timeout = 300
auto_cleanup = false
default_reason = "working"

[discovery]
stale_threshold = 60
auto_refresh_interval = null

[onboarding]
enabled = true
custom_messages = null
auto_onboard = false

project_root = null
```

---

## Common Workflows

### First-Time Setup

```bash
# 1. Create default config
claudeswarm config init

# 2. View what was created
claudeswarm config show

# 3. Edit for your needs
claudeswarm config edit

# 4. Validate changes
claudeswarm config validate
```

### Using Example Configs

```bash
# 1. Copy an example
cp examples/configs/small-team.yaml .claudeswarm.yaml

# 2. Customize
claudeswarm config edit

# 3. Validate
claudeswarm config validate

# 4. View final config
claudeswarm config show
```

### Troubleshooting Config

```bash
# 1. Check if config exists
claudeswarm config show
# If "defaults (no config file found)", create one

# 2. Validate config
claudeswarm config validate

# 3. Fix errors
claudeswarm config edit

# 4. Validate again
claudeswarm config validate
```

### Switching Between Configs

```bash
# Show current (searches for .claudeswarm.yaml)
claudeswarm config show

# Show specific config
claudeswarm config show --file dev-config.yaml

# Switch configs by renaming
mv .claudeswarm.yaml .claudeswarm.yaml.prod
mv dev-config.yaml .claudeswarm.yaml

# Or use explicit file with other commands
claudeswarm --config dev-config.yaml discover-agents
```

---

## Configuration Search Order

Claude Swarm searches for configuration files in this order:

1. Explicit path: `--file PATH` argument
2. Current directory: `.claudeswarm.yaml`
3. Current directory: `.claudeswarm.toml`
4. Parent directories (walking up to root)
5. Built-in defaults (if no file found)

---

## Examples

### Minimal Config (Override One Setting)

```yaml
rate_limiting:
  messages_per_minute: 20
```

All other settings use defaults.

### Small Team Config

```yaml
rate_limiting:
  messages_per_minute: 15

locking:
  stale_timeout: 180
  auto_cleanup: true

discovery:
  stale_threshold: 45
  auto_refresh_interval: 20
```

### Large Team Config

```yaml
rate_limiting:
  messages_per_minute: 8

locking:
  stale_timeout: 600

discovery:
  stale_threshold: 90
  auto_refresh_interval: 45

onboarding:
  custom_messages:
    - "Large team coordination active"
    - "Follow structured workflows"
```

### Strict/Secure Config

```yaml
rate_limiting:
  messages_per_minute: 3

locking:
  stale_timeout: 1800
  auto_cleanup: false

discovery:
  auto_refresh_interval: null

onboarding:
  auto_onboard: false
```

---

## Integration with Other Commands

All Claude Swarm commands respect the configuration file:

```bash
# Discovery uses discovery.stale_threshold
claudeswarm discover-agents

# Locking uses locking.stale_timeout
claudeswarm acquire-file-lock myfile.py agent-1 "editing"

# Onboarding uses onboarding settings
claudeswarm onboard
```

---

## Dependencies

Configuration file support requires:

- **YAML**: `pip install pyyaml`
- **TOML**: Built-in for Python 3.11+, or `pip install tomli tomli-w` for earlier versions

Install both:
```bash
pip install pyyaml tomli tomli-w
```

---

## See Also

- [Configuration Guide](CONFIGURATION.md) - Complete reference
- [Integration Guide](INTEGRATION_GUIDE.md) - Setup instructions
- [Tutorial](TUTORIAL.md) - Step-by-step guide
- [Quick Reference](QUICK_REFERENCE.md) - Command cheat sheet
