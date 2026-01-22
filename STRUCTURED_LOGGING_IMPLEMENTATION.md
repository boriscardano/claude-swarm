# Structured Logging Implementation

## Overview

This document summarizes the implementation of structured logging throughout the claude-swarm codebase to provide consistent, production-ready logging for monitoring and debugging.

## Changes Made

### 1. Created Central Logging Configuration (`src/claudeswarm/logging_config.py`)

**New module** providing centralized logging setup:

```python
from claudeswarm.logging_config import setup_logging, get_logger

# Initialize logging (typically in CLI entry point)
setup_logging(level="INFO", log_file="/path/to/log.log")

# Get module-specific logger
logger = get_logger(__name__)
logger.info("Operation completed")
```

**Features:**
- Configurable log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Optional file logging (in addition to stderr)
- Consistent format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Third-party library noise reduction (uvicorn, httpx, urllib3 set to WARNING)
- Module hierarchy support (e.g., `claudeswarm.messaging`, `claudeswarm.locking`)

### 2. Updated Core Modules to Use Centralized Logging

#### a. `src/claudeswarm/messaging.py`
- **Changed:** `import logging` → `from .logging_config import get_logger`
- **Changed:** `logger = logging.getLogger(__name__)` → `logger = get_logger(__name__)`
- **Already had:** Comprehensive logging for:
  - Message delivery and failures
  - Rate limit hits
  - Signature verification
  - Broadcast operations
  - Message log rotation

#### b. `src/claudeswarm/locking.py`
- **Changed:** Added `from .logging_config import get_logger`
- **Changed:** `logger = get_logger(__name__)`
- **Added logging for:**
  - Lock acquisitions: `logger.info(f"Lock acquired on '{filepath}' by {agent_id}")`
  - Lock refreshes: `logger.debug(f"Lock refreshed on '{filepath}' by {agent_id}")`
  - Lock conflicts: `logger.warning(f"Lock conflict on '{filepath}': ...")`
  - Lock releases: `logger.info(f"Lock released on '{filepath}' by {agent_id}")`
  - Stale lock cleanup: `logger.info(f"Cleaned up {count} stale lock(s)")`
  - Agent lock cleanup: `logger.info(f"Cleaned up {count} lock(s) for agent {agent_id}")`

#### c. `src/claudeswarm/discovery.py`
- **Changed:** `import logging` → `from .logging_config import get_logger`
- **Changed:** `logger = logging.getLogger(__name__)` → `logger = get_logger(__name__)`
- **Already had:** Comprehensive logging for agent discovery, stale agent cleanup, and errors

#### d. `src/claudeswarm/ack.py`
- **Changed:** `import logging` → `from .logging_config import get_logger`
- **Changed:** `logger = logging.getLogger(__name__)` → `logger = get_logger(__name__)`
- **Already had:** Logging for ACK sends, receives, retries, and escalations

#### e. `src/claudeswarm/file_lock.py`
- **Changed:** `import logging` → `from .logging_config import get_logger`
- **Changed:** `logger = logging.getLogger(__name__)` → `logger = get_logger(__name__)`
- **Already had:** Logging for file locking operations

### 3. Updated CLI Entry Point (`src/claudeswarm/cli.py`)

**Added CLI arguments:**
```bash
--log-level {DEBUG,INFO,WARNING,ERROR,CRITICAL}  # Default: WARNING
--log-file LOG_FILE                              # Optional file output
```

**Added initialization in `main()` function:**
```python
# Parse arguments
args = parser.parse_args()

# Initialize logging with configured level
setup_logging(level=args.log_level, log_file=args.log_file)
logger.debug(f"Logging initialized at {args.log_level} level")
```

**Changed imports:**
- Added: `from claudeswarm.logging_config import get_logger, setup_logging`
- Removed: `import logging`
- Changed: `logger = logging.getLogger(__name__)` → `logger = get_logger(__name__)`

### 4. Updated Package Exports (`src/claudeswarm/__init__.py`)

Added `"logging_config"` to `__all__` to expose logging utilities.

## Usage Examples

### Basic Usage (Default - Minimal Logging)

```bash
# Default log level is WARNING - only warnings, errors, and critical messages
claudeswarm list-agents
```

### Info Level Logging (Recommended for Development)

```bash
# See important operations like lock acquisitions, message sends
claudeswarm --log-level INFO list-agents
```

### Debug Level Logging (Troubleshooting)

```bash
# See all debug information including lock refreshes, cache hits, etc.
claudeswarm --log-level DEBUG send-message agent-2 "Hello"
```

### File Logging (Production)

```bash
# Write logs to file in addition to stderr
claudeswarm --log-level INFO --log-file /var/log/claudeswarm.log broadcast-message "Update"
```

### Programmatic Usage

```python
from claudeswarm.logging_config import setup_logging, get_logger

# Setup logging (do this once at application startup)
setup_logging(level="INFO", log_file="/tmp/myapp.log")

# Get module-specific logger
logger = get_logger("mymodule")

# Use logger
logger.debug("Detailed debugging info")
logger.info("Operation completed successfully")
logger.warning("Something unusual happened")
logger.error("Operation failed")
logger.critical("System in critical state")
```

## Log Format

All logs follow this format:
```
2026-01-22 21:19:02,382 - claudeswarm.messaging - INFO - Message sent successfully
```

Components:
- Timestamp: ISO 8601 format with milliseconds
- Logger name: Hierarchical module path (e.g., `claudeswarm.messaging`)
- Log level: DEBUG, INFO, WARNING, ERROR, or CRITICAL
- Message: Human-readable log message

## Benefits

1. **Consistent Format:** All logs follow the same format across modules
2. **Configurable Verbosity:** Control logging level via CLI or API
3. **Production Ready:** File logging support for production deployments
4. **Noise Reduction:** Third-party libraries (uvicorn, httpx) limited to WARNING level
5. **Module Hierarchy:** Clear module identification in logs
6. **Debugging Support:** DEBUG level provides detailed operation traces
7. **Performance Monitoring:** INFO level logs key operations (locks, messages, discoveries)

## Testing

A comprehensive test suite is provided in `test_structured_logging.py`:

```bash
python3 test_structured_logging.py
```

Tests verify:
- Basic logging at different levels
- Module hierarchy
- File logging
- Third-party library suppression
- CLI integration

## Log Locations

### Development
- **Default:** Logs to `stderr` only (appears in terminal)
- **With --log-file:** Also writes to specified file

### Production Recommendations
- Use `--log-level WARNING` or `INFO` to balance verbosity and usefulness
- Use `--log-file /var/log/claudeswarm.log` for persistent logs
- Implement log rotation (external tool like `logrotate`)
- Monitor logs for WARNING and ERROR messages

## Future Enhancements

Potential improvements for future versions:

1. **Structured Logging (JSON):** Add JSON formatter for machine-readable logs
2. **Log Rotation:** Built-in log rotation support
3. **Syslog Integration:** Send logs to system logger
4. **Remote Logging:** Support for centralized logging services (Sentry, DataDog, etc.)
5. **Performance Metrics:** Add performance logging for operation timing
6. **Contextual Logging:** Add context managers for request/operation tracking

## Migration Notes

**For developers adding new modules:**

1. Import logging utilities:
   ```python
   from .logging_config import get_logger
   ```

2. Create module logger:
   ```python
   logger = get_logger(__name__)
   ```

3. Use logger instead of print:
   ```python
   # Bad
   print(f"Debug info: {data}")

   # Good
   logger.debug(f"Debug info: {data}")
   logger.info(f"Operation completed: {result}")
   logger.warning(f"Unusual condition: {issue}")
   logger.error(f"Operation failed: {error}")
   ```

**Log Level Guidelines:**
- **DEBUG:** Detailed information for diagnosing problems (cache hits, retries, detailed state)
- **INFO:** Confirmation that things are working as expected (operations completed, resources acquired)
- **WARNING:** Something unexpected but recoverable (missing optional config, fallback used)
- **ERROR:** A serious problem occurred (operation failed, data loss risk)
- **CRITICAL:** System instability or data corruption (should rarely be used)

## Summary

Structured logging has been successfully implemented across the entire claude-swarm codebase, providing:
- ✅ Centralized logging configuration
- ✅ Consistent log format across all modules
- ✅ CLI integration with configurable levels
- ✅ File logging support
- ✅ Production-ready monitoring capabilities
- ✅ Comprehensive test coverage

The implementation maintains backward compatibility while providing powerful new logging capabilities for development, debugging, and production monitoring.
