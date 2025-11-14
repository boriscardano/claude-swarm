# Agent Discovery Logging Guide

## Quick Start

Enable debug logging to see detailed information about agent discovery and project filtering:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from claudeswarm.discovery import discover_agents
registry = discover_agents()
```

## Log Levels Used

### DEBUG (Detailed Information)
- Process CWD detection for each agent
- Project filtering decisions
- Agent discovery start/completion
- Registry loading/saving
- Stale/dead agent processing
- Filtering statistics

### INFO (High-Level Summary)
- Final discovery results with counts
- Overall success/failure status

### WARNING (Non-Fatal Errors)
- lsof command timeouts
- Process CWD query failures
- Invalid timestamp parsing errors

## Logging Flow

```
Agent Discovery Starts
  ↓
[DEBUG] Starting agent discovery (parameters)
[DEBUG] Loaded existing registry (or starting fresh)
  ↓
[DEBUG] Found N total tmux panes
[DEBUG] Filtered to N panes in session (if filtered)
[DEBUG] Project root: /path/to/project
  ↓
For Each Pane:
  ↓
  [DEBUG] Found Claude Code process (or skipped)
  [DEBUG] Process PID CWD: /path (or error)
  [DEBUG] Working in/outside project (filtering decision)
  [DEBUG] Added agent (or excluded with reason)
  ↓
[DEBUG] Project filtering summary (statistics)
  ↓
For Each Stale Agent:
  ↓
  [DEBUG] Marked as stale (or removed)
  [WARNING] Invalid timestamp (if applicable)
  ↓
[INFO] Agent discovery complete: X active, Y stale, Z removed
```

## Example Debug Session

```bash
$ python3 test_logging.py
======================================================================
Agent Discovery with Debug Logging
======================================================================

DEBUG:claudeswarm.discovery:Starting agent discovery (session_name=None, stale_threshold=300s)
DEBUG:claudeswarm.discovery:Loaded existing registry with 2 agents
DEBUG:claudeswarm.discovery:Found 8 total tmux panes
DEBUG:claudeswarm.discovery:Project root: /Users/boris/work/aspire11/claude-swarm
DEBUG:claudeswarm.discovery:Found Claude Code process in pane main:1.0 (PID: 12345)
DEBUG:claudeswarm.discovery:Process 12345 CWD: /Users/boris/work/aspire11/claude-swarm
DEBUG:claudeswarm.discovery:Process 12345: Working in project (CWD: /Users/boris/work/aspire11/claude-swarm)
DEBUG:claudeswarm.discovery:Added agent agent-0 for pane main:1.0 (PID: 12345)
DEBUG:claudeswarm.discovery:Found Claude Code process in pane main:1.1 (PID: 67890)
DEBUG:claudeswarm.discovery:Process 67890 CWD: /Users/boris/work/other-project
DEBUG:claudeswarm.discovery:Process 67890: Working outside project (CWD: /Users/boris/work/other-project, Project: /Users/boris/work/aspire11/claude-swarm)
DEBUG:claudeswarm.discovery:Agent in pane main:1.1 excluded: working outside project (CWD: /Users/boris/work/other-project)
DEBUG:claudeswarm.discovery:Project filtering summary: 2 Claude processes found, 1 in project, 1 outside project, 0 with unknown CWD
INFO:claudeswarm.discovery:Agent discovery complete: 1 active, 0 stale, 1 removed

======================================================================
Discovery Summary
======================================================================
Total agents: 1
Active agents: 1
Stale agents: 0

Discovered Agents:
  - agent-0: main:1.0 (PID: 12345, Status: active)
```

## Common Debug Patterns

### Agent Filtered by Project Directory

```
DEBUG:claudeswarm.discovery:Found Claude Code process in pane main:1.1 (PID: 67890)
DEBUG:claudeswarm.discovery:Process 67890 CWD: /Users/user/other-project
DEBUG:claudeswarm.discovery:Process 67890: Working outside project (CWD: /Users/user/other-project, Project: /Users/user/current-project)
DEBUG:claudeswarm.discovery:Agent in pane main:1.1 excluded: working outside project (CWD: /Users/user/other-project)
```

**Interpretation**: Agent is running in a different project directory and was filtered out.

### CWD Detection Failed

```
DEBUG:claudeswarm.discovery:Found Claude Code process in pane main:1.2 (PID: 45678)
DEBUG:claudeswarm.discovery:Could not determine CWD for process 45678 (lsof returned 1)
DEBUG:claudeswarm.discovery:Process 45678: Could not determine CWD, excluding from project
DEBUG:claudeswarm.discovery:Agent in pane main:1.2 excluded: could not determine CWD
```

**Interpretation**: Unable to determine process working directory (lsof failed or not available).

### Platform Not Supported

```
DEBUG:claudeswarm.discovery:lsof not found on system - CWD detection unavailable
DEBUG:claudeswarm.discovery:Process 12345: Could not determine CWD, excluding from project
```

**Interpretation**: Platform doesn't support CWD detection (e.g., Linux without /proc support).

### Timeout During CWD Detection

```
WARNING:claudeswarm.discovery:Timeout while getting CWD for process 12345
DEBUG:claudeswarm.discovery:Process 12345: Could not determine CWD, excluding from project
```

**Interpretation**: lsof command took too long and timed out (> 2 seconds).

## Debugging Common Issues

### No Agents Discovered

1. **Enable debug logging** to see what's happening
2. **Check for Claude processes**: Look for "Found Claude Code process" messages
3. **Check CWD detection**: Look for process CWD messages
4. **Check filtering**: Look for "Working in/outside project" messages

### Agents Not Filtered by Project

1. **Verify platform support**: Check for lsof availability
2. **Check project root**: Verify the detected project root is correct
3. **Look for CWD messages**: Ensure process CWDs are being detected

### Slow Discovery

1. **Check for timeouts**: Look for WARNING messages about timeouts
2. **Count panes**: Large number of panes increases discovery time
3. **Monitor lsof performance**: Each process requires an lsof call

## Logging Configuration

### Using Python's logging module

```python
import logging

# Basic configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Or configure specific logger
logger = logging.getLogger('claudeswarm.discovery')
logger.setLevel(logging.DEBUG)
```

### Using environment variables (if supported)

```bash
# Set log level
export CLAUDESWARM_LOG_LEVEL=DEBUG

# Run commands
claudeswarm discover-agents
```

## Performance Considerations

- **DEBUG logging** can generate significant output with many panes
- **Each lsof call** takes ~100ms on average
- **Discovery with 10 panes** typically takes 1-2 seconds
- Consider using **INFO level** for production use

## Best Practices

1. **Use DEBUG during development** to understand filtering behavior
2. **Use INFO in production** for basic monitoring
3. **Monitor WARNING logs** to catch intermittent errors
4. **Review logs regularly** to identify patterns
5. **Include logs in bug reports** for troubleshooting
