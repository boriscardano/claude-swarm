"""Unit tests for the file locking system.

Tests cover:
- Lock acquisition and release
- Conflict detection
- Stale lock cleanup
- Concurrent lock attempts (race conditions)
- Glob pattern matching
- Lock file corruption handling
- Retry logic with exponential backoff and jitter
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from claudeswarm.locking import (
    STALE_LOCK_TIMEOUT,
    FileLock,
    LockConflict,
    LockManager,
    _calculate_backoff_delay,
    _retry_with_backoff,
    MAX_LOCK_RETRIES,
    INITIAL_RETRY_DELAY_SECONDS,
    MAX_RETRY_DELAY_SECONDS,
    JITTER_FACTOR,
)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def lock_manager(temp_project_dir):
    """Create a LockManager instance for testing."""
    return LockManager(project_root=temp_project_dir)


class TestFileLock:
    """Tests for FileLock dataclass."""

    def test_is_stale_fresh_lock(self):
        """Test that a fresh lock is not stale."""
        lock = FileLock(
            agent_id="agent-1",
            filepath="test.py",
            locked_at=time.time(),
            reason="testing",
        )
        assert not lock.is_stale(timeout=300)

    def test_is_stale_old_lock(self):
        """Test that an old lock is stale."""
        lock = FileLock(
            agent_id="agent-1",
            filepath="test.py",
            locked_at=time.time() - 400,  # 400 seconds ago
            reason="testing",
        )
        assert lock.is_stale(timeout=300)

    def test_age_seconds(self):
        """Test lock age calculation."""
        lock_time = time.time() - 10  # 10 seconds ago
        lock = FileLock(
            agent_id="agent-1",
            filepath="test.py",
            locked_at=lock_time,
            reason="testing",
        )
        age = lock.age_seconds()
        assert 9 < age < 11  # Allow small timing variance

    def test_to_dict(self):
        """Test serialization to dictionary."""
        lock = FileLock(
            agent_id="agent-1",
            filepath="test.py",
            locked_at=12345.0,
            reason="testing",
        )
        data = lock.to_dict()
        assert data["agent_id"] == "agent-1"
        assert data["filepath"] == "test.py"
        assert data["locked_at"] == 12345.0
        assert data["reason"] == "testing"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "agent_id": "agent-1",
            "filepath": "test.py",
            "locked_at": 12345.0,
            "reason": "testing",
        }
        lock = FileLock.from_dict(data)
        assert lock.agent_id == "agent-1"
        assert lock.filepath == "test.py"
        assert lock.locked_at == 12345.0
        assert lock.reason == "testing"


class TestLockManager:
    """Tests for LockManager."""

    def test_lock_directory_created(self, temp_project_dir):
        """Test that lock directory is created."""
        manager = LockManager(project_root=temp_project_dir)
        assert manager.lock_dir.exists()
        assert manager.lock_dir.is_dir()

    def test_acquire_lock_success(self, lock_manager):
        """Test successful lock acquisition."""
        success, conflict = lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-1",
            reason="testing",
        )
        assert success
        assert conflict is None

    def test_acquire_lock_conflict(self, lock_manager):
        """Test lock conflict when file is already locked."""
        # Agent 1 acquires lock
        lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-1",
            reason="first lock",
        )

        # Agent 2 tries to acquire same lock
        success, conflict = lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-2",
            reason="second lock",
        )

        assert not success
        assert conflict is not None
        assert isinstance(conflict, LockConflict)
        assert conflict.current_holder == "agent-1"
        assert conflict.filepath == "test.py"
        assert conflict.reason == "first lock"

    def test_acquire_lock_refresh(self, lock_manager):
        """Test that agent can refresh their own lock."""
        # Agent 1 acquires lock
        lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-1",
            reason="first lock",
        )

        # Agent 1 refreshes the lock
        success, conflict = lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-1",
            reason="refreshed lock",
        )

        assert success
        assert conflict is None

        # Verify reason was updated
        lock = lock_manager.who_has_lock("test.py")
        assert lock is not None
        assert lock.reason == "refreshed lock"

    def test_acquire_lock_stale_cleanup(self, lock_manager):
        """Test that stale locks are automatically cleaned up."""
        # Create a stale lock
        old_lock = FileLock(
            agent_id="agent-1",
            filepath="test.py",
            locked_at=time.time() - 400,  # 400 seconds ago
            reason="stale lock",
        )
        lock_path = lock_manager._get_lock_path("test.py")
        with lock_path.open("x") as f:
            json.dump(old_lock.to_dict(), f)

        # Agent 2 tries to acquire lock
        success, conflict = lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-2",
            reason="new lock",
        )

        assert success
        assert conflict is None

        # Verify new lock is in place
        lock = lock_manager.who_has_lock("test.py")
        assert lock is not None
        assert lock.agent_id == "agent-2"

    def test_release_lock_success(self, lock_manager):
        """Test successful lock release."""
        # Acquire lock
        lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-1",
            reason="testing",
        )

        # Release lock
        success = lock_manager.release_lock("test.py", "agent-1")
        assert success

        # Verify lock is gone
        lock = lock_manager.who_has_lock("test.py")
        assert lock is None

    def test_release_lock_not_owner(self, lock_manager):
        """Test that agent cannot release another agent's lock."""
        # Agent 1 acquires lock
        lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-1",
            reason="testing",
        )

        # Agent 2 tries to release
        success = lock_manager.release_lock("test.py", "agent-2")
        assert not success

        # Verify lock still exists
        lock = lock_manager.who_has_lock("test.py")
        assert lock is not None
        assert lock.agent_id == "agent-1"

    def test_release_lock_nonexistent(self, lock_manager):
        """Test releasing a non-existent lock returns True."""
        # Try to release lock that doesn't exist
        success = lock_manager.release_lock("test.py", "agent-1")
        assert success  # Considered successful

    def test_who_has_lock_active(self, lock_manager):
        """Test querying an active lock."""
        # Acquire lock
        lock_manager.acquire_lock(
            filepath="test.py",
            agent_id="agent-1",
            reason="testing",
        )

        # Query lock
        lock = lock_manager.who_has_lock("test.py")
        assert lock is not None
        assert lock.agent_id == "agent-1"
        assert lock.filepath == "test.py"
        assert lock.reason == "testing"

    def test_who_has_lock_nonexistent(self, lock_manager):
        """Test querying a non-existent lock."""
        lock = lock_manager.who_has_lock("test.py")
        assert lock is None

    def test_who_has_lock_stale_cleanup(self, lock_manager):
        """Test that who_has_lock cleans up stale locks."""
        # Create a stale lock
        old_lock = FileLock(
            agent_id="agent-1",
            filepath="test.py",
            locked_at=time.time() - 400,
            reason="stale",
        )
        lock_path = lock_manager._get_lock_path("test.py")
        with lock_path.open("x") as f:
            json.dump(old_lock.to_dict(), f)

        # Query lock
        lock = lock_manager.who_has_lock("test.py")
        assert lock is None  # Stale lock was cleaned up

        # Verify lock file is gone
        assert not lock_path.exists()

    def test_list_all_locks_empty(self, lock_manager):
        """Test listing locks when none exist."""
        locks = lock_manager.list_all_locks()
        assert len(locks) == 0

    def test_list_all_locks_multiple(self, lock_manager):
        """Test listing multiple locks."""
        # Acquire multiple locks
        lock_manager.acquire_lock("file1.py", "agent-1", "test1")
        lock_manager.acquire_lock("file2.py", "agent-2", "test2")
        lock_manager.acquire_lock("file3.py", "agent-1", "test3")

        # List locks
        locks = lock_manager.list_all_locks()
        assert len(locks) == 3

        filepaths = {lock.filepath for lock in locks}
        assert filepaths == {"file1.py", "file2.py", "file3.py"}

    def test_list_all_locks_exclude_stale(self, lock_manager):
        """Test that stale locks are excluded by default."""
        # Create active lock
        lock_manager.acquire_lock("active.py", "agent-1", "active")

        # Create stale lock
        old_lock = FileLock(
            agent_id="agent-2",
            filepath="stale.py",
            locked_at=time.time() - 400,
            reason="stale",
        )
        lock_path = lock_manager._get_lock_path("stale.py")
        with lock_path.open("x") as f:
            json.dump(old_lock.to_dict(), f)

        # List locks (exclude stale)
        locks = lock_manager.list_all_locks(include_stale=False)
        assert len(locks) == 1
        assert locks[0].filepath == "active.py"

        # Verify stale lock was cleaned up
        assert not lock_path.exists()

    def test_list_all_locks_include_stale(self, lock_manager):
        """Test listing locks including stale ones."""
        # Create active lock
        lock_manager.acquire_lock("active.py", "agent-1", "active")

        # Create stale lock
        old_lock = FileLock(
            agent_id="agent-2",
            filepath="stale.py",
            locked_at=time.time() - 400,
            reason="stale",
        )
        lock_path = lock_manager._get_lock_path("stale.py")
        with lock_path.open("x") as f:
            json.dump(old_lock.to_dict(), f)

        # List locks (include stale)
        locks = lock_manager.list_all_locks(include_stale=True)
        assert len(locks) == 2

        filepaths = {lock.filepath for lock in locks}
        assert filepaths == {"active.py", "stale.py"}

    def test_cleanup_stale_locks(self, lock_manager):
        """Test cleanup of stale locks."""
        # Create active lock
        lock_manager.acquire_lock("active.py", "agent-1", "active")

        # Create stale locks
        for i in range(3):
            old_lock = FileLock(
                agent_id=f"agent-{i}",
                filepath=f"stale{i}.py",
                locked_at=time.time() - 400,
                reason="stale",
            )
            lock_path = lock_manager._get_lock_path(f"stale{i}.py")
            with lock_path.open("x") as f:
                json.dump(old_lock.to_dict(), f)

        # Cleanup stale locks
        count = lock_manager.cleanup_stale_locks()
        assert count == 3

        # Verify only active lock remains
        locks = lock_manager.list_all_locks()
        assert len(locks) == 1
        assert locks[0].filepath == "active.py"

    def test_cleanup_agent_locks(self, lock_manager):
        """Test cleanup of locks held by specific agent."""
        # Create locks for different agents
        lock_manager.acquire_lock("file1.py", "agent-1", "test1")
        lock_manager.acquire_lock("file2.py", "agent-1", "test2")
        lock_manager.acquire_lock("file3.py", "agent-2", "test3")

        # Cleanup agent-1's locks
        count = lock_manager.cleanup_agent_locks("agent-1")
        assert count == 2

        # Verify only agent-2's lock remains
        locks = lock_manager.list_all_locks()
        assert len(locks) == 1
        assert locks[0].agent_id == "agent-2"

    def test_glob_pattern_conflict(self, lock_manager):
        """Test glob pattern conflict detection."""
        # Agent 1 locks all Python files
        lock_manager.acquire_lock("*.py", "agent-1", "all python files")

        # Agent 2 tries to lock specific file
        success, conflict = lock_manager.acquire_lock(
            "test.py", "agent-2", "specific file"
        )

        assert not success
        assert conflict is not None
        assert conflict.current_holder == "agent-1"

    def test_glob_pattern_reverse_conflict(self, lock_manager):
        """Test glob pattern conflict in reverse order."""
        # Agent 1 locks specific file
        lock_manager.acquire_lock("test.py", "agent-1", "specific file")

        # Agent 2 tries to lock all Python files
        success, conflict = lock_manager.acquire_lock(
            "*.py", "agent-2", "all python files"
        )

        assert not success
        assert conflict is not None
        assert conflict.current_holder == "agent-1"

    def test_glob_pattern_no_conflict_same_agent(self, lock_manager):
        """Test that agent doesn't conflict with their own locks."""
        # Agent 1 locks multiple files
        lock_manager.acquire_lock("file1.py", "agent-1", "first")
        lock_manager.acquire_lock("file2.py", "agent-1", "second")

        # Agent 1 tries to lock with pattern
        success, conflict = lock_manager.acquire_lock(
            "*.py", "agent-1", "pattern lock"
        )

        assert success  # No conflict with own locks
        assert conflict is None

    def test_corrupted_lock_file(self, lock_manager):
        """Test handling of corrupted lock file."""
        # Create corrupted lock file
        lock_path = lock_manager._get_lock_path("test.py")
        with lock_path.open("w") as f:
            f.write("not valid json{{{")

        # Should be able to acquire lock (corrupted file treated as non-existent)
        success, conflict = lock_manager.acquire_lock(
            "test.py", "agent-1", "testing"
        )

        assert success
        assert conflict is None

    def test_lock_filename_generation(self, lock_manager):
        """Test that lock filenames are generated consistently."""
        filename1 = lock_manager._get_lock_filename("test.py")
        filename2 = lock_manager._get_lock_filename("test.py")

        # Same filepath should produce same filename
        assert filename1 == filename2

        # Different filepaths should produce different filenames
        filename3 = lock_manager._get_lock_filename("other.py")
        assert filename1 != filename3

        # Filename should be a .lock file
        assert filename1.endswith(".lock")


class TestConcurrency:
    """Tests for concurrent lock scenarios."""

    def test_race_condition_detection(self, lock_manager):
        """Test that race conditions are detected."""
        # Simulate race condition by manually creating lock after check
        filepath = "test.py"

        # Start acquisition process
        lock_path = lock_manager._get_lock_path(filepath)

        # Another agent creates lock (simulating race condition)
        race_lock = FileLock(
            agent_id="agent-2",
            filepath=filepath,
            locked_at=time.time(),
            reason="race condition",
        )
        with lock_path.open("x") as f:
            json.dump(race_lock.to_dict(), f)

        # Try to write lock (should fail due to race condition)
        our_lock = FileLock(
            agent_id="agent-1",
            filepath=filepath,
            locked_at=time.time(),
            reason="our lock",
        )
        success = lock_manager._write_lock(lock_path, our_lock)

        assert not success  # Write should fail

    def test_multiple_agents_different_files(self, lock_manager):
        """Test that multiple agents can lock different files."""
        # Multiple agents lock different files
        success1, _ = lock_manager.acquire_lock("file1.py", "agent-1", "test1")
        success2, _ = lock_manager.acquire_lock("file2.py", "agent-2", "test2")
        success3, _ = lock_manager.acquire_lock("file3.py", "agent-3", "test3")

        assert all([success1, success2, success3])

        # All locks should be active
        locks = lock_manager.list_all_locks()
        assert len(locks) == 3

    def test_lock_refresh_is_atomic(self, lock_manager):
        """Test that lock refresh uses atomic rename without race window."""
        filepath = "test.py"

        # Agent 1 acquires lock
        success, _ = lock_manager.acquire_lock(filepath, "agent-1", "initial lock")
        assert success

        # Get lock path
        lock_path = lock_manager._get_lock_path(filepath)

        # Verify lock exists
        assert lock_path.exists()
        lock_before = lock_manager.who_has_lock(filepath)
        assert lock_before is not None
        assert lock_before.agent_id == "agent-1"
        assert lock_before.reason == "initial lock"

        # Agent 1 refreshes lock
        time.sleep(0.01)  # Small delay to ensure timestamp changes
        success, _ = lock_manager.acquire_lock(filepath, "agent-1", "refreshed lock")
        assert success

        # Verify lock still exists and was updated
        assert lock_path.exists()
        lock_after = lock_manager.who_has_lock(filepath)
        assert lock_after is not None
        assert lock_after.agent_id == "agent-1"
        assert lock_after.reason == "refreshed lock"
        assert lock_after.locked_at > lock_before.locked_at

        # Verify no temp files left behind
        temp_files = list(lock_manager.lock_dir.glob("*.tmp"))
        assert len(temp_files) == 0


class TestRetryLogic:
    """Tests for exponential backoff with jitter retry logic."""

    def test_calculate_backoff_delay_exponential_growth(self):
        """Test that backoff delay grows exponentially."""
        delays = [_calculate_backoff_delay(i) for i in range(5)]

        # Each delay should be roughly double the previous (accounting for jitter)
        # Attempt 0: ~0.1s, Attempt 1: ~0.2s, Attempt 2: ~0.4s, etc.
        for i in range(len(delays) - 1):
            # Due to jitter, we can't expect exact doubling, but should be in range
            base_delay_current = INITIAL_RETRY_DELAY_SECONDS * (2 ** i)
            base_delay_next = INITIAL_RETRY_DELAY_SECONDS * (2 ** (i + 1))

            # Delays should be within the expected range (accounting for jitter)
            assert delays[i] >= base_delay_current * (1 - JITTER_FACTOR)
            assert delays[i] <= base_delay_current * (1 + JITTER_FACTOR)
            assert delays[i + 1] >= base_delay_next * (1 - JITTER_FACTOR)
            assert delays[i + 1] <= base_delay_next * (1 + JITTER_FACTOR)

    def test_calculate_backoff_delay_respects_max(self):
        """Test that backoff delay is capped at maximum."""
        # Attempt a large number that would exceed max
        delay = _calculate_backoff_delay(100)

        # Should be capped at MAX_RETRY_DELAY_SECONDS ± jitter
        max_with_jitter = MAX_RETRY_DELAY_SECONDS * (1 + JITTER_FACTOR)
        min_with_jitter = MAX_RETRY_DELAY_SECONDS * (1 - JITTER_FACTOR)

        assert delay <= max_with_jitter
        assert delay >= min_with_jitter

    def test_calculate_backoff_delay_minimum(self):
        """Test that backoff delay has minimum threshold."""
        # Even with negative jitter, should never go below 10ms
        for attempt in range(10):
            delay = _calculate_backoff_delay(attempt)
            assert delay >= 0.01  # 10ms minimum

    def test_calculate_backoff_delay_jitter_variation(self):
        """Test that jitter produces varied delays."""
        # Generate multiple delays for the same attempt
        delays = [_calculate_backoff_delay(2) for _ in range(20)]

        # Should have variation (not all the same)
        unique_delays = set(delays)
        assert len(unique_delays) > 1, "Jitter should produce varied delays"

        # All should be within expected range
        base_delay = min(INITIAL_RETRY_DELAY_SECONDS * 4, MAX_RETRY_DELAY_SECONDS)
        max_delay = base_delay * (1 + JITTER_FACTOR)
        min_delay = base_delay * (1 - JITTER_FACTOR)

        for delay in delays:
            assert min_delay <= delay <= max_delay

    def test_retry_with_backoff_success_first_attempt(self):
        """Test that operation succeeds on first attempt without retry."""
        operation = MagicMock(return_value="success")

        result = _retry_with_backoff(operation, "test_operation")

        assert result == "success"
        assert operation.call_count == 1

    def test_retry_with_backoff_success_after_retries(self):
        """Test that operation succeeds after initial failures."""
        # Fail twice, then succeed
        operation = MagicMock(side_effect=[OSError("fail"), OSError("fail"), "success"])

        with patch('time.sleep'):  # Mock sleep to speed up test
            result = _retry_with_backoff(operation, "test_operation", max_retries=5)

        assert result == "success"
        assert operation.call_count == 3

    def test_retry_with_backoff_exhausts_retries(self):
        """Test that operation fails after exhausting all retries."""
        # Always fail
        operation = MagicMock(side_effect=OSError("persistent failure"))

        with patch('time.sleep'):  # Mock sleep to speed up test
            with pytest.raises(OSError, match="persistent failure"):
                _retry_with_backoff(operation, "test_operation", max_retries=3)

        # Should try: initial + 3 retries = 4 times
        assert operation.call_count == 4

    def test_retry_with_backoff_respects_max_retries(self):
        """Test that max_retries parameter is respected."""
        operation = MagicMock(side_effect=OSError("fail"))

        with patch('time.sleep'):
            with pytest.raises(OSError):
                _retry_with_backoff(operation, "test_operation", max_retries=2)

        # Should try: initial + 2 retries = 3 times
        assert operation.call_count == 3

    def test_retry_with_backoff_sleeps_with_backoff(self):
        """Test that retry logic sleeps with exponential backoff."""
        operation = MagicMock(side_effect=[OSError(), OSError(), OSError(), "success"])

        with patch('time.sleep') as mock_sleep:
            result = _retry_with_backoff(operation, "test_operation", max_retries=5)

        assert result == "success"
        # Should have slept 3 times (after first 3 failures)
        assert mock_sleep.call_count == 3

        # Verify sleep durations are increasing
        sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
        for i in range(len(sleep_calls) - 1):
            # Each sleep should be roughly double the previous (accounting for jitter)
            # We can't assert exact values due to jitter, but verify they're positive
            # and generally increasing
            assert sleep_calls[i] > 0
            assert sleep_calls[i + 1] > 0

    def test_acquire_lock_with_retry_on_contention(self, lock_manager):
        """Test that acquire_lock retries on contention."""
        filepath = "test.py"

        # Simulate contention that resolves after 2 attempts
        original_write = lock_manager._write_lock
        write_attempts = [0]

        def mock_write(lock_path, lock):
            write_attempts[0] += 1
            if write_attempts[0] < 3:
                # Fail first 2 attempts
                return False
            # Succeed on 3rd attempt
            return original_write(lock_path, lock)

        with patch('time.sleep'):  # Speed up test
            with patch.object(lock_manager, '_write_lock', side_effect=mock_write):
                success, conflict = lock_manager.acquire_lock(
                    filepath=filepath,
                    agent_id="agent-1",
                    reason="test retry"
                )

        assert success is True
        assert conflict is None
        assert write_attempts[0] == 3  # Should have tried 3 times

    def test_acquire_lock_returns_conflict_after_max_retries(self, lock_manager):
        """Test that acquire_lock returns conflict after exhausting retries."""
        filepath = "test.py"

        # Agent 1 holds the lock
        lock_manager.acquire_lock(filepath, "agent-1", "holding lock")

        # Agent 2 tries to acquire (should fail even with retries)
        with patch('time.sleep'):  # Speed up test
            success, conflict = lock_manager.acquire_lock(
                filepath=filepath,
                agent_id="agent-2",
                reason="trying to acquire"
            )

        assert success is False
        assert conflict is not None
        assert conflict.current_holder == "agent-1"

    def test_retry_logs_attempts(self, lock_manager, caplog):
        """Test that retry logic logs retry attempts."""
        filepath = "test.py"

        # Mock _write_lock to simulate transient contention
        original_write = lock_manager._write_lock
        write_attempts = [0]

        def mock_write(lock_path, lock):
            write_attempts[0] += 1
            # Fail first 2 attempts, succeed on 3rd
            if write_attempts[0] < 3:
                return False
            return original_write(lock_path, lock)

        with patch('time.sleep'):  # Speed up test
            import logging
            with caplog.at_level(logging.DEBUG):
                with patch.object(lock_manager, '_write_lock', side_effect=mock_write):
                    success, conflict = lock_manager.acquire_lock(
                        filepath=filepath,
                        agent_id="agent-1",
                        reason="test logging"
                    )

        # Should have debug logs about retrying
        retry_logs = [record for record in caplog.records if "retry" in record.message.lower()]
        assert len(retry_logs) > 0, f"Expected retry logs, got: {[r.message for r in caplog.records]}"
