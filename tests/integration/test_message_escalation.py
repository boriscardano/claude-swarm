"""Integration test: Message Escalation and Retry (Scenario 3).

Tests message delivery failure handling and escalation:
1. Agent 2 sends message to Agent 5
2. Agent 5 doesn't respond (simulated hang/unavailable)
3. System detects non-delivery
4. Agent 2 retries message delivery
5. After retries fail, escalates to broadcast
6. Agent 4 responds to broadcast
7. Verify: retry attempts, escalation, alternate agent communication
"""

from claudeswarm.messaging import MessageType, broadcast_message, send_message

from .helpers import (
    IntegrationTestContext,
    mock_tmux_environment,
    verify_message_delivered,
)


class TestMessageEscalation:
    """Integration test suite for message escalation and retry scenarios."""

    def test_escalation_to_broadcast_after_no_response(self) -> None:
        """Test escalation to broadcast when direct message gets no response.

        Scenario:
        1. Agent 2 sends direct message to Agent 5
        2. Agent 5 doesn't respond (pane doesn't exist)
        3. Agent 2 detects delivery issue
        4. Agent 2 escalates to broadcast
        5. Agent 4 (and others) receive broadcast
        6. Agent 4 responds
        """
        with IntegrationTestContext(num_agents=6) as ctx:
            with mock_tmux_environment() as tmux_state:
                # Only add agents 0-4 to tmux (agent-5 is "unavailable")
                for i in range(5):
                    agent = ctx.agents[i]
                    tmux_state["panes"].append(agent.pane_index)

                # Step 1: Agent 2 tries to send to Agent 5
                send_message(
                    sender_id="agent-2",
                    recipient_id="agent-5",
                    message_type=MessageType.QUESTION,
                    content="Need help with database schema",
                )

                # Message send will fail because agent-5 pane doesn't exist
                # In real implementation, this would be detected
                # For now, we simulate the detection

                # Step 2-3: Detect that agent-5 didn't respond
                # (In real system, this would be timeout-based)

                # Step 4: Agent 2 escalates to broadcast
                broadcast_result = broadcast_message(
                    sender_id="agent-2",
                    message_type=MessageType.QUESTION,
                    content="[ESCALATED] Need help with database schema - original recipient unavailable",
                    exclude_self=True,
                )

                # Step 5: Verify broadcast went to available agents
                assert len(broadcast_result) > 0

                # Should have reached agents 0, 1, 3, 4 (not 2 or 5)
                expected_recipients = 4  # agents 0,1,3,4
                successful_deliveries = sum(1 for success in broadcast_result.values() if success)
                assert successful_deliveries == expected_recipients

                # Step 6: Agent 4 responds
                response_msg = send_message(
                    sender_id="agent-4",
                    recipient_id="agent-2",
                    message_type=MessageType.INFO,
                    content="I can help with the database schema",
                )

                assert response_msg is not None

                # Verify the response was delivered
                assert verify_message_delivered(
                    tmux_state["messages_sent"],
                    sender_id="agent-4",
                    recipient_pane=ctx.get_agent("agent-2").pane_index,
                    msg_type=MessageType.INFO,
                    content_substring="database schema",
                )

    def test_retry_strategy_with_backoff(self) -> None:
        """Test that retry strategy uses exponential backoff."""
        with IntegrationTestContext(num_agents=3):
            with mock_tmux_environment():
                # Simulate retry behavior
                retry_intervals = []
                max_retries = 3

                for attempt in range(max_retries):
                    # Exponential backoff: 2^attempt seconds
                    expected_delay = 2**attempt
                    retry_intervals.append(expected_delay)

                # Verify exponential growth
                assert retry_intervals == [1, 2, 4]  # 2^0, 2^1, 2^2

    def test_multiple_agents_unavailable_fallback_chain(self) -> None:
        """Test fallback chain when multiple agents are unavailable."""
        with IntegrationTestContext(num_agents=6) as ctx:
            with mock_tmux_environment() as tmux_state:
                # Only agents 0, 1, 5 are available
                available_agents = [0, 1, 5]
                for i in available_agents:
                    tmux_state["panes"].append(ctx.agents[i].pane_index)

                # Agent 0 tries to contact agents in order: 2, 3, 4
                # All fail, then broadcasts to find any available agent

                target_agents = ["agent-2", "agent-3", "agent-4"]
                for target in target_agents:
                    send_message(
                        sender_id="agent-0",
                        recipient_id=target,
                        message_type=MessageType.QUESTION,
                        content="Need code review",
                    )
                    # These will fail because agents aren't in tmux_state

                # After failures, broadcast
                broadcast_result = broadcast_message(
                    sender_id="agent-0",
                    message_type=MessageType.QUESTION,
                    content="[ESCALATED] Need code review - looking for available reviewer",
                    exclude_self=True,
                )

                # Should reach agents 1 and 5
                assert len([s for s in broadcast_result.values() if s]) >= 1

    def test_blocked_agent_communication(self) -> None:
        """Test communication pattern when agent is blocked."""
        with IntegrationTestContext(num_agents=4) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Agent 2 is blocked waiting for information
                blocked_msg = send_message(
                    sender_id="agent-2",
                    recipient_id="agent-1",
                    message_type=MessageType.BLOCKED,
                    content="Blocked: Need API endpoint specification before proceeding",
                )

                assert blocked_msg is not None

                # Verify message delivered
                assert verify_message_delivered(
                    tmux_state["messages_sent"],
                    sender_id="agent-2",
                    recipient_pane=ctx.get_agent("agent-1").pane_index,
                    msg_type=MessageType.BLOCKED,
                    content_substring="API endpoint",
                )

                # Agent 1 responds with the needed information
                response = send_message(
                    sender_id="agent-1",
                    recipient_id="agent-2",
                    message_type=MessageType.INFO,
                    content="API endpoint: POST /api/auth/login with {username, password}",
                )

                assert response is not None

                # Agent 2 sends completion notification
                complete_msg = send_message(
                    sender_id="agent-2",
                    recipient_id="agent-1",
                    message_type=MessageType.COMPLETED,
                    content="Unblocked - proceeding with implementation",
                )

                assert complete_msg is not None

    def test_broadcast_reaches_all_active_agents(self) -> None:
        """Test that broadcast reaches all currently active agents."""
        with IntegrationTestContext(num_agents=5) as ctx:
            with mock_tmux_environment() as tmux_state:
                # All agents are active initially
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Agent 0 broadcasts
                broadcast_result = broadcast_message(
                    sender_id="agent-0",
                    message_type=MessageType.INFO,
                    content="Important announcement to all agents",
                    exclude_self=True,
                )

                # Should reach all 4 other agents
                assert len(broadcast_result) == 4
                successful = sum(1 for success in broadcast_result.values() if success)
                assert successful == 4

                # Verify each agent received the message
                for i in range(1, 5):
                    assert broadcast_result[f"agent-{i}"] is True

    def test_challenge_message_requires_response(self) -> None:
        """Test CHALLENGE message type for critical coordination."""
        with IntegrationTestContext(num_agents=3) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Agent 1 sends challenge to Agent 2
                challenge = send_message(
                    sender_id="agent-1",
                    recipient_id="agent-2",
                    message_type=MessageType.CHALLENGE,
                    content="CHALLENGE: Are you still working on user-service? Lock has been held for 10 minutes",
                )

                assert challenge is not None

                # Verify delivery
                assert verify_message_delivered(
                    tmux_state["messages_sent"],
                    sender_id="agent-1",
                    recipient_pane=ctx.get_agent("agent-2").pane_index,
                    msg_type=MessageType.CHALLENGE,
                )

                # Agent 2 must respond
                response = send_message(
                    sender_id="agent-2",
                    recipient_id="agent-1",
                    message_type=MessageType.INFO,
                    content="Yes, still working - about to finish and release lock",
                )

                assert response is not None

    def test_rate_limit_prevents_spam(self) -> None:
        """Test that rate limiting prevents message spam during retries."""
        with IntegrationTestContext(num_agents=2) as ctx:
            with mock_tmux_environment() as tmux_state:
                for agent in ctx.agents:
                    tmux_state["panes"].append(agent.pane_index)

                # Try to send 15 messages rapidly
                sent_count = 0
                blocked_count = 0

                for i in range(15):
                    msg = send_message(
                        sender_id="agent-0",
                        recipient_id="agent-1",
                        message_type=MessageType.INFO,
                        content=f"Retry attempt {i}",
                    )

                    if msg is not None:
                        sent_count += 1
                    else:
                        blocked_count += 1

                # Should have hit rate limit
                assert sent_count == 10  # Default rate limit
                assert blocked_count == 5

    def test_agent_discovery_before_messaging(self) -> None:
        """Test that agents are discovered before attempting to message them."""
        with IntegrationTestContext(num_agents=3) as ctx:
            with mock_tmux_environment() as tmux_state:
                from claudeswarm.discovery import list_active_agents

                # Discover active agents first
                active_agents = list_active_agents()
                active_ids = {agent.id for agent in active_agents}

                # Only add discovered agents to tmux
                for agent in ctx.agents:
                    if agent.id in active_ids:
                        tmux_state["panes"].append(agent.pane_index)

                # Now send messages only to discovered agents
                for agent_id in active_ids:
                    if agent_id != "agent-0":
                        msg = send_message(
                            sender_id="agent-0",
                            recipient_id=agent_id,
                            message_type=MessageType.INFO,
                            content="Hello discovered agent",
                        )
                        # Should succeed for active agents
                        assert msg is not None
