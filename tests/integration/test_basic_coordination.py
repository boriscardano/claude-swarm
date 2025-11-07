"""Integration test: Basic Coordination (Scenario 1).

Tests a complete coordination workflow with 3 agents:
1. Agent 0 discovers other agents
2. Agent 0 broadcasts a task assignment
3. Agents acknowledge the broadcast
4. Agent 1 acquires lock, performs work, releases
5. Agent 2 acquires lock, performs review
6. Verify: messages delivered, no conflicts, monitoring shows activity
"""

import pytest

from claudeswarm.discovery import list_active_agents, refresh_registry
from claudeswarm.messaging import MessageType, broadcast_message, send_message

from .helpers import (
    IntegrationTestContext,
    assert_lock_state,
    mock_tmux_environment,
    verify_message_broadcast,
    verify_message_delivered,
    wait_for_lock_release,
)


class TestBasicCoordination:
    """Integration test suite for basic coordination scenarios."""

    def test_three_agent_coordination_workflow(self) -> None:
        """Test complete coordination workflow with 3 agents.

        Scenario:
        1. Agent 0 discovers agents 1 and 2
        2. Agent 0 broadcasts task assignment
        3. Agents 1 and 2 acknowledge
        4. Agent 1 acquires lock on target file
        5. Agent 1 does work (simulated)
        6. Agent 1 releases lock
        7. Agent 2 acquires lock for review
        8. Agent 2 does review (simulated)
        9. Agent 2 releases lock
        """
        with IntegrationTestContext(num_agents=3) as ctx:
            with mock_tmux_environment() as tmux_state:
                # Add panes to mock state
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Step 1: Agent 0 discovers other agents
                registry = refresh_registry()
                active_agents = list_active_agents()

                assert len(active_agents) == 3
                assert any(a.id == "agent-0" for a in active_agents)
                assert any(a.id == "agent-1" for a in active_agents)
                assert any(a.id == "agent-2" for a in active_agents)

                # Step 2: Agent 0 broadcasts task assignment
                task_content = "Please implement user authentication feature"
                broadcast_result = broadcast_message(
                    sender_id="agent-0",
                    message_type=MessageType.INFO,
                    content=task_content,
                    exclude_self=True
                )

                # Verify broadcast succeeded
                assert len(broadcast_result) == 2
                assert broadcast_result.get("agent-1") is True
                assert broadcast_result.get("agent-2") is True

                # Verify messages were delivered to both agents
                assert verify_message_broadcast(
                    tmux_state["messages_sent"],
                    sender_id="agent-0",
                    expected_recipients=[
                        ctx.get_agent("agent-1").pane_index,
                        ctx.get_agent("agent-2").pane_index,
                    ],
                    msg_type=MessageType.INFO
                )

                # Step 3: Agents acknowledge
                agent1_ack = send_message(
                    sender_id="agent-1",
                    recipient_id="agent-0",
                    message_type=MessageType.ACK,
                    content="Acknowledged - starting authentication implementation"
                )
                assert agent1_ack is not None

                agent2_ack = send_message(
                    sender_id="agent-2",
                    recipient_id="agent-0",
                    message_type=MessageType.ACK,
                    content="Acknowledged - will review when ready"
                )
                assert agent2_ack is not None

                # Verify ACK messages delivered
                assert verify_message_delivered(
                    tmux_state["messages_sent"],
                    sender_id="agent-1",
                    recipient_pane=ctx.get_agent("agent-0").pane_index,
                    msg_type=MessageType.ACK
                )

                # Step 4: Agent 1 acquires lock on auth file
                test_file = "src/auth/authentication.py"
                ctx.create_test_file(test_file, content="# Auth module")

                success, conflict = ctx.lock_manager.acquire_lock(
                    filepath=test_file,
                    agent_id="agent-1",
                    reason="Implementing user authentication"
                )

                assert success is True
                assert conflict is None
                assert ctx.verify_lock_held(test_file, "agent-1")

                # Step 5: Agent 1 does work (simulated by updating file)
                file_path = ctx.temp_dir / test_file
                file_path.write_text("# Auth module\n\ndef authenticate_user(username, password):\n    pass")

                # Step 6: Agent 1 releases lock
                release_success = ctx.lock_manager.release_lock(test_file, "agent-1")
                assert release_success is True
                assert ctx.verify_no_lock(test_file)

                # Step 7: Agent 2 acquires lock for review
                success, conflict = ctx.lock_manager.acquire_lock(
                    filepath=test_file,
                    agent_id="agent-2",
                    reason="Reviewing authentication implementation"
                )

                assert success is True
                assert conflict is None
                assert ctx.verify_lock_held(test_file, "agent-2")

                # Step 8: Agent 2 does review (send review feedback)
                review_msg = send_message(
                    sender_id="agent-2",
                    recipient_id="agent-1",
                    message_type=MessageType.REVIEW_REQUEST,
                    content="LGTM - authentication looks good!"
                )
                assert review_msg is not None

                # Step 9: Agent 2 releases lock
                release_success = ctx.lock_manager.release_lock(test_file, "agent-2")
                assert release_success is True
                assert ctx.verify_no_lock(test_file)

                # Final verification: check no locks remain
                all_locks = ctx.lock_manager.list_all_locks()
                assert len(all_locks) == 0

    def test_discovery_with_active_and_stale_agents(self) -> None:
        """Test agent discovery correctly identifies active vs stale agents."""
        with IntegrationTestContext(num_agents=3) as ctx:
            # Initially all agents are active
            active = list_active_agents()
            assert len(active) == 3

            # Simulate agent-2 crashing
            ctx.simulate_agent_crash("agent-2")

            # Refresh and check
            refresh_registry()
            active = list_active_agents()

            # Only agents 0 and 1 should be active now
            assert len(active) == 2
            active_ids = {a.id for a in active}
            assert "agent-0" in active_ids
            assert "agent-1" in active_ids
            assert "agent-2" not in active_ids

    def test_broadcast_excludes_sender(self) -> None:
        """Test that broadcast with exclude_self doesn't send to sender."""
        with IntegrationTestContext(num_agents=3) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Agent 1 broadcasts with exclude_self=True
                broadcast_result = broadcast_message(
                    sender_id="agent-1",
                    message_type=MessageType.INFO,
                    content="Testing broadcast exclusion",
                    exclude_self=True
                )

                # Should only send to agent-0 and agent-2
                assert len(broadcast_result) == 2
                assert "agent-0" in broadcast_result
                assert "agent-2" in broadcast_result
                assert "agent-1" not in broadcast_result

    def test_lock_prevents_concurrent_access(self) -> None:
        """Test that locks prevent concurrent file access."""
        with IntegrationTestContext(num_agents=2) as ctx:
            test_file = "src/shared_file.py"
            ctx.create_test_file(test_file)

            # Agent 0 acquires lock
            success, conflict = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-0",
                reason="First edit"
            )
            assert success is True

            # Agent 1 tries to acquire lock - should fail
            success, conflict = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-1",
                reason="Conflicting edit"
            )
            assert success is False
            assert conflict is not None
            assert conflict.current_holder == "agent-0"
            assert conflict.reason == "First edit"

            # Agent 0 releases lock
            ctx.lock_manager.release_lock(test_file, "agent-0")

            # Now agent 1 can acquire
            success, conflict = ctx.lock_manager.acquire_lock(
                filepath=test_file,
                agent_id="agent-1",
                reason="Second edit"
            )
            assert success is True
            assert conflict is None

    def test_glob_pattern_locking(self) -> None:
        """Test that glob pattern locks prevent conflicts."""
        with IntegrationTestContext(num_agents=2) as ctx:
            # Create multiple files
            ctx.create_test_file("src/auth/login.py")
            ctx.create_test_file("src/auth/logout.py")
            ctx.create_test_file("src/auth/session.py")

            # Agent 0 locks all auth files with glob
            success, conflict = ctx.lock_manager.acquire_lock(
                filepath="src/auth/*.py",
                agent_id="agent-0",
                reason="Refactoring auth module"
            )
            assert success is True

            # Agent 1 tries to lock specific file - should fail
            success, conflict = ctx.lock_manager.acquire_lock(
                filepath="src/auth/login.py",
                agent_id="agent-1",
                reason="Updating login"
            )
            assert success is False
            assert conflict is not None
            assert conflict.current_holder == "agent-0"

    def test_message_rate_limiting(self) -> None:
        """Test that message rate limiting works correctly."""
        with IntegrationTestContext(num_agents=2) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Send 10 messages (should work)
                for i in range(10):
                    msg = send_message(
                        sender_id="agent-0",
                        recipient_id="agent-1",
                        message_type=MessageType.INFO,
                        content=f"Message {i}"
                    )
                    assert msg is not None

                # 11th message should be rate limited
                msg = send_message(
                    sender_id="agent-0",
                    recipient_id="agent-1",
                    message_type=MessageType.INFO,
                    content="Message 11 - should be blocked"
                )
                assert msg is None

    def test_monitoring_state_reflects_activity(self) -> None:
        """Test that monitoring can track agent activity."""
        with IntegrationTestContext(num_agents=3) as ctx:
            # Create some activity
            test_file1 = "src/file1.py"
            test_file2 = "src/file2.py"

            ctx.create_test_file(test_file1)
            ctx.create_test_file(test_file2)

            # Agent 0 locks file1
            ctx.lock_manager.acquire_lock(test_file1, "agent-0", "Working on file1")

            # Agent 1 locks file2
            ctx.lock_manager.acquire_lock(test_file2, "agent-1", "Working on file2")

            # Check lock state
            all_locks = ctx.lock_manager.list_all_locks()
            assert len(all_locks) == 2

            lock_holders = {lock.filepath: lock.agent_id for lock in all_locks}
            assert lock_holders[test_file1] == "agent-0"
            assert lock_holders[test_file2] == "agent-1"

            # Verify active agents
            active = list_active_agents()
            assert len(active) == 3
