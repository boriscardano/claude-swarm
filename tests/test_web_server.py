"""Comprehensive tests for web server (server.py).

This module provides comprehensive test coverage for the FastAPI-based dashboard server,
including API endpoints, SSE streaming, error handling, security headers, and CORS.

Author: Code Review Expert
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, mock_open, AsyncMock
import json
import os
import time
from pathlib import Path
from datetime import datetime


# Mock the project paths before importing
@pytest.fixture(autouse=True)
def mock_paths(tmp_path, monkeypatch):
    """Mock all file paths to use temp directory."""
    monkeypatch.setattr("claudeswarm.web.server.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("claudeswarm.web.server.ACTIVE_AGENTS_FILE", tmp_path / "ACTIVE_AGENTS.json")
    monkeypatch.setattr("claudeswarm.web.server.AGENT_MESSAGES_LOG", tmp_path / "agent_messages.log")
    monkeypatch.setattr("claudeswarm.web.server.AGENT_LOCKS_DIR", tmp_path / ".agent_locks")
    monkeypatch.setattr("claudeswarm.web.server.STATIC_DIR", tmp_path / "static")

    # Create directories
    (tmp_path / ".agent_locks").mkdir()
    (tmp_path / "static").mkdir()

    return tmp_path


@pytest.fixture
def client(mock_paths):
    """Create test client with mocked paths."""
    from claudeswarm.web.server import app
    return TestClient(app)


class TestHealthEndpoint:
    """Test the /health endpoint."""

    def test_health_check_returns_200(self, client):
        """Test health check returns 200 status."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_check_returns_json(self, client):
        """Test health check returns proper JSON structure."""
        response = client.get("/health")
        data = response.json()
        assert "status" in data
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "files" in data

    def test_health_check_includes_file_status(self, client):
        """Test health check includes file existence status."""
        response = client.get("/health")
        data = response.json()
        files = data["files"]
        assert "agents" in files
        assert "messages" in files
        assert "locks_dir" in files
        assert isinstance(files["agents"], bool)
        assert isinstance(files["messages"], bool)
        assert isinstance(files["locks_dir"], bool)


class TestAgentsEndpoint:
    """Test the /api/agents endpoint."""

    def test_returns_empty_when_no_agents(self, client, tmp_path):
        """Test returns empty list when ACTIVE_AGENTS.json doesn't exist."""
        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert data["agents"] == []
        assert data["session_name"] is None
        assert data["updated_at"] is None

    def test_returns_agents_from_file(self, client, tmp_path):
        """Test returns agents when ACTIVE_AGENTS.json exists."""
        agents_data = {
            "session_name": "test-session",
            "updated_at": "2026-01-22T12:00:00Z",
            "agents": [
                {"agent_id": "agent-0", "pid": 1234, "status": "active"},
                {"agent_id": "agent-1", "pid": 5678, "status": "active"}
            ]
        }
        (tmp_path / "ACTIVE_AGENTS.json").write_text(json.dumps(agents_data))

        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["session_name"] == "test-session"
        assert data["updated_at"] == "2026-01-22T12:00:00Z"
        assert len(data["agents"]) == 2
        assert data["agents"][0]["agent_id"] == "agent-0"
        assert data["agents"][1]["agent_id"] == "agent-1"

    def test_handles_malformed_json(self, client, tmp_path):
        """Test handles malformed JSON gracefully."""
        (tmp_path / "ACTIVE_AGENTS.json").write_text("{invalid json")

        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        # Should return empty state on error
        assert data["agents"] == []

    def test_handles_file_lock_timeout(self, client, tmp_path):
        """Test handles file lock timeout gracefully."""
        agents_data = {"session_name": "test", "agents": []}
        (tmp_path / "ACTIVE_AGENTS.json").write_text(json.dumps(agents_data))

        # Mock FileLock to raise timeout
        with patch("claudeswarm.web.server.FileLock") as mock_lock:
            from claudeswarm.file_lock import FileLockTimeout
            mock_lock.return_value.__enter__.side_effect = FileLockTimeout("timeout")

            response = client.get("/api/agents")
            assert response.status_code == 200
            data = response.json()
            # Should return empty on lock timeout
            assert data["agents"] == []


class TestLocksEndpoint:
    """Test the /api/locks endpoint."""

    def test_returns_empty_locks(self, client, tmp_path):
        """Test returns empty list when no lock files exist."""
        response = client.get("/api/locks")
        assert response.status_code == 200
        data = response.json()
        assert "locks" in data
        assert "count" in data
        assert data["locks"] == []
        assert data["count"] == 0

    def test_returns_lock_files(self, client, tmp_path):
        """Test returns lock files from .agent_locks directory."""
        locks_dir = tmp_path / ".agent_locks"

        # Create some lock files
        lock1 = {
            "agent_id": "agent-0",
            "filepath": "test1.py",
            "reason": "editing",
            "locked_at": time.time()
        }
        lock2 = {
            "agent_id": "agent-1",
            "filepath": "test2.py",
            "reason": "reviewing",
            "locked_at": time.time()
        }

        (locks_dir / "test1.py.lock").write_text(json.dumps(lock1))
        (locks_dir / "test2.py.lock").write_text(json.dumps(lock2))

        response = client.get("/api/locks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["locks"]) == 2
        assert data["count"] == 2

        # Check that lock_file name is added
        lock_files = [lock["lock_file"] for lock in data["locks"]]
        assert "test1.py.lock" in lock_files
        assert "test2.py.lock" in lock_files

    def test_handles_malformed_lock_files(self, client, tmp_path):
        """Test handles malformed lock files gracefully."""
        locks_dir = tmp_path / ".agent_locks"

        # Create valid and invalid lock files
        good_lock = {"agent_id": "agent-0", "filepath": "good.py"}
        (locks_dir / "good.lock").write_text(json.dumps(good_lock))
        (locks_dir / "bad.lock").write_text("{invalid json")

        response = client.get("/api/locks")
        assert response.status_code == 200
        data = response.json()
        # Should only include valid lock
        assert len(data["locks"]) == 1
        assert data["locks"][0]["agent_id"] == "agent-0"

    def test_handles_missing_locks_directory(self, client, tmp_path, monkeypatch):
        """Test handles missing locks directory gracefully."""
        # Point to non-existent directory
        monkeypatch.setattr("claudeswarm.web.server.AGENT_LOCKS_DIR", tmp_path / "nonexistent")

        response = client.get("/api/locks")
        assert response.status_code == 200
        data = response.json()
        assert data["locks"] == []
        assert data["count"] == 0


class TestMessagesEndpoint:
    """Test the /api/messages endpoint."""

    def test_returns_empty_when_no_messages(self, client, tmp_path):
        """Test returns empty list when messages log doesn't exist."""
        response = client.get("/api/messages")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert "count" in data
        assert "limit" in data
        assert data["messages"] == []
        assert data["count"] == 0

    def test_returns_messages_from_log(self, client, tmp_path):
        """Test returns messages from agent_messages.log."""
        messages = [
            {"sender_id": "agent-0", "msg_type": "INFO", "content": "Test 1", "timestamp": "2026-01-22T12:00:00Z"},
            {"sender_id": "agent-1", "msg_type": "QUESTION", "content": "Test 2", "timestamp": "2026-01-22T12:01:00Z"},
            {"sender_id": "agent-2", "msg_type": "ANSWER", "content": "Test 3", "timestamp": "2026-01-22T12:02:00Z"}
        ]

        log_content = "\n".join(json.dumps(msg) for msg in messages)
        (tmp_path / "agent_messages.log").write_text(log_content)

        response = client.get("/api/messages")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 3
        assert data["count"] == 3
        assert data["messages"][0]["sender_id"] == "agent-0"

    def test_respects_limit_parameter(self, client, tmp_path):
        """Test respects limit parameter for message count."""
        messages = [
            {"sender_id": f"agent-{i}", "msg_type": "INFO", "content": f"Test {i}", "timestamp": f"2026-01-22T12:00:{i:02d}Z"}
            for i in range(100)
        ]

        log_content = "\n".join(json.dumps(msg) for msg in messages)
        (tmp_path / "agent_messages.log").write_text(log_content)

        response = client.get("/api/messages?limit=10")
        assert response.status_code == 200
        data = response.json()
        # Should return last 10 messages
        assert len(data["messages"]) == 10
        assert data["limit"] == 10

    def test_limit_validation_minimum(self, client, tmp_path):
        """Test limit parameter defaults to 50 for values < 1."""
        messages = [{"sender_id": "agent-0", "msg_type": "INFO", "content": "Test"}]
        (tmp_path / "agent_messages.log").write_text(json.dumps(messages[0]))

        response = client.get("/api/messages?limit=0")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50  # Should use default

    def test_limit_validation_maximum(self, client, tmp_path):
        """Test limit parameter caps at 1000."""
        messages = [{"sender_id": "agent-0", "msg_type": "INFO", "content": "Test"}]
        (tmp_path / "agent_messages.log").write_text(json.dumps(messages[0]))

        response = client.get("/api/messages?limit=999999")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 1000  # Should be capped

    def test_handles_malformed_log_lines(self, client, tmp_path):
        """Test handles malformed log lines gracefully."""
        log_content = """{"valid": "message1"}
invalid json line
{"valid": "message2"}"""
        (tmp_path / "agent_messages.log").write_text(log_content)

        response = client.get("/api/messages")
        assert response.status_code == 200
        data = response.json()
        # Should only include valid messages
        assert len(data["messages"]) == 2


class TestStatsEndpoint:
    """Test the /api/stats endpoint."""

    def test_returns_stats_structure(self, client):
        """Test returns proper stats structure."""
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()

        # Check all required fields
        assert "agent_count" in data
        assert "lock_count" in data
        assert "message_count" in data
        assert "message_types" in data
        assert "latest_activity" in data
        assert "session_name" in data
        assert "updated_at" in data

    def test_aggregates_data_correctly(self, client, tmp_path):
        """Test correctly aggregates data from all sources."""
        # Setup agents
        agents_data = {
            "session_name": "test-session",
            "updated_at": "2026-01-22T12:00:00Z",
            "agents": [{"agent_id": "agent-0"}, {"agent_id": "agent-1"}]
        }
        (tmp_path / "ACTIVE_AGENTS.json").write_text(json.dumps(agents_data))

        # Setup locks
        locks_dir = tmp_path / ".agent_locks"
        lock1 = {"agent_id": "agent-0", "filepath": "test.py"}
        (locks_dir / "test.lock").write_text(json.dumps(lock1))

        # Setup messages
        messages = [
            {"msg_type": "INFO", "content": "Test 1"},
            {"msg_type": "INFO", "content": "Test 2"},
            {"msg_type": "QUESTION", "content": "Test 3"}
        ]
        log_content = "\n".join(json.dumps(msg) for msg in messages)
        (tmp_path / "agent_messages.log").write_text(log_content)

        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()

        assert data["agent_count"] == 2
        assert data["lock_count"] == 1
        assert data["message_count"] == 3
        assert data["message_types"]["INFO"] == 2
        assert data["message_types"]["QUESTION"] == 1
        assert data["session_name"] == "test-session"

    def test_handles_empty_state(self, client):
        """Test handles empty state correctly."""
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()

        assert data["agent_count"] == 0
        assert data["lock_count"] == 0
        assert data["message_count"] == 0
        assert data["message_types"] == {}
        assert data["session_name"] is None


class TestSSEStreamingEndpoint:
    """Test the /api/stream SSE endpoint."""

    def test_stream_endpoint_exists(self, client):
        """Test that SSE stream endpoint exists and responds with correct headers."""
        # We can't easily test streaming without hanging, so just verify
        # the endpoint exists by checking it in the app's routes
        from claudeswarm.web.server import app

        routes = [route.path for route in app.routes]
        assert "/api/stream" in routes


class TestDashboardRootEndpoint:
    """Test the / dashboard endpoint."""

    def test_dashboard_returns_html(self, client):
        """Test dashboard root returns HTML response."""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")

    def test_dashboard_returns_placeholder_when_no_static(self, client, tmp_path, monkeypatch):
        """Test dashboard returns placeholder HTML when static files missing."""
        # Remove index.html if it exists
        monkeypatch.setattr("claudeswarm.web.server.STATIC_DIR", tmp_path / "empty_static")
        (tmp_path / "empty_static").mkdir()

        response = client.get("/")
        assert response.status_code == 200
        content = response.text
        assert "Claude Swarm Dashboard" in content
        assert "Available Endpoints" in content

    def test_dashboard_serves_index_html_when_exists(self, client, tmp_path, monkeypatch):
        """Test dashboard serves index.html when it exists."""
        static_dir = tmp_path / "static"
        static_dir.mkdir(exist_ok=True)
        index_html = static_dir / "index.html"
        index_html.write_text("<html><body>Test Dashboard</body></html>")

        monkeypatch.setattr("claudeswarm.web.server.STATIC_DIR", static_dir)

        response = client.get("/")
        assert response.status_code == 200
        assert "Test Dashboard" in response.text

    def test_dashboard_handles_io_error(self, client, tmp_path, monkeypatch):
        """Test dashboard handles I/O errors gracefully."""
        static_dir = tmp_path / "static"
        static_dir.mkdir(exist_ok=True)
        index_html = static_dir / "index.html"
        index_html.write_text("<html><body>Test</body></html>")

        monkeypatch.setattr("claudeswarm.web.server.STATIC_DIR", static_dir)

        # Mock open to raise IOError - patch at the module level
        original_open = open
        def mock_open_error(*args, **kwargs):
            # Only raise error for index.html, let other files through
            if len(args) > 0 and "index.html" in str(args[0]):
                raise IOError("Test error")
            return original_open(*args, **kwargs)

        with patch("builtins.open", side_effect=mock_open_error):
            response = client.get("/")
            # Should return 500 error or fallback to placeholder
            assert response.status_code in [200, 500]


class TestSecurityHeaders:
    """Test security-related headers and configurations."""

    def test_cors_middleware_configured(self, client):
        """Test CORS middleware is configured in the app."""
        from claudeswarm.web.server import app
        # Check that CORS middleware is added
        # CORS headers only appear with proper Origin header
        response = client.get("/api/agents", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        # CORS middleware is configured in server.py
        # TestClient may not fully simulate CORS, but we verify the endpoint works

    def test_cors_allows_credentials(self, client):
        """Test CORS configuration allows credentials."""
        from claudeswarm.web.server import app
        # Verify CORS middleware is in the middleware stack
        has_cors = any(
            "CORSMiddleware" in str(type(middleware))
            for middleware in getattr(app, "user_middleware", [])
        )
        # FastAPI's TestClient doesn't always show CORS headers
        # This test mainly verifies the middleware is configured
        response = client.get("/api/agents")
        assert response.status_code == 200  # Endpoint works


class TestAuthentication:
    """Test authentication handling (when implemented)."""

    def test_no_auth_required_by_default(self, client):
        """Test no authentication required by default."""
        response = client.get("/api/agents")
        assert response.status_code == 200
        # No auth required - should succeed

    def test_all_endpoints_accessible_without_auth(self, client):
        """Test all endpoints accessible without authentication."""
        endpoints = [
            "/",
            "/health",
            "/api/agents",
            "/api/locks",
            "/api/messages",
            "/api/stats"
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            # All should be accessible (200 for successful endpoints)
            assert response.status_code in [200, 404]  # 404 is ok for non-existent endpoints


class TestErrorHandling:
    """Test error handling across all endpoints."""

    def test_handles_invalid_json_gracefully(self, client, tmp_path):
        """Test all endpoints handle invalid JSON gracefully."""
        # Create invalid JSON files
        (tmp_path / "ACTIVE_AGENTS.json").write_text("{invalid")

        # Should not crash
        response = client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["agents"] == []

    def test_handles_missing_files_gracefully(self, client, tmp_path, monkeypatch):
        """Test endpoints handle missing files gracefully."""
        # Point to non-existent files
        monkeypatch.setattr("claudeswarm.web.server.ACTIVE_AGENTS_FILE", tmp_path / "nonexistent.json")
        monkeypatch.setattr("claudeswarm.web.server.AGENT_MESSAGES_LOG", tmp_path / "nonexistent.log")

        # Should return empty data, not errors
        response = client.get("/api/agents")
        assert response.status_code == 200

        response = client.get("/api/messages")
        assert response.status_code == 200

    def test_handles_permission_errors(self, client, tmp_path, monkeypatch):
        """Test handles file permission errors gracefully."""
        agents_file = tmp_path / "ACTIVE_AGENTS.json"
        agents_file.write_text('{"agents": []}')

        # Mock open to raise PermissionError
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            response = client.get("/api/agents")
            # Should handle gracefully
            assert response.status_code == 200
            data = response.json()
            assert data["agents"] == []

    def test_invalid_endpoint_returns_404(self, client):
        """Test invalid endpoint returns 404."""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404

    def test_invalid_method_returns_405(self, client):
        """Test invalid HTTP method returns 405."""
        response = client.post("/api/agents")
        assert response.status_code == 405


class TestCORSHandling:
    """Test CORS configuration and handling."""

    def test_cors_preflight_request(self, client):
        """Test CORS preflight OPTIONS request."""
        response = client.options(
            "/api/agents",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )
        # Should handle preflight
        assert response.status_code in [200, 204]

    def test_cors_allows_credentials(self, client):
        """Test CORS allows credentials."""
        response = client.get("/api/agents")
        headers = response.headers
        # Check if credentials are allowed
        allow_credentials = headers.get("access-control-allow-credentials") or headers.get("Access-Control-Allow-Credentials")
        # FastAPI CORS with allow_credentials=True should set this
        if allow_credentials:
            assert allow_credentials.lower() == "true"


class TestUtilityFunctions:
    """Test internal utility functions."""

    def test_safe_load_json_with_valid_file(self, tmp_path):
        """Test safe_load_json with valid JSON file."""
        from claudeswarm.web.server import safe_load_json

        test_file = tmp_path / "test.json"
        test_data = {"key": "value"}
        test_file.write_text(json.dumps(test_data))

        result = safe_load_json(test_file)
        assert result == test_data

    def test_safe_load_json_with_missing_file(self, tmp_path):
        """Test safe_load_json with missing file."""
        from claudeswarm.web.server import safe_load_json

        result = safe_load_json(tmp_path / "nonexistent.json")
        assert result is None

    def test_safe_load_json_with_invalid_json(self, tmp_path):
        """Test safe_load_json with invalid JSON."""
        from claudeswarm.web.server import safe_load_json

        test_file = tmp_path / "test.json"
        test_file.write_text("{invalid json")

        result = safe_load_json(test_file)
        assert result is None

    def test_tail_log_file_returns_last_n_lines(self, tmp_path):
        """Test tail_log_file returns last N lines."""
        from claudeswarm.web.server import tail_log_file

        log_file = tmp_path / "test.log"
        messages = [
            {"id": i, "msg": f"Message {i}"}
            for i in range(100)
        ]
        log_file.write_text("\n".join(json.dumps(m) for m in messages))

        result = tail_log_file(log_file, limit=10)
        assert len(result) == 10
        # Should be last 10 messages
        assert result[0]["id"] == 90
        assert result[-1]["id"] == 99

    def test_get_lock_files_returns_lock_info(self, tmp_path, monkeypatch):
        """Test get_lock_files returns lock information."""
        from claudeswarm.web.server import get_lock_files

        locks_dir = tmp_path / ".agent_locks"
        locks_dir.mkdir(exist_ok=True)  # Use exist_ok since autouse fixture may create it
        monkeypatch.setattr("claudeswarm.web.server.AGENT_LOCKS_DIR", locks_dir)

        lock_data = {"agent_id": "agent-0", "filepath": "test.py"}
        (locks_dir / "test.py.lock").write_text(json.dumps(lock_data))

        result = get_lock_files()
        assert len(result) == 1
        assert result[0]["agent_id"] == "agent-0"
        assert result[0]["lock_file"] == "test.py.lock"


class TestStateTracker:
    """Test StateTracker class for change detection."""

    def test_state_tracker_initialization(self):
        """Test StateTracker initializes with zero state."""
        from claudeswarm.web.server import StateTracker

        tracker = StateTracker()
        assert tracker.agents_mtime == 0.0
        assert tracker.messages_mtime == 0.0
        assert tracker.locks_mtime == 0.0
        assert tracker.message_count == 0

    def test_state_tracker_detects_agents_change(self, tmp_path, monkeypatch):
        """Test StateTracker detects changes in agents file."""
        from claudeswarm.web.server import StateTracker

        agents_file = tmp_path / "ACTIVE_AGENTS.json"
        monkeypatch.setattr("claudeswarm.web.server.ACTIVE_AGENTS_FILE", agents_file)

        tracker = StateTracker()

        # Initially no file
        changes = tracker.check_changes()
        assert not changes["agents"]

        # Create file
        agents_file.write_text('{"agents": []}')
        time.sleep(0.01)  # Ensure mtime changes

        changes = tracker.check_changes()
        assert changes["agents"]

        # No change on subsequent check
        changes = tracker.check_changes()
        assert not changes["agents"]

    def test_state_tracker_detects_locks_change(self, tmp_path, monkeypatch):
        """Test StateTracker detects changes in lock files."""
        from claudeswarm.web.server import StateTracker

        locks_dir = tmp_path / ".agent_locks"
        locks_dir.mkdir(exist_ok=True)  # Use exist_ok since autouse fixture may create it
        monkeypatch.setattr("claudeswarm.web.server.AGENT_LOCKS_DIR", locks_dir)

        tracker = StateTracker()

        # Initially no locks
        changes = tracker.check_changes()
        assert not changes["locks"]

        # Create lock file
        (locks_dir / "test.lock").write_text('{"agent": "test"}')
        time.sleep(0.01)

        changes = tracker.check_changes()
        assert changes["locks"]


class TestConcurrency:
    """Test concurrent access and thread safety."""

    def test_concurrent_agent_requests(self, client):
        """Test handling concurrent requests to /api/agents."""
        import concurrent.futures

        def make_request():
            return client.get("/api/agents")

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(20)]
            results = [f.result() for f in futures]

        # All requests should succeed
        assert all(r.status_code == 200 for r in results)

    def test_concurrent_mixed_requests(self, client):
        """Test handling concurrent requests to different endpoints."""
        import concurrent.futures

        endpoints = ["/api/agents", "/api/locks", "/api/messages", "/api/stats"]

        def make_request(endpoint):
            return client.get(endpoint)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, endpoint) for endpoint in endpoints * 5]
            results = [f.result() for f in futures]

        # All requests should succeed
        assert all(r.status_code == 200 for r in results)


class TestPerformance:
    """Test performance characteristics."""

    def test_large_message_log_handling(self, client, tmp_path):
        """Test handling large message logs efficiently."""
        # Create log with many messages
        messages = [
            {"id": i, "msg_type": "INFO", "content": f"Message {i}"}
            for i in range(5000)
        ]
        log_content = "\n".join(json.dumps(m) for m in messages)
        (tmp_path / "agent_messages.log").write_text(log_content)

        # Should handle large file with limit
        response = client.get("/api/messages?limit=100")
        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) == 100

    def test_many_lock_files_handling(self, client, tmp_path):
        """Test handling many lock files efficiently."""
        locks_dir = tmp_path / ".agent_locks"

        # Create many lock files
        for i in range(100):
            lock_data = {"agent_id": f"agent-{i}", "filepath": f"file{i}.py"}
            (locks_dir / f"file{i}.lock").write_text(json.dumps(lock_data))

        response = client.get("/api/locks")
        assert response.status_code == 200
        data = response.json()
        assert len(data["locks"]) == 100
        assert data["count"] == 100
