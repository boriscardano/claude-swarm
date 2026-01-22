"""Dashboard launcher utilities.

This module provides utilities for launching the web-based monitoring dashboard,
including port availability checking, browser auto-opening, and server startup.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import webbrowser
from typing import NoReturn

__all__ = [
    "check_port_available",
    "start_dashboard_server",
]


def check_port_available(port: int, host: str = "localhost") -> bool:
    """Check if a port is available for binding.

    Args:
        port: Port number to check
        host: Host address to check (default: localhost)

    Returns:
        True if port is available, False if already in use
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, port))
        sock.close()
        return True
    except OSError:
        return False


def start_dashboard_server(
    port: int = 8080,
    host: str = "localhost",
    auto_open: bool = True,
    reload: bool = False
) -> NoReturn:
    """Start the dashboard server.

    Launches the FastAPI server using uvicorn and optionally opens
    the browser automatically. This is a blocking call that runs
    until interrupted.

    Args:
        port: Port to run server on (default: 8080)
        host: Host to bind to (default: localhost)
        auto_open: Open browser automatically (default: True)
        reload: Enable auto-reload for development (default: False)

    Raises:
        RuntimeError: If server fails to start or port is already in use

    Exit:
        This function does not return normally. It exits via sys.exit()
        when the server is stopped (Ctrl+C or error).
    """
    # Check port availability
    if not check_port_available(port, host):
        raise RuntimeError(
            f"Port {port} is already in use. "
            f"Try a different port with --port or stop the other service."
        )

    # Build uvicorn command using the current Python interpreter
    # This ensures we use the same environment where claudeswarm is installed
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "claudeswarm.web.server:app",
        "--host", host,
        "--port", str(port),
    ]

    if reload:
        cmd.append("--reload")

    # Print access info
    url = f"http://{host}:{port}"
    print(f"Starting Claude Swarm Dashboard...")
    print(f"Dashboard URL: {url}")
    print(f"Press Ctrl+C to stop")
    print()

    # Open browser after a short delay
    if auto_open:
        # Launch browser opener in background
        def open_browser() -> None:
            time.sleep(1.5)  # Wait for server to start
            try:
                webbrowser.open(url)
                print(f"Opened browser to {url}")
            except Exception as e:
                print(f"Warning: Could not open browser automatically: {e}")

        import threading
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()

    # Start server (blocking)
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nDashboard stopped")
        raise SystemExit(0)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to start dashboard: {e}") from e
    except FileNotFoundError:
        raise RuntimeError(
            f"Python interpreter not found at {sys.executable}. "
            "This may indicate a corrupted installation. Try reinstalling claudeswarm."
        ) from None
