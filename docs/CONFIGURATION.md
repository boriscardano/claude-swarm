# Claude Swarm Configuration Guide

Complete reference for configuring Claude Swarm coordination system.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration File Format](#configuration-file-format)
3. [Configuration Options](#configuration-options)
4. [Example Configurations](#example-configurations)
5. [When to Customize](#when-to-customize)
6. [CLI Commands](#cli-commands)

---

## Quick Start

### Create Default Config

```bash
# Create .claudeswarm.yaml with defaults
claudeswarm config init

# View current configuration
claudeswarm config show

# Edit configuration
claudeswarm config edit

# Validate configuration
claudeswarm config validate
```

### File Locations

Claude Swarm searches for configuration files in the following order:

1. Current directory: `.claudeswarm.yaml` or `.claudeswarm.toml`
2. Parent directories (walking up to root)
3. If no file found, uses built-in defaults

### Supported Formats

- **YAML** (recommended): `.claudeswarm.yaml` or `.claudeswarm.yml`
- **TOML**: `.claudeswarm.toml`

---

## Configuration File Format

### YAML Example

```yaml
rate_limit:
  messages_per_minute: 10
  burst_size: 3
  cooldown_seconds: 60

lock:
  stale_threshold_seconds: 300
  max_lock_age_seconds: 3600
  auto_cleanup: true
  retry_attempts: 3
  retry_delay_seconds: 1

discovery:
  stale_threshold_seconds: 60
  auto_refresh_interval: 30
  require_tmux: true

ack:
  timeout_seconds: 30
  retry_attempts: 3
  retry_delay_seconds: 10
  escalate_to_all: true

monitoring:
  log_file: agent_messages.log
  log_level: INFO
  enable_dashboard: true
  dashboard_refresh_seconds: 2

coordination:
  file_path: COORDINATION.md
  auto_create: true
  template_sections:
    - Sprint Goals
    - Current Work
    - Blocked Items
    - Code Review Queue
    - Decisions

project_root: null
```

### TOML Example

```toml
[rate_limit]
messages_per_minute = 10
burst_size = 3
cooldown_seconds = 60

[lock]
stale_threshold_seconds = 300
max_lock_age_seconds = 3600
auto_cleanup = true
retry_attempts = 3
retry_delay_seconds = 1

[discovery]
stale_threshold_seconds = 60
auto_refresh_interval = 30
require_tmux = true

[ack]
timeout_seconds = 30
retry_attempts = 3
retry_delay_seconds = 10
escalate_to_all = true

[monitoring]
log_file = "agent_messages.log"
log_level = "INFO"
enable_dashboard = true
dashboard_refresh_seconds = 2

[coordination]
file_path = "COORDINATION.md"
auto_create = true
template_sections = [
    "Sprint Goals",
    "Current Work",
    "Blocked Items",
    "Code Review Queue",
    "Decisions"
]

project_root = null
```

---

## Configuration Options

### Rate Limit Configuration

Controls messaging rate limits to prevent overwhelming agents.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `messages_per_minute` | int | 10 | Maximum messages per minute per agent |
| `burst_size` | int | 3 | Number of messages allowed in a burst |
| `cooldown_seconds` | int | 60 | Cooldown period after rate limit hit |

**Example:**
```yaml
rate_limit:
  messages_per_minute: 20    # Double the rate for faster workflows
  burst_size: 5              # Allow larger bursts
  cooldown_seconds: 30       # Shorter cooldown
```

**When to adjust:**
- **Increase** for fast-paced development with frequent communication
- **Decrease** for slower, more deliberate coordination
- **Increase burst_size** when broadcasting to many agents

---

### Lock Configuration

Controls file locking behavior and stale lock cleanup.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `stale_threshold_seconds` | int | 300 | When a lock is considered stale (5 min) |
| `max_lock_age_seconds` | int | 3600 | Maximum lock age before forced cleanup (1 hour) |
| `auto_cleanup` | bool | true | Automatically clean up stale locks |
| `retry_attempts` | int | 3 | Retries for lock acquisition |
| `retry_delay_seconds` | int | 1 | Delay between retry attempts |

**Example:**
```yaml
lock:
  stale_threshold_seconds: 600    # 10 minutes (longer edits)
  max_lock_age_seconds: 1800      # 30 minutes max
  auto_cleanup: true
  retry_attempts: 5               # More retries
  retry_delay_seconds: 2          # Longer delays
```

**When to adjust:**
- **Increase stale_threshold** for complex refactoring tasks
- **Decrease stale_threshold** for fast-paced work
- **Disable auto_cleanup** if you want manual control
- **Increase retry_attempts** in high-contention scenarios

---

### Discovery Configuration

Controls agent discovery and registry management.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `stale_threshold_seconds` | int | 60 | When an agent is considered stale |
| `auto_refresh_interval` | int | 30 | Auto-refresh interval in seconds |
| `require_tmux` | bool | true | Require tmux for discovery |

**Example:**
```yaml
discovery:
  stale_threshold_seconds: 120    # 2 minutes (longer timeout)
  auto_refresh_interval: 60       # Refresh every minute
  require_tmux: true
```

**When to adjust:**
- **Increase stale_threshold** for agents that pause frequently
- **Decrease auto_refresh_interval** for real-time coordination
- **Set require_tmux to false** for testing/CI environments

---

### Acknowledgment Configuration

Controls message acknowledgment and retry behavior.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `timeout_seconds` | int | 30 | Seconds to wait for ACK |
| `retry_attempts` | int | 3 | Retries before escalation |
| `retry_delay_seconds` | int | 10 | Delay between retries |
| `escalate_to_all` | bool | true | Escalate unacked messages to all agents |

**Example:**
```yaml
ack:
  timeout_seconds: 60          # Wait longer for ACK
  retry_attempts: 5            # More retries
  retry_delay_seconds: 15      # Longer delays
  escalate_to_all: true        # Always escalate
```

**When to adjust:**
- **Increase timeout** for slower agents or complex tasks
- **Increase retry_attempts** for critical coordination
- **Disable escalate_to_all** to avoid broadcast spam

---

### Monitoring Configuration

Controls logging and monitoring dashboard.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `log_file` | str | "agent_messages.log" | Path to message log file |
| `log_level` | str | "INFO" | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `enable_dashboard` | bool | true | Enable monitoring dashboard |
| `dashboard_refresh_seconds` | int | 2 | Dashboard refresh interval |

**Valid log levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL

**Example:**
```yaml
monitoring:
  log_file: logs/swarm.log       # Custom log location
  log_level: DEBUG               # Verbose logging
  enable_dashboard: true
  dashboard_refresh_seconds: 1   # Faster refresh
```

**When to adjust:**
- **Set log_level to DEBUG** for troubleshooting
- **Change log_file** to organize logs
- **Disable dashboard** to save resources
- **Decrease refresh** for real-time monitoring

---

### Coordination Configuration

Controls shared coordination file (COORDINATION.md).

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `file_path` | str | "COORDINATION.md" | Path to coordination file |
| `auto_create` | bool | true | Create file if missing |
| `template_sections` | list | See below | Default sections |

**Default sections:**
- Sprint Goals
- Current Work
- Blocked Items
- Code Review Queue
- Decisions

**Example:**
```yaml
coordination:
  file_path: docs/TEAM_SYNC.md
  auto_create: true
  template_sections:
    - Sprint Goals
    - Active Tasks
    - Blockers
    - Review Queue
    - Decisions
    - Archived
```

**When to adjust:**
- **Change file_path** to match your project structure
- **Modify template_sections** for your workflow
- **Disable auto_create** if you want manual setup

---

### Project Root

Optional project root directory. Defaults to current directory if not specified.

```yaml
project_root: /path/to/project
```

---

## Example Configurations

### Small Team (2-3 Agents)

Optimized for close collaboration with minimal overhead.

```yaml
# .claudeswarm.yaml - Small Team Configuration

rate_limit:
  messages_per_minute: 15       # More frequent communication
  burst_size: 5                 # Larger bursts for rapid exchanges
  cooldown_seconds: 30          # Quick recovery

lock:
  stale_threshold_seconds: 180  # 3 minutes (quick edits)
  max_lock_age_seconds: 900     # 15 minutes max
  auto_cleanup: true
  retry_attempts: 2             # Fewer retries (low contention)
  retry_delay_seconds: 1

discovery:
  stale_threshold_seconds: 45   # Faster stale detection
  auto_refresh_interval: 20     # Frequent refreshes
  require_tmux: true

ack:
  timeout_seconds: 20           # Quick responses expected
  retry_attempts: 2             # Fewer retries needed
  retry_delay_seconds: 5
  escalate_to_all: true         # Always escalate (small team)

monitoring:
  log_file: agent_messages.log
  log_level: INFO
  enable_dashboard: true
  dashboard_refresh_seconds: 1  # Real-time updates

coordination:
  file_path: COORDINATION.md
  auto_create: true
  template_sections:
    - Current Sprint
    - Who's Working On What
    - Blockers
    - Quick Decisions
```

**Best for:**
- 2-3 agents
- Fast-paced development
- Close collaboration
- Quick turnaround times

---

### Large Team (10+ Agents)

Optimized for scale with stricter rate limits and longer timeouts.

```yaml
# .claudeswarm.yaml - Large Team Configuration

rate_limit:
  messages_per_minute: 8        # Lower rate (more agents)
  burst_size: 2                 # Smaller bursts
  cooldown_seconds: 90          # Longer cooldown

lock:
  stale_threshold_seconds: 600  # 10 minutes (complex work)
  max_lock_age_seconds: 3600    # 1 hour max
  auto_cleanup: true
  retry_attempts: 5             # More retries (high contention)
  retry_delay_seconds: 3        # Longer delays

discovery:
  stale_threshold_seconds: 90   # Tolerate slower agents
  auto_refresh_interval: 45     # Less frequent refreshes
  require_tmux: true

ack:
  timeout_seconds: 45           # Longer timeout (more agents)
  retry_attempts: 4             # More retries
  retry_delay_seconds: 15       # Longer delays
  escalate_to_all: false        # Avoid broadcast spam

monitoring:
  log_file: agent_messages.log
  log_level: INFO
  enable_dashboard: true
  dashboard_refresh_seconds: 3  # Slower refresh (save resources)

coordination:
  file_path: COORDINATION.md
  auto_create: true
  template_sections:
    - Sprint Goals
    - Team A Tasks
    - Team B Tasks
    - Cross-Team Blockers
    - Integration Points
    - Architectural Decisions
    - Review Queue
```

**Best for:**
- 10+ agents
- Complex projects
- Multiple sub-teams
- Structured coordination

---

### High-Security Project

Stricter settings with manual controls and verbose logging.

```yaml
# .claudeswarm.yaml - High-Security Configuration

rate_limit:
  messages_per_minute: 5        # Very restrictive
  burst_size: 1                 # No bursts
  cooldown_seconds: 120         # Long cooldown

lock:
  stale_threshold_seconds: 900  # 15 minutes (deliberate work)
  max_lock_age_seconds: 7200    # 2 hours max
  auto_cleanup: false           # Manual cleanup only
  retry_attempts: 1             # No automatic retries
  retry_delay_seconds: 5

discovery:
  stale_threshold_seconds: 120  # Longer timeout
  auto_refresh_interval: 60     # Less frequent
  require_tmux: true

ack:
  timeout_seconds: 60           # Long timeout
  retry_attempts: 5             # Many retries (critical)
  retry_delay_seconds: 20
  escalate_to_all: true         # Always escalate

monitoring:
  log_file: secure/audit.log    # Separate audit log
  log_level: DEBUG              # Verbose logging
  enable_dashboard: true
  dashboard_refresh_seconds: 5

coordination:
  file_path: COORDINATION.md
  auto_create: false            # Manual creation
  template_sections:
    - Security Review Tasks
    - Code Review Queue
    - Security Decisions
    - Audit Trail
```

**Best for:**
- Security-critical projects
- Compliance requirements
- Detailed audit trails
- Manual oversight

---

### Fast-Paced Development

Optimized for rapid iteration and quick feedback.

```yaml
# .claudeswarm.yaml - Fast-Paced Configuration

rate_limit:
  messages_per_minute: 25       # High rate
  burst_size: 8                 # Large bursts
  cooldown_seconds: 20          # Quick recovery

lock:
  stale_threshold_seconds: 120  # 2 minutes
  max_lock_age_seconds: 600     # 10 minutes max
  auto_cleanup: true
  retry_attempts: 3
  retry_delay_seconds: 0.5      # Very quick retries

discovery:
  stale_threshold_seconds: 30   # Fast stale detection
  auto_refresh_interval: 15     # Very frequent refreshes
  require_tmux: true

ack:
  timeout_seconds: 15           # Quick timeout
  retry_attempts: 2
  retry_delay_seconds: 3
  escalate_to_all: true

monitoring:
  log_file: agent_messages.log
  log_level: WARNING            # Less verbose
  enable_dashboard: true
  dashboard_refresh_seconds: 1  # Real-time

coordination:
  file_path: COORDINATION.md
  auto_create: true
  template_sections:
    - Current Sprint
    - In Progress
    - Done Today
    - Quick Notes
```

**Best for:**
- Hackathons
- Prototyping
- Rapid iteration
- Continuous deployment

---

### Strict/Conservative

Very conservative settings with manual controls.

```yaml
# .claudeswarm.yaml - Strict Configuration

rate_limit:
  messages_per_minute: 3        # Very low rate
  burst_size: 1                 # No bursts
  cooldown_seconds: 180         # 3 minute cooldown

lock:
  stale_threshold_seconds: 1800 # 30 minutes
  max_lock_age_seconds: 7200    # 2 hours
  auto_cleanup: false           # Manual only
  retry_attempts: 0             # No retries
  retry_delay_seconds: 10

discovery:
  stale_threshold_seconds: 180  # 3 minutes
  auto_refresh_interval: 120    # Every 2 minutes
  require_tmux: true

ack:
  timeout_seconds: 120          # 2 minute timeout
  retry_attempts: 6             # Many retries
  retry_delay_seconds: 30
  escalate_to_all: true

monitoring:
  log_file: agent_messages.log
  log_level: DEBUG              # Full logging
  enable_dashboard: true
  dashboard_refresh_seconds: 10 # Slow refresh

coordination:
  file_path: COORDINATION.md
  auto_create: false            # Manual creation
  template_sections:
    - Sprint Goals
    - Current Work
    - Blockers
    - Decisions
    - Changelog
```

**Best for:**
- Regulated industries
- Mission-critical systems
- Teams requiring strict oversight
- Learning/training environments

---

## When to Customize

### You Should Customize If...

1. **Team Size Changes**
   - Small team (2-3): Increase rates, decrease timeouts
   - Large team (10+): Decrease rates, increase timeouts

2. **Work Style Changes**
   - Fast-paced: Higher rates, shorter timeouts
   - Deliberate: Lower rates, longer timeouts

3. **Project Type**
   - Prototype: Relaxed settings
   - Production: Stricter settings
   - Security: Very strict settings

4. **Performance Issues**
   - Too many rate limit errors: Increase `messages_per_minute`
   - Too many stale locks: Decrease `stale_threshold_seconds`
   - Dashboard lag: Increase `dashboard_refresh_seconds`

5. **Workflow Conflicts**
   - Frequent lock conflicts: Increase `retry_attempts` and `stale_threshold`
   - Missed messages: Enable escalation, increase retries

### You Can Keep Defaults If...

- Team of 3-5 agents
- Moderate pace development
- Standard file locking needs
- No special security requirements
- Using built-in monitoring

---

## CLI Commands

### Initialize Config

```bash
# Create default config
claudeswarm config init

# Create with custom name
claudeswarm config init -o my-config.yaml

# Overwrite existing
claudeswarm config init --force

# Create TOML format
claudeswarm config init -o .claudeswarm.toml
```

### Show Config

```bash
# Show current config
claudeswarm config show

# Show specific file
claudeswarm config show --file custom-config.yaml

# Output as JSON
claudeswarm config show --json
```

### Validate Config

```bash
# Validate current config
claudeswarm config validate

# Validate specific file
claudeswarm config validate --file custom-config.yaml
```

### Edit Config

```bash
# Edit with $EDITOR
claudeswarm config edit

# Edit specific file
claudeswarm config edit --file custom-config.yaml
```

---

## Troubleshooting

### Config Not Found

```bash
# Check search path
claudeswarm config show
# Output: "Configuration source: defaults (no config file found)"

# Create config
claudeswarm config init
```

### Validation Errors

```bash
$ claudeswarm config validate
Validating: .claudeswarm.yaml

✗ Syntax: Invalid - rate_limit.messages_per_minute must be >= 1

# Fix the error in your config file
claudeswarm config edit

# Validate again
claudeswarm config validate
```

### Format Errors

```yaml
# Bad YAML syntax
rate_limit
  messages_per_minute: 10  # Missing colon after rate_limit

# Good YAML syntax
rate_limit:
  messages_per_minute: 10
```

### Dependencies

Install required libraries for config formats:

```bash
# For YAML support
pip install pyyaml

# For TOML support
pip install tomli tomli-w

# Install both
pip install pyyaml tomli tomli-w
```

---

## Best Practices

1. **Start with defaults** - Only customize what you need
2. **Version control** - Commit `.claudeswarm.yaml` to share team settings
3. **Document changes** - Add comments explaining customizations
4. **Validate often** - Run `config validate` after editing
5. **Test incrementally** - Change one setting at a time
6. **Use examples** - Start from provided examples and adjust

---

## Related Documentation

- [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) - Integration instructions
- [TUTORIAL.md](TUTORIAL.md) - Step-by-step tutorial
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Command reference
- [README.md](../README.md) - Main documentation

---

## Summary

Configuration in Claude Swarm is **optional but powerful**:

- **No config needed** - Sensible defaults work for most teams
- **Easy to customize** - Change only what you need
- **Multiple formats** - YAML or TOML
- **Validation built-in** - Catch errors before runtime
- **Team-specific** - Share config via version control

Start with defaults, customize as needed, and iterate based on your team's workflow!
