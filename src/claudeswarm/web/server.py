"""FastAPI server for Claude Swarm monitoring dashboard.

This module provides a real-time web dashboard for monitoring Claude Swarm agents,
locks, and message flow. It exposes REST API endpoints and Server-Sent Events (SSE)
for live updates.
"""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

# Import project utilities
from ..project import (
    get_project_root,
    get_active_agents_path,
    get_messages_log_path,
    get_locks_dir_path,
)

# Project paths
PROJECT_ROOT = get_project_root()
ACTIVE_AGENTS_FILE = get_active_agents_path()
AGENT_MESSAGES_LOG = get_messages_log_path()
AGENT_LOCKS_DIR = get_locks_dir_path()
STATIC_DIR = Path(__file__).parent / "static"

# FastAPI app initialization
app = FastAPI(
    title="Claude Swarm Dashboard",
    description="Real-time monitoring dashboard for Claude Swarm multi-agent system",
    version="1.0.0",
)

# CORS configuration for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files if directory exists
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Utility functions
def safe_load_json(file_path: Path) -> dict[str, Any] | None:
    """Safely load JSON file with error handling.

    Args:
        file_path: Path to JSON file

    Returns:
        Parsed JSON data or None if file doesn't exist or is invalid
    """
    try:
        if not file_path.exists():
            return None
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return None


def tail_log_file(file_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    """Read last N lines from log file and parse as JSON.

    Args:
        file_path: Path to log file
        limit: Maximum number of lines to return

    Returns:
        List of parsed JSON message objects
    """
    messages = []
    try:
        if not file_path.exists():
            return messages

        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # Get last 'limit' lines
            for line in lines[-limit:]:
                line = line.strip()
                if line:
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError:
                        # Skip malformed lines
                        continue
    except (IOError, OSError):
        pass

    return messages


def get_lock_files() -> list[dict[str, Any]]:
    """Read all lock files from .agent_locks directory.

    Returns:
        List of lock information dictionaries
    """
    locks = []
    try:
        if not AGENT_LOCKS_DIR.exists():
            return locks

        for lock_file in AGENT_LOCKS_DIR.glob("*.lock"):
            try:
                with open(lock_file, "r", encoding="utf-8") as f:
                    lock_data = json.load(f)
                    lock_data["lock_file"] = lock_file.name
                    locks.append(lock_data)
            except (json.JSONDecodeError, IOError, OSError):
                # Skip corrupt lock files
                continue
    except OSError:
        pass

    return locks


# State tracking for SSE
class StateTracker:
    """Track file modification times for change detection."""

    def __init__(self) -> None:
        """Initialize state tracker."""
        self.agents_mtime: float = 0.0
        self.messages_mtime: float = 0.0
        self.locks_mtime: float = 0.0
        self.message_count: int = 0

    def check_changes(self) -> dict[str, bool]:
        """Check which files have changed since last check.

        Returns:
            Dictionary with change flags for agents, messages, and locks
        """
        changes = {
            "agents": False,
            "messages": False,
            "locks": False,
        }

        # Check agents file
        if ACTIVE_AGENTS_FILE.exists():
            mtime = os.path.getmtime(ACTIVE_AGENTS_FILE)
            if mtime != self.agents_mtime:
                self.agents_mtime = mtime
                changes["agents"] = True

        # Check messages log
        if AGENT_MESSAGES_LOG.exists():
            mtime = os.path.getmtime(AGENT_MESSAGES_LOG)
            if mtime != self.messages_mtime:
                self.messages_mtime = mtime
                changes["messages"] = True

        # Check locks directory (check all lock files)
        if AGENT_LOCKS_DIR.exists():
            try:
                lock_files = list(AGENT_LOCKS_DIR.glob("*.lock"))
                current_locks_mtime = max(
                    (os.path.getmtime(f) for f in lock_files),
                    default=0.0,
                )
                if current_locks_mtime != self.locks_mtime:
                    self.locks_mtime = current_locks_mtime
                    changes["locks"] = True
            except (OSError, ValueError):
                pass

        return changes


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the dashboard HTML page.

    Returns:
        HTML response with dashboard page or placeholder
    """
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                content = f.read()
            return HTMLResponse(content=content)
        except (IOError, OSError) as e:
            raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {e}")

    # Placeholder if frontend hasn't been created yet
    placeholder_html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Claude Swarm Dashboard</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                text-align: center;
                padding: 2rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                backdrop-filter: blur(10px);
            }
            h1 { margin-bottom: 1rem; }
            p { opacity: 0.9; }
            .endpoints {
                margin-top: 2rem;
                text-align: left;
                background: rgba(0, 0, 0, 0.2);
                padding: 1rem;
                border-radius: 5px;
            }
            code {
                background: rgba(0, 0, 0, 0.3);
                padding: 0.2rem 0.5rem;
                border-radius: 3px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Claude Swarm Dashboard</h1>
            <p>Backend API Server is Running</p>
            <div class="endpoints">
                <h3>Available Endpoints:</h3>
                <ul>
                    <li><code>GET /api/agents</code> - Active agents</li>
                    <li><code>GET /api/locks</code> - Active locks</li>
                    <li><code>GET /api/messages</code> - Recent messages</li>
                    <li><code>GET /api/stats</code> - System statistics</li>
                    <li><code>GET /api/stream</code> - SSE live updates</li>
                    <li><code>GET /docs</code> - API documentation</li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=placeholder_html)


@app.get("/api/agents")
async def get_agents() -> dict[str, Any]:
    """Get list of active agents.

    Returns:
        Dictionary containing session info and list of active agents
    """
    data = safe_load_json(ACTIVE_AGENTS_FILE)
    if data is None:
        return {
            "session_name": None,
            "updated_at": None,
            "agents": [],
        }

    return {
        "session_name": data.get("session_name"),
        "updated_at": data.get("updated_at"),
        "agents": data.get("agents", []),
    }


@app.get("/api/locks")
async def get_locks() -> dict[str, Any]:
    """Get list of active file locks.

    Returns:
        Dictionary containing list of active locks
    """
    locks = get_lock_files()
    return {
        "locks": locks,
        "count": len(locks),
    }


@app.get("/api/messages")
async def get_messages(limit: int = 50) -> dict[str, Any]:
    """Get recent messages from log file.

    Args:
        limit: Maximum number of messages to return (default: 50)

    Returns:
        Dictionary containing list of messages and count
    """
    if limit < 1:
        limit = 50
    elif limit > 1000:
        limit = 1000  # Cap at 1000 for performance

    messages = tail_log_file(AGENT_MESSAGES_LOG, limit)
    return {
        "messages": messages,
        "count": len(messages),
        "limit": limit,
    }


@app.get("/api/stats")
async def get_stats() -> dict[str, Any]:
    """Get aggregated system statistics.

    Returns:
        Dictionary containing various system metrics
    """
    # Load agents data
    agents_data = safe_load_json(ACTIVE_AGENTS_FILE)
    agent_count = len(agents_data.get("agents", [])) if agents_data else 0

    # Count locks
    locks = get_lock_files()
    lock_count = len(locks)

    # Count messages
    messages = tail_log_file(AGENT_MESSAGES_LOG, 1000)  # Sample last 1000
    message_count = len(messages)

    # Count message types
    message_types: dict[str, int] = {}
    for msg in messages:
        msg_type = msg.get("msg_type", "UNKNOWN")
        message_types[msg_type] = message_types.get(msg_type, 0) + 1

    # Get latest timestamp
    latest_timestamp = None
    if messages:
        latest_timestamp = messages[-1].get("timestamp")

    return {
        "agent_count": agent_count,
        "lock_count": lock_count,
        "message_count": message_count,
        "message_types": message_types,
        "latest_activity": latest_timestamp,
        "session_name": agents_data.get("session_name") if agents_data else None,
        "updated_at": agents_data.get("updated_at") if agents_data else None,
    }


@app.get("/api/stream")
async def event_stream() -> StreamingResponse:
    """Server-Sent Events endpoint for real-time updates.

    Returns:
        StreamingResponse with SSE stream
    """

    async def generate_events() -> AsyncGenerator[str, None]:
        """Generate SSE events for changes in agents, locks, and messages.

        Yields:
            SSE formatted event strings
        """
        tracker = StateTracker()

        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'timestamp': datetime.utcnow().isoformat()})}\n\n"

        while True:
            try:
                # Check for changes
                changes = tracker.check_changes()

                # Send agents update if changed
                if changes["agents"]:
                    agents_data = await get_agents()
                    yield f"event: agents\ndata: {json.dumps(agents_data)}\n\n"

                # Send locks update if changed
                if changes["locks"]:
                    locks_data = await get_locks()
                    yield f"event: locks\ndata: {json.dumps(locks_data)}\n\n"

                # Send new messages if log changed
                if changes["messages"]:
                    messages_data = await get_messages(limit=10)  # Send last 10 new messages
                    yield f"event: messages\ndata: {json.dumps(messages_data)}\n\n"

                # Send stats update periodically (every iteration)
                stats_data = await get_stats()
                yield f"event: stats\ndata: {json.dumps(stats_data)}\n\n"

                # Send heartbeat
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': datetime.utcnow().isoformat()})}\n\n"

                # Wait before next check
                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                # Client disconnected
                break
            except Exception as e:
                # Log error but continue
                error_data = {"error": str(e), "timestamp": datetime.utcnow().isoformat()}
                yield f"event: error\ndata: {json.dumps(error_data)}\n\n"
                await asyncio.sleep(1.0)

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check endpoint for monitoring.

    Returns:
        Dictionary with health status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "files": {
            "agents": ACTIVE_AGENTS_FILE.exists(),
            "messages": AGENT_MESSAGES_LOG.exists(),
            "locks_dir": AGENT_LOCKS_DIR.exists(),
        },
    }


# Development server entry point
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "claudeswarm.web.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
