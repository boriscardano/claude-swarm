"""Command-line interface for Claude Swarm.

This module provides the main CLI entry point and command handlers
for all claudeswarm operations. It delegates to the appropriate
modules for each command.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

from claudeswarm.locking import LockManager
from claudeswarm.discovery import refresh_registry, list_active_agents
from claudeswarm.monitoring import start_monitoring
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
    send-to-agent        Send message to specific agent
    broadcast-to-all     Broadcast message to all agents
    acquire-file-lock    Acquire lock on a file
    release-file-lock    Release lock on a file
    who-has-lock        Query lock holder for a file
    send-with-ack       Send message requiring acknowledgment
    start-monitoring    Start monitoring dashboard
    
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
