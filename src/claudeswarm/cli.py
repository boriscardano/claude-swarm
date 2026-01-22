"""Command-line interface for Claude Swarm.

This module provides the main CLI entry point and command handlers
for all claudeswarm operations. It delegates to the appropriate
modules for each command.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import NoReturn

from claudeswarm.config import (
    ConfigValidationError,
    _find_config_file,
    get_config,
    load_config,
)
from claudeswarm.discovery import list_active_agents, refresh_registry
from claudeswarm.locking import LockManager
from claudeswarm.logging_config import get_logger, setup_logging
from claudeswarm.monitoring import start_monitoring
from claudeswarm.project import find_project_root
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


def cmd_acquire_file_lock(args: argparse.Namespace) -> None:
    """Acquire a lock on a file."""
    try:
        # Auto-detect agent_id if not provided
        agent_id = args.agent_id
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

        # Validate inputs
        validated_agent_id = validate_agent_id(agent_id)
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
        # Auto-detect agent_id if not provided
        agent_id = args.agent_id
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

        # Validate inputs
        validated_agent_id = validate_agent_id(agent_id)
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
                    registry = refresh_registry(stale_threshold=args.stale_threshold)

                    if not args.json:
                        print(f"\n=== Agent Discovery [{registry.updated_at}] ===")
                        print(f"Session: {registry.session_name}")
                        print(f"Total agents: {len(registry.agents)}")
                        print()

                        for agent in registry.agents:
                            status_symbol = (
                                "✓"
                                if agent.status == "active"
                                else "⚠" if agent.status == "stale" else "✗"
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
            registry = refresh_registry(stale_threshold=args.stale_threshold)

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
                            else "⚠" if agent.status == "stale" else "✗"
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
    """Detect the current agent from TMUX_PANE environment variable.

    Returns:
        Tuple of (agent_id, agent_dict) if found, (None, None) otherwise
    """
    import os

    from claudeswarm.project import get_active_agents_path

    # Check if running in tmux
    tmux_pane_id = os.environ.get("TMUX_PANE")
    if not tmux_pane_id:
        return None, None

    # Validate tmux pane ID to prevent command injection
    try:
        tmux_pane_id = validate_tmux_pane_id(tmux_pane_id)
    except ValidationError:
        # Invalid pane ID format - cannot proceed safely
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

    # Try matching by TMUX_PANE env var (works in sandboxed environments!)
    for agent in agents:
        if agent.get("tmux_pane_id") == tmux_pane_id:
            return agent.get("id"), agent

    # Fallback: Try converting TMUX_PANE to pane index format
    try:
        result = subprocess.run(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                tmux_pane_id,
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

    return None, None


def cmd_send_message(args: argparse.Namespace) -> None:
    """Send a message to a specific agent.

    Args:
        args.sender_id: ID of the sending agent (optional, auto-detected if in tmux)
        args.recipient_id: ID of the receiving agent
        args.type: Message type (case-insensitive, supports hyphens and underscores)
        args.content: Message content to send
        args.json: Whether to output JSON format

    Exit Codes:
        0: Success - message sent
        1: Failure - validation error, recipient not found, or send failed
    """
    from claudeswarm.messaging import MessageType, send_message
    from claudeswarm.validators import sanitize_message_content

    try:
        # Auto-detect sender if not provided
        sender_id = args.sender_id
        if not sender_id:
            detected_id, _ = _detect_current_agent()
            if detected_id:
                sender_id = detected_id
            else:
                print("Error: Could not auto-detect agent identity", file=sys.stderr)
                print(
                    "Please provide sender_id or run 'claudeswarm whoami' to verify registration",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Validate agent IDs (validators handle all validation including length)
        validated_sender = validate_agent_id(sender_id)
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
                print(f"✓ Message delivered to {args.recipient_id} (real-time)")
            else:
                print(f"✓ Message sent to inbox: {args.recipient_id}")
                print("  ℹ️  Message logged to inbox (real-time delivery attempted)")
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
        # Auto-detect sender if not provided
        sender_id = args.sender_id
        if not sender_id:
            detected_id, _ = _detect_current_agent()
            if detected_id:
                sender_id = detected_id
            else:
                print("Error: Could not auto-detect agent identity", file=sys.stderr)
                print(
                    "Please provide sender_id or run 'claudeswarm whoami' to verify registration",
                    file=sys.stderr,
                )
                sys.exit(1)

        # Validate sender ID (validators handle all validation including length)
        validated_sender = validate_agent_id(sender_id)

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
    import os

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

    # Get editor
    editor = os.environ.get("EDITOR")
    if not editor:
        # Try common editors
        for e in ["vim", "vi", "nano", "emacs"]:
            if subprocess.run(["which", e], capture_output=True).returncode == 0:
                editor = e
                break

    if not editor:
        print("Error: No editor found", file=sys.stderr)
        print("Set EDITOR environment variable or install vim/nano", file=sys.stderr)
        sys.exit(1)

    # Open in editor
    try:
        result = subprocess.run([editor, str(config_path)])
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
    return [f"""=== CLAUDE SWARM COORDINATION ACTIVE ===
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

COORDINATION READY! 🎉"""]


def _send_onboarding_messages(
    agents: list, messages: list[str], args: argparse.Namespace
) -> tuple[int, int]:
    """Send onboarding messages to all agents.

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
            result = broadcast_message(
                sender_id="system",
                message_type=MessageType.INFO,
                content=msg,
                exclude_self=True,  # System doesn't need its own messages
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
    print("=== Claude Swarm Agent Onboarding ===")
    print()

    # Step 1: Discover agents
    agents = _discover_agents_for_onboarding(args)

    # Step 2: Prepare onboarding content
    messages = _prepare_onboarding_content(agents)

    # Step 3: Send onboarding messages
    messages_sent, failed_messages = _send_onboarding_messages(agents, messages, args)

    # Step 4: Report results
    _report_onboarding_results(agents, messages_sent, failed_messages, len(messages))

    sys.exit(0)


def cmd_check_messages(args: argparse.Namespace) -> None:
    """Check messages for the current agent.

    Reads messages from the agent_messages.log file and filters for messages
    sent to this agent. Works in sandboxed environments by reading from file
    instead of relying on tmux delivery.

    Exit Codes:
        0: Success
        1: Error (not an agent, file not found, etc.)
    """
    from claudeswarm.project import get_messages_log_path

    # Auto-detect current agent (or use explicit agent-id for testing)
    agent_id = getattr(args, "agent_id", None)
    if not agent_id:
        detected_id, _ = _detect_current_agent()
        if detected_id:
            agent_id = detected_id
        else:
            print("Error: Could not auto-detect agent identity", file=sys.stderr)
            print("Please run 'claudeswarm whoami' to verify registration", file=sys.stderr)
            sys.exit(1)

    # Read messages log
    messages_log = get_messages_log_path()
    if not messages_log.exists():
        print("No messages found (log file doesn't exist)")
        sys.exit(0)

    try:
        with open(messages_log, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        print(f"Error reading messages: {e}", file=sys.stderr)
        sys.exit(1)

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
                my_messages.append(msg)
        except json.JSONDecodeError:
            continue

    # Display messages
    if not my_messages:
        print(f"No messages for {agent_id}")
        sys.exit(0)

    # Show last N messages (default 10)
    limit = args.limit if hasattr(args, "limit") and args.limit else 10
    recent_messages = my_messages[-limit:]

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

    sys.exit(0)


def cmd_whoami(args: argparse.Namespace) -> None:
    """Display information about the current agent.

    Checks if the current tmux pane is registered as an agent and displays
    agent information if found, or indicates if not running as an agent.

    Exit Codes:
        0: Success (agent found or not)
        1: Error (not in tmux, registry not found, etc.)
    """
    # Check if running in tmux by checking TMUX_PANE environment variable
    import os

    from claudeswarm.project import get_active_agents_path

    tmux_pane_id = os.environ.get("TMUX_PANE")

    if not tmux_pane_id:
        print("Not running in a tmux session.", file=sys.stderr)
        print("The 'whoami' command only works within tmux panes.", file=sys.stderr)
        sys.exit(1)

    # Validate tmux pane ID to prevent command injection
    try:
        tmux_pane_id = validate_tmux_pane_id(tmux_pane_id)
    except ValidationError as e:
        print(f"Error: Invalid TMUX_PANE environment variable: {e}", file=sys.stderr)
        sys.exit(1)

    # Convert tmux pane ID (like %2) to session:window.pane format (like 0:1.1)
    current_pane = None

    try:
        result = subprocess.run(
            [
                "tmux",
                "display-message",
                "-p",
                "-t",
                tmux_pane_id,
                "#{session_name}:#{window_index}.#{pane_index}",
            ],
            capture_output=True,
            text=True,
            timeout=2.0,
        )
        if result.returncode == 0:
            current_pane = result.stdout.strip()
        else:
            # Store error for optional display (permission errors are expected in sandboxed environments)
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

    # Search for current pane in registry
    agents = registry.get("agents", [])
    current_agent = None

    # Try matching by TMUX_PANE env var first (works in sandboxed environments!)
    for agent in agents:
        if agent.get("tmux_pane_id") == tmux_pane_id:
            current_agent = agent
            break

    # Fallback 1: Try matching by pane index (if we successfully converted it)
    if not current_agent and current_pane:
        for agent in agents:
            if agent.get("pane_index") == current_pane:
                current_agent = agent
                break

    # Fallback 2: Try matching by PID (last resort for old registries without tmux_pane_id)
    if not current_agent:
        # Get current process and check if it's a Claude Code agent
        # Claude Code agents spawn bash as child processes, so check parent
        current_pid = os.getpid()
        parent_pid = os.getppid()

        # Try both current PID and parent PID
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
        print("📬 RECENT MESSAGES (auto-checked)")
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
        print("=== Current Pane ===")
        print()
        print(f"  Pane: {current_pane if current_pane else tmux_pane_id}")
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
        subprocess.run(
            [
                "find",
                "/Library/Frameworks/Python.framework/Versions/3.12/lib/python3.12/site-packages",
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
                    "git+https://github.com/borisbanach/claude-swarm.git",
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
            response = input("  Create default configuration? [Y/n]: ").strip().lower()
            should_create = not response or response in ["y", "yes"]

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


def _init_check_tmux_status() -> None:
    """Check tmux installation and running status."""
    print("Step 3: Checking tmux...")
    try:
        result = subprocess.run(["tmux", "list-sessions"], capture_output=True, timeout=2)
        if result.returncode == 0:
            sessions = result.stdout.decode().strip().split("\n")
            print(f"✓ tmux is running with {len(sessions)} session(s)")
        else:
            print("⚠ tmux is installed but no sessions are running")
            print("  Tip: Start tmux with: tmux new -s myproject")
    except FileNotFoundError:
        print("✗ tmux not found - Install it first!")
        print("  macOS: brew install tmux")
        print("  Linux: apt install tmux / yum install tmux")
    except subprocess.TimeoutExpired:
        print("⚠ tmux command timed out")
    except Exception as e:
        print(f"⚠ Error checking tmux: {e}")

    print()


def _init_display_next_steps(project_root: Path) -> None:
    """Display next steps for user to complete setup.

    Args:
        project_root: Path to project root directory
    """
    print("=== Next Steps ===")
    print()
    print("1. Set up tmux session (if not already):")
    print("   tmux new -s myproject")
    print()
    print("2. Split panes and start Claude Code agents:")
    print("   Ctrl+b %    # Split vertically")
    print('   Ctrl+b "    # Split horizontally')
    print()
    print("3. Discover agents:")
    print("   claudeswarm discover-agents")
    print()
    print("4. Onboard agents (send coordination info):")
    print("   claudeswarm onboard")
    print()
    print("5. Start web dashboard:")
    print("   claudeswarm start-dashboard")
    print()
    print(f"📁 Project root: {project_root}")
    print(f"📋 Files will be created in: {project_root}")
    print()
    print("For more help: claudeswarm --help")
    print("Documentation: https://github.com/borisbanach/claude-swarm")


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize Claude Swarm in current project with guided setup.

    This command helps users set up Claude Swarm by:
    1. Detecting the project root
    2. Creating config file if needed
    3. Showing next steps

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

    # Step 3: Check tmux status
    _init_check_tmux_status()

    # Step 4: Display next steps
    _init_display_next_steps(project_root)

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
        type=int,
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
        type=int,
        default=10,
        help="Number of recent messages to show (default: 10)",
    )
    check_messages_parser.add_argument(
        "--agent-id",
        dest="agent_id",
        default=None,
        help="Agent ID to check messages for (auto-detected if omitted)",
    )
    check_messages_parser.set_defaults(func=cmd_check_messages)

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
