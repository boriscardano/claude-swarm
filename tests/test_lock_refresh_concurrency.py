"""Advanced concurrency tests for lock refresh mechanism.

This test suite specifically targets the race condition in lock refresh
to ensure it's properly fixed using atomic operations.
"""

import json
import tempfile
import threading
import time
from pathlib import Path

import pytest

from claudeswarm.locking import LockManager


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def lock_manager(temp_project_dir):
    """Create a LockManager instance for testing."""
    return LockManager(project_root=temp_project_dir)


class TestLockRefreshAtomicity:
    """Tests specifically for lock refresh atomicity."""

    def test_lock_refresh_no_race_window(self, lock_manager):
        """Test that lock refresh is truly atomic with no race window."""
        filepath = "test.py"

        # Agent 1 acquires initial lock
        success, _ = lock_manager.acquire_lock(filepath, "agent-1", "initial")
        assert success

        lock_path = lock_manager._get_lock_path(filepath)

        # Track if lock file ever disappears during refresh
        lock_disappeared = False
        stop_checking = False

        def monitor_lock_file():
            """Monitor if lock file disappears during refresh."""
            nonlocal lock_disappeared, stop_checking
            while not stop_checking:
                if not lock_path.exists():
                    lock_disappeared = True
                    break
                time.sleep(0.0001)  # Check very frequently

        # Start monitoring in background
        monitor_thread = threading.Thread(target=monitor_lock_file, daemon=True)
        monitor_thread.start()

        # Perform multiple refreshes
        for i in range(100):
            success, _ = lock_manager.acquire_lock(filepath, "agent-1", f"refresh-{i}")
            assert success
            time.sleep(0.001)  # Small delay between refreshes

        stop_checking = True
        monitor_thread.join(timeout=1.0)

        # Lock file should NEVER have disappeared during refresh
        assert not lock_disappeared, "Lock file disappeared during refresh - not atomic!"

    def test_concurrent_refresh_attempts(self, lock_manager):
        """Test multiple concurrent refresh attempts by same agent."""
        filepath = "test.py"

        # Agent acquires initial lock
        success, _ = lock_manager.acquire_lock(filepath, "agent-1", "initial")
        assert success

        results = []
        errors = []

        def refresh_lock(iteration):
            """Attempt to refresh lock."""
            try:
                success, conflict = lock_manager.acquire_lock(
                    filepath, "agent-1", f"refresh-{iteration}"
                )
                results.append((iteration, success, conflict))
            except Exception as e:
                errors.append((iteration, e))

        # Launch multiple concurrent refresh attempts
        threads = []
        for i in range(50):
            thread = threading.Thread(target=refresh_lock, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join(timeout=5.0)

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # All refreshes should succeed (same agent)
        assert len(results) == 50
        for iteration, success, conflict in results:
            assert success, f"Refresh {iteration} failed with conflict: {conflict}"

        # Lock should still exist and be owned by agent-1
        lock = lock_manager.who_has_lock(filepath)
        assert lock is not None
        assert lock.agent_id == "agent-1"

    def test_refresh_vs_acquisition_race(self, lock_manager):
        """Test race between lock refresh and new acquisition attempts."""
        filepath = "test.py"

        # Agent 1 acquires lock
        success, _ = lock_manager.acquire_lock(filepath, "agent-1", "initial")
        assert success

        results = {"agent-1": [], "agent-2": []}
        errors = []
        stop_flag = False

        def agent_1_refresh():
            """Agent 1 continuously refreshes their lock."""
            while not stop_flag:
                try:
                    success, conflict = lock_manager.acquire_lock(filepath, "agent-1", "refresh")
                    results["agent-1"].append((success, conflict))
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(("agent-1", e))
                    break

        def agent_2_acquire():
            """Agent 2 continuously tries to acquire lock."""
            while not stop_flag:
                try:
                    success, conflict = lock_manager.acquire_lock(filepath, "agent-2", "steal")
                    results["agent-2"].append((success, conflict))
                    time.sleep(0.001)
                except Exception as e:
                    errors.append(("agent-2", e))
                    break

        # Run both agents concurrently
        thread1 = threading.Thread(target=agent_1_refresh, daemon=True)
        thread2 = threading.Thread(target=agent_2_acquire, daemon=True)

        thread1.start()
        thread2.start()

        # Let them race for a bit
        time.sleep(1.0)
        stop_flag = True

        thread1.join(timeout=2.0)
        thread2.join(timeout=2.0)

        # Should have no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"

        # Agent 1 refreshes should all succeed
        agent_1_results = results["agent-1"]
        assert len(agent_1_results) > 0
        for success, conflict in agent_1_results:
            assert success, "Agent 1 refresh failed"
            assert conflict is None

        # Agent 2 acquisitions should all fail (agent 1 holds lock)
        agent_2_results = results["agent-2"]
        assert len(agent_2_results) > 0
        for success, conflict in agent_2_results:
            assert not success, "Agent 2 should not acquire agent 1's lock"
            assert conflict is not None
            assert conflict.current_holder == "agent-1"

        # Final lock should still be owned by agent-1
        lock = lock_manager.who_has_lock(filepath)
        assert lock is not None
        assert lock.agent_id == "agent-1"

    def test_no_temp_files_left_behind(self, lock_manager):
        """Test that temporary files are cleaned up properly."""
        filepath = "test.py"

        # Acquire and refresh lock many times
        lock_manager.acquire_lock(filepath, "agent-1", "initial")

        for i in range(100):
            lock_manager.acquire_lock(filepath, "agent-1", f"refresh-{i}")

        # Check for temp files
        temp_files = list(lock_manager.lock_dir.glob("*.tmp"))
        assert len(temp_files) == 0, f"Found temp files: {temp_files}"

        # Should only have the one lock file
        lock_files = list(lock_manager.lock_dir.glob("*.lock"))
        assert len(lock_files) == 1

    def test_refresh_error_handling(self, lock_manager, temp_project_dir):
        """Test that refresh handles errors gracefully."""
        filepath = "test.py"

        # Acquire lock
        success, _ = lock_manager.acquire_lock(filepath, "agent-1", "initial")
        assert success

        lock_path = lock_manager._get_lock_path(filepath)

        # Make lock directory read-only to cause write errors
        # (We'll do this by creating a mock that raises an error)
        import os

        original_replace = os.replace

        call_count = [0]

        def failing_replace(src, dst):
            call_count[0] += 1
            if call_count[0] == 1:
                # Fail on first call
                raise OSError("Simulated write error")
            return original_replace(src, dst)

        # Temporarily replace os.replace
        os.replace = failing_replace

        try:
            # Try to refresh - should raise error
            with pytest.raises(OSError, match="Simulated write error"):
                lock_manager.acquire_lock(filepath, "agent-1", "refresh")

            # Temp file should be cleaned up
            temp_files = list(lock_manager.lock_dir.glob("*.tmp"))
            assert len(temp_files) == 0

            # Original lock should still exist
            assert lock_path.exists()

            # Now let it succeed
            success, _ = lock_manager.acquire_lock(filepath, "agent-1", "refresh-2")
            assert success

        finally:
            os.replace = original_replace

    def test_multiple_agents_concurrent_different_files(self, lock_manager):
        """Test that multiple agents can refresh different files concurrently."""
        files = [f"file{i}.py" for i in range(10)]

        # Each agent acquires their file
        for i, filepath in enumerate(files):
            success, _ = lock_manager.acquire_lock(filepath, f"agent-{i}", "initial")
            assert success

        results = {f"agent-{i}": [] for i in range(10)}
        errors = []
        stop_flag = False

        def agent_refresh(agent_id, filepath):
            """Agent continuously refreshes their lock."""
            while not stop_flag:
                try:
                    success, conflict = lock_manager.acquire_lock(filepath, agent_id, "refresh")
                    results[agent_id].append((success, conflict))
                    time.sleep(0.001)
                except Exception as e:
                    errors.append((agent_id, e))
                    break

        # Start all agents
        threads = []
        for i, filepath in enumerate(files):
            thread = threading.Thread(
                target=agent_refresh, args=(f"agent-{i}", filepath), daemon=True
            )
            threads.append(thread)
            thread.start()

        # Let them run
        time.sleep(1.0)
        stop_flag = True

        for thread in threads:
            thread.join(timeout=2.0)

        # No errors
        assert len(errors) == 0, f"Errors: {errors}"

        # All agents should have successfully refreshed
        for agent_id, agent_results in results.items():
            assert len(agent_results) > 0
            for success, conflict in agent_results:
                assert success, f"{agent_id} refresh failed"
                assert conflict is None

    def test_lock_integrity_during_refresh(self, lock_manager):
        """Test that lock data integrity is maintained during refresh."""
        filepath = "test.py"

        # Acquire initial lock
        lock_manager.acquire_lock(filepath, "agent-1", "v1")

        lock_path = lock_manager._get_lock_path(filepath)

        # Monitor that lock file always contains valid JSON
        invalid_content_detected = False
        stop_checking = False

        def monitor_lock_content():
            """Monitor that lock file always has valid JSON."""
            nonlocal invalid_content_detected, stop_checking
            while not stop_checking:
                if lock_path.exists():
                    try:
                        with lock_path.open("r") as f:
                            data = json.load(f)
                        # Verify required fields
                        assert "agent_id" in data
                        assert "filepath" in data
                        assert "locked_at" in data
                        assert "reason" in data
                        assert data["agent_id"] == "agent-1"
                    except (json.JSONDecodeError, AssertionError):
                        invalid_content_detected = True
                        break
                time.sleep(0.0001)

        # Start monitoring
        monitor_thread = threading.Thread(target=monitor_lock_content, daemon=True)
        monitor_thread.start()

        # Perform many refreshes
        for i in range(100):
            lock_manager.acquire_lock(filepath, "agent-1", f"v{i+2}")
            time.sleep(0.001)

        stop_checking = True
        monitor_thread.join(timeout=1.0)

        # Should never have detected invalid content
        assert not invalid_content_detected, "Lock file had invalid content during refresh"

    def test_threading_lock_prevents_internal_races(self, lock_manager):
        """Test that internal threading.Lock prevents races in refresh logic."""
        filepath = "test.py"

        # Acquire lock
        lock_manager.acquire_lock(filepath, "agent-1", "initial")

        # Launch many threads that all try to refresh at same instant
        results = []
        errors = []
        barrier = threading.Barrier(50)  # Sync 50 threads

        def synchronized_refresh(iteration):
            """Wait at barrier then refresh immediately."""
            try:
                barrier.wait()  # All threads start together
                success, conflict = lock_manager.acquire_lock(
                    filepath, "agent-1", f"refresh-{iteration}"
                )
                results.append((iteration, success, conflict))
            except Exception as e:
                errors.append((iteration, e))

        threads = []
        for i in range(50):
            thread = threading.Thread(target=synchronized_refresh, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join(timeout=5.0)

        # No errors
        assert len(errors) == 0, f"Errors: {errors}"

        # All should succeed
        assert len(results) == 50
        for iteration, success, _conflict in results:
            assert success, f"Refresh {iteration} failed"

        # Lock should exist and be valid
        lock = lock_manager.who_has_lock(filepath)
        assert lock is not None
        assert lock.agent_id == "agent-1"


class TestAtomicRenameImplementation:
    """Tests to verify the atomic rename implementation details."""

    def test_uses_os_replace_not_rename(self, lock_manager):
        """Test that implementation uses os.replace (works on Windows too)."""
        import os

        filepath = "test.py"
        lock_manager.acquire_lock(filepath, "agent-1", "initial")

        # Track which function is called
        replace_called = False
        original_replace = os.replace

        def tracked_replace(src, dst):
            nonlocal replace_called
            replace_called = True
            return original_replace(src, dst)

        os.replace = tracked_replace

        try:
            # Refresh lock
            lock_manager.acquire_lock(filepath, "agent-1", "refresh")

            # Verify os.replace was called
            assert replace_called, "os.replace was not called - not using atomic rename!"
        finally:
            os.replace = original_replace

    def test_temp_file_naming_convention(self, lock_manager):
        """Test that temp files use .lock.tmp suffix."""

        filepath = "test.py"
        lock_manager.acquire_lock(filepath, "agent-1", "initial")

        lock_path = lock_manager._get_lock_path(filepath)
        expected_temp_path = lock_path.with_suffix(".lock.tmp")

        # Track temp file creation
        temp_file_created = False
        original_open = Path.open

        def tracked_open(self, *args, **kwargs):
            nonlocal temp_file_created
            if self.suffix == ".tmp":
                temp_file_created = True
                assert self == expected_temp_path, f"Wrong temp path: {self}"
            return original_open(self, *args, **kwargs)

        Path.open = tracked_open

        try:
            lock_manager.acquire_lock(filepath, "agent-1", "refresh")
            assert temp_file_created, "Temp file was not created"
        finally:
            Path.open = original_open
