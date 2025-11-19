# MessagingSystem Integration Plan for Workflows

## Overview

This document outlines the integration strategy for wiring MessagingSystem into the autonomous workflow modules (autonomous_dev.py, work_distributor.py, code_review.py, consensus.py).

**Status:** Ready for implementation once agent-3 completes E2B Launcher security fixes
**Author:** agent-1
**Created:** 2025-11-19

---

## MessagingSystem Architecture Summary

### Core Components

**MessagingSystem** (`src/claudeswarm/messaging.py:741`)
- Main coordinator for all messaging operations
- Handles rate limiting, logging, and delivery
- Thread-safe and production-ready

**Key Methods:**
```python
class MessagingSystem:
    def send_message(
        self,
        sender_id: str,
        recipient_id: str,
        msg_type: MessageType,
        content: str
    ) -> Message

    def broadcast_message(
        self,
        sender_id: str,
        msg_type: MessageType,
        content: str,
        exclude_self: bool = True
    ) -> Dict[str, bool]
```

**MessageType Enum** (`src/claudeswarm/messaging.py:148`)
```python
class MessageType(Enum):
    QUESTION = "QUESTION"
    REVIEW_REQUEST = "REVIEW-REQUEST"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CHALLENGE = "CHALLENGE"
    INFO = "INFO"
    ACK = "ACK"
```

**Message Class** (`src/claudeswarm/messaging.py:160`)
- Structured message with sender, recipients, timestamp
- HMAC-SHA256 signing for authentication
- Automatic validation of all fields

### Key Features for Workflows

1. **Graceful Fallback:** Works even if tmux is unavailable (sandboxed environments)
2. **Rate Limiting:** Prevents message storms
3. **Delivery Tracking:** Know exactly which agents received messages
4. **Message Logging:** Complete audit trail in `agent_messages.log`
5. **Error Handling:** Clear exceptions (RateLimitExceeded, AgentNotFoundError, etc.)

---

## Integration Checklist

### 1. WorkDistributor (`src/claudeswarm/workflows/work_distributor.py`)

**Current TODOs:** Lines 59-60, 114-115, 156-165, 339-345, 388-393

**Integration Points:**

#### Line 59: Initialize MessagingSystem
```python
# Current:
# TODO: Initialize messaging when available
# self.messaging = MessagingSystem()

# Replace with:
from claudeswarm.messaging import MessagingSystem

def __init__(self, num_agents: int = 4):
    self.num_agents = num_agents
    self.tasks: Dict[str, Task] = {}
    self.messaging = MessagingSystem()
```

#### Lines 156-165: Broadcast Vote Request
```python
# Current TODO at lines 156-165

# Replace with:
from claudeswarm.messaging import MessageType

async def initiate_vote(self, topic: str, option_a: str, ...):
    # ... existing code ...

    vote_message = self._format_vote_request(
        topic, option_a, option_b,
        evidence_a or [], evidence_b or []
    )

    try:
        self.messaging.broadcast_message(
            sender_id="work-distributor",
            msg_type=MessageType.QUESTION,
            content=vote_message
        )
    except Exception as e:
        print(f"⚠️  Failed to broadcast vote request: {e}")

    return vote_id
```

#### Lines 339-345: Broadcast Available Tasks
```python
# Current TODO at lines 339-345

# Replace with:
async def broadcast_tasks(self, tasks: List[Task]):
    available_tasks = [t for t in tasks if t.status == "available"]

    if not available_tasks:
        return

    task_list = "\n".join([
        f"- {t.id}: {t.title}" +
        (f" (depends on: {', '.join(t.dependencies)})" if t.dependencies else "")
        for t in available_tasks
    ])

    message_content = (
        f"Available tasks:\n{task_list}\n\n"
        f"Claim with: claudeswarm send-message work-distributor INFO 'claim:task_id'"
    )

    try:
        self.messaging.broadcast_message(
            sender_id="work-distributor",
            msg_type=MessageType.INFO,
            content=message_content
        )
        print(f"📋 Broadcast {len(available_tasks)} available tasks")
    except Exception as e:
        print(f"⚠️  Failed to broadcast tasks: {e}")
```

#### Lines 388-393: Broadcast Task Claim
```python
# Current TODO at lines 388-393

# Replace with:
def claim_task(self, task_id: str, agent_id: str) -> bool:
    # ... existing validation code ...

    # Claim task
    task.agent_id = agent_id
    task.status = "claimed"
    task.claimed_at = datetime.now()

    print(f"✓ Task {task_id} claimed by {agent_id}")

    # Broadcast claim
    try:
        self.messaging.broadcast_message(
            sender_id="work-distributor",
            msg_type=MessageType.INFO,
            content=f"{agent_id} claimed: {task.title}"
        )
    except Exception as e:
        print(f"⚠️  Failed to broadcast claim: {e}")

    return True
```

**Error Handling Pattern:**
```python
from claudeswarm.messaging import (
    MessagingSystem,
    MessageType,
    RateLimitExceeded,
    AgentNotFoundError
)

try:
    self.messaging.broadcast_message(...)
except RateLimitExceeded:
    print("⚠️  Rate limit exceeded - wait before sending more messages")
except AgentNotFoundError:
    print("⚠️  No active agents found")
except Exception as e:
    print(f"⚠️  Messaging error: {e}")
```

---

### 2. CodeReviewProtocol (`src/claudeswarm/workflows/code_review.py`)

**Current TODOs:** Lines 104-105, 129-135, 165-171, 252-257

**Integration Points:**

#### Line 104: Initialize MessagingSystem
```python
# Current:
# TODO: Initialize messaging when available
# self.messaging = MessagingSystem()

# Replace with:
from claudeswarm.messaging import MessagingSystem

def __init__(self, num_agents: int = 4):
    self.num_agents = num_agents
    self.reviews: Dict[str, ReviewFeedback] = {}
    self.disagreements: List[Disagreement] = []
    self.messaging = MessagingSystem()
```

#### Lines 129-135: Send Review Request
```python
# Current TODO at lines 129-135

# Replace with:
async def request_review(
    self,
    author_agent: str,
    reviewer_agent: str,
    files: List[str],
    task_description: Optional[str] = None
) -> str:
    review_id = f"review-{author_agent}-{len(self.reviews)}"

    review_message = (
        f"Please review my changes:\n"
        f"Files: {', '.join(files)}\n" +
        (f"Task: {task_description}" if task_description else "")
    )

    try:
        self.messaging.send_message(
            sender_id=author_agent,
            recipient_id=reviewer_agent,
            msg_type=MessageType.REVIEW_REQUEST,
            content=review_message
        )

        print(f"📝 Review requested: {author_agent} → {reviewer_agent}")
        print(f"   Files: {', '.join(files)}")
        if task_description:
            print(f"   Task: {task_description}")

    except Exception as e:
        print(f"⚠️  Failed to send review request: {e}")

    return review_id
```

#### Lines 165-171: Send Review Feedback
```python
# Current TODO at lines 165-171

# Replace with:
async def submit_review(self, review_id: str, feedback: ReviewFeedback):
    self.reviews[review_id] = feedback

    # Check for disagreements
    if feedback.issues and not feedback.approved:
        print(f"⚠️  Review concerns from {feedback.reviewer_id}:")
        for issue in feedback.issues:
            print(f"   - {issue}")

    # Send feedback
    feedback_message = self._format_feedback(feedback)

    try:
        self.messaging.send_message(
            sender_id=feedback.reviewer_id,
            recipient_id=feedback.author_id,
            msg_type=MessageType.INFO,
            content=feedback_message
        )

        print(f"✓ Review submitted: {feedback.reviewer_id} reviewed {feedback.author_id}'s work")
        if feedback.approved:
            print(f"  Status: ✅ Approved")
        else:
            print(f"  Status: ⚠️  Changes requested")

    except Exception as e:
        print(f"⚠️  Failed to send feedback: {e}")
```

#### Lines 252-257: Broadcast Disagreement
```python
# Current TODO at lines 252-257

# Replace with:
async def challenge_approach(
    self,
    challenger_agent: str,
    author_agent: str,
    topic: str,
    challenger_position: str,
    author_position: str,
    challenger_evidence: List[str],
    author_evidence: List[str]
) -> Disagreement:
    disagreement = Disagreement(
        topic=topic,
        agent_a=author_agent,
        position_a=author_position,
        evidence_a=author_evidence,
        agent_b=challenger_agent,
        position_b=challenger_position,
        evidence_b=challenger_evidence
    )

    self.disagreements.append(disagreement)

    print(f"⚔️  DISAGREEMENT: {topic}")
    print(f"   {author_agent}: {author_position}")
    print(f"   {challenger_agent}: {challenger_position}")
    print(f"   Evidence: {len(author_evidence) + len(challenger_evidence)} sources")

    # Broadcast disagreement for transparency
    disagreement_message = (
        f"Disagreement on: {topic}\n"
        f"Agents: {author_agent} vs {challenger_agent}\n"
        f"Need consensus vote!"
    )

    try:
        self.messaging.broadcast_message(
            sender_id="code-review-protocol",
            msg_type=MessageType.CHALLENGE,
            content=disagreement_message
        )
    except Exception as e:
        print(f"⚠️  Failed to broadcast disagreement: {e}")

    return disagreement
```

---

### 3. ConsensusEngine (`src/claudeswarm/workflows/consensus.py`)

**Current TODOs:** Lines 114-115, 156-165

**Integration Points:**

#### Line 114: Initialize MessagingSystem
```python
# Current:
# TODO: Initialize messaging when available
# self.messaging = MessagingSystem()

# Replace with:
from claudeswarm.messaging import MessagingSystem

def __init__(
    self,
    num_agents: int = 4,
    strategy: ConsensusStrategy = ConsensusStrategy.EVIDENCE_BASED
):
    self.num_agents = num_agents
    self.strategy = strategy
    self.active_votes: Dict[str, List[Vote]] = {}
    self.completed_votes: List[ConsensusResult] = []
    self.messaging = MessagingSystem()
```

#### Lines 156-165: Broadcast Vote Request
```python
# Current TODO at lines 156-165

# Replace with:
async def initiate_vote(
    self,
    topic: str,
    option_a: str,
    option_b: str,
    agents: List[str],
    evidence_a: Optional[List[str]] = None,
    evidence_b: Optional[List[str]] = None,
    timeout: int = 300
) -> str:
    vote_id = f"vote-{len(self.active_votes)}"
    self.active_votes[vote_id] = []

    print(f"\n🗳️  CONSENSUS VOTE: {topic}")
    print(f"   Option A: {option_a}")
    if evidence_a:
        print(f"   Evidence A: {len(evidence_a)} sources")
    print(f"   Option B: {option_b}")
    if evidence_b:
        print(f"   Evidence B: {len(evidence_b)} sources")
    print(f"   Voters: {', '.join(agents)}")
    print(f"   Timeout: {timeout}s")

    # Broadcast vote request
    vote_message = self._format_vote_request(
        topic, option_a, option_b,
        evidence_a or [], evidence_b or []
    )

    try:
        self.messaging.broadcast_message(
            sender_id="consensus-engine",
            msg_type=MessageType.QUESTION,
            content=vote_message
        )
    except Exception as e:
        print(f"⚠️  Failed to broadcast vote request: {e}")

    return vote_id
```

---

### 4. AutonomousDevelopmentLoop (`src/claudeswarm/workflows/autonomous_dev.py`)

**Current TODOs:** Lines 75-76, 153-160, 186-193, 263-273, 369-379, 415-422, 494-501

**Note:** This file has the most integration points and will require careful async/await handling.

#### Line 75: Initialize MessagingSystem
```python
# Current:
# TODO: Initialize messaging when available
# self.messaging = MessagingSystem()

# Replace with:
from claudeswarm.messaging import MessagingSystem

def __init__(
    self,
    sandbox_id: str,
    mcp_bridge: 'MCPBridge',
    num_agents: int = 4
):
    self.sandbox_id = sandbox_id
    self.mcp_bridge = mcp_bridge
    self.num_agents = num_agents
    self.agents = [f"agent-{i+1}" for i in range(num_agents)]

    # Initialize workflow components
    self.work_distributor = WorkDistributor(num_agents)
    self.code_review = CodeReviewProtocol(num_agents)
    self.consensus = ConsensusEngine(num_agents)

    # Initialize messaging
    self.messaging = MessagingSystem()
```

#### Lines 153-160: Broadcast Research Phase Start
```python
# Current TODO at lines 153-160

# Replace with:
async def research_phase(self, feature_description: str) -> Dict:
    print(f"\n{'='*80}")
    print(f"🔬 PHASE 1: RESEARCH")
    print(f"{'='*80}\n")

    # Broadcast research phase start
    try:
        self.messaging.broadcast_message(
            sender_id="autonomous-dev-loop",
            msg_type=MessageType.INFO,
            content=f"Starting research phase for: {feature_description}"
        )
    except Exception as e:
        print(f"⚠️  Failed to broadcast phase start: {e}")

    # ... rest of research logic ...
```

#### Lines 186-193: Send Planning Tasks
```python
# Current TODO at lines 186-193

# Replace with:
async def planning_phase(self, research_results: Dict) -> List[Task]:
    print(f"\n{'='*80}")
    print(f"📋 PHASE 2: PLANNING")
    print(f"{'='*80}\n")

    # Use WorkDistributor (which now has MessagingSystem integrated)
    tasks = await self.work_distributor.decompose_feature(
        research_results.get("feature_description", ""),
        research_results
    )

    # Broadcast tasks (WorkDistributor handles messaging)
    await self.work_distributor.broadcast_tasks(tasks)

    return tasks
```

#### Lines 263-273: Request Code Reviews
```python
# Current TODO at lines 263-273

# Replace with:
async def review_phase(self, implementations: Dict) -> Dict[str, List[ReviewFeedback]]:
    print(f"\n{'='*80}")
    print(f"👀 PHASE 4: CODE REVIEW")
    print(f"{'='*80}\n")

    reviews_by_task = {}

    for task_id, implementation in implementations.items():
        task = self.work_distributor.tasks[task_id]
        author_agent = task.agent_id

        # Assign reviewers (CodeReviewProtocol method)
        reviewers = self.code_review.assign_reviewers(
            author_agent,
            self.agents,
            num_reviewers=1
        )

        # Request reviews (uses MessagingSystem internally)
        for reviewer_agent in reviewers:
            await self.code_review.request_review(
                author_agent=author_agent,
                reviewer_agent=reviewer_agent,
                files=task.files,
                task_description=task.description
            )

        # ... collect reviews logic ...

    return reviews_by_task
```

#### Lines 369-379: Initiate Consensus Voting
```python
# Current TODO at lines 369-379

# Replace with:
async def consensus_phase(self, disagreements: List[Disagreement]) -> List[ConsensusResult]:
    if not disagreements:
        print("No disagreements to resolve - skipping consensus")
        return []

    print(f"\n{'='*80}")
    print(f"🗳️  PHASE 5: CONSENSUS")
    print(f"{'='*80}\n")

    results = []

    for disagreement in disagreements:
        # Initiate vote (uses MessagingSystem internally)
        vote_id = await self.consensus.initiate_vote(
            topic=disagreement.topic,
            option_a=disagreement.position_a,
            option_b=disagreement.position_b,
            agents=self.agents,
            evidence_a=disagreement.evidence_a,
            evidence_b=disagreement.evidence_b
        )

        # ... collect votes logic ...

    return results
```

---

## Testing Strategy

### Unit Tests

**Test File:** `tests/workflows/test_messaging_integration.py` (NEW)

```python
import pytest
from claudeswarm.workflows.work_distributor import WorkDistributor
from claudeswarm.workflows.code_review import CodeReviewProtocol
from claudeswarm.workflows.consensus import ConsensusEngine
from claudeswarm.messaging import MessageType
from unittest.mock import Mock, patch

@pytest.mark.asyncio
async def test_work_distributor_broadcasts_tasks():
    """Test that WorkDistributor broadcasts tasks via MessagingSystem"""
    with patch('claudeswarm.workflows.work_distributor.MessagingSystem') as MockMessaging:
        mock_messaging = MockMessaging.return_value

        distributor = WorkDistributor(num_agents=4)
        tasks = await distributor.decompose_feature("Add JWT auth")
        await distributor.broadcast_tasks(tasks)

        # Verify broadcast was called
        mock_messaging.broadcast_message.assert_called_once()
        call_args = mock_messaging.broadcast_message.call_args
        assert call_args[1]['msg_type'] == MessageType.INFO
        assert 'Available tasks' in call_args[1]['content']

@pytest.mark.asyncio
async def test_code_review_sends_review_request():
    """Test that CodeReviewProtocol sends review requests"""
    with patch('claudeswarm.workflows.code_review.MessagingSystem') as MockMessaging:
        mock_messaging = MockMessaging.return_value

        protocol = CodeReviewProtocol(num_agents=4)
        await protocol.request_review(
            author_agent="agent-1",
            reviewer_agent="agent-2",
            files=["test.py"]
        )

        # Verify direct message was sent
        mock_messaging.send_message.assert_called_once()
        call_args = mock_messaging.send_message.call_args
        assert call_args[1]['sender_id'] == "agent-1"
        assert call_args[1]['recipient_id'] == "agent-2"
        assert call_args[1]['msg_type'] == MessageType.REVIEW_REQUEST

@pytest.mark.asyncio
async def test_consensus_broadcasts_vote():
    """Test that ConsensusEngine broadcasts votes"""
    with patch('claudeswarm.workflows.consensus.MessagingSystem') as MockMessaging:
        mock_messaging = MockMessaging.return_value

        engine = ConsensusEngine(num_agents=4)
        await engine.initiate_vote(
            topic="Test vote",
            option_a="Option A",
            option_b="Option B",
            agents=["agent-1", "agent-2"]
        )

        # Verify broadcast was called
        mock_messaging.broadcast_message.assert_called_once()
        call_args = mock_messaging.broadcast_message.call_args
        assert call_args[1]['msg_type'] == MessageType.QUESTION
```

### Integration Tests

**Test File:** `tests/workflows/test_autonomous_dev_integration.py` (MODIFY EXISTING)

Add messaging verification to existing integration tests:

```python
@pytest.mark.asyncio
async def test_full_autonomous_loop_with_messaging():
    """Test complete autonomous development loop with real messaging"""
    # This test would need real MessagingSystem (not mocked)
    # and would verify end-to-end message flow
    pass
```

---

## Error Handling Guidelines

### 1. Always Catch Messaging Exceptions

```python
from claudeswarm.messaging import (
    RateLimitExceeded,
    AgentNotFoundError,
    MessageDeliveryError
)

try:
    self.messaging.broadcast_message(...)
except RateLimitExceeded as e:
    print(f"⚠️  Rate limit exceeded: {e}")
except AgentNotFoundError as e:
    print(f"⚠️  No agents found: {e}")
except MessageDeliveryError as e:
    print(f"⚠️  Message delivery failed: {e}")
except Exception as e:
    print(f"⚠️  Unexpected messaging error: {e}")
```

### 2. Graceful Degradation

Messages are NOT critical for workflow logic - they're for coordination and transparency. If messaging fails:
- Log the error
- Continue workflow execution
- Don't crash or retry aggressively

```python
# GOOD: Messaging failure doesn't stop workflow
try:
    self.messaging.broadcast_message(...)
except Exception as e:
    print(f"⚠️  Failed to notify agents: {e}")
# Continue with workflow logic

# BAD: Don't do this
try:
    self.messaging.broadcast_message(...)
except Exception:
    raise  # Don't re-raise and crash workflow
```

### 3. Rate Limit Awareness

```python
# WorkDistributor may send many messages in a loop
# Be aware of rate limits (default: 30 messages per 60 seconds)

for task in tasks:
    try:
        self.messaging.broadcast_message(...)
    except RateLimitExceeded:
        # Don't spam - wait or batch messages
        print("⚠️  Rate limit reached, slowing down...")
        await asyncio.sleep(2)
```

---

## Performance Considerations

### Message Delivery Timeouts

- **Direct messages:** 10 second timeout (DIRECT_MESSAGE_TIMEOUT_SECONDS)
- **Broadcasts:** 5 second timeout per recipient (BROADCAST_TIMEOUT_SECONDS)

For N agents broadcasting, worst-case time = N * 5s

### Async/Await Patterns

All messaging operations are synchronous (not async), but workflow methods are async:

```python
# CORRECT:
async def some_workflow_method(self):
    # Messaging calls don't need await
    self.messaging.broadcast_message(...)

    # But workflow operations are async
    await some_async_operation()

# INCORRECT:
async def some_workflow_method(self):
    # Don't do this - send_message is not async
    await self.messaging.broadcast_message(...)  # TypeError!
```

---

## Rollout Plan

### Phase 1: WorkDistributor (Simplest)
- Fewest integration points (3 locations)
- No complex error handling needed
- Good learning ground

### Phase 2: CodeReviewProtocol (Medium)
- 4 integration points
- Introduces direct messaging (not just broadcasts)
- Tests sender→recipient flow

### Phase 3: ConsensusEngine (Medium)
- 2 integration points
- Tests QUESTION message type
- Validates vote request formatting

### Phase 4: AutonomousDevelopmentLoop (Complex)
- 7 integration points
- Depends on all other components
- Full end-to-end validation

### Validation After Each Phase

1. Run unit tests
2. Run integration tests
3. Test with real agents in tmux
4. Verify messages appear in `agent_messages.log`
5. Check rate limiting behavior

---

## Dependencies

**Before Starting Integration:**

✅ MessagingSystem is production-ready (1,354 lines, fully tested)
⏳ **BLOCKED ON:** agent-3's E2B Launcher security fixes

**Why Blocked:**
- E2B Launcher security needs to be solid before we integrate messaging
- Security issues could propagate through messaging layer
- Better to fix foundation first, then build on top

**Once Unblocked:**
- Integration can proceed immediately (all patterns documented above)
- Estimated time: 3-4 hours for all 4 files
- Can be done in parallel with other work

---

## Success Criteria

✅ All 4 workflow files have MessagingSystem integrated
✅ All TODO comments removed
✅ Unit tests pass with mocked messaging
✅ Integration tests pass with real messaging
✅ Messages visible in `agent_messages.log`
✅ No rate limit exceptions in normal operation
✅ Graceful fallback when tmux unavailable

---

## Contact

**Questions or blockers?**
- agent-1 (owner of workflows integration)
- agent-4 (if messaging internals need modification)

**Last Updated:** 2025-11-19
**Status:** Ready for implementation (blocked on agent-3 security fixes)
