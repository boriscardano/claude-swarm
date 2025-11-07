"""Integration test: Stale Lock Recovery (Scenario 4).

Tests stale lock detection and automatic recovery:
1. Agent 7 acquires lock on a file
2. Agent 7 crashes (simulated)
3. Wait for stale timeout period (or mock time)
4. Agent 3 tries to acquire same lock
5. System detects stale lock and auto-releases it
6. Agent 3 successfully acquires the lock
7. Verify: stale detection, auto-cleanup, successful acquisition
"""

import time

import pytest

from claudeswarm.locking import STALE_LOCK_TIMEOUT

from .helpers import IntegrationTestContext, wait_for_lock_release


class TestStaleLockRecovery:
    """Integration test suite for stale lock recovery scenarios."""

    def test_stale_lock_automatic_recovery(self) -> None:
        """Test that stale locks are automatically cleaned up.

        Scenario:
        1. Agent 7 (index 7 in our mock) acquires lock
        2. Simulate agent crash
        3. Advance time past stale threshold
        4. Agent 3 attempts to acquire same lock
        5. System auto-releases stale lock
        6. Agent 3 successfully acquires
        """
        with IntegrationTestContext(num_agents=8) as ctx:
            test_file = "src/critical_file.py"
            ctx.create_test_file(test_file, content="# Critical file")

            # Step 1: Agent 7 acquires lock
            success, conflict = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-7",
                reason="Working on critical feature"
            )
            assert success is True
            assert ctx.verify_lock_held(test_file, "agent-7")

            # Verify lock is active
            lock = ctx.lock_manager.who_has_lock(test_file)
            assert lock is not None
            assert lock.agent_id == "agent-7"
            assert not lock.is_stale()

            # Step 2: Simulate agent 7 crash
            ctx.simulate_agent_crash("agent-7")

            # Step 3: Advance time past stale threshold
            # Use our helper to simulate time passing
            ctx.advance_time(STALE_LOCK_TIMEOUT + 10)

            # Step 4 & 5: Agent 3 attempts to acquire lock
            # The lock manager should detect the stale lock and auto-release it
            success, conflict = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-3",
                reason="Taking over critical feature"
            )

            # Step 6: Verify agent 3 successfully acquired the lock
            assert success is True
            assert conflict is None
            assert ctx.verify_lock_held(test_file, "agent-3")

            # Verify the lock is now held by agent 3
            lock = ctx.lock_manager.who_has_lock(test_file)
            assert lock is not None
            assert lock.agent_id == "agent-3"

    def test_stale_lock_cleanup_batch(self) -> None:
        """Test that cleanup_stale_locks removes all stale locks."""
        with IntegrationTestContext(num_agents=5) as ctx:
            # Create multiple files and locks
            files = [
                "src/file1.py",
                "src/file2.py",
                "src/file3.py",
            ]

            for i, file in enumerate(files):
                ctx.create_test_file(file)
                ctx.lock_manager.acquire_lock(
                    filepath=file,
                    agent_id=f"agent-{i}",
                    reason=f"Working on {file}"
                )

            # Verify all locks are active
            all_locks = ctx.lock_manager.list_all_locks()
            assert len(all_locks) == 3

            # Simulate time passing
            ctx.advance_time(STALE_LOCK_TIMEOUT + 10)

            # Run cleanup
            cleanup_count = ctx.lock_manager.cleanup_stale_locks()

            # Verify all stale locks were cleaned up
            assert cleanup_count == 3

            # Verify no locks remain
            all_locks = ctx.lock_manager.list_all_locks()
            assert len(all_locks) == 0

    def test_non_stale_locks_not_affected(self) -> None:
        """Test that non-stale locks are not affected by cleanup."""
        with IntegrationTestContext(num_agents=3) as ctx:
            old_file = "src/old_file.py"
            new_file = "src/new_file.py"

            ctx.create_test_file(old_file)
            ctx.create_test_file(new_file)

            # Agent 0 acquires old lock
            ctx.lock_manager.acquire_lock(
                filepath=old_file,
                agent_id="agent-0",
                reason="Old work"
            )

            # Simulate time passing to make it stale
            ctx.advance_time(STALE_LOCK_TIMEOUT + 10)

            # Agent 1 acquires new lock (should be fresh)
            ctx.lock_manager.acquire_lock(
                filepath=new_file,
                agent_id="agent-1",
                reason="New work"
            )

            # Run cleanup
            cleanup_count = ctx.lock_manager.cleanup_stale_locks()

            # Only the old lock should be cleaned up
            assert cleanup_count == 1

            # Verify new lock still exists
            assert ctx.verify_lock_held(new_file, "agent-1")
            assert ctx.verify_no_lock(old_file)

    def test_lock_refresh_prevents_staleness(self) -> None:
        """Test that re-acquiring a lock refreshes its timestamp."""
        with IntegrationTestContext(num_agents=2) as ctx:
            test_file = "src/long_running.py"
            ctx.create_test_file(test_file)

            # Agent 0 acquires lock
            success, _ = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-0",
                reason="Long running task"
            )
            assert success is True

            # Simulate some time passing (but not enough to be stale)
            ctx.advance_time(STALE_LOCK_TIMEOUT // 2)

            # Agent 0 re-acquires (refreshes) the lock
            success, _ = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-0",
                reason="Still working on long running task"
            )
            assert success is True  # Should succeed as it's our own lock

            # Simulate more time passing
            ctx.advance_time(STALE_LOCK_TIMEOUT // 2 + 10)

            # Lock should still be active because it was refreshed
            lock = ctx.lock_manager.who_has_lock(test_file)
            assert lock is not None
            assert lock.agent_id == "agent-0"

    def test_who_has_lock_cleans_stale(self) -> None:
        """Test that who_has_lock automatically cleans stale locks."""
        with IntegrationTestContext(num_agents=2) as ctx:
            test_file = "src/test.py"
            ctx.create_test_file(test_file)

            # Agent 0 acquires lock
            ctx.lock_manager.acquire_lock(test_file, "agent-0", "Test")

            # Verify lock is held
            lock = ctx.lock_manager.who_has_lock(test_file)
            assert lock is not None
            assert lock.agent_id == "agent-0"

            # Make lock stale
            ctx.advance_time(STALE_LOCK_TIMEOUT + 10)

            # who_has_lock should return None and clean up
            lock = ctx.lock_manager.who_has_lock(test_file)
            assert lock is None

            # Lock should be gone
            assert ctx.verify_no_lock(test_file)

    def test_multiple_agents_racing_for_stale_lock(self) -> None:
        """Test race condition when multiple agents try to acquire stale lock."""
        with IntegrationTestContext(num_agents=4) as ctx:
            test_file = "src/contested.py"
            ctx.create_test_file(test_file)

            # Agent 0 acquires lock
            ctx.lock_manager.acquire_lock(test_file, "agent-0", "Initial work")

            # Make it stale
            ctx.advance_time(STALE_LOCK_TIMEOUT + 10)

            # Agent 1 and Agent 2 both try to acquire
            # Only one should succeed

            success1, conflict1 = ctx.lock_manager.acquire_lock(
                test_file, "agent-1", "Agent 1 work"
            )

            success2, conflict2 = ctx.lock_manager.acquire_lock(
                test_file, "agent-2", "Agent 2 work"
            )

            # Exactly one should succeed
            assert success1 != success2

            if success1:
                assert ctx.verify_lock_held(test_file, "agent-1")
                assert not success2
                assert conflict2 is not None
            else:
                assert ctx.verify_lock_held(test_file, "agent-2")
                assert not success1
                assert conflict1 is not None

    def test_agent_specific_lock_cleanup(self) -> None:
        """Test cleanup of all locks for a specific agent."""
        with IntegrationTestContext(num_agents=3) as ctx:
            # Agent 0 acquires multiple locks
            files = ["src/file1.py", "src/file2.py", "src/file3.py"]
            for file in files:
                ctx.create_test_file(file)
                ctx.lock_manager.acquire_lock(file, "agent-0", "Multi-file work")

            # Agent 1 acquires one lock
            agent1_file = "src/agent1_file.py"
            ctx.create_test_file(agent1_file)
            ctx.lock_manager.acquire_lock(agent1_file, "agent-1", "Agent 1 work")

            # Verify all locks exist
            all_locks = ctx.lock_manager.list_all_locks()
            assert len(all_locks) == 4

            # Clean up agent 0's locks
            cleanup_count = ctx.lock_manager.cleanup_agent_locks("agent-0")
            assert cleanup_count == 3

            # Verify only agent 1's lock remains
            all_locks = ctx.lock_manager.list_all_locks()
            assert len(all_locks) == 1
            assert all_locks[0].agent_id == "agent-1"

    def test_lock_age_reporting(self) -> None:
        """Test that lock age is correctly reported."""
        with IntegrationTestContext(num_agents=1) as ctx:
            test_file = "src/test.py"
            ctx.create_test_file(test_file)

            # Acquire lock
            ctx.lock_manager.acquire_lock(test_file, "agent-0", "Test")

            # Get lock and check age
            lock = ctx.lock_manager.who_has_lock(test_file)
            assert lock is not None

            initial_age = lock.age_seconds()
            assert initial_age >= 0
            assert initial_age < 1  # Should be very recent

            # Advance time
            ctx.advance_time(100)

            # Check age again
            lock = ctx.lock_manager.who_has_lock(test_file)
            assert lock is not None
            age = lock.age_seconds()
            assert age >= 100

    def test_stale_threshold_parameter(self) -> None:
        """Test that custom stale threshold is respected."""
        with IntegrationTestContext(num_agents=2) as ctx:
            test_file = "src/test.py"
            ctx.create_test_file(test_file)

            # Acquire lock
            ctx.lock_manager.acquire_lock(test_file, "agent-0", "Test")

            # Advance time but not past default threshold
            custom_threshold = 60  # 1 minute
            ctx.advance_time(custom_threshold + 10)

            # Try to acquire with custom shorter threshold
            success, _ = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-1",
                reason="Test with custom threshold",
                timeout=custom_threshold
            )

            # Should succeed because lock is stale under custom threshold
            assert success is True
            assert ctx.verify_lock_held(test_file, "agent-1")
