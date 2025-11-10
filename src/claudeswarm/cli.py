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
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from claudeswarm.locking import LockManager
from claudeswarm.discovery import refresh_registry, list_active_agents
from claudeswarm.monitoring import start_monitoring
from claudeswarm.config import (
    load_config,
    get_config,
    ClaudeSwarmConfig,
    ConfigValidationError,
    _find_config_file,
)
from claudeswarm.validators import (
    ValidationError,
    validate_agent_id,
    validate_file_path,
    validate_timeout,
    validate_message_content,
)

__all__ = ["main"]


def format_timestamp(ts: float) -> str:
    """Format a Unix timestamp as a human-readable string."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def cmd_acquire_file_lock(args: argparse.Namespace) -> None:
    """Acquire a lock on a file."""
    try:
        # Validate inputs
        validated_agent_id = validate_agent_id(args.agent_id)
        validated_filepath = validate_file_path(
            args.filepath,
            must_be_relative=False,
            check_traversal=True
        )

        # Validate reason if provided
        reason = args.reason or ""
        if reason and len(reason) > 512:
            print("Error: Lock reason too long (max 512 characters)", file=sys.stderr)
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
        print(f"  Agent: {args.agent_id}")
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
        # Validate inputs
        validated_agent_id = validate_agent_id(args.agent_id)
        validated_filepath = validate_file_path(
            args.filepath,
            must_be_relative=False,
            check_traversal=True
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
        print(
            "  (Lock may not exist or is owned by another agent)", file=sys.stderr
        )
        sys.exit(1)


def cmd_who_has_lock(args: argparse.Namespace) -> None:
    """Check who has a lock on a file."""
    try:
        # Validate filepath
        validated_filepath = validate_file_path(
            args.filepath,
            must_be_relative=False,
            check_traversal=True
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
        if args.stale_threshold < 1 or args.stale_threshold > 3600:
            print("Error: stale_threshold must be between 1 and 3600 seconds", file=sys.stderr)
            sys.exit(1)
        if args.watch and (args.interval < 1 or args.interval > 3600):
            print("Error: interval must be between 1 and 3600 seconds", file=sys.stderr)
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
                            status_symbol = "✓" if agent.status == "active" else "⚠" if agent.status == "stale" else "✗"
                            print(f"  {status_symbol} {agent.id:<12} | {agent.pane_index:<20} | PID: {agent.pid:<8} | {agent.status}")
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
                        status_symbol = "✓" if agent.status == "active" else "⚠" if agent.status == "stale" else "✗"
                        print(f"  {status_symbol} {agent.id:<12} | {agent.pane_index:<20} | PID: {agent.pid:<8} | {agent.status}")

                print()
                print(f"Registry saved to: ACTIVE_AGENTS.json")

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
            filter_type=args.filter_type,
            filter_agent=args.filter_agent,
            use_tmux=not args.no_tmux
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
        print(f"View with: claudeswarm config show")
        print(f"Edit with: claudeswarm config edit")
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
            config = load_config(config_path)
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

    try:
        start_dashboard_server(
            port=port,
            host=host,
            auto_open=auto_open,
            reload=reload
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


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
    import time
    from claudeswarm.messaging import broadcast_message, MessageType

    print("=== Claude Swarm Agent Onboarding ===")
    print()

    # Step 1: Discover agents
    print("Step 1: Discovering active agents...")
    try:
        registry = refresh_registry()
        agents = list_active_agents()

        if not agents:
            print("No agents discovered.")
            print("Make sure Claude Code instances are running in tmux panes.")
            sys.exit(1)

        print(f"Found {len(agents)} active agent(s): {', '.join(a.id for a in agents)}")
        print()

    except subprocess.CalledProcessError as e:
        print(f"Error: tmux command failed. Is tmux running?", file=sys.stderr)
        print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: Required file not found: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during discovery: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Send onboarding messages
    print("Step 2: Broadcasting onboarding messages...")

    messages = [
        "=== CLAUDE SWARM COORDINATION ACTIVE ===",
        "Multi-agent coordination is now available in this session.",
        "",
        "KEY PROTOCOL RULES:",
        "1. ALWAYS acquire file locks before editing (claudeswarm acquire-file-lock <path> <agent-id> <reason>)",
        "2. ALWAYS release locks immediately after editing (claudeswarm release-file-lock <path> <agent-id>)",
        "3. Use specific message types when communicating (INFO, QUESTION, REVIEW-REQUEST, BLOCKED, etc.)",
        "4. Check COORDINATION.md for sprint goals and current work",
        "",
        "QUICK COMMAND REFERENCE:",
        "Discovery: claudeswarm discover-agents",
        "List locks: claudeswarm list-all-locks",
        "Clean up stale locks: claudeswarm cleanup-stale-locks",
        "",
        f"ACTIVE AGENTS: {', '.join(a.id for a in agents)}",
        "",
        "DOCUMENTATION: See docs/AGENT_PROTOCOL.md, docs/TUTORIAL.md, or docs/INTEGRATION_GUIDE.md",
        "",
        "Ready to coordinate! Use 'claudeswarm --help' for full command list.",
    ]

    # Filter out empty messages
    messages_to_send = [m for m in messages if m.strip()]

    messages_sent = 0
    failed_messages = 0
    MESSAGE_DELAY = 0.5  # Rate limiting: wait between messages

    for i, msg in enumerate(messages_to_send, 1):
        # Progress indication
        print(f"  Sending message {i}/{len(messages_to_send)}...", end='\r')
        sys.stdout.flush()

        try:
            result = broadcast_message(
                sender_id="system",
                message_type=MessageType.INFO,
                content=msg,
                exclude_self=True  # System doesn't need its own messages
            )

            delivered = sum(result.values())
            if delivered == 0:
                failed_messages += 1
            else:
                messages_sent += 1

            # Rate limiting: wait between messages to avoid overwhelming the system
            if i < len(messages_to_send):
                time.sleep(MESSAGE_DELAY)

        except Exception as e:
            print(f"\nWarning: Failed to send message: {e}", file=sys.stderr)
            failed_messages += 1

    print(f"  Sent {messages_sent}/{len(messages_to_send)} messages successfully          ")
    print()

    # Check if too many messages failed
    if failed_messages > len(messages_to_send) * 0.5:
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

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

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
        default=60,
        help="Seconds after which an agent is considered stale (default: 60)",
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

    # onboard command
    onboard_parser = subparsers.add_parser(
        "onboard",
        help="Onboard all discovered agents to the coordination system",
    )
    onboard_parser.set_defaults(func=cmd_onboard)

    # acquire-file-lock command
    acquire_parser = subparsers.add_parser(
        "acquire-file-lock",
        help="Acquire a lock on a file",
    )
    acquire_parser.add_argument("filepath", help="Path to the file to lock")
    acquire_parser.add_argument("agent_id", help="Agent ID acquiring the lock")
    acquire_parser.add_argument(
        "reason", nargs="?", default="", help="Reason for the lock"
    )
    acquire_parser.set_defaults(func=cmd_acquire_file_lock)

    # release-file-lock command
    release_parser = subparsers.add_parser(
        "release-file-lock",
        help="Release a lock on a file",
    )
    release_parser.add_argument("filepath", help="Path to the file to unlock")
    release_parser.add_argument("agent_id", help="Agent ID releasing the lock")
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
    list_parser.add_argument(
        "--include-stale", action="store_true", help="Include stale locks"
    )
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
        "-o", "--output",
        type=str,
        help="Output path (default: .claudeswarm.yaml)",
    )
    config_init_parser.add_argument(
        "-f", "--force",
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute the command
    args.func(args)


def print_help() -> None:
    """Print CLI help message."""
    print("""
Claude Swarm - Multi-agent coordination system

Usage:
    claudeswarm <command> [options]

Commands:
    discover-agents       Discover active Claude Code agents
    list-agents          List active agents from registry
    onboard              Onboard all agents to coordination system
    send-to-agent        Send message to specific agent
    broadcast-to-all     Broadcast message to all agents
    acquire-file-lock    Acquire lock on a file
    release-file-lock    Release lock on a file
    who-has-lock        Query lock holder for a file
    list-all-locks      List all active locks
    cleanup-stale-locks Clean up stale locks
    send-with-ack       Send message requiring acknowledgment
    start-monitoring    Start monitoring dashboard
    start-dashboard     Start web-based monitoring dashboard

    help                Show this help message
    version             Show version information

For detailed help on each command, run:
    claudeswarm <command> --help
""")


def print_version() -> None:
    """Print version information."""
    from claudeswarm import __version__
    print(f"claudeswarm {__version__}")


if __name__ == "__main__":
    main()
