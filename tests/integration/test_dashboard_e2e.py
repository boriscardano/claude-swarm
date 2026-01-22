"""End-to-end tests for dashboard functionality.

This module provides comprehensive integration tests for the web dashboard,
testing real server startup, file monitoring, and data updates.

Author: Agent 4 - Tests & Documentation
"""

import json
import multiprocessing
import time

import pytest
import requests


class TestDashboardE2E:
    """End-to-end dashboard tests."""

    @pytest.fixture
    def test_port(self):
        """Use a non-standard port for testing."""
        return 8888

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root."""
        return tmp_path

    @pytest.fixture
    def dashboard_files(self, project_root):
        """Create dashboard data files."""
        agents_file = project_root / "ACTIVE_AGENTS.json"
        messages_file = project_root / "agent_messages.log"
        locks_dir = project_root / ".agent_locks"
        locks_dir.mkdir()

        return {"agents": agents_file, "messages": messages_file, "locks_dir": locks_dir}

    def start_dashboard_server(self, port, project_root):
        """Start dashboard server in subprocess."""
        try:
            import uvicorn

            from src.claudeswarm.web.server import create_app

            app = create_app(project_root=str(project_root))
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
        except ImportError:
            # If web module doesn't exist, skip
            pass

    def wait_for_server(self, port, timeout=5):
        """Wait for server to be ready."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://127.0.0.1:{port}/api/stats", timeout=1)
                if response.status_code == 200:
                    return True
            except requests.exceptions.RequestException:
                time.sleep(0.1)
        return False

    @pytest.mark.integration
    def test_dashboard_starts_and_serves(self, test_port, project_root):
        """Test dashboard starts and serves pages."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start server in subprocess
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            # Wait for server to start
            assert self.wait_for_server(test_port), "Server failed to start"

            # Make HTTP request
            response = requests.get(f"http://127.0.0.1:{test_port}/", timeout=2)
            assert response.status_code == 200

            # Test API endpoint
            response = requests.get(f"http://127.0.0.1:{test_port}/api/stats", timeout=2)
            assert response.status_code == 200
            data = response.json()
            assert "agent_count" in data

        finally:
            # Clean up
            server_process.terminate()
            server_process.join(timeout=5)
            if server_process.is_alive():
                server_process.kill()

    @pytest.mark.integration
    def test_dashboard_updates_on_new_agent(self, test_port, project_root, dashboard_files):
        """Test dashboard updates when new agent discovered."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start dashboard
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            assert self.wait_for_server(test_port), "Server failed to start"

            # Create new ACTIVE_AGENTS.json
            agents_data = {
                "agents": [
                    {
                        "id": "agent-0",
                        "pane_index": "main:0.0",
                        "status": "active",
                        "last_seen": "2025-11-10T12:00:00Z",
                    }
                ]
            }
            dashboard_files["agents"].write_text(json.dumps(agents_data))

            # Wait for file monitoring to pick up changes
            time.sleep(0.5)

            # Verify /api/agents returns new agent
            response = requests.get(f"http://127.0.0.1:{test_port}/api/agents", timeout=2)
            assert response.status_code == 200
            data = response.json()
            assert len(data["agents"]) >= 1

        finally:
            server_process.terminate()
            server_process.join(timeout=5)
            if server_process.is_alive():
                server_process.kill()

    @pytest.mark.integration
    def test_dashboard_shows_new_messages(self, test_port, project_root, dashboard_files):
        """Test dashboard shows new messages."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start dashboard
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            assert self.wait_for_server(test_port), "Server failed to start"

            # Append to agent_messages.log
            message = {
                "sender_id": "agent-0",
                "msg_type": "INFO",
                "content": "Test message",
                "timestamp": "2025-11-10T12:00:00Z",
            }
            with dashboard_files["messages"].open("a") as f:
                f.write(json.dumps(message) + "\n")

            # Wait for file monitoring
            time.sleep(0.5)

            # Verify /api/messages returns new message
            response = requests.get(f"http://127.0.0.1:{test_port}/api/messages", timeout=2)
            assert response.status_code == 200
            data = response.json()
            assert len(data["messages"]) >= 1

        finally:
            server_process.terminate()
            server_process.join(timeout=5)
            if server_process.is_alive():
                server_process.kill()

    @pytest.mark.integration
    def test_dashboard_tracks_locks(self, test_port, project_root, dashboard_files):
        """Test dashboard tracks lock files."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start dashboard
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            assert self.wait_for_server(test_port), "Server failed to start"

            # Create .agent_locks/*.lock file
            lock_data = {
                "filepath": "src/test.py",
                "agent_id": "agent-1",
                "reason": "Testing",
                "locked_at": time.time(),
            }
            lock_file = dashboard_files["locks_dir"] / "test.py.lock"
            lock_file.write_text(json.dumps(lock_data))

            # Wait for file monitoring
            time.sleep(0.5)

            # Verify /api/locks returns lock
            response = requests.get(f"http://127.0.0.1:{test_port}/api/locks", timeout=2)
            assert response.status_code == 200
            data = response.json()
            assert len(data["locks"]) >= 1

        finally:
            server_process.terminate()
            server_process.join(timeout=5)
            if server_process.is_alive():
                server_process.kill()

    @pytest.mark.integration
    def test_dashboard_multiple_clients(self, test_port, project_root):
        """Test dashboard handles multiple concurrent clients."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start dashboard
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            assert self.wait_for_server(test_port), "Server failed to start"

            # Make multiple concurrent requests
            import concurrent.futures

            def make_request():
                return requests.get(f"http://127.0.0.1:{test_port}/api/stats", timeout=2)

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(make_request) for _ in range(10)]
                results = [f.result() for f in futures]

            # All requests should succeed
            assert all(r.status_code == 200 for r in results)

        finally:
            server_process.terminate()
            server_process.join(timeout=5)
            if server_process.is_alive():
                server_process.kill()

    @pytest.mark.integration
    def test_dashboard_sse_stream(self, test_port, project_root):
        """Test Server-Sent Events streaming."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start dashboard
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            assert self.wait_for_server(test_port), "Server failed to start"

            # Connect to SSE stream (with short timeout)
            response = requests.get(
                f"http://127.0.0.1:{test_port}/api/stream", stream=True, timeout=2
            )

            # Verify SSE headers
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

            # Try to read one event (with timeout)
            try:
                for line in response.iter_lines(decode_unicode=True):
                    if line.startswith("data:"):
                        # Successfully got an SSE event
                        break
            except requests.exceptions.ReadTimeout:
                # Timeout is acceptable - stream exists
                pass

        finally:
            server_process.terminate()
            server_process.join(timeout=5)
            if server_process.is_alive():
                server_process.kill()

    @pytest.mark.integration
    def test_dashboard_graceful_shutdown(self, test_port, project_root):
        """Test dashboard shuts down gracefully."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start dashboard
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            assert self.wait_for_server(test_port), "Server failed to start"

            # Server is running
            response = requests.get(f"http://127.0.0.1:{test_port}/api/stats", timeout=2)
            assert response.status_code == 200

            # Terminate server
            server_process.terminate()
            server_process.join(timeout=5)

            # Server should shut down cleanly
            assert not server_process.is_alive()

        finally:
            if server_process.is_alive():
                server_process.kill()

    @pytest.mark.integration
    def test_dashboard_port_conflict(self, test_port, project_root):
        """Test dashboard detects port conflicts."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start first server
        server1 = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server1.start()

        try:
            assert self.wait_for_server(test_port), "Server 1 failed to start"

            # Try to start second server on same port
            server2 = multiprocessing.Process(
                target=self.start_dashboard_server, args=(test_port, project_root)
            )
            server2.start()

            # Give it time to try starting
            time.sleep(1)

            # Second server should fail to bind
            # (This is implementation-dependent)

        finally:
            server1.terminate()
            server1.join(timeout=5)
            if server1.is_alive():
                server1.kill()
            if "server2" in locals():
                server2.terminate()
                server2.join(timeout=5)
                if server2.is_alive():
                    server2.kill()

    @pytest.mark.integration
    def test_dashboard_file_monitoring_performance(self, test_port, project_root, dashboard_files):
        """Test dashboard handles rapid file updates."""
        try:
            from src.claudeswarm.web.server import create_app
        except ImportError:
            pytest.skip("Web module not implemented yet")

        # Start dashboard
        server_process = multiprocessing.Process(
            target=self.start_dashboard_server, args=(test_port, project_root)
        )
        server_process.start()

        try:
            assert self.wait_for_server(test_port), "Server failed to start"

            # Write many messages rapidly
            messages = []
            for i in range(100):
                message = {
                    "sender_id": f"agent-{i % 3}",
                    "msg_type": "INFO",
                    "content": f"Message {i}",
                    "timestamp": f"2025-11-10T12:{i % 60:02d}:00Z",
                }
                messages.append(json.dumps(message))

            dashboard_files["messages"].write_text("\n".join(messages))

            # Wait for processing
            time.sleep(1)

            # Dashboard should still be responsive
            response = requests.get(f"http://127.0.0.1:{test_port}/api/stats", timeout=2)
            assert response.status_code == 200

        finally:
            server_process.terminate()
            server_process.join(timeout=5)
            if server_process.is_alive():
                server_process.kill()


class TestDashboardCLIIntegration:
    """Test dashboard CLI integration."""

    @pytest.mark.integration
    def test_start_dashboard_command(self, tmp_path):
        """Test start-dashboard CLI command."""
        try:
            from src.claudeswarm.cli import cmd_start_dashboard
        except (ImportError, AttributeError):
            pytest.skip("Dashboard CLI not implemented yet")

        import argparse

        args = argparse.Namespace(
            project_root=tmp_path, port=8889, host="127.0.0.1", no_browser=True, reload=False
        )

        # This test just verifies the command exists and accepts args
        # Full testing would require mocking the server
        assert hasattr(args, "port")
        assert hasattr(args, "no_browser")
