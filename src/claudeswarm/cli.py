"""Command-line interface for Claude Swarm.

This module provides the main CLI entry point and command handlers
for all claudeswarm operations. It delegates to the appropriate
modules for each command.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import site
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from claudeswarm.agent_cards import AgentCardRegistry
from claudeswarm.config import (
    ConfigValidationError,
    _find_config_file,
    get_config,
    load_config,
)
from claudeswarm.conflict_resolution import ConflictResolver
from claudeswarm.context import ContextDecision, ContextStore
from claudeswarm.delegation import DelegationManager
from claudeswarm.discovery import list_active_agents, refresh_registry
from claudeswarm.learning import LearningSystem
from claudeswarm.locking import LockManager
from claudeswarm.logging_config import get_logger, setup_logging
from claudeswarm.memory import MemoryStore
from claudeswarm.monitoring import start_monitoring
from claudeswarm.project import find_project_root
from claudeswarm.tasks import TaskManager, TaskPriority, TaskStatus
from claudeswarm.validators import (
    ValidationError,
    validate_agent_id,
    validate_file_path,
    validate_host,
    validate_message_content,
    validate_port,
    validate_tmux_pane_id,
)

__all__ = ["main"]

# Configure logging
logger = get_logger(__name__)

# Command-line validation constants
# Lock reason length limit (enforces concise lock descriptions)
MAX_LOCK_REASON_LENGTH = 512


# Custom type validators for argparse
def positive_int(value: str) -> int:
    """Validate that a string represents a positive integer.

    Args:
        value: String to validate

    Returns:
        Integer value if valid

    Raises:
        argparse.ArgumentTypeError: If value is not a positive integer
    """
    try:
        ivalue = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a valid integer")

    if ivalue <= 0:
        raise argparse.ArgumentTypeError(f"'{value}' must be a positive integer (greater than 0)")

    return ivalue


# Stale threshold validation bounds (in seconds)
# These align with DiscoveryConfig validation in config.py
MIN_STALE_THRESHOLD = 1
MAX_STALE_THRESHOLD = 3600
DEFAULT_STALE_THRESHOLD = 60

# Interval validation bounds for watch mode (in seconds)
MIN_INTERVAL = 1
MAX_INTERVAL = 3600

# Message preview limit for whoami command
WHOAMI_MESSAGE_PREVIEW_LIMIT = 3


def format_timestamp(ts: float) -> str:
    """Format a Unix timestamp as a human-readable string."""
    dt = datetime.fromtimestamp(ts, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _require_agent_id(args: argparse.Namespace, arg_name: str = "agent_id") -> str:
    """Extract and validate agent ID from args, with auto-detection fallback.

    Args:
        args: Parsed command-line arguments
        arg_name: Name of the argument to extract (default: "agent_id")

    Returns:
        Validated agent ID string

    Raises:
        SystemExit: If agent ID cannot be determined or validated
    """
    agent_id = getattr(args, arg_name, None)
    if not agent_id:
        detected_id, _ = _detect_current_agent()
        if detected_id:
            agent_id = detected_id
        else:
            print("Error: Could not auto-detect agent identity", file=sys.stderr)
            print(
                "Please provide agent_id or run 'claudeswarm whoami' to verify registration",
                file=sys.stderr,
            )
            sys.exit(1)

    try:
        return validate_agent_id(agent_id)
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)


def _get_safe_editor() -> str | None:
    """Get and validate EDITOR environment variable, with safe fallbacks.

    Returns:
        Path to safe editor executable, or None if no safe editor found

    Security Notes:
        - Validates that EDITOR path exists and is executable
        - Rejects values containing shell metacharacters to prevent injection
        - Falls back to common safe editors if EDITOR is invalid
    """
    import re

    # Shell metacharacters that could indicate command injection attempts
    SHELL_METACHARACTERS = re.compile(r"[;&|`$<>(){}[\]\\'\"\n]")

    # Safe fallback editors in order of preference
    SAFE_FALLBACKS = ["vim", "vi", "nano", "emacs"]

    # Get EDITOR from environment
    editor = os.environ.get("EDITOR")

    if editor:
        # Check for suspicious shell metacharacters
        if SHELL_METACHARACTERS.search(editor):
            logger.warning(f"EDITOR contains shell metacharacters: {editor}")
            print(
                "Warning: EDITOR environment variable contains suspicious characters, ignoring",
                file=sys.stderr,
            )
            editor = None
        else:
            # Validate that the editor path exists and is executable
            editor_path = shutil.which(editor)
            if not editor_path:
                logger.warning(f"EDITOR not found in PATH: {editor}")
                print(
                    f"Warning: EDITOR '{editor}' not found in PATH, trying fallbacks",
                    file=sys.stderr,
                )
                editor = None
            elif not os.access(editor_path, os.X_OK):
                logger.warning(f"EDITOR not executable: {editor_path}")
                print(
                    f"Warning: EDITOR '{editor}' is not executable, trying fallbacks",
                    file=sys.stderr,
                )
                editor = None
            else:
                # Valid editor found
                return editor_path

    # Fallback to safe default editors
    if not editor:
        for fallback in SAFE_FALLBACKS:
            editor_path = shutil.which(fallback)
            if editor_path and os.access(editor_path, os.X_OK):
                return fallback

    return None


def cmd_acquire_file_lock(args: argparse.Namespace) -> None:
    """Acquire a lock on a file."""
    try:
        # Auto-detect and validate agent_id if not provided
        validated_agent_id = _require_agent_id(args)
        validated_filepath = validate_file_path(
            args.filepath, must_be_relative=False, check_traversal=True
        )

        # Validate reason if provided
        reason = args.reason or ""
        if reason and len(reason) > MAX_LOCK_REASON_LENGTH:
            print(
                f"Error: Lock reason too long (max {MAX_LOCK_REASON_LENGTH} characters)",
                file=sys.stderr,
            )
            sys.exit(1)
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    manager = LockManager(project_root=args.project_root)

    success, conflict = manager.acquire_lock(
        filepath=str(validated_filepath),
        agent_id=validated_agent_id,
        reason=reason,
    )

    if success:
        print(f"Lock acquired on: {args.filepath}")
        print(f"  Agent: {validated_agent_id}")
        if args.reason:
            print(f"  Reason: {args.reason}")
        sys.exit(0)
    else:
        if conflict:
            print(f"Lock conflict on: {args.filepath}", file=sys.stderr)
            print(f"  Currently held by: {conflict.current_holder}", file=sys.stderr)
            print(
                f"  Locked at: {conflict.locked_at.strftime('%Y-%m-%d %H:%M:%S UTC')}",
                file=sys.stderr,
            )
            print(f"  Reason: {conflict.reason}", file=sys.stderr)
        else:
            print(f"Failed to acquire lock on: {args.filepath}", file=sys.stderr)
        sys.exit(1)


def cmd_release_file_lock(args: argparse.Namespace) -> None:
    """Release a lock on a file."""
    try:
        # Auto-detect and validate agent_id if not provided
        validated_agent_id = _require_agent_id(args)
        validated_filepath = validate_file_path(
            args.filepath, must_be_relative=False, check_traversal=True
        )
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    manager = LockManager(project_root=args.project_root)

    success = manager.release_lock(
        filepath=str(validated_filepath),
        agent_id=validated_agent_id,
    )

    if success:
        print(f"Lock released on: {args.filepath}")
        sys.exit(0)
    else:
        print(f"Failed to release lock on: {args.filepath}", file=sys.stderr)
        print("  (Lock may not exist or is owned by another agent)", file=sys.stderr)
        sys.exit(1)


def cmd_who_has_lock(args: argparse.Namespace) -> None:
    """Check who has a lock on a file."""
    try:
        # Validate filepath
        validated_filepath = validate_file_path(
            args.filepath, must_be_relative=False, check_traversal=True
        )
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    manager = LockManager(project_root=args.project_root)

    lock = manager.who_has_lock(filepath=str(validated_filepath))

    if lock:
        print(f"Lock on: {args.filepath}")
        print(f"  Held by: {lock.agent_id}")
        print(f"  Locked at: {format_timestamp(lock.locked_at)}")
        print(f"  Age: {lock.age_seconds():.1f} seconds")
        if lock.reason:
            print(f"  Reason: {lock.reason}")

        if args.json:
            print("\nJSON:")
            print(json.dumps(lock.to_dict(), indent=2))

        sys.exit(0)
    else:
        print(f"No active lock on: {args.filepath}")
        sys.exit(0)


def cmd_list_all_locks(args: argparse.Namespace) -> None:
    """List all active locks."""
    manager = LockManager(project_root=args.project_root)

    locks = manager.list_all_locks(include_stale=args.include_stale)

    if not locks:
        print("No active locks.")
        sys.exit(0)

    print(f"Active locks ({len(locks)}):")
    print()

    for lock in locks:
        stale_marker = " [STALE]" if lock.is_stale() else ""
        print(f"{lock.filepath}{stale_marker}")
        print(f"  Held by: {lock.agent_id}")
        print(f"  Locked at: {format_timestamp(lock.locked_at)}")
        print(f"  Age: {lock.age_seconds():.1f} seconds")
        if lock.reason:
            print(f"  Reason: {lock.reason}")
        print()

    if args.json:
        print("JSON:")
        print(json.dumps([lock.to_dict() for lock in locks], indent=2))

    sys.exit(0)


def cmd_discover_agents(args: argparse.Namespace) -> None:
    """Discover active Claude Code agents."""
    import time

    from claudeswarm.backend import get_backend

    backend = get_backend()

    # Validate stale_threshold
    try:
        if args.stale_threshold < MIN_STALE_THRESHOLD or args.stale_threshold > MAX_STALE_THRESHOLD:
            print(
                f"Error: stale_threshold must be between {MIN_STALE_THRESHOLD} and {MAX_STALE_THRESHOLD} seconds",
                file=sys.stderr,
            )
            sys.exit(1)
        if args.watch and (args.interval < MIN_INTERVAL or args.interval > MAX_INTERVAL):
            print(
                f"Error: interval must be between {MIN_INTERVAL} and {MAX_INTERVAL} seconds",
                file=sys.stderr,
            )
            sys.exit(1)
    except (TypeError, AttributeError) as e:
        print(f"Error: Invalid argument type: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.watch:
            # Continuous monitoring mode
            print("Watching for agents (Ctrl+C to stop)...")
            try:
                while True:
                    registry = refresh_registry(
                        stale_threshold=args.stale_threshold, backend=backend
                    )

                    if not args.json:
                        print(f"\n=== Agent Discovery [{registry.updated_at}] ===")
                        print(f"Session: {registry.session_name}")
                        print(f"Total agents: {len(registry.agents)}")
                        print()

                        for agent in registry.agents:
                            status_symbol = (
                                "✓"
                                if agent.status == "active"
                                else "⚠"
                                if agent.status == "stale"
                                else "✗"
                            )
                            print(
                                f"  {status_symbol} {agent.id:<12} | {agent.pane_index:<20} | PID: {agent.pid:<8} | {agent.status}"
                            )
                    else:
                        print(json.dumps(registry.to_dict(), indent=2))

                    time.sleep(args.interval)
            except KeyboardInterrupt:
                print("\nStopped watching.")
                sys.exit(0)
        else:
            # Single discovery
            registry = refresh_registry(stale_threshold=args.stale_threshold, backend=backend)

            if args.json:
                print(json.dumps(registry.to_dict(), indent=2))
            else:
                print(f"=== Agent Discovery [{registry.updated_at}] ===")
                print(f"Session: {registry.session_name}")
                print(f"Total agents: {len(registry.agents)}")
                print()

                if not registry.agents:
                    print("  No agents discovered.")
                else:
                    for agent in registry.agents:
                        status_symbol = (
                            "✓"
                            if agent.status == "active"
                            else "⚠"
                            if agent.status == "stale"
                            else "✗"
                        )
                        print(
                            f"  {status_symbol} {agent.id:<12} | {agent.pane_index:<20} | PID: {agent.pid:<8} | {agent.status}"
                        )

                print()
                print("Registry saved to: ACTIVE_AGENTS.json")

        sys.exit(0)

    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list_agents(args: argparse.Namespace) -> None:
    """List active agents from registry."""
    try:
        agents = list_active_agents()

        if args.json:
            print(json.dumps([agent.to_dict() for agent in agents], indent=2))
        else:
            if not agents:
                print("No active agents found.")
            else:
                print(f"=== Active Agents ({len(agents)}) ===")
                for agent in agents:
                    print(f"  {agent.id:<12} | {agent.pane_index:<20} | PID: {agent.pid}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _detect_current_agent() -> tuple[str | None, dict | None]:
    """Detect the current agent from the active backend.

    Uses the backend abstraction to get the current agent identifier,
    then matches against the agent registry.

    For tmux backend: uses TMUX_PANE env var
    For process backend: uses TTY path

    Returns:
        Tuple of (agent_id, agent_dict) if found, (None, None) otherwise
    """
    import os

    from claudeswarm.backend import get_backend
    from claudeswarm.project import get_active_agents_path

    backend = get_backend()
    current_identifier = backend.get_current_agent_identifier()

    if not current_identifier:
        return None, None

    # For tmux backend, validate the pane ID format
    if backend.name == "tmux":
        try:
            current_identifier = validate_tmux_pane_id(current_identifier)
        except ValidationError:
            return None, None

    # Load registry
    registry_path = get_active_agents_path()
    if not registry_path.exists():
        return None, None

    try:
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None, None

    agents = registry.get("agents", [])

    if backend.name == "tmux":
        # Try matching by TMUX_PANE env var (works in sandboxed environments!)
        for agent in agents:
            if agent.get("tmux_pane_id") == current_identifier:
                if agent.get("status") != "active":
                    logger.debug(
                        f"Skipping non-active agent {agent.get('id')} with matching pane ID"
                    )
                    continue

                agent_pid = agent.get("pid")
                if agent_pid:
                    try:
                        os.kill(agent_pid, 0)
                    except ProcessLookupError:
                        logger.debug(
                            f"Agent {agent.get('id')} PID {agent_pid} no longer running, "
                            f"skipping stale registry entry"
                        )
                        continue
                    except PermissionError:
                        pass
                    except OSError:
                        logger.debug(
                            f"Could not verify PID {agent_pid} for agent {agent.get('id')}, "
                            f"allowing match anyway"
                        )

                return agent.get("id"), agent

        # Fallback: Try converting TMUX_PANE to pane index format
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "display-message",
                    "-p",
                    "-t",
                    current_identifier,
                    "#{session_name}:#{window_index}.#{pane_index}",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if result.returncode == 0:
                current_pane = result.stdout.strip()
                for agent in agents:
                    if agent.get("pane_index") == current_pane:
                        return agent.get("id"), agent
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    elif backend.name == "process":
        # Match by TTY path or pane_index (which is the identifier for process backend)
        for agent in agents:
            if (
                agent.get("tty") == current_identifier
                or agent.get("pane_index") == current_identifier
            ):
                if agent.get("status") != "active":
                    continue

                agent_pid = agent.get("pid")
                if agent_pid:
                    try:
                        os.kill(agent_pid, 0)
                    except ProcessLookupError:
                        continue
                    except (PermissionError, OSError):
                        pass

                return agent.get("id"), agent

    return None, None


def cmd_send_message(args: argparse.Namespace) -> None:
    """Send a message to a specific agent.

    Args:
        args.sender_id: ID of the sending agent (optional, auto-detected if in tmux)
        args.recipient_id: ID of the receiving agent
        args.type: Message type (case-insensitive, supports hyphens and underscores)
        args.content: Message content to send
        args.json: Whether to output JSON format
        args.ack: Whether to request acknowledgment with automatic retry

    Exit Codes:
        0: Success - message sent
        1: Failure - validation error, recipient not found, or send failed
    """
    from claudeswarm.messaging import MessageType, send_message
    from claudeswarm.validators import sanitize_message_content

    try:
        # Auto-detect and validate sender if not provided
        validated_sender = _require_agent_id(args, arg_name="sender_id")
        validated_recipient = validate_agent_id(args.recipient_id)

        # Validate and sanitize message content
        validated_content = validate_message_content(args.content)
        sanitized_content = sanitize_message_content(validated_content)

        # Parse message type with case-insensitive handling
        normalized_type = args.type.upper().replace("-", "_")
        try:
            msg_type = MessageType[normalized_type]
        except KeyError:
            # Show valid types with both enum names and user-friendly formats
            valid_types = sorted([t.name for t in MessageType])
            valid_types_display = [t.replace("_", "-").lower() for t in valid_types]
            print(f"Error: Invalid message type '{args.type}'", file=sys.stderr)
            print(f"Valid types: {', '.join(valid_types_display)}", file=sys.stderr)
            print("  (case-insensitive, use hyphens or underscores)", file=sys.stderr)
            sys.exit(1)

        # Check if ACK is requested
        if getattr(args, "ack", False):
            from claudeswarm.ack import send_with_ack

            msg_id = send_with_ack(
                validated_sender, validated_recipient, msg_type, sanitized_content
            )
            if msg_id:
                print(f"[ACK-REQUIRED] Message sent to {args.recipient_id} (ID: {msg_id[:8]})")
                print("  Will auto-retry if not acknowledged within 30s")
                sys.exit(0)
            else:
                print("Failed to send message with ACK", file=sys.stderr)
                sys.exit(1)

        # Send message (messaging layer validates recipient exists via _get_agent_pane)
        message = send_message(
            sender_id=validated_sender,
            recipient_id=validated_recipient,
            message_type=msg_type,
            content=sanitized_content,
        )

        if message:
            delivered = message.to_dict().get("delivery_status", {}).get(validated_recipient, False)
            if delivered:
                print(f"[DELIVERED] Message sent to {args.recipient_id}")
            else:
                print(f"[QUEUED] Message saved to {args.recipient_id}'s inbox")
                print("  (Will be seen on their next check-messages)")
            if args.json:
                # Serialize JSON and fail hard if serialization fails
                try:
                    json_output = json.dumps(message.to_dict(), indent=2)
                    print(json_output)
                except (TypeError, ValueError) as e:
                    print(f"Error: Could not format JSON output: {e}", file=sys.stderr)
                    sys.exit(1)
            sys.exit(0)
        else:
            print(f"Failed to send message to {args.recipient_id}", file=sys.stderr)
            sys.exit(1)

    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: Agent registry not found. Run 'claudeswarm discover-agents' first",
            file=sys.stderr,
        )
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_broadcast_message(args: argparse.Namespace) -> None:
    """Broadcast a message to all agents.

    Args:
        args.sender_id: ID of the sending agent (optional, auto-detected if in tmux)
        args.type: Message type (case-insensitive, supports hyphens and underscores)
        args.content: Message content to broadcast
        args.include_self: Whether to include sender in broadcast
        args.json: Whether to output JSON format
        args.verbose: Whether to show detailed delivery status

    Exit Codes:
        0: Success - at least one agent reached
        1: Failure - validation error, no agents found, or all deliveries failed
    """
    from claudeswarm.messaging import MessageType, broadcast_message
    from claudeswarm.validators import sanitize_message_content

    try:
        # Auto-detect and validate sender if not provided
        validated_sender = _require_agent_id(args, arg_name="sender_id")

        # Validate and sanitize message content
        validated_content = validate_message_content(args.content)
        sanitized_content = sanitize_message_content(validated_content)

        # Parse message type with case-insensitive handling
        normalized_type = args.type.upper().replace("-", "_")
        try:
            msg_type = MessageType[normalized_type]
        except KeyError:
            # Show valid types with both enum names and user-friendly formats
            valid_types = sorted([t.name for t in MessageType])
            valid_types_display = [t.replace("_", "-").lower() for t in valid_types]
            print(f"Error: Invalid message type '{args.type}'", file=sys.stderr)
            print(f"Valid types: {', '.join(valid_types_display)}", file=sys.stderr)
            print("  (case-insensitive, use hyphens or underscores)", file=sys.stderr)
            sys.exit(1)

        # Broadcast message
        results = broadcast_message(
            sender_id=validated_sender,
            message_type=msg_type,
            content=sanitized_content,
            exclude_self=not args.include_self,
        )

        # Check if any agents were found in registry
        if not results:
            print("Error: No active agents found for broadcast", file=sys.stderr)
            print(
                "Run 'claudeswarm discover-agents' to refresh the agent registry", file=sys.stderr
            )
            sys.exit(1)

        # Count successful deliveries (tmux send-keys)
        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)

        # Show delivery status
        if success_count == total_count:
            print(f"✓ Broadcast delivered to {total_count}/{total_count} agents (real-time)")
        elif success_count > 0:
            print(
                f"✓ Message broadcast: {success_count}/{total_count} real-time, {total_count - success_count}/{total_count} inbox"
            )
        else:
            print(f"✓ Message sent to inbox: {total_count}/{total_count} agents")
            print("  ℹ️  Messages logged to inbox (real-time delivery attempted)")

        if args.json:
            # Serialize JSON and fail hard if serialization fails
            try:
                json_output = json.dumps(results, indent=2)
                print(json_output)
            except (TypeError, ValueError) as e:
                print(f"Error: Could not format JSON output: {e}", file=sys.stderr)
                sys.exit(1)
        elif args.verbose:
            for agent_id, success in sorted(results.items()):
                status = "✓ delivered" if success else "📬 in inbox"
                print(f"  {status}: {agent_id}")

        # Always exit 0 since message is logged (inbox delivery always succeeds)
        sys.exit(0)

    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: Agent registry not found. Run 'claudeswarm discover-agents' first",
            file=sys.stderr,
        )
        sys.exit(1)
    except PermissionError as e:
        print(f"Error: Permission denied: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_cleanup_stale_locks(args: argparse.Namespace) -> None:
    """Clean up stale locks."""
    manager = LockManager(project_root=args.project_root)

    count = manager.cleanup_stale_locks()

    print(f"Cleaned up {count} stale lock(s)")
    sys.exit(0)


def cmd_start_monitoring(args: argparse.Namespace) -> None:
    """Start the monitoring dashboard."""
    try:
        start_monitoring(
            filter_type=args.filter_type, filter_agent=args.filter_agent, use_tmux=not args.no_tmux
        )
        sys.exit(0)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_init(args: argparse.Namespace) -> None:
    """Create default configuration file."""
    config_path = Path(args.output or ".claudeswarm.yaml")

    # Check if file exists
    if config_path.exists() and not args.force:
        print(f"Error: Config file already exists: {config_path}", file=sys.stderr)
        print("Use --force to overwrite", file=sys.stderr)
        sys.exit(1)

    # Create default config content
    default_yaml = """# Claude Swarm Configuration
# Complete reference: docs/CONFIGURATION.md

# Rate limiting for messaging system
rate_limiting:
  # Maximum messages an agent can send per window
  messages_per_minute: 10
  # Time window for rate limiting in seconds
  window_seconds: 60

# Distributed file locking settings
locking:
  # Seconds after which a lock is considered stale
  stale_timeout: 300
  # Automatically clean up stale locks
  auto_cleanup: false
  # Default reason when no reason is provided
  default_reason: "working"

# Agent discovery configuration
discovery:
  # Seconds after which an agent is considered stale
  stale_threshold: 60
  # Automatic registry refresh interval (null = disabled)
  auto_refresh_interval: null

# Agent onboarding configuration
onboarding:
  # Whether onboarding system is enabled
  enabled: true
  # Custom onboarding messages (null = use defaults)
  custom_messages: null
  # Automatically onboard new agents when discovered
  auto_onboard: false

# Web dashboard configuration
dashboard:
  # Whether dashboard is available
  enabled: true
  # Default port for dashboard server
  port: 8080
  # Default host to bind to
  host: localhost
  # Whether to open browser automatically
  auto_open_browser: true
  # Data refresh interval in seconds
  refresh_interval: 1

# Project root directory (null = auto-detect from current directory)
project_root: null
"""

    try:
        config_path.write_text(default_yaml)
        print(f"Created config file: {config_path.resolve()}")
        print()
        print("Default configuration created. Edit this file to customize settings.")
        print("View with: claudeswarm config show")
        print("Edit with: claudeswarm config edit")
        sys.exit(0)
    except Exception as e:
        print(f"Error creating config file: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_show(args: argparse.Namespace) -> None:
    """Display current configuration."""
    try:
        # Load config
        if args.file:
            config_path = Path(args.file)
            config = load_config(config_path)
            source = str(config_path)
        else:
            config_path = _find_config_file()
            if config_path:
                config = load_config(config_path)
                source = str(config_path)
            else:
                config = load_config()  # Load defaults
                source = "defaults (no config file found)"

        # Output format
        if args.json:
            print(json.dumps(config.to_dict(), indent=2))
        else:
            print(f"Configuration source: {source}")
            print()

            # Pretty print as YAML-like format
            data = config.to_dict()
            for section, values in data.items():
                if values is None:
                    print(f"{section}: null")
                elif isinstance(values, dict):
                    print(f"{section}:")
                    for key, value in values.items():
                        print(f"  {key}: {value}")
                else:
                    print(f"{section}: {values}")
                print()

        sys.exit(0)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_validate(args: argparse.Namespace) -> None:
    """Validate configuration file."""
    try:
        # Load config
        if args.file:
            config_path = Path(args.file)
        else:
            config_path = _find_config_file()
            if not config_path:
                print("No config file found to validate", file=sys.stderr)
                print("Create one with: claudeswarm config init", file=sys.stderr)
                sys.exit(1)

        print(f"Validating: {config_path}")
        print()

        # Try to load and validate
        try:
            load_config(config_path)
            print("✓ Syntax: Valid")
            print("✓ Values: Valid")
            print()
            print(f"Config file is valid: {config_path}")
            sys.exit(0)
        except ConfigValidationError as e:
            print("✓ Syntax: Valid")
            print("✗ Values: Invalid", file=sys.stderr)
            print()
            print("Validation errors:", file=sys.stderr)
            print(f"  - {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"✗ Syntax: Invalid - {e}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error validating config: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_config_edit(args: argparse.Namespace) -> None:
    """Open configuration file in editor."""
    # Find or create config file
    if args.file:
        config_path = Path(args.file)
    else:
        config_path = _find_config_file()
        if not config_path:
            # Create default config
            config_path = Path(".claudeswarm.yaml")
            if not config_path.exists():
                print(f"No config file found. Creating: {config_path}")
                # Create default config by calling config init
                cmd_config_init(argparse.Namespace(output=str(config_path), force=False))

    # Get validated editor
    editor = _get_safe_editor()

    if not editor:
        print("Error: No editor found", file=sys.stderr)
        print("Set EDITOR environment variable or install vim/nano", file=sys.stderr)
        sys.exit(1)

    # Open in editor
    try:
        result = subprocess.run([editor, str(config_path)])  # nosec B603
        if result.returncode == 0:
            print(f"Saved: {config_path}")
            print()
            print("Validate with: claudeswarm config validate")
        sys.exit(result.returncode)
    except Exception as e:
        print(f"Error opening editor: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_start_dashboard(args: argparse.Namespace) -> None:
    """Start the web-based monitoring dashboard.

    Launches FastAPI server and optionally opens browser.

    Args:
        args.port: Port to run server on (default: from config or 8080)
        args.host: Host to bind to (default: from config or localhost)
        args.no_browser: Don't auto-open browser
        args.reload: Enable auto-reload for development

    Exit Codes:
        0: Server started successfully (won't reach due to blocking)
        1: Server failed to start
    """
    from claudeswarm.web.launcher import start_dashboard_server

    # Load configuration
    try:
        config = get_config()
    except Exception:
        # Fall back to defaults if config loading fails
        from claudeswarm.config import DashboardConfig

        config = argparse.Namespace(dashboard=DashboardConfig())

    # Use command-line args if provided, otherwise use config
    port = args.port if args.port is not None else config.dashboard.port
    host = args.host if args.host is not None else config.dashboard.host
    auto_open = not args.no_browser and config.dashboard.auto_open_browser
    reload = args.reload

    # Validate host and port
    try:
        # Validate port
        validated_port = validate_port(port)

        # Validate host with warning callback
        def warn(msg: str) -> None:
            print(msg, file=sys.stderr)

        validated_host = validate_host(host, allow_all_interfaces=False, warn_callback=warn)

    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        start_dashboard_server(
            port=validated_port, host=validated_host, auto_open=auto_open, reload=reload
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


def _discover_agents_for_onboarding(args: argparse.Namespace) -> list:
    """Discover active agents in current project.

    Args:
        args: Parsed command-line arguments

    Returns:
        List of discovered agents

    Exit Codes:
        1: Error during discovery or no agents found
    """
    print("Step 1: Discovering active agents in current project...")
    try:
        # refresh_registry() discovers agents filtered by current project
        registry = refresh_registry()
        agents = registry.agents

        if not agents:
            print("No agents discovered in this project.")
            print("Make sure Claude Code instances are running in tmux panes.")
            sys.exit(1)

        print(f"Found {len(agents)} agent(s) in current project: {', '.join(a.id for a in agents)}")
        print()
        return agents

    except subprocess.CalledProcessError as e:
        print("Error: tmux command failed. Is tmux running?", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: Required file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during discovery: {e}", file=sys.stderr)
        sys.exit(1)


def _prepare_onboarding_content(agents: list) -> list[str]:
    """Prepare the onboarding message content.

    Args:
        agents: List of discovered agents

    Returns:
        List of onboarding messages to send
    """
    agent_list = ", ".join(a.id for a in agents)

    # Single comprehensive onboarding message
    return [
        f"""=== CLAUDE SWARM COORDINATION ACTIVE ===
Multi-agent coordination is now available in this session.

ACTIVE AGENTS: {agent_list}

═══════════════════════════════════════════════════════════════════
HOW TO SEND MESSAGES TO OTHER AGENTS:
═══════════════════════════════════════════════════════════════════

IMPORTANT: Real-time messaging is FULLY AVAILABLE in this sandbox environment!
Messages are delivered instantly via tmux to all agents in this session.

Your AI assistant will automatically handle all tmux operations - just use the
commands naturally and messages will appear immediately in recipient conversations!

• Send direct message:
  claudeswarm send-message <agent-id> INFO "your message here"
  Example: claudeswarm send-message agent-1 INFO "Ready to start!"

• Broadcast to all agents:
  claudeswarm broadcast-message INFO "your message here"
  Example: claudeswarm broadcast-message TASK-UPDATE "Starting work on API"

• Find out who you are:
  claudeswarm whoami

• See all active agents:
  claudeswarm list-agents

Messages appear AUTOMATICALLY in recipient conversations - no manual checking needed!

Message types: INFO, QUESTION, REVIEW-REQUEST, BLOCKED, TASK-UPDATE, URGENT

═══════════════════════════════════════════════════════════════════
FILE LOCKING PROTOCOL (CRITICAL):
═══════════════════════════════════════════════════════════════════

BEFORE editing ANY file, you MUST acquire a lock:
  claudeswarm acquire-file-lock <filepath> "reason for editing"
  Example: claudeswarm acquire-file-lock src/main.py "refactoring auth"

AFTER editing, ALWAYS release the lock immediately:
  claudeswarm release-file-lock <filepath>
  Example: claudeswarm release-file-lock src/main.py

Check if file is locked:
  claudeswarm who-has-lock <filepath>

List all locks:
  claudeswarm list-all-locks

NEVER skip file locks - they prevent conflicts between agents!

═══════════════════════════════════════════════════════════════════
DOCUMENTATION & HELP:
═══════════════════════════════════════════════════════════════════

• docs/AGENT_PROTOCOL.md - Full protocol documentation
• docs/AGENT_QUICK_REFERENCE.md - Quick command reference
• claudeswarm --help - All available commands
• COORDINATION.md - Sprint goals and current work assignments

═══════════════════════════════════════════════════════════════════
🤝 SAY HELLO TO YOUR TEAMMATES!
═══════════════════════════════════════════════════════════════════

Now that you're connected, introduce yourself to the other agents!
Send a greeting to let them know you're online and ready to collaborate.

Example:
  claudeswarm broadcast-message INFO "Hello team! I'm agent-X, ready to help!"

This helps establish communication and confirms messaging is working.

COORDINATION READY! 🎉"""
    ]


def _send_onboarding_messages(
    agents: list, messages: list[str], args: argparse.Namespace
) -> tuple[int, int]:
    """Send onboarding messages to all agents (except self, which is sent later).

    Args:
        agents: List of agents to send messages to
        messages: List of message content to broadcast
        args: Parsed command-line arguments

    Returns:
        Tuple of (messages_sent, failed_messages) counts
    """
    import time

    from claudeswarm.messaging import MessageType, broadcast_message

    print("Step 2: Broadcasting onboarding messages to project agents...")

    messages_sent = 0
    failed_messages = 0
    MESSAGE_DELAY = 0.5  # Rate limiting: wait between messages

    for i, msg in enumerate(messages, 1):
        # Progress indication
        print(f"  Sending message {i}/{len(messages)}...", end="\r")
        sys.stdout.flush()

        try:
            # Exclude self from initial broadcast - we'll send to self at the end
            # after all command output is done, to avoid Enter key being swallowed
            result = broadcast_message(
                sender_id="system",
                message_type=MessageType.INFO,
                content=msg,
                exclude_self=True,
            )

            delivered = sum(result.values())
            if delivered == 0:
                failed_messages += 1
            else:
                messages_sent += 1

            # Rate limiting: wait between messages to avoid overwhelming the system
            if i < len(messages):
                time.sleep(MESSAGE_DELAY)

        except Exception as e:
            print(f"\nWarning: Failed to send message: {e}", file=sys.stderr)
            failed_messages += 1

    print(f"  Sent {messages_sent}/{len(messages)} messages successfully          ")
    print()

    return messages_sent, failed_messages


def _report_onboarding_results(
    agents: list, messages_sent: int, failed_messages: int, total_messages: int
) -> None:
    """Report onboarding results.

    Args:
        agents: List of agents that were onboarded
        messages_sent: Number of messages successfully sent
        failed_messages: Number of messages that failed to send
        total_messages: Total number of messages attempted

    Exit Codes:
        1: Too many messages failed to deliver
    """
    # Check if too many messages failed
    if failed_messages > total_messages * 0.5:
        print("WARNING: Most messages failed to deliver!", file=sys.stderr)
        print("Agents may not have received onboarding information.", file=sys.stderr)
        sys.exit(1)

    print(f"Onboarding complete! {messages_sent} messages delivered to {len(agents)} agent(s).")
    print()
    print("All agents have been notified about:")
    print("  - Coordination protocol rules")
    print("  - Available commands")
    print("  - How to send messages and acquire locks")
    print("  - Where to find documentation")

    if failed_messages > 0:
        print()
        print(f"Note: {failed_messages} message(s) failed to deliver", file=sys.stderr)

    print()
    print("Agents are now ready to coordinate!")


def cmd_onboard(args: argparse.Namespace) -> None:
    """Onboard all discovered agents to the coordination system.

    This command:
    1. Discovers all active Claude Code agents via tmux
    2. Broadcasts onboarding messages to all discovered agents
    3. Provides coordination protocol documentation
    4. Sends onboarding to self at the end (after all output)

    Args:
        args: Parsed command-line arguments

    Side Effects:
        - Refreshes agent registry (ACTIVE_AGENTS.json)
        - Sends multiple broadcast messages to all agents
        - May trigger rate limiting in messaging system

    Exit Codes:
        0: Success - all agents onboarded
        1: Error - discovery failed or no agents found
    """
    import time

    print("=== Claude Swarm Agent Onboarding ===")
    print()

    # Step 1: Discover agents
    agents = _discover_agents_for_onboarding(args)

    # Step 2: Prepare onboarding content
    messages = _prepare_onboarding_content(agents)

    # Step 3: Send onboarding messages (to others, excluding self)
    messages_sent, failed_messages = _send_onboarding_messages(agents, messages, args)

    # Step 4: Report results
    _report_onboarding_results(agents, messages_sent, failed_messages, len(messages))

    # Step 5: Send onboarding to self AFTER all output is done
    # This ensures the Enter key isn't swallowed while the command is still printing.
    # When tmux send-keys sends an Enter key while the CLI is still printing output,
    # the Enter can be "swallowed" by the terminal's input buffer, causing the message
    # to not execute. The delay ensures terminal rendering completes before self-messaging.
    self_agent_id, _ = _detect_current_agent()
    if self_agent_id:
        from claudeswarm.messaging import MessageType, send_message

        # Delay to ensure all stdout is flushed and terminal rendering completes
        sys.stdout.flush()
        sys.stderr.flush()
        time.sleep(0.5)

        for msg in messages:
            try:
                send_message(
                    sender_id="system",
                    recipient_id=self_agent_id,
                    message_type=MessageType.INFO,
                    content=msg,
                )
            except Exception as e:
                # Log but don't fail - self-message delivery is best effort
                logger.debug(f"Failed to send onboarding message to self: {e}")

    sys.exit(0)


def cmd_check_messages(args: argparse.Namespace) -> None:
    """Check messages for the current agent.

    Reads messages from the agent_messages.log file and filters for messages
    sent to this agent. Works in sandboxed environments by reading from file
    instead of relying on tmux delivery.

    Flags:
        --new-only: Only show messages since last check (unread)
        --quiet: Compact output suitable for hooks (one line per message)

    Exit Codes:
        0: Success
        1: Error (not an agent, file not found, etc.)
    """
    from claudeswarm.project import get_messages_log_path, get_project_root

    # Auto-detect current agent (or use explicit agent-id for testing)
    agent_id = getattr(args, "agent_id", None)
    if not agent_id:
        detected_id, _ = _detect_current_agent()
        if detected_id:
            agent_id = detected_id
        else:
            if not getattr(args, "quiet", False):
                print("Error: Could not auto-detect agent identity", file=sys.stderr)
                print("Please run 'claudeswarm whoami' to verify registration", file=sys.stderr)
            sys.exit(1)

    # Get flags
    new_only = getattr(args, "new_only", False)
    quiet = getattr(args, "quiet", False)

    # Read messages log
    messages_log = get_messages_log_path()
    if not messages_log.exists():
        if not quiet:
            print("No messages found (log file doesn't exist)")
        sys.exit(0)

    try:
        with open(messages_log, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        if not quiet:
            print(f"Error reading messages: {e}", file=sys.stderr)
        sys.exit(1)

    # Load last read timestamp if using --new-only
    project_root = get_project_root(getattr(args, "project_root", None))
    last_read_file = project_root / ".swarm" / "last_read_messages.json"
    last_read_timestamp = None
    if new_only:
        try:
            if last_read_file.exists():
                with open(last_read_file, encoding="utf-8") as f:
                    last_read_data = json.load(f)
                    last_read_timestamp = last_read_data.get(agent_id)
        except (OSError, json.JSONDecodeError):
            pass  # Ignore errors reading last read file

    # Parse and filter messages for this agent
    my_messages = []
    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)

            # Check if this message is for us
            recipients = msg.get("recipients", [])
            if agent_id in recipients or "all" in recipients:
                # Filter by timestamp if --new-only
                if new_only and last_read_timestamp:
                    msg_timestamp = msg.get("timestamp", "")
                    if msg_timestamp <= last_read_timestamp:
                        continue  # Skip already-read messages
                my_messages.append(msg)
        except json.JSONDecodeError:
            continue

    # Update last read timestamp (always, even with --new-only, to mark as read)
    if my_messages:
        latest_timestamp = max(msg.get("timestamp", "") for msg in my_messages)
        try:
            last_read_data = {}
            if last_read_file.exists():
                with open(last_read_file, encoding="utf-8") as f:
                    last_read_data = json.load(f)
            last_read_data[agent_id] = latest_timestamp
            last_read_file.parent.mkdir(parents=True, exist_ok=True)
            with open(last_read_file, "w", encoding="utf-8") as f:
                json.dump(last_read_data, f, indent=2)
        except OSError:
            pass  # Ignore errors saving last read file

    # Display messages
    if not my_messages:
        if not quiet:
            if new_only:
                print(f"No new messages for {agent_id}")
            else:
                print(f"No messages for {agent_id}")
        sys.exit(0)

    # Show last N messages (default 10)
    limit = args.limit if hasattr(args, "limit") and args.limit else 10
    recent_messages = my_messages[-limit:]

    if quiet:
        # Compact output for hooks - one line per message
        for msg in recent_messages:
            sender = msg.get("sender", "unknown")
            msg_type = msg.get("msg_type", "INFO")
            content = msg.get("content", "").replace("\n", " ")
            print(f"[{sender}:{msg_type}] {content}")
    else:
        # Standard output
        print(f"=== Messages for {agent_id} ({len(recent_messages)} recent) ===")
        print()

        for msg in recent_messages:
            sender = msg.get("sender", "unknown")
            timestamp = msg.get("timestamp", "unknown")
            msg_type = msg.get("msg_type", "INFO")
            content = msg.get("content", "")
            msg_id = msg.get("msg_id", "")[:8]  # Short ID

            print(f"[{timestamp}] From: {sender} ({msg_type})")
            print(f"  {content}")
            print(f"  (ID: {msg_id})")
            print()

        if len(my_messages) > limit:
            print(f"({len(my_messages) - limit} older messages not shown. Use --limit to see more)")

    # Process pending ACK retries (runs periodically via check-messages hook)
    try:
        from claudeswarm.ack import process_pending_retries

        retried = process_pending_retries()
        if retried > 0:
            logger.info(f"Processed {retried} pending message retries")
    except Exception as e:
        logger.debug(f"ACK processing skipped: {e}")

    sys.exit(0)


def cmd_acknowledge_message(args: argparse.Namespace) -> None:
    """Acknowledge receipt of a message.

    This removes the message from the sender's pending ACK list,
    preventing automatic retries and escalation.

    Args:
        args.msg_id: Message ID to acknowledge

    Exit Codes:
        0: Success - message acknowledged
        1: Error - message not found or not pending
    """
    from claudeswarm.ack import acknowledge_message

    # Get current agent ID
    agent_id, _ = _detect_current_agent()
    if not agent_id:
        print("Error: Could not detect current agent identity", file=sys.stderr)
        print("Please run 'claudeswarm whoami' to verify registration", file=sys.stderr)
        sys.exit(1)

    msg_id = args.msg_id

    # Calculate short ID once (fix duplicate calculation)
    short_id = msg_id[:8] if len(msg_id) > 8 else msg_id

    try:
        if acknowledge_message(msg_id, agent_id):
            print(f"ACK sent for message {short_id}")
            sys.exit(0)
        else:
            print(f"Message {short_id} not found in pending ACKs", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error acknowledging message: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_whoami(args: argparse.Namespace) -> None:
    """Display information about the current agent.

    Checks if the current terminal is registered as an agent and displays
    agent information if found, or indicates if not running as an agent.
    Works with both tmux and process backends.

    Exit Codes:
        0: Success (agent found or not)
        1: Error (no identifier available, registry not found, etc.)
    """
    import os

    from claudeswarm.backend import get_backend
    from claudeswarm.project import get_active_agents_path

    backend = get_backend()
    current_identifier = backend.get_current_agent_identifier()

    if not current_identifier:
        if backend.name == "tmux":
            print("Not running in a tmux session.", file=sys.stderr)
            print("The 'whoami' command only works within tmux panes.", file=sys.stderr)
        else:
            print("Could not determine terminal identity.", file=sys.stderr)
            print(
                f"Backend: {backend.name}. No TTY or terminal identifier found.",
                file=sys.stderr,
            )
        sys.exit(1)

    # For tmux backend, validate pane ID format
    if backend.name == "tmux":
        try:
            current_identifier = validate_tmux_pane_id(current_identifier)
        except ValidationError as e:
            print(f"Error: Invalid TMUX_PANE environment variable: {e}", file=sys.stderr)
            sys.exit(1)

    # Convert tmux pane ID to session:window.pane format for display
    current_pane = None
    if backend.name == "tmux":
        try:
            result = subprocess.run(
                [
                    "tmux",
                    "display-message",
                    "-p",
                    "-t",
                    current_identifier,
                    "#{session_name}:#{window_index}.#{pane_index}",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if result.returncode == 0:
                current_pane = result.stdout.strip()
            else:
                _ = result.stderr.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            _ = str(e)

    # Load active agents registry
    registry_path = get_active_agents_path()
    if not registry_path.exists():
        print("No active agents registry found.")
        print()
        print("You are NOT registered as an agent.")
        print()
        print("To discover and register agents, run:")
        print("  claudeswarm discover-agents")
        sys.exit(0)

    try:
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"Error reading agent registry: {e}", file=sys.stderr)
        sys.exit(1)

    # Search for current agent in registry
    agents = registry.get("agents", [])
    current_agent = None

    if backend.name == "tmux":
        # Try matching by TMUX_PANE env var first
        for agent in agents:
            if agent.get("tmux_pane_id") == current_identifier:
                current_agent = agent
                break

        # Fallback 1: Try matching by pane index
        if not current_agent and current_pane:
            for agent in agents:
                if agent.get("pane_index") == current_pane:
                    current_agent = agent
                    break

    elif backend.name == "process":
        # Match by TTY path or pane_index
        for agent in agents:
            if (
                agent.get("tty") == current_identifier
                or agent.get("pane_index") == current_identifier
            ):
                current_agent = agent
                break

    # Fallback: Try matching by PID (works for any backend)
    if not current_agent:
        current_pid = os.getpid()
        parent_pid = os.getppid()

        for agent in agents:
            agent_pid = agent.get("pid")
            if agent_pid and agent_pid in (current_pid, parent_pid):
                current_agent = agent
                break

    # Display results
    if current_agent:
        print("=== Agent Identity ===")
        print()
        print(f"  Agent ID: {current_agent.get('id', 'unknown')}")
        print(f"  Pane: {current_agent.get('pane_index', 'unknown')}")
        print(f"  PID: {current_agent.get('pid', 'unknown')}")
        print(f"  Status: {current_agent.get('status', 'unknown')}")
        print(f"  Session: {current_agent.get('session_name', 'unknown')}")
        print(f"  Backend: {backend.name}")

        if current_agent.get("tty"):
            print(f"  TTY: {current_agent.get('tty')}")

        last_seen = current_agent.get("last_seen")
        if last_seen:
            print(f"  Last Seen: {last_seen}")

        print()
        print("You ARE registered as an active agent.")
        print()
        print("Commands available (agent ID auto-detected):")
        print("  claudeswarm check-messages              # Check your inbox")
        print("  claudeswarm send-message <recipient> <type> <message>")
        print("  claudeswarm broadcast-message <type> <message>")
        print("  claudeswarm acquire-file-lock <path> <reason>")
        print("  claudeswarm release-file-lock <path>")
        print("  claudeswarm who-has-lock <path>")
        print("  claudeswarm list-agents")
        print("  claudeswarm list-all-locks")

        # Auto-check for pending messages (shows recent 3)
        print()
        print("=" * 68)
        print("RECENT MESSAGES (auto-checked)")
        print("=" * 68)
        try:
            from claudeswarm.messaging import MessageLogger

            msg_logger: MessageLogger = MessageLogger()
            messages: list[dict] = msg_logger.get_messages_for_agent(
                current_agent["id"], limit=WHOAMI_MESSAGE_PREVIEW_LIMIT
            )
            if messages:
                for msg in messages:
                    timestamp = msg["timestamp"][:19]  # Trim to YYYY-MM-DDTHH:MM:SS
                    print(f"\n[{timestamp}] From: {msg['sender']} ({msg['msg_type']})")
                    print(f"  {msg['content']}")
                if len(messages) >= WHOAMI_MESSAGE_PREVIEW_LIMIT:
                    print(
                        f"\n(Showing {WHOAMI_MESSAGE_PREVIEW_LIMIT} most recent. Use 'claudeswarm check-messages' for more)"
                    )
            else:
                print("\n  No messages.")
        except Exception as e:
            logger.debug(
                f"Failed to check messages for agent {current_agent.get('id', 'unknown')}: {e}",
                exc_info=True,
            )
            print(f"\n  (Could not check messages: {e})")
        print()
    else:
        print("=== Current Terminal ===")
        print()
        if backend.name == "tmux":
            print(f"  Pane: {current_pane if current_pane else current_identifier}")
        else:
            print(f"  Terminal: {current_identifier}")
            print(f"  Backend: {backend.name}")
        print()
        print("You are NOT registered as an agent.")
        print()
        print("Registered agents in this session:")
        if agents:
            for agent in agents:
                print(
                    f"  - {agent.get('id', 'unknown')} (pane: {agent.get('pane_index', 'unknown')}, PID: {agent.get('pid', 'unknown')})"
                )
        else:
            print("  (none)")
        print()
        print("To discover and register agents, run:")
        print("  claudeswarm discover-agents")

    sys.exit(0)


def cmd_reload(args: argparse.Namespace) -> None:
    """Reload claudeswarm CLI with latest changes.

    This command clears Python caches and reinstalls the package from
    the specified source (local or github).

    Args:
        args.source: Source to reload from ('local' or 'github')

    Exit Codes:
        0: Success
        1: Error during reload
    """
    import os

    source = args.source

    print("🔄 Reloading claudeswarm CLI...")
    print()

    # Find the claude-swarm installation directory
    try:
        import claudeswarm

        _ = Path(claudeswarm.__file__)

        # Try to find the source directory (for editable installs)
        editable_location = None

        # Check if installed via uv tool (look for .pth file)
        try:
            tool_dir = Path.home() / ".local/share/uv/tools/claude-swarm"
            if tool_dir.exists():
                # Find site-packages directory
                site_packages = list(tool_dir.glob("lib/python*/site-packages"))
                if site_packages:
                    pth_file = site_packages[0] / "_claude_swarm.pth"
                    if pth_file.exists():
                        # Read the path from the .pth file
                        pth_content = pth_file.read_text().strip()
                        # The path points to src/, we want the parent directory
                        if pth_content.endswith("/src"):
                            editable_location = str(Path(pth_content).parent)
                        else:
                            editable_location = pth_content
        except Exception as e:
            print(f"   Warning: Could not detect editable location: {e}", file=sys.stderr)

        if source == "local" and not editable_location:
            print("⚠️  No editable installation found.", file=sys.stderr)
            print(
                "   Run 'uv tool install --editable /path/to/claude-swarm' first", file=sys.stderr
            )
            sys.exit(1)

    except Exception as e:
        print(f"Error: Failed to locate claudeswarm installation: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 1: Clear Python caches
    print("1️⃣  Clearing Python caches...")
    try:
        if editable_location:
            subprocess.run(
                [
                    "find",
                    editable_location,
                    "-type",
                    "d",
                    "-name",
                    "__pycache__",
                    "-exec",
                    "rm",
                    "-rf",
                    "{}",
                    "+",
                ],
                capture_output=True,
                timeout=10,
            )
            subprocess.run(
                ["find", editable_location, "-type", "f", "-name", "*.pyc", "-delete"],
                capture_output=True,
                timeout=10,
            )

        # Clear site-packages cache
        for site_packages_dir in site.getsitepackages():
            subprocess.run(
                [
                    "find",
                    site_packages_dir,
                    "-type",
                    "d",
                    "-name",
                    "__pycache__",
                    "-path",
                    "*/claudeswarm/*",
                    "-exec",
                    "rm",
                    "-rf",
                    "{}",
                    "+",
                ],
                capture_output=True,
                timeout=10,
            )
        print("   ✓ Caches cleared")
    except Exception as e:
        print(f"   ⚠️  Warning: Cache clearing incomplete: {e}", file=sys.stderr)
    print()

    # Step 2: Install from source
    print(f"2️⃣  Installing from {source}...")
    try:
        if source == "local":
            if not editable_location:
                print("   ✗ No editable location found", file=sys.stderr)
                sys.exit(1)

            result = subprocess.run(
                ["uv", "tool", "install", "--force", "--editable", editable_location],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode == 0:
                print(f"   ✓ Installed from {editable_location} (editable mode)")
            else:
                # Check for uv cache permission errors
                if "Operation not permitted" in result.stderr and ".cache/uv" in result.stderr:
                    print("   ⚠️  uv cache permission error detected", file=sys.stderr)
                    print("   Attempting to clear cache and retry...", file=sys.stderr)
                    # Clear the problematic cache directory
                    subprocess.run(
                        ["rm", "-rf", os.path.expanduser("~/.cache/uv/sdists-v9/.git")],
                        capture_output=True,
                        timeout=5,
                    )
                    # Retry installation
                    result = subprocess.run(
                        [
                            "uv",
                            "tool",
                            "install",
                            "--force",
                            "--editable",
                            editable_location,
                        ],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    if result.returncode == 0:
                        print(
                            f"   ✓ Installed from {editable_location} (editable mode) after cache clear"
                        )
                    else:
                        print(f"   ✗ Installation failed: {result.stderr}", file=sys.stderr)
                        sys.exit(1)
                else:
                    print(f"   ✗ Installation failed: {result.stderr}", file=sys.stderr)
                    sys.exit(1)
        else:  # github
            result = subprocess.run(
                [
                    "uv",
                    "tool",
                    "install",
                    "--force",
                    "git+https://github.com/boriscardano/claude-swarm.git",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                print("   ✓ Installed from GitHub")
            else:
                print(f"   ✗ Installation failed: {result.stderr}", file=sys.stderr)
                sys.exit(1)
    except subprocess.TimeoutExpired:
        print("   ✗ Installation timed out", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"   ✗ Installation failed: {e}", file=sys.stderr)
        sys.exit(1)
    print()

    # Step 3: Verify installation
    print("3️⃣  Verifying installation...")
    try:
        result = subprocess.run(
            ["python3", "-c", "import claudeswarm; print(claudeswarm.__version__)"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        version = result.stdout.strip()
        print(f"   ✓ Version: {version}")
    except Exception:
        print("   ⚠️  Could not verify version", file=sys.stderr)
    print()

    print("✅ Reload complete!")
    print()
    if source == "local":
        print("You can now use 'claudeswarm' with your latest LOCAL changes in any tmux pane.")
        print("Future code changes will be immediately available (editable install).")
    else:
        print("You can now use 'claudeswarm' with the latest GITHUB version in any tmux pane.")
    print()
    print("Quick test: claudeswarm discover-agents")

    sys.exit(0)


def _init_detect_project_root() -> Path:
    """Detect and display project root directory.

    Returns:
        Path to project root directory
    """
    print("Step 1: Detecting project root...")
    detected_root = find_project_root()
    current_dir = Path.cwd()

    if detected_root:
        print(f"✓ Detected project root: {detected_root}")
        if detected_root != current_dir:
            print(f"  (You're currently in: {current_dir})")
    else:
        print("⚠ No project markers found (e.g., .git, pyproject.toml)")
        print(f"  Using current directory: {current_dir}")
        detected_root = current_dir

    print()
    return detected_root


def _init_check_and_create_config(project_root: Path, auto_yes: bool) -> None:
    """Check for existing configuration and create if needed.

    Args:
        project_root: Path to project root directory
        auto_yes: Whether to auto-accept prompts
    """
    print("Step 2: Checking configuration...")
    config_path = project_root / ".claudeswarm.yaml"

    if config_path.exists():
        print(f"✓ Configuration already exists: {config_path}")
    else:
        print("⚠ No configuration file found")

        # Ask user if they want to create config
        should_create = auto_yes
        if not auto_yes:
            # Check if stdin is a TTY (interactive terminal)
            if sys.stdin.isatty():
                try:
                    response = input("  Create default configuration? [Y/n]: ").strip().lower()
                    should_create = not response or response in ["y", "yes"]
                except EOFError:
                    # Non-interactive, default to creating config
                    print("  (non-interactive mode, creating config)")
                    should_create = True
            else:
                # Non-interactive, default to creating config
                print("  (non-interactive mode, creating config)")
                should_create = True

        if should_create:
            # Create config using existing cmd_config_init
            init_args = argparse.Namespace(output=str(config_path), force=False)
            try:
                cmd_config_init(init_args)
            except SystemExit:
                pass  # cmd_config_init calls sys.exit, catch it
        else:
            print("  Skipping config creation")

    print()


def _init_check_terminal_status() -> str:
    """Check terminal backend status.

    Detects the active backend and reports its status.

    Returns:
        Status string: "running", "not_running", "not_installed", or "error"
    """
    from claudeswarm.backend import get_backend

    backend = get_backend()
    print(f"Step 3: Checking terminal backend ({backend.name})...")

    if backend.name == "tmux":
        try:
            result = subprocess.run(["tmux", "list-sessions"], capture_output=True, timeout=2)
            if result.returncode == 0:
                sessions = result.stdout.decode().strip().split("\n")
                print(f"  Backend: tmux with {len(sessions)} session(s)")
                print()
                return "running"
            else:
                print("  tmux is installed but no sessions are running")
                print("  Tip: Start tmux with: tmux new -s myproject")
                print()
                return "not_running"
        except FileNotFoundError:
            print("  tmux not found - Install it first!")
            print("  macOS: brew install tmux")
            print("  Linux: apt install tmux / yum install tmux")
            print()
            return "not_installed"
        except subprocess.TimeoutExpired:
            print("  tmux command timed out")
            print()
            return "error"
        except Exception as e:
            print(f"  Error checking tmux: {e}")
            print()
            return "error"
    elif backend.name == "process":
        terminal_name = _detect_terminal_name()
        identifier = backend.get_current_agent_identifier()
        print(f"  Backend: process (terminal: {terminal_name})")
        if identifier:
            print(f"  TTY: {identifier}")
        print("  Messages: file-based (via Claude Code hooks)")
        print()
        return "running"
    else:
        print(f"  Unknown backend: {backend.name}")
        print()
        return "error"


def _detect_terminal_name() -> str:
    """Detect the current terminal application name.

    Returns:
        Terminal name string.
    """
    from .process_backend import _detect_terminal_name as _detect

    return _detect()


def _init_display_next_steps(project_root: Path, tmux_status: str) -> None:
    """Display next steps for user to complete setup.

    Args:
        project_root: Path to project root directory
        tmux_status: Status from tmux check ("running", "not_running", "not_installed", "error")
    """
    print("=== Next Steps ===")
    print()

    step = 1

    # Only show tmux setup if not running
    if tmux_status == "not_installed":
        print(f"{step}. Install tmux:")
        print("   macOS: brew install tmux")
        print("   Linux: apt install tmux / yum install tmux")
        print()
        step += 1
        print(f"{step}. Start a tmux session:")
        print("   tmux new -s myproject")
        print()
        step += 1
    elif tmux_status == "not_running":
        print(f"{step}. Start a tmux session:")
        print("   tmux new -s myproject")
        print()
        step += 1

    # Only show pane setup tip if tmux is running (user may need more panes)
    if tmux_status == "running":
        print(f"{step}. Split panes for multiple agents (if needed):")
        print("   Ctrl+b %    # Split vertically")
        print('   Ctrl+b "    # Split horizontally')
        print()
        step += 1

    print(f"{step}. Discover agents:")
    print("   claudeswarm discover-agents")
    print()
    step += 1

    print(f"{step}. Onboard agents (send coordination info):")
    print("   claudeswarm onboard")
    print()
    step += 1

    print(f"{step}. Start web dashboard:")
    print("   claudeswarm start-dashboard")
    print()

    print(f"📁 Project root: {project_root}")
    print()
    print("For more help: claudeswarm --help")
    print("Documentation: https://github.com/boriscardano/claude-swarm")


# Hook script content for automatic message checking
_HOOK_SCRIPT_CONTENT = """#!/bin/bash
#
# Claude Swarm Message Checker Hook
#
# This hook automatically checks for NEW (unread) messages from other agents
# and injects them into the conversation context before each user prompt.
#
# Uses --new-only to only show messages since last check (avoids duplicates)
# Uses --quiet for compact one-line format suitable for hook injection
#
# Triggered by: UserPromptSubmit hook in Claude Code
# Output: Automatically injected into agent's conversation as additional context

# Don't exit on errors - we handle them gracefully
set +e

# Optional debug logging
if [ "${CLAUDESWARM_DEBUG:-0}" = "1" ]; then
    echo "[DEBUG] check-for-messages.sh executed" >&2
fi

# Check for NEW messages only (unread since last check)
# Try uv run first (dev mode), fall back to direct claudeswarm (installed)
MESSAGES=""
if command -v uv &> /dev/null; then
  MESSAGES=$(uv run claudeswarm check-messages --new-only --quiet --limit 5 2>&1) || true
fi

# Fall back to direct claudeswarm if uv failed or not available
if [ -z "$MESSAGES" ] && command -v claudeswarm &> /dev/null; then
  MESSAGES=$(claudeswarm check-messages --new-only --quiet --limit 5 2>&1) || true
fi

# Filter out error messages (keep only lines starting with [)
MESSAGES=$(echo "$MESSAGES" | grep '^\\[' || true)

# Only output if there are actual new messages
if [ -n "$MESSAGES" ]; then
  echo "╔════════════════════════════════════════════════════════════════╗"
  echo "║  📬 NEW MESSAGES FROM OTHER AGENTS                             ║"
  echo "╚════════════════════════════════════════════════════════════════╝"
  echo ""
  printf '%s\\n' "$MESSAGES"
  echo ""
  echo "Reply with: claudeswarm send-message <agent-id> INFO \\"your message\\""
  echo "───────────────────────────────────────────────────────────────"
fi

exit 0
"""


def _init_setup_hooks(project_root: Path, auto_yes: bool) -> None:
    """Set up Claude Code hooks for automatic message checking.

    Creates the hooks directory, writes the check-for-messages.sh script,
    and configures settings.json to trigger the hook on UserPromptSubmit.

    Args:
        project_root: Path to project root directory
        auto_yes: Whether to auto-accept prompts
    """
    print("Step 4: Setting up message hooks...")

    hooks_dir = project_root / ".claude" / "hooks"
    hook_script = hooks_dir / "check-for-messages.sh"
    settings_file = project_root / ".claude" / "settings.json"

    # Check if hooks already exist
    if hook_script.exists():
        print(f"✓ Hook script already exists: {hook_script}")
        # Still check if settings.json has the hook configured
        _ensure_hook_in_settings(settings_file)
        print()
        return

    # Ask user if they want to set up hooks
    should_setup = auto_yes
    if not auto_yes:
        if sys.stdin.isatty():
            try:
                response = input("  Set up automatic message checking? [Y/n]: ").strip().lower()
                should_setup = not response or response in ["y", "yes"]
            except EOFError:
                print("  (non-interactive mode, setting up hooks)")
                should_setup = True
        else:
            print("  (non-interactive mode, setting up hooks)")
            should_setup = True

    if not should_setup:
        print("  Skipping hook setup")
        print()
        return

    # Create hooks directory
    hooks_dir.mkdir(parents=True, exist_ok=True)

    # Write hook script
    hook_script.write_text(_HOOK_SCRIPT_CONTENT)
    hook_script.chmod(0o755)
    print(f"✓ Created hook script: {hook_script}")

    # Configure settings.json
    _ensure_hook_in_settings(settings_file)
    print()


def _ensure_hook_in_settings(settings_file: Path) -> None:
    """Ensure the message hook is configured in settings.json.

    Args:
        settings_file: Path to .claude/settings.json
    """
    hook_entry = {
        "type": "command",
        "command": "./.claude/hooks/check-for-messages.sh",
    }

    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text())
        except json.JSONDecodeError:
            print(f"  Warning: Could not parse {settings_file}, skipping hook config")
            return

        hooks = settings.setdefault("hooks", {})
        user_prompt_hooks = hooks.setdefault("UserPromptSubmit", [])

        # Check if hook already exists
        if any(h.get("command") == hook_entry["command"] for h in user_prompt_hooks):
            print(f"✓ Hook already configured in {settings_file}")
            return

        user_prompt_hooks.append(hook_entry)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        print(f"✓ Added hook to {settings_file}")
    else:
        # Create new settings file with hook
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        settings = {"hooks": {"UserPromptSubmit": [hook_entry]}}
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        print(f"✓ Created {settings_file} with hook config")


# =============================================================================
# A2A-Inspired Command Handlers
# =============================================================================


def cmd_cards_list(args: argparse.Namespace) -> None:
    """List all registered agent cards."""
    try:
        registry = AgentCardRegistry(project_root=args.project_root)
        cards = registry.list_cards()

        if args.json:
            print(json.dumps([card.to_dict() for card in cards], indent=2))
        else:
            if not cards:
                print("No agent cards registered.")
            else:
                print(f"=== Agent Cards ({len(cards)}) ===")
                for card in cards:
                    status_symbol = (
                        "✓"
                        if card.availability == "active"
                        else "⚠"
                        if card.availability == "busy"
                        else "✗"
                    )
                    skills_str = ", ".join(card.skills[:3])
                    if len(card.skills) > 3:
                        skills_str += f" (+{len(card.skills) - 3} more)"
                    print(
                        f"  {status_symbol} {card.agent_id:<12} | {card.name:<20} | Skills: {skills_str}"
                    )

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_cards_get(args: argparse.Namespace) -> None:
    """Get a specific agent card."""
    try:
        registry = AgentCardRegistry(project_root=args.project_root)
        card = registry.get_card(args.agent_id)

        if not card:
            print(f"No card found for agent: {args.agent_id}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(card.to_dict(), indent=2))
        else:
            print(f"=== Agent Card: {card.agent_id} ===")
            print(f"  Name: {card.name}")
            print(f"  Description: {card.description}")
            print(f"  Availability: {card.availability}")
            print(f"  Skills: {', '.join(card.skills)}")
            print(f"  Tools: {', '.join(card.tools)}")
            if card.success_rates:
                print("  Success Rates:")
                for skill, rate in sorted(card.success_rates.items(), key=lambda x: -x[1]):
                    print(f"    {skill}: {rate:.1%}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_cards_register(args: argparse.Namespace) -> None:
    """Register a new agent card."""
    try:
        validated_agent_id = _require_agent_id(args)
        skills = args.skills.split(",") if args.skills else []
        tools = args.tools.split(",") if args.tools else []

        registry = AgentCardRegistry(project_root=args.project_root)
        card = registry.register_agent(
            agent_id=validated_agent_id,
            name=args.name or validated_agent_id,
            skills=skills,
            tools=tools,
        )

        print(f"Agent card registered: {validated_agent_id}")
        print(f"  Name: {card.name}")
        print(f"  Skills: {', '.join(card.skills) or 'none'}")
        print(f"  Tools: {', '.join(card.tools) or 'none'}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_cards_update(args: argparse.Namespace) -> None:
    """Update an agent card."""
    try:
        validated_agent_id = _require_agent_id(args)

        registry = AgentCardRegistry(project_root=args.project_root)
        card = registry.get_card(validated_agent_id)

        if not card:
            print(f"No card found for agent: {validated_agent_id}", file=sys.stderr)
            sys.exit(1)

        updates = {}
        if args.name:
            updates["name"] = args.name
        if args.description:
            updates["description"] = args.description
        if args.skills:
            updates["skills"] = args.skills.split(",")
        if args.tools:
            updates["tools"] = args.tools.split(",")
        if args.availability:
            updates["availability"] = args.availability

        if not updates:
            print("No updates specified.", file=sys.stderr)
            sys.exit(1)

        registry.update_card(validated_agent_id, **updates)
        print(f"Agent card updated: {validated_agent_id}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tasks_list(args: argparse.Namespace) -> None:
    """List all tasks."""
    try:
        manager = TaskManager(project_root=args.project_root)
        tasks = manager.list_tasks(
            status=TaskStatus(args.status) if args.status else None,
            assigned_to=args.assignee,
        )

        if args.json:
            print(json.dumps([task.to_dict() for task in tasks], indent=2))
        else:
            if not tasks:
                print("No tasks found.")
            else:
                print(f"=== Tasks ({len(tasks)}) ===")
                for task in tasks:
                    priority_symbol = {
                        TaskPriority.CRITICAL: "🔴",
                        TaskPriority.HIGH: "🟠",
                        TaskPriority.NORMAL: "🟢",
                        TaskPriority.LOW: "⚪",
                    }.get(task.priority, "⚪")
                    assignee = task.assigned_to or "unassigned"
                    print(
                        f"  {priority_symbol} [{task.status.value:<10}] {task.task_id[:8]}... | {task.objective[:40]} | {assignee}"
                    )

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tasks_get(args: argparse.Namespace) -> None:
    """Get a specific task."""
    try:
        manager = TaskManager(project_root=args.project_root)
        task = manager.get_task(args.task_id)

        if not task:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(task.to_dict(), indent=2))
        else:
            print(f"=== Task: {task.task_id} ===")
            print(f"  Objective: {task.objective}")
            print(f"  Status: {task.status.value}")
            print(f"  Priority: {task.priority.value}")
            print(f"  Creator: {task.created_by}")
            print(f"  Assignee: {task.assigned_to or 'unassigned'}")
            if task.constraints:
                print(f"  Constraints: {', '.join(task.constraints)}")
            if task.files:
                print(f"  Files: {', '.join(task.files)}")
            if task.blocked_by:
                print(f"  Blocked by: {', '.join(task.blocked_by)}")
            print(f"  Created: {task.created_at}")
            print(f"  Updated: {task.updated_at}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tasks_create(args: argparse.Namespace) -> None:
    """Create a new task."""
    try:
        validated_agent_id = _require_agent_id(args, "creator")

        constraints = args.constraints.split(",") if args.constraints else []
        files = args.files.split(",") if args.files else []

        manager = TaskManager(project_root=args.project_root)
        task = manager.create_task(
            objective=args.objective,
            created_by=validated_agent_id,
            priority=TaskPriority(args.priority) if args.priority else TaskPriority.NORMAL,
            constraints=constraints,
            files=files,
            context_id=args.context_id,
        )

        print(f"Task created: {task.task_id}")
        print(f"  Objective: {task.objective}")
        print(f"  Priority: {task.priority.value}")
        print(f"  Creator: {task.created_by}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_tasks_update(args: argparse.Namespace) -> None:
    """Update a task's status."""
    try:
        manager = TaskManager(project_root=args.project_root)
        task = manager.get_task(args.task_id)

        if not task:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            sys.exit(1)

        if args.status:
            new_status = TaskStatus(args.status)
            task.transition_to(new_status)

        if args.assignee:
            task.assigned_to = args.assignee

        manager.save_task(task)
        print(f"Task updated: {task.task_id}")
        print(f"  Status: {task.status.value}")
        if task.assigned_to:
            print(f"  Assignee: {task.assigned_to}")

        sys.exit(0)

    except ValueError as e:
        print(f"Invalid transition: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_delegate(args: argparse.Namespace) -> None:
    """Delegate a task to the best-matched agent."""
    try:
        manager = TaskManager(project_root=args.project_root)
        task = manager.get_task(args.task_id)

        if not task:
            print(f"Task not found: {args.task_id}", file=sys.stderr)
            sys.exit(1)

        delegation_manager = DelegationManager(project_root=args.project_root)
        result = delegation_manager.delegate_task(task)

        if result:
            print("Task delegated successfully!")
            print(f"  Task: {task.task_id}")
            print(f"  Assigned to: {result['agent_id']}")
            print(f"  Match score: {result['score']:.2f}")
            print(f"  Matched skills: {', '.join(result['matched_skills'])}")
        else:
            print("No suitable agent found for delegation.", file=sys.stderr)
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_find_agent(args: argparse.Namespace) -> None:
    """Find the best agent for a task or skill."""
    try:
        delegation_manager = DelegationManager(project_root=args.project_root)

        if args.skill:
            # Find agents with specific skill
            registry = AgentCardRegistry(project_root=args.project_root)
            agent_tuples = registry.find_agents_with_skill(args.skill)

            if args.json:
                print(json.dumps([a.to_dict() for a, _ in agent_tuples], indent=2))
            else:
                if not agent_tuples:
                    print(f"No agents found with skill: {args.skill}")
                else:
                    print(f"=== Agents with '{args.skill}' skill ({len(agent_tuples)}) ===")
                    for agent, proficiency in agent_tuples:
                        print(f"  {agent.agent_id:<12} | Proficiency: {proficiency:.1%}")
        else:
            # Find best agent for a task description
            if not args.objective:
                print("Either --skill or --objective must be provided", file=sys.stderr)
                sys.exit(1)

            # Create a temporary task to find best agent
            manager = TaskManager(project_root=args.project_root)
            temp_task = manager.create_task(
                objective=args.objective,
                created_by="cli",
            )
            agent, score, skill_matches = delegation_manager.find_best_agent(temp_task)

            if args.json:
                if agent:
                    print(
                        json.dumps(
                            {
                                "agent_id": agent.agent_id,
                                "score": score,
                                "skill_matches": skill_matches,
                            },
                            indent=2,
                        )
                    )
                else:
                    print("{}")
            else:
                if agent:
                    print(f"Best agent for: {args.objective}")
                    print(f"  Agent: {agent.agent_id}")
                    print(f"  Score: {score:.2f}")
                    matched = [f"{k}: {v:.1%}" for k, v in skill_matches.items()]
                    print(f"  Matched skills: {', '.join(matched) or 'none'}")
                else:
                    print("No suitable agent found.")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_context_list(args: argparse.Namespace) -> None:
    """List all shared contexts."""
    try:
        store = ContextStore(project_root=args.project_root)
        contexts = store.list_contexts()

        if args.json:
            print(json.dumps([ctx.to_dict() for ctx in contexts], indent=2))
        else:
            if not contexts:
                print("No contexts found.")
            else:
                print(f"=== Shared Contexts ({len(contexts)}) ===")
                for ctx in contexts:
                    files_count = len(ctx.files_touched)
                    decisions_count = len(ctx.decisions)
                    print(
                        f"  {ctx.context_id:<20} | {ctx.summary[:40]} | {files_count} files, {decisions_count} decisions"
                    )

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_context_get(args: argparse.Namespace) -> None:
    """Get a specific context."""
    try:
        store = ContextStore(project_root=args.project_root)
        ctx = store.get_context(args.context_id)

        if not ctx:
            print(f"Context not found: {args.context_id}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(ctx.to_dict(), indent=2))
        else:
            print(f"=== Context: {ctx.context_id} ===")
            print(f"  Summary: {ctx.summary}")
            if ctx.files_touched:
                print(f"  Files: {', '.join(ctx.files_touched)}")
            if ctx.related_contexts:
                print(f"  Related: {', '.join(ctx.related_contexts)}")
            if ctx.decisions:
                print("  Decisions:")
                for decision in ctx.decisions:
                    print(f"    - {decision.decision} (by {decision.by})")
                    if decision.reason:
                        print(f"      Reason: {decision.reason}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_context_create(args: argparse.Namespace) -> None:
    """Create a new shared context."""
    try:
        validated_agent_id = _require_agent_id(args, "creator")
        related = args.related.split(",") if args.related else []

        store = ContextStore(project_root=args.project_root)
        ctx = store.create_context(
            name=args.context_id,
            created_by=validated_agent_id,
            summary=args.summary,
            context_id=args.context_id,
            related_contexts=related,
        )

        print(f"Context created: {ctx.context_id}")
        print(f"  Summary: {ctx.summary}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_context_add_decision(args: argparse.Namespace) -> None:
    """Add a decision to a context."""
    try:
        validated_agent_id = _require_agent_id(args, "by")

        store = ContextStore(project_root=args.project_root)
        ctx = store.get_context(args.context_id)

        if not ctx:
            print(f"Context not found: {args.context_id}", file=sys.stderr)
            sys.exit(1)

        decision = ContextDecision(
            decision=args.decision,
            by=validated_agent_id,
            reason=args.reason,
        )

        ctx.add_decision(decision)
        store.save_context(ctx)

        print(f"Decision added to context: {ctx.context_id}")
        print(f"  Decision: {decision.decision}")
        print(f"  By: {decision.by}")

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_memory_get(args: argparse.Namespace) -> None:
    """Get an agent's memory."""
    try:
        validated_agent_id = _require_agent_id(args)

        store = MemoryStore(project_root=args.project_root)
        memory = store.get_memory(validated_agent_id)

        if not memory:
            print(f"No memory found for agent: {validated_agent_id}")
            sys.exit(0)

        if args.json:
            print(json.dumps(memory.to_dict(), indent=2))
        else:
            print(f"=== Memory: {memory.agent_id} ===")
            print(f"  Task history: {len(memory.task_history)} tasks")
            print(f"  Patterns learned: {len(memory.patterns)} patterns")
            print(f"  Relationships: {len(memory.relationships)} agents")
            print(f"  Knowledge items: {len(memory.knowledge)} items")

            if memory.patterns:
                print("\n  Recent Patterns:")
                for pattern in list(memory.patterns.values())[:3]:
                    print(f"    - {pattern.pattern}: {pattern.description}")

            if memory.relationships:
                print("\n  Agent Relationships:")
                for agent_id, rel in list(memory.relationships.items())[:3]:
                    print(
                        f"    - {agent_id}: trust={rel.trust_score:.2f}, collaborations={rel.collaboration_count}"
                    )

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_memory_clear(args: argparse.Namespace) -> None:
    """Clear an agent's memory."""
    try:
        validated_agent_id = _require_agent_id(args)

        store = MemoryStore(project_root=args.project_root)
        store.clear_memory(validated_agent_id)

        print(f"Memory cleared for agent: {validated_agent_id}")
        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_learning_stats(args: argparse.Namespace) -> None:
    """Show learning statistics for an agent."""
    try:
        validated_agent_id = _require_agent_id(args)

        system = LearningSystem(project_root=args.project_root)
        performance = system.get_agent_performance(validated_agent_id)

        if not performance:
            print(f"No learning data for agent: {validated_agent_id}")
            sys.exit(0)

        if args.json:
            print(json.dumps(performance.to_dict(), indent=2))
        else:
            print(f"=== Learning Stats: {performance.agent_id} ===")
            print(f"  Tasks completed: {performance.tasks_completed}")
            print(f"  Tasks failed: {performance.tasks_failed}")
            print(f"  Average response time: {performance.avg_response_time:.1f}s")

            if performance.skill_metrics:
                print("\n  Skill Performance:")
                for skill, metrics in sorted(
                    performance.skill_metrics.items(), key=lambda x: -x[1].success_rate
                )[:5]:
                    print(
                        f"    {skill}: {metrics.success_rate:.1%} ({metrics.success_count}/{metrics.total_count})"
                    )

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_conflict_resolve(args: argparse.Namespace) -> None:
    """Resolve a file lock conflict."""
    try:
        resolver = ConflictResolver(project_root=args.project_root)

        # Get the current conflict for the file
        lock_manager = LockManager(project_root=args.project_root)
        lock = lock_manager.who_has_lock(args.filepath)

        if not lock:
            print(f"No lock conflict on: {args.filepath}")
            sys.exit(0)

        validated_agent_id = _require_agent_id(args, "requester")

        if lock.agent_id == validated_agent_id:
            print(f"You already hold the lock on: {args.filepath}")
            sys.exit(0)

        # Try to resolve the conflict
        result = resolver.resolve_conflict(
            filepath=args.filepath,
            requester_id=validated_agent_id,
            holder_id=lock.agent_id,
        )

        if result.resolved:
            print(f"Conflict resolved: {args.filepath}")
            print(f"  Winner: {result.winner}")
            print(f"  Strategy: {result.strategy.value}")
            if result.message:
                print(f"  Message: {result.message}")
        else:
            print(f"Conflict not resolved: {args.filepath}", file=sys.stderr)
            if result.message:
                print(f"  Reason: {result.message}", file=sys.stderr)
            sys.exit(1)

        sys.exit(0)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize Claude Swarm in current project with guided setup.

    This command helps users set up Claude Swarm by:
    1. Detecting the project root
    2. Creating config file if needed
    3. Checking tmux status
    4. Setting up message hooks for auto-checking
    5. Showing next steps

    Args:
        args: Parsed command-line arguments

    Exit Codes:
        0: Success
        1: Error during setup
    """
    print("=== Claude Swarm Project Setup ===")
    print()

    # Step 1: Detect project root
    project_root = _init_detect_project_root()

    # Step 2: Check and create configuration
    _init_check_and_create_config(project_root, args.yes)

    # Step 3: Check terminal backend status
    tmux_status = _init_check_terminal_status()

    # Step 4: Set up message hooks
    _init_setup_hooks(project_root, args.yes)

    # Step 5: Display next steps (adapts based on what's already set up)
    _init_display_next_steps(project_root, tmux_status)

    sys.exit(0)


def main() -> NoReturn:
    """Main entry point for the claudeswarm CLI.

    Parses command-line arguments and dispatches to appropriate handler.
    """
    parser = argparse.ArgumentParser(
        description="Claude Swarm - Multi-agent coordination system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (default: current directory)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        help="Set logging level (default: WARNING)",
    )

    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Write logs to specified file (in addition to stderr)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # init command
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize Claude Swarm in current project (guided setup)",
    )
    init_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Auto-accept all prompts",
    )
    init_parser.set_defaults(func=cmd_init)

    # reload command
    reload_parser = subparsers.add_parser(
        "reload",
        help="Reload claudeswarm CLI with latest changes",
    )
    reload_parser.add_argument(
        "--source",
        type=str,
        choices=["local", "github"],
        default="local",
        help="Source to reload from: 'local' for editable install or 'github' for remote (default: local)",
    )
    reload_parser.set_defaults(func=cmd_reload)

    # discover-agents command
    discover_parser = subparsers.add_parser(
        "discover-agents",
        help="Discover active Claude Code agents in tmux",
    )
    discover_parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously monitor for agents",
    )
    discover_parser.add_argument(
        "--interval",
        type=positive_int,
        default=30,
        help="Refresh interval in seconds for watch mode (default: 30)",
    )
    discover_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    discover_parser.add_argument(
        "--stale-threshold",
        type=int,
        default=DEFAULT_STALE_THRESHOLD,
        help=f"Seconds after which an agent is considered stale (default: {DEFAULT_STALE_THRESHOLD})",
    )
    discover_parser.set_defaults(func=cmd_discover_agents)

    # list-agents command
    list_agents_parser = subparsers.add_parser(
        "list-agents",
        help="List active agents from registry",
    )
    list_agents_parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    list_agents_parser.set_defaults(func=cmd_list_agents)

    # send-message command
    send_parser = subparsers.add_parser(
        "send-message",
        help="Send a message to a specific agent",
    )
    send_parser.add_argument("recipient_id", help="ID of receiving agent")
    send_parser.add_argument("type", help="Message type (INFO, QUESTION, BLOCKED, etc.)")
    send_parser.add_argument("content", help="Message content")
    send_parser.add_argument(
        "--sender-id",
        dest="sender_id",
        default=None,
        help="ID of sending agent (auto-detected if omitted)",
    )
    send_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    send_parser.add_argument(
        "--ack",
        action="store_true",
        help="Request acknowledgment with automatic retry if unacknowledged",
    )
    send_parser.set_defaults(func=cmd_send_message)

    # broadcast-message command
    broadcast_parser = subparsers.add_parser(
        "broadcast-message",
        help="Broadcast a message to all agents",
    )
    broadcast_parser.add_argument("type", help="Message type (INFO, QUESTION, BLOCKED, etc.)")
    broadcast_parser.add_argument("content", help="Message content")
    broadcast_parser.add_argument(
        "--sender-id",
        dest="sender_id",
        default=None,
        help="ID of sending agent (auto-detected if omitted)",
    )
    broadcast_parser.add_argument(
        "--include-self",
        action="store_true",
        help="Include sender in broadcast (default: exclude)",
    )
    broadcast_parser.add_argument("--json", action="store_true", help="Output in JSON format")
    broadcast_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed delivery status"
    )
    broadcast_parser.set_defaults(func=cmd_broadcast_message)

    # onboard command
    onboard_parser = subparsers.add_parser(
        "onboard",
        help="Onboard all discovered agents to the coordination system",
    )
    onboard_parser.set_defaults(func=cmd_onboard)

    # whoami command
    whoami_parser = subparsers.add_parser(
        "whoami",
        help="Display information about the current agent (if registered)",
    )
    whoami_parser.set_defaults(func=cmd_whoami)

    # check-messages command
    check_messages_parser = subparsers.add_parser(
        "check-messages",
        help="Check messages sent to this agent (inbox)",
    )
    check_messages_parser.add_argument(
        "--limit",
        type=positive_int,
        default=10,
        help="Number of recent messages to show (default: 10)",
    )
    check_messages_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID to check messages for (auto-detected if omitted)",
    )
    check_messages_parser.add_argument(
        "--new-only",
        action="store_true",
        help="Only show unread messages (messages since last check)",
    )
    check_messages_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Compact output suitable for hooks (one line per message)",
    )
    check_messages_parser.set_defaults(func=cmd_check_messages)

    # acknowledge-message command
    ack_parser = subparsers.add_parser(
        "acknowledge-message",
        help="Acknowledge receipt of a message (stops retry attempts)",
    )
    ack_parser.add_argument("msg_id", help="Message ID to acknowledge")
    ack_parser.set_defaults(func=cmd_acknowledge_message)

    # acquire-file-lock command
    acquire_parser = subparsers.add_parser(
        "acquire-file-lock",
        help="Acquire a lock on a file",
    )
    acquire_parser.add_argument("filepath", help="Path to the file to lock")
    acquire_parser.add_argument("reason", nargs="?", default="", help="Reason for the lock")
    acquire_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID acquiring the lock (auto-detected if omitted)",
    )
    acquire_parser.set_defaults(func=cmd_acquire_file_lock)

    # release-file-lock command
    release_parser = subparsers.add_parser(
        "release-file-lock",
        help="Release a lock on a file",
    )
    release_parser.add_argument("filepath", help="Path to the file to unlock")
    release_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID releasing the lock (auto-detected if omitted)",
    )
    release_parser.set_defaults(func=cmd_release_file_lock)

    # who-has-lock command
    who_parser = subparsers.add_parser(
        "who-has-lock",
        help="Check who has a lock on a file",
    )
    who_parser.add_argument("filepath", help="Path to the file to check")
    who_parser.add_argument("--json", action="store_true", help="Output as JSON")
    who_parser.set_defaults(func=cmd_who_has_lock)

    # list-all-locks command
    list_parser = subparsers.add_parser(
        "list-all-locks",
        help="List all active locks",
    )
    list_parser.add_argument("--include-stale", action="store_true", help="Include stale locks")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    list_parser.set_defaults(func=cmd_list_all_locks)

    # cleanup-stale-locks command
    cleanup_parser = subparsers.add_parser(
        "cleanup-stale-locks",
        help="Clean up stale locks",
    )
    cleanup_parser.set_defaults(func=cmd_cleanup_stale_locks)

    # start-monitoring command
    monitoring_parser = subparsers.add_parser(
        "start-monitoring",
        help="Start the monitoring dashboard",
    )
    monitoring_parser.add_argument(
        "--filter-type",
        type=str,
        help="Filter messages by type (BLOCKED, QUESTION, INFO, etc.)",
    )
    monitoring_parser.add_argument(
        "--filter-agent",
        type=str,
        help="Filter messages by agent ID",
    )
    monitoring_parser.add_argument(
        "--no-tmux",
        action="store_true",
        help="Run in current terminal instead of creating tmux pane",
    )
    monitoring_parser.set_defaults(func=cmd_start_monitoring)

    # start-dashboard command
    dashboard_parser = subparsers.add_parser(
        "start-dashboard",
        help="Start web-based monitoring dashboard",
    )
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to run server on (default: from config or 8080)",
    )
    dashboard_parser.add_argument(
        "--host",
        default=None,
        help="Host to bind to (default: from config or localhost)",
    )
    dashboard_parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser",
    )
    dashboard_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    dashboard_parser.set_defaults(func=cmd_start_dashboard)

    # config command group
    config_parser = subparsers.add_parser(
        "config",
        help="Configuration management",
    )
    config_subparsers = config_parser.add_subparsers(dest="config_command", help="Config command")

    # config init
    config_init_parser = config_subparsers.add_parser(
        "init",
        help="Create default configuration file",
    )
    config_init_parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Output path (default: .claudeswarm.yaml)",
    )
    config_init_parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing file",
    )
    config_init_parser.set_defaults(func=cmd_config_init)

    # config show
    config_show_parser = config_subparsers.add_parser(
        "show",
        help="Display current configuration",
    )
    config_show_parser.add_argument(
        "--file",
        type=str,
        help="Path to config file (default: search for .claudeswarm.yaml)",
    )
    config_show_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    config_show_parser.set_defaults(func=cmd_config_show)

    # config validate
    config_validate_parser = config_subparsers.add_parser(
        "validate",
        help="Validate configuration file",
    )
    config_validate_parser.add_argument(
        "--file",
        type=str,
        help="Path to config file (default: search for .claudeswarm.yaml)",
    )
    config_validate_parser.set_defaults(func=cmd_config_validate)

    # config edit
    config_edit_parser = config_subparsers.add_parser(
        "edit",
        help="Open configuration file in editor",
    )
    config_edit_parser.add_argument(
        "--file",
        type=str,
        help="Path to config file (default: search for .claudeswarm.yaml)",
    )
    config_edit_parser.set_defaults(func=cmd_config_edit)

    # ==========================================================================
    # A2A-Inspired Commands
    # ==========================================================================

    # cards command group
    cards_parser = subparsers.add_parser(
        "cards",
        help="Agent card management (A2A protocol)",
    )
    cards_subparsers = cards_parser.add_subparsers(dest="cards_command", help="Cards command")

    # cards list
    cards_list_parser = cards_subparsers.add_parser(
        "list",
        help="List all registered agent cards",
    )
    cards_list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    cards_list_parser.set_defaults(func=cmd_cards_list)

    # cards get
    cards_get_parser = cards_subparsers.add_parser(
        "get",
        help="Get a specific agent card",
    )
    cards_get_parser.add_argument("agent_id", help="Agent ID to get card for")
    cards_get_parser.add_argument("--json", action="store_true", help="Output as JSON")
    cards_get_parser.set_defaults(func=cmd_cards_get)

    # cards register
    cards_register_parser = cards_subparsers.add_parser(
        "register",
        help="Register a new agent card",
    )
    cards_register_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID (auto-detected if omitted)",
    )
    cards_register_parser.add_argument("--name", help="Agent display name")
    cards_register_parser.add_argument("--description", help="Agent description")
    cards_register_parser.add_argument("--skills", help="Comma-separated list of skills")
    cards_register_parser.add_argument("--tools", help="Comma-separated list of tools")
    cards_register_parser.set_defaults(func=cmd_cards_register)

    # cards update
    cards_update_parser = cards_subparsers.add_parser(
        "update",
        help="Update an agent card",
    )
    cards_update_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID (auto-detected if omitted)",
    )
    cards_update_parser.add_argument("--name", help="New agent display name")
    cards_update_parser.add_argument("--description", help="New agent description")
    cards_update_parser.add_argument("--skills", help="New comma-separated list of skills")
    cards_update_parser.add_argument("--tools", help="New comma-separated list of tools")
    cards_update_parser.add_argument(
        "--availability",
        choices=["active", "busy", "offline"],
        help="New availability status",
    )
    cards_update_parser.set_defaults(func=cmd_cards_update)

    # tasks command group
    tasks_parser = subparsers.add_parser(
        "tasks",
        help="Task lifecycle management",
    )
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command", help="Tasks command")

    # tasks list
    tasks_list_parser = tasks_subparsers.add_parser(
        "list",
        help="List all tasks",
    )
    tasks_list_parser.add_argument(
        "--status",
        choices=[
            "pending",
            "assigned",
            "working",
            "review",
            "completed",
            "blocked",
            "failed",
            "cancelled",
        ],
        help="Filter by status",
    )
    tasks_list_parser.add_argument("--assignee", help="Filter by assignee")
    tasks_list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    tasks_list_parser.set_defaults(func=cmd_tasks_list)

    # tasks get
    tasks_get_parser = tasks_subparsers.add_parser(
        "get",
        help="Get a specific task",
    )
    tasks_get_parser.add_argument("task_id", help="Task ID")
    tasks_get_parser.add_argument("--json", action="store_true", help="Output as JSON")
    tasks_get_parser.set_defaults(func=cmd_tasks_get)

    # tasks create
    tasks_create_parser = tasks_subparsers.add_parser(
        "create",
        help="Create a new task",
    )
    tasks_create_parser.add_argument("objective", help="Task objective")
    tasks_create_parser.add_argument(
        "--creator",
        default=None,
        help="Creator agent ID (auto-detected if omitted)",
    )
    tasks_create_parser.add_argument(
        "--priority",
        choices=["low", "normal", "high", "critical"],
        default="normal",
        help="Task priority (default: normal)",
    )
    tasks_create_parser.add_argument("--constraints", help="Comma-separated constraints")
    tasks_create_parser.add_argument("--files", help="Comma-separated file paths")
    tasks_create_parser.add_argument("--context-id", dest="context_id", help="Related context ID")
    tasks_create_parser.set_defaults(func=cmd_tasks_create)

    # tasks update
    tasks_update_parser = tasks_subparsers.add_parser(
        "update",
        help="Update a task",
    )
    tasks_update_parser.add_argument("task_id", help="Task ID to update")
    tasks_update_parser.add_argument(
        "--status",
        choices=[
            "pending",
            "assigned",
            "working",
            "review",
            "completed",
            "blocked",
            "failed",
            "cancelled",
        ],
        help="New status",
    )
    tasks_update_parser.add_argument("--assignee", help="New assignee agent ID")
    tasks_update_parser.set_defaults(func=cmd_tasks_update)

    # delegate command
    delegate_parser = subparsers.add_parser(
        "delegate",
        help="Delegate a task to the best-matched agent",
    )
    delegate_parser.add_argument("task_id", help="Task ID to delegate")
    delegate_parser.set_defaults(func=cmd_delegate)

    # find-agent command
    find_agent_parser = subparsers.add_parser(
        "find-agent",
        help="Find the best agent for a task or skill",
    )
    find_agent_parser.add_argument("--skill", help="Find agents with specific skill")
    find_agent_parser.add_argument("--objective", help="Find best agent for task objective")
    find_agent_parser.add_argument("--json", action="store_true", help="Output as JSON")
    find_agent_parser.set_defaults(func=cmd_find_agent)

    # context command group
    context_parser = subparsers.add_parser(
        "context",
        help="Shared context management",
    )
    context_subparsers = context_parser.add_subparsers(
        dest="context_command", help="Context command"
    )

    # context list
    context_list_parser = context_subparsers.add_parser(
        "list",
        help="List all shared contexts",
    )
    context_list_parser.add_argument("--json", action="store_true", help="Output as JSON")
    context_list_parser.set_defaults(func=cmd_context_list)

    # context get
    context_get_parser = context_subparsers.add_parser(
        "get",
        help="Get a specific context",
    )
    context_get_parser.add_argument("context_id", help="Context ID")
    context_get_parser.add_argument("--json", action="store_true", help="Output as JSON")
    context_get_parser.set_defaults(func=cmd_context_get)

    # context create
    context_create_parser = context_subparsers.add_parser(
        "create",
        help="Create a new shared context",
    )
    context_create_parser.add_argument("context_id", help="Context ID (e.g., feature-auth)")
    context_create_parser.add_argument("summary", help="Context summary")
    context_create_parser.add_argument(
        "--creator", default=None, help="Creator agent ID (auto-detected if omitted)"
    )
    context_create_parser.add_argument("--related", help="Comma-separated related context IDs")
    context_create_parser.set_defaults(func=cmd_context_create)

    # context add-decision
    context_decision_parser = context_subparsers.add_parser(
        "add-decision",
        help="Add a decision to a context",
    )
    context_decision_parser.add_argument("context_id", help="Context ID")
    context_decision_parser.add_argument("decision", help="Decision made")
    context_decision_parser.add_argument("--reason", help="Reason for decision")
    context_decision_parser.add_argument(
        "--by",
        default=None,
        help="Agent who made the decision (auto-detected if omitted)",
    )
    context_decision_parser.set_defaults(func=cmd_context_add_decision)

    # memory command group
    memory_parser = subparsers.add_parser(
        "memory",
        help="Agent memory management",
    )
    memory_subparsers = memory_parser.add_subparsers(dest="memory_command", help="Memory command")

    # memory get
    memory_get_parser = memory_subparsers.add_parser(
        "get",
        help="Get an agent's memory",
    )
    memory_get_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID (auto-detected if omitted)",
    )
    memory_get_parser.add_argument("--json", action="store_true", help="Output as JSON")
    memory_get_parser.set_defaults(func=cmd_memory_get)

    # memory clear
    memory_clear_parser = memory_subparsers.add_parser(
        "clear",
        help="Clear an agent's memory",
    )
    memory_clear_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID (auto-detected if omitted)",
    )
    memory_clear_parser.set_defaults(func=cmd_memory_clear)

    # learning command group
    learning_parser = subparsers.add_parser(
        "learning",
        help="Capability learning statistics",
    )
    learning_subparsers = learning_parser.add_subparsers(
        dest="learning_command", help="Learning command"
    )

    # learning stats
    learning_stats_parser = learning_subparsers.add_parser(
        "stats",
        help="Show learning statistics for an agent",
    )
    learning_stats_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID (auto-detected if omitted)",
    )
    learning_stats_parser.add_argument("--json", action="store_true", help="Output as JSON")
    learning_stats_parser.set_defaults(func=cmd_learning_stats)

    # resolve-conflict command
    resolve_conflict_parser = subparsers.add_parser(
        "resolve-conflict",
        help="Resolve a file lock conflict",
    )
    resolve_conflict_parser.add_argument("filepath", help="Path to the conflicted file")
    resolve_conflict_parser.add_argument(
        "--requester",
        default=None,
        help="Agent ID requesting the lock (auto-detected if omitted)",
    )
    resolve_conflict_parser.set_defaults(func=cmd_conflict_resolve)

    # help command
    help_parser = subparsers.add_parser(
        "help",
        help="Show this help message",
    )
    help_parser.set_defaults(func=lambda args: print_help())

    # version command
    version_parser = subparsers.add_parser(
        "version",
        help="Show version information",
    )
    version_parser.set_defaults(func=lambda args: print_version())

    args = parser.parse_args()

    # Initialize logging with configured level
    setup_logging(level=args.log_level, log_file=args.log_file)
    logger.debug(f"Logging initialized at {args.log_level} level")

    if not args.command:
        print_help()
        sys.exit(1)

    # Execute the command
    args.func(args)


def print_help() -> None:
    """Print CLI help message."""
    print("""
Claude Swarm - Multi-agent coordination system

Usage:
    claudeswarm <command> [options]

Setup Commands (run from regular terminal):
    init                 Initialize Claude Swarm in current project (guided setup)
    discover-agents      Discover active Claude Code agents in tmux
    onboard              Onboard all discovered agents to coordination system
    start-monitoring     Start monitoring dashboard (terminal-based)
    start-dashboard      Start web-based monitoring dashboard

Agent Commands (run from within Claude Code):
    list-agents          List active agents from registry
    send-message         Send message to specific agent
    broadcast-message    Broadcast message to all agents
    whoami               Display information about current agent
    check-messages       Check messages in inbox
    acquire-file-lock    Acquire lock on a file
    release-file-lock    Release lock on a file

Utility Commands (run from anywhere):
    who-has-lock         Query lock holder for a file
    list-all-locks       List all active locks
    cleanup-stale-locks  Clean up stale locks
    reload               Reload claudeswarm CLI with latest changes

A2A Protocol Commands (autonomous coordination):
    cards list           List all registered agent cards
    cards get            Get a specific agent card
    cards register       Register a new agent card
    cards update         Update an agent card

    tasks list           List all tasks
    tasks get            Get a specific task
    tasks create         Create a new task
    tasks update         Update a task's status

    delegate             Delegate a task to the best-matched agent
    find-agent           Find the best agent for a task or skill
    resolve-conflict     Resolve a file lock conflict autonomously

    context list         List all shared contexts
    context get          Get a specific context
    context create       Create a new shared context
    context add-decision Add a decision to a context

    memory get           Get an agent's memory
    memory clear         Clear an agent's memory

    learning stats       Show learning statistics for an agent

Configuration Commands:
    config init          Create default configuration file
    config show          Display current configuration
    config validate      Validate configuration file
    config edit          Open configuration file in editor

Other:
    help                 Show this help message
    version              Show version information

For detailed help on each command, run:
    claudeswarm <command> --help
""")


def print_version() -> None:
    """Print version information."""
    from claudeswarm import __version__

    print(f"claudeswarm {__version__}")


if __name__ == "__main__":
    main()
