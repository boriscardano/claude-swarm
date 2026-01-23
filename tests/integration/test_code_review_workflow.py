"""Integration test: Code Review Workflow (Scenario 2).

Tests a complete code review workflow:
1. Agent 3 requests review from Agent 1
2. Agent 1 acknowledges review request
3. Agent 1 acquires lock on files to review
4. Agent 1 reviews code and provides feedback
5. Agent 3 addresses feedback
6. Agent 1 approves changes
7. Verify: proper ACKs, lock transitions, coordination updated
"""

from claudeswarm.messaging import MessageType, send_message

from .helpers import (
    IntegrationTestContext,
    mock_tmux_environment,
    verify_message_delivered,
)


class TestCodeReviewWorkflow:
    """Integration test suite for code review workflow scenarios."""

    def test_complete_review_workflow(self) -> None:
        """Test complete code review workflow from request to approval.

        Scenario:
        1. Agent 3 creates changes and requests review
        2. Agent 3 sends review request to Agent 1
        3. Agent 1 acknowledges the review request
        4. Agent 1 acquires lock on files under review
        5. Agent 1 reviews code and sends feedback
        6. Agent 3 addresses feedback and updates code
        7. Agent 1 re-reviews and approves
        8. Verify lock transitions and message flow
        """
        with IntegrationTestContext(num_agents=4) as ctx:
            with mock_tmux_environment() as tmux_state:
                # Add panes to mock state
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Step 1: Agent 3 creates changes
                feature_file = "src/features/new_feature.py"
                ctx.create_test_file(
                    feature_file, content="def new_feature():\n    # TODO: implement\n    pass"
                )

                # Agent 3 acquires lock to make changes
                success, _ = ctx.lock_manager.acquire_lock(
                    filepath=feature_file, agent_id="agent-3", reason="Implementing new feature"
                )
                assert success is True

                # Agent 3 makes changes
                file_path = ctx.temp_dir / feature_file
                file_path.write_text(
                    "def new_feature():\n"
                    '    """New feature implementation."""\n'
                    "    return 'feature complete'\n"
                )

                # Agent 3 releases lock
                ctx.lock_manager.release_lock(feature_file, "agent-3")

                # Step 2: Agent 3 requests review from Agent 1
                review_request = send_message(
                    sender_id="agent-3",
                    recipient_id="agent-1",
                    message_type=MessageType.REVIEW_REQUEST,
                    content=f"Please review {feature_file} - new feature implementation",
                )
                assert review_request is not None

                # Verify message delivered
                assert verify_message_delivered(
                    tmux_state["messages_sent"],
                    sender_id="agent-3",
                    recipient_pane=ctx.get_agent("agent-1").pane_index,
                    msg_type=MessageType.REVIEW_REQUEST,
                    content_substring=feature_file,
                )

                # Step 3: Agent 1 acknowledges review request
                ack_msg = send_message(
                    sender_id="agent-1",
                    recipient_id="agent-3",
                    message_type=MessageType.ACK,
                    content="Starting review of new feature",
                )
                assert ack_msg is not None

                # Step 4: Agent 1 acquires lock for review
                success, conflict = ctx.lock_manager.acquire_lock(
                    filepath=feature_file, agent_id="agent-1", reason="Code review in progress"
                )
                assert success is True
                assert ctx.verify_lock_held(feature_file, "agent-1")

                # Step 5: Agent 1 reviews and sends feedback
                feedback_msg = send_message(
                    sender_id="agent-1",
                    recipient_id="agent-3",
                    message_type=MessageType.REVIEW_REQUEST,
                    content=(
                        "Review feedback:\n"
                        "- Add docstring parameter descriptions\n"
                        "- Add type hints\n"
                        "- Add unit tests"
                    ),
                )
                assert feedback_msg is not None

                # Agent 1 releases lock after initial review
                ctx.lock_manager.release_lock(feature_file, "agent-1")
                assert ctx.verify_no_lock(feature_file)

                # Step 6: Agent 3 addresses feedback
                success, _ = ctx.lock_manager.acquire_lock(
                    filepath=feature_file, agent_id="agent-3", reason="Addressing review feedback"
                )
                assert success is True

                # Agent 3 updates code
                file_path.write_text(
                    "def new_feature() -> str:\n"
                    '    """New feature implementation.\n\n'
                    "    Returns:\n"
                    "        str: Feature completion message\n"
                    '    """\n'
                    "    return 'feature complete'\n"
                )

                # Agent 3 releases lock and notifies
                ctx.lock_manager.release_lock(feature_file, "agent-3")

                update_msg = send_message(
                    sender_id="agent-3",
                    recipient_id="agent-1",
                    message_type=MessageType.INFO,
                    content="Addressed all review feedback - ready for re-review",
                )
                assert update_msg is not None

                # Step 7: Agent 1 re-reviews and approves
                success, _ = ctx.lock_manager.acquire_lock(
                    filepath=feature_file, agent_id="agent-1", reason="Final review"
                )
                assert success is True

                approval_msg = send_message(
                    sender_id="agent-1",
                    recipient_id="agent-3",
                    message_type=MessageType.COMPLETED,
                    content=f"APPROVED: {feature_file} looks great! Ready to merge.",
                )
                assert approval_msg is not None

                ctx.lock_manager.release_lock(feature_file, "agent-1")

                # Verify final state
                assert ctx.verify_no_lock(feature_file)
                assert len(tmux_state["messages_sent"]) >= 6  # At least 6 messages exchanged

    def test_review_with_multiple_files(self) -> None:
        """Test code review workflow with multiple files."""
        with IntegrationTestContext(num_agents=3) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Create multiple files
                files = [
                    "src/feature/main.py",
                    "src/feature/helpers.py",
                    "src/feature/constants.py",
                ]

                for file in files:
                    ctx.create_test_file(file, content=f"# {file}")

                # Agent 2 requests review of all files using glob pattern
                pattern = "src/feature/*.py"

                review_request = send_message(
                    sender_id="agent-2",
                    recipient_id="agent-1",
                    message_type=MessageType.REVIEW_REQUEST,
                    content=f"Please review {pattern} - new feature module",
                )
                assert review_request is not None

                # Agent 1 locks all files at once with glob
                success, conflict = ctx.lock_manager.acquire_lock(
                    filepath=pattern, agent_id="agent-1", reason="Reviewing feature module"
                )
                assert success is True

                # Verify agent 2 cannot modify any file while review is in progress
                for file in files:
                    success, conflict = ctx.lock_manager.acquire_lock(
                        filepath=file, agent_id="agent-2", reason="Trying to modify during review"
                    )
                    assert success is False
                    assert conflict is not None

                # Agent 1 completes review and releases
                ctx.lock_manager.release_lock(pattern, "agent-1")

                # Now agent 2 can modify
                success, _ = ctx.lock_manager.acquire_lock(
                    filepath=files[0], agent_id="agent-2", reason="Addressing feedback"
                )
                assert success is True

    def test_review_request_to_unavailable_agent(self) -> None:
        """Test review request when target agent becomes unavailable."""
        with IntegrationTestContext(num_agents=3) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                test_file = "src/review_needed.py"
                ctx.create_test_file(test_file)

                # Agent 0 requests review from Agent 1
                review_request = send_message(
                    sender_id="agent-0",
                    recipient_id="agent-1",
                    message_type=MessageType.REVIEW_REQUEST,
                    content=f"Please review {test_file}",
                )
                assert review_request is not None

                # Simulate Agent 1 crash
                ctx.simulate_agent_crash("agent-1")

                # Agent 0 realizes Agent 1 is unavailable, re-requests from Agent 2
                fallback_request = send_message(
                    sender_id="agent-0",
                    recipient_id="agent-2",
                    message_type=MessageType.REVIEW_REQUEST,
                    content=f"Please review {test_file} (Agent 1 unavailable)",
                )
                assert fallback_request is not None

                # Verify both messages were sent
                assert verify_message_delivered(
                    tmux_state["messages_sent"],
                    sender_id="agent-0",
                    recipient_pane=ctx.get_agent("agent-2").pane_index,
                    msg_type=MessageType.REVIEW_REQUEST,
                )

    def test_concurrent_review_requests(self) -> None:
        """Test handling of concurrent review requests from multiple agents."""
        with IntegrationTestContext(num_agents=4) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Agent 1 and Agent 2 both request reviews from Agent 3
                file1 = "src/module_a.py"
                file2 = "src/module_b.py"

                ctx.create_test_file(file1)
                ctx.create_test_file(file2)

                # Agent 1 requests review
                request1 = send_message(
                    sender_id="agent-1",
                    recipient_id="agent-3",
                    message_type=MessageType.REVIEW_REQUEST,
                    content=f"Please review {file1}",
                )
                assert request1 is not None

                # Agent 2 requests review
                request2 = send_message(
                    sender_id="agent-2",
                    recipient_id="agent-3",
                    message_type=MessageType.REVIEW_REQUEST,
                    content=f"Please review {file2}",
                )
                assert request2 is not None

                # Agent 3 handles them sequentially

                # First handles Agent 1's request
                ctx.lock_manager.acquire_lock(file1, "agent-3", "Reviewing module A")
                send_message(
                    sender_id="agent-3",
                    recipient_id="agent-1",
                    message_type=MessageType.COMPLETED,
                    content=f"Reviewed {file1} - LGTM",
                )
                ctx.lock_manager.release_lock(file1, "agent-3")

                # Then handles Agent 2's request
                ctx.lock_manager.acquire_lock(file2, "agent-3", "Reviewing module B")
                send_message(
                    sender_id="agent-3",
                    recipient_id="agent-2",
                    message_type=MessageType.COMPLETED,
                    content=f"Reviewed {file2} - LGTM",
                )
                ctx.lock_manager.release_lock(file2, "agent-3")

                # Verify all messages delivered
                assert len(tmux_state["messages_sent"]) >= 4

    def test_review_rejection_and_iteration(self) -> None:
        """Test review rejection leading to multiple iteration cycles."""
        with IntegrationTestContext(num_agents=2) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                test_file = "src/needs_work.py"
                ctx.create_test_file(test_file, content="# Bad code")

                iteration_count = 0
                max_iterations = 3

                # Simulate multiple review iterations
                for _i in range(max_iterations):
                    iteration_count += 1

                    # Agent 0 requests review
                    send_message(
                        sender_id="agent-0",
                        recipient_id="agent-1",
                        message_type=MessageType.REVIEW_REQUEST,
                        content=f"Review iteration {iteration_count}",
                    )

                    # Agent 1 reviews
                    ctx.lock_manager.acquire_lock(test_file, "agent-1", "Reviewing")

                    if iteration_count < max_iterations:
                        # Send feedback for improvement
                        send_message(
                            sender_id="agent-1",
                            recipient_id="agent-0",
                            message_type=MessageType.REVIEW_REQUEST,
                            content=f"Needs more work - iteration {iteration_count}",
                        )
                        ctx.lock_manager.release_lock(test_file, "agent-1")

                        # Agent 0 makes improvements
                        ctx.lock_manager.acquire_lock(test_file, "agent-0", "Improving")
                        file_path = ctx.temp_dir / test_file
                        file_path.write_text(f"# Improved code v{iteration_count + 1}")
                        ctx.lock_manager.release_lock(test_file, "agent-0")
                    else:
                        # Final approval
                        send_message(
                            sender_id="agent-1",
                            recipient_id="agent-0",
                            message_type=MessageType.COMPLETED,
                            content="APPROVED after multiple iterations",
                        )
                        ctx.lock_manager.release_lock(test_file, "agent-1")

                # Verify we had the expected number of message exchanges
                # Each iteration: request + feedback (except last has approval instead)
                expected_min_messages = max_iterations * 2
                assert len(tmux_state["messages_sent"]) >= expected_min_messages
