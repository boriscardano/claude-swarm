"""
Code Review Protocol

This module implements the structured code review process where agents
review each other's work, provide feedback, and challenge approaches
with evidence-based arguments.

Key features:
- Cross-agent code review (agents review each other, not their own work)
- Evidence-based feedback (link to docs, research, best practices)
- Structured review format (issues, suggestions, approval)
- Debate/challenge mechanism for disagreements

Author: agent-1
Created: 2025-11-19
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from claudeswarm.messaging import MessageType, MessagingSystem


@dataclass
class ReviewFeedback:
    """
    Structured code review feedback from an agent.

    Attributes:
        reviewer_id: Agent who performed the review
        author_id: Agent who wrote the code
        files: Files that were reviewed
        issues: List of problems found (bugs, security, performance)
        suggestions: Improvement recommendations
        evidence: Links to documentation supporting feedback
        approved: Whether code is approved as-is
        created_at: When review was submitted
    """

    reviewer_id: str
    author_id: str
    files: list[str]
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    approved: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Disagreement:
    """
    Represents a disagreement between agents on implementation approach.

    This triggers the consensus mechanism to resolve the dispute.

    Attributes:
        topic: What the disagreement is about
        agent_a: First agent's ID
        position_a: First agent's position
        agent_b: Second agent's ID
        position_b: Second agent's position
        evidence_a: Links/research supporting position A
        evidence_b: Links/research supporting position B
        resolved: Whether consensus has been reached
        resolution: Final decision after consensus
    """

    topic: str
    agent_a: str
    position_a: str
    agent_b: str
    position_b: str
    evidence_a: list[str] = field(default_factory=list)
    evidence_b: list[str] = field(default_factory=list)
    resolved: bool = False
    resolution: str | None = None


class CodeReviewProtocol:
    """
    Manages the code review process among autonomous agents.

    This class coordinates:
    - Review request distribution (round-robin or expertise-based)
    - Feedback collection and validation
    - Disagreement detection and escalation
    - Review quality metrics

    Example:
        protocol = CodeReviewProtocol(num_agents=4)
        await protocol.request_review(
            author_agent="agent-1",
            reviewer_agent="agent-2",
            files=["models/user.py"]
        )
        feedback = await protocol.collect_feedback("review-123")
        if feedback.has_disagreements():
            await protocol.escalate_to_consensus(feedback)
    """

    # Maximum number of agents allowed to prevent resource exhaustion
    MAX_AGENTS = 100

    def __init__(self, num_agents: int = 4):
        if num_agents > self.MAX_AGENTS:
            raise ValueError(f"num_agents must not exceed {self.MAX_AGENTS}")
        if num_agents < 1:
            raise ValueError("num_agents must be at least 1")

        self.num_agents = num_agents
        self.reviews: dict[str, ReviewFeedback] = {}
        self.disagreements: list[Disagreement] = []
        self.messaging = MessagingSystem()

    async def request_review(
        self,
        author_agent: str,
        reviewer_agent: str,
        files: list[str],
        task_description: str | None = None,
    ) -> str:
        """
        Send a code review request from author to reviewer.

        Args:
            author_agent: Agent who wrote the code
            reviewer_agent: Agent who should review
            files: List of files to review
            task_description: Optional context about what was implemented

        Returns:
            Review request ID
        """

        review_id = f"review-{author_agent}-{len(self.reviews)}"

        # Format review request message
        review_message = f"Please review my changes:\n" f"Files: {', '.join(files)}\n" + (
            f"Task: {task_description}" if task_description else ""
        )

        # Send review request via messaging
        try:
            self.messaging.send_message(
                sender_id=author_agent,
                recipient_id=reviewer_agent,
                msg_type=MessageType.REVIEW_REQUEST,
                content=review_message,
            )

            print(f"📝 Review requested: {author_agent} → {reviewer_agent}")
            print(f"   Files: {', '.join(files)}")
            if task_description:
                print(f"   Task: {task_description}")

        except Exception as e:
            print(f"⚠️  Failed to send review request: {e}")
            print(f"📝 Review requested (local only): {author_agent} → {reviewer_agent}")

        return review_id

    async def submit_review(self, review_id: str, feedback: ReviewFeedback):
        """
        Submit review feedback.

        Args:
            review_id: ID of the review request
            feedback: Structured feedback from reviewer
        """

        self.reviews[review_id] = feedback

        # Check for disagreements
        if feedback.issues and not feedback.approved:
            print(f"⚠️  Review concerns from {feedback.reviewer_id}:")
            for issue in feedback.issues:
                print(f"   - {issue}")

        # Send feedback via messaging
        feedback_message = self._format_feedback(feedback)

        try:
            self.messaging.send_message(
                sender_id=feedback.reviewer_id,
                recipient_id=feedback.author_id,
                msg_type=MessageType.INFO,
                content=feedback_message,
            )

            print(
                f"✓ Review submitted: {feedback.reviewer_id} reviewed {feedback.author_id}'s work"
            )
            if feedback.approved:
                print("  Status: ✅ Approved")
            else:
                print("  Status: ⚠️  Changes requested")

        except Exception as e:
            print(f"⚠️  Failed to send feedback: {e}")
            print(
                f"✓ Review submitted (local only): {feedback.reviewer_id} reviewed {feedback.author_id}'s work"
            )

    def _format_feedback(self, feedback: ReviewFeedback) -> str:
        """Format feedback for messaging"""

        lines = ["Code Review Feedback:", ""]

        if feedback.issues:
            lines.append("Issues Found:")
            for issue in feedback.issues:
                lines.append(f"  - {issue}")
            lines.append("")

        if feedback.suggestions:
            lines.append("Suggestions:")
            for suggestion in feedback.suggestions:
                lines.append(f"  - {suggestion}")
            lines.append("")

        if feedback.evidence:
            lines.append("Supporting Evidence:")
            for evidence in feedback.evidence:
                lines.append(f"  - {evidence}")
            lines.append("")

        lines.append(f"Approved: {'Yes' if feedback.approved else 'No'}")

        return "\n".join(lines)

    async def challenge_approach(
        self,
        challenger_agent: str,
        author_agent: str,
        topic: str,
        challenger_position: str,
        author_position: str,
        challenger_evidence: list[str],
        author_evidence: list[str],
    ) -> Disagreement:
        """
        Register a disagreement/challenge between agents.

        This happens when a reviewer strongly disagrees with an approach
        and has evidence to support an alternative.

        Args:
            challenger_agent: Agent challenging the approach
            author_agent: Original author
            topic: What the disagreement is about
            challenger_position: Challenger's recommended approach
            author_position: Author's original approach
            challenger_evidence: Research/docs supporting challenger
            author_evidence: Research/docs supporting author

        Returns:
            Disagreement object for consensus resolution
        """

        disagreement = Disagreement(
            topic=topic,
            agent_a=author_agent,
            position_a=author_position,
            evidence_a=author_evidence,
            agent_b=challenger_agent,
            position_b=challenger_position,
            evidence_b=challenger_evidence,
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
                content=disagreement_message,
            )
        except Exception as e:
            print(f"⚠️  Failed to broadcast disagreement: {e}")

        return disagreement

    def detect_disagreements(
        self, reviews: list[ReviewFeedback], threshold: int = 2
    ) -> list[Disagreement]:
        """
        Analyze reviews to detect disagreements.

        Looks for cases where multiple reviewers give conflicting feedback
        on the same topic.

        Args:
            reviews: List of review feedback to analyze
            threshold: Minimum number of conflicting opinions to flag

        Returns:
            List of detected disagreements
        """

        # Simple heuristic: if multiple reviewers mention same topic
        # with different recommendations, flag as disagreement

        # TODO: Implement smarter disagreement detection
        # For now, return existing disagreements

        return [d for d in self.disagreements if not d.resolved]

    def get_review_statistics(self) -> dict:
        """
        Get code review quality metrics.

        Returns:
            Dictionary with review statistics
        """

        total_reviews = len(self.reviews)
        approved_count = sum(1 for r in self.reviews.values() if r.approved)
        issues_count = sum(len(r.issues) for r in self.reviews.values())
        suggestions_count = sum(len(r.suggestions) for r in self.reviews.values())

        return {
            "total_reviews": total_reviews,
            "approved": approved_count,
            "rejected": total_reviews - approved_count,
            "approval_rate": (approved_count / total_reviews * 100) if total_reviews > 0 else 0,
            "total_issues": issues_count,
            "total_suggestions": suggestions_count,
            "avg_issues_per_review": issues_count / total_reviews if total_reviews > 0 else 0,
        }

    def assign_reviewers(
        self, author_agent: str, all_agents: list[str], num_reviewers: int = 1
    ) -> list[str]:
        """
        Assign reviewers for an agent's code.

        Uses round-robin by default, but could be enhanced with:
        - Expertise matching (assign frontend expert for UI code)
        - Workload balancing (avoid overloading one reviewer)
        - Conflict of interest (don't assign pair programmers)

        Args:
            author_agent: Agent who wrote the code
            all_agents: List of all available agents
            num_reviewers: How many reviewers to assign

        Returns:
            List of reviewer agent IDs
        """

        # Remove author from potential reviewers
        available_reviewers = [a for a in all_agents if a != author_agent]

        if len(available_reviewers) < num_reviewers:
            num_reviewers = len(available_reviewers)

        # Round-robin selection
        author_idx = int(author_agent.split("-")[1]) if "-" in author_agent else 0
        reviewers = []

        for i in range(num_reviewers):
            reviewer_idx = (author_idx + i + 1) % len(available_reviewers)
            reviewers.append(available_reviewers[reviewer_idx])

        return reviewers


# Pre-defined review checklists for common code types

REVIEW_CHECKLIST_AUTH = [
    "Password hashing uses approved algorithm (argon2/bcrypt)",
    "No plaintext passwords in logs or errors",
    "Token expiry times are appropriate",
    "Input validation on all auth endpoints",
    "Rate limiting on login endpoints",
    "Secure random for token generation",
    "HTTPS-only in production",
    "SQL injection prevention",
    "OWASP Top 10 compliance",
]

REVIEW_CHECKLIST_API = [
    "Input validation with Pydantic/schemas",
    "Proper error handling and status codes",
    "OpenAPI documentation complete",
    "Rate limiting where appropriate",
    "Authentication/authorization checks",
    "No sensitive data in responses",
    "Consistent response format",
    "Performance considerations",
]

REVIEW_CHECKLIST_DATABASE = [
    "Indexes on frequently queried fields",
    "Foreign key constraints defined",
    "Migration scripts tested",
    "No N+1 query problems",
    "Connection pooling configured",
    "Transactions used correctly",
    "No SQL injection vulnerabilities",
    "Backup/recovery considered",
]

REVIEW_CHECKLIST_GENERAL = [
    "Code follows project style guide",
    "Meaningful variable/function names",
    "No commented-out code",
    "Error handling comprehensive",
    "Tests cover main functionality",
    "Documentation up to date",
    "No security vulnerabilities",
    "Performance acceptable",
]


# ============================================================================
# AUTONOMOUS REVIEW ITERATION SYSTEM
# ============================================================================
# This section implements autonomous code review with iteration until quality
# standards are met. Agents review each other's work and iterate until approval.


class ReviewResult(Enum):
    """Result of a code review."""

    APPROVED = "approved"  # Good to merge
    REQUEST_CHANGES = "changes"  # Specific fixes needed
    NEEDS_DISCUSSION = "discuss"  # Unclear, need sync


@dataclass
class ReviewIteration:
    """A single iteration of the review cycle.

    Attributes:
        iteration_number: Which iteration this is (1-based)
        reviewer_id: Agent performing the review
        author_id: Agent who wrote the code
        result: Review result
        feedback: Detailed feedback
        issues_found: List of issues that need fixing
        suggestions: Improvement suggestions
        timestamp: When the review was performed
    """

    iteration_number: int
    reviewer_id: str
    author_id: str
    result: ReviewResult
    feedback: str = ""
    issues_found: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self):
        if isinstance(self.result, str):
            self.result = ReviewResult(self.result)


@dataclass
class AutonomousReviewSession:
    """Tracks a complete autonomous review session with iterations.

    Attributes:
        session_id: Unique session identifier
        task_id: Related task ID (if any)
        context_id: Related context ID (if any)
        author_id: Agent who wrote the code
        reviewer_id: Agent performing review
        files: Files being reviewed
        iterations: List of review iterations
        status: Current status (pending, in_progress, approved, failed)
        max_iterations: Maximum allowed iterations
        created_at: When the session started
        completed_at: When the session completed
    """

    session_id: str
    author_id: str
    reviewer_id: str
    files: list[str]
    task_id: str | None = None
    context_id: str | None = None
    iterations: list[ReviewIteration] = field(default_factory=list)
    status: str = "pending"  # pending, in_progress, approved, failed
    max_iterations: int = 5
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def add_iteration(self, iteration: ReviewIteration) -> None:
        """Add a review iteration."""
        self.iterations.append(iteration)
        self.status = "in_progress"

        if iteration.result == ReviewResult.APPROVED:
            self.status = "approved"
            self.completed_at = datetime.now(UTC)
        elif len(self.iterations) >= self.max_iterations:
            self.status = "failed"
            self.completed_at = datetime.now(UTC)

    @property
    def current_iteration(self) -> int:
        """Get the current iteration number."""
        return len(self.iterations)

    @property
    def is_complete(self) -> bool:
        """Check if the session is complete."""
        return self.status in ("approved", "failed")

    @property
    def is_approved(self) -> bool:
        """Check if the code was approved."""
        return self.status == "approved"


class AutonomousCodeReview:
    """Manages autonomous code review with iteration until approval.

    This class coordinates:
    - Finding the best reviewer using skill matching
    - Iterating review cycles until approval
    - Tracking review history
    - Enforcing maximum iteration limits

    Example:
        auto_review = AutonomousCodeReview()
        session = await auto_review.start_review(
            author_id="agent-0",
            files=["src/auth.py"],
            task_id="task-123"
        )
        # The system will iterate until approved or max iterations reached
    """

    DEFAULT_MAX_ITERATIONS = 5

    def __init__(self, max_iterations: int = DEFAULT_MAX_ITERATIONS):
        """Initialize the autonomous code review system.

        Args:
            max_iterations: Maximum review iterations before failing
        """
        self.max_iterations = max_iterations
        self.sessions: dict[str, AutonomousReviewSession] = {}
        self.messaging = MessagingSystem()

    def _find_best_reviewer(
        self,
        author_id: str,
        files: list[str],
    ) -> str | None:
        """Find the best reviewer for the given files.

        Uses skill matching from agent cards if available,
        otherwise falls back to round-robin selection.

        Args:
            author_id: Author to exclude from reviewers
            files: Files being reviewed (used to determine required skills)

        Returns:
            Best reviewer agent ID, or None if none available
        """
        try:
            from pathlib import Path

            from claudeswarm.agent_cards import AgentCardRegistry
            from claudeswarm.delegation import FILE_EXTENSION_SKILLS

            # Determine required skills from file extensions
            required_skills = set()
            for filepath in files:
                ext = Path(filepath).suffix.lower()
                if ext in FILE_EXTENSION_SKILLS:
                    required_skills.update(FILE_EXTENSION_SKILLS[ext])

            # Add code-review as a skill to look for
            required_skills.add("code-review")

            card_registry = AgentCardRegistry()

            # Find agents with relevant skills
            best_reviewer = None
            best_score = 0.0

            for card in card_registry.list_cards(availability="active"):
                if card.agent_id == author_id:
                    continue

                # Calculate skill match score
                score = 0.0
                for skill in required_skills:
                    proficiency = card.get_skill_proficiency(skill)
                    score += proficiency

                if score > best_score:
                    best_score = score
                    best_reviewer = card.agent_id

            if best_reviewer:
                return best_reviewer

        except ImportError:
            pass  # Agent cards not available

        # Fallback: Get active agents from discovery
        try:
            from claudeswarm.discovery import list_active_agents

            agents = list_active_agents()
            for agent in agents:
                if agent.id != author_id:
                    return agent.id
        except Exception:
            pass

        return None

    async def start_review(
        self,
        author_id: str,
        files: list[str],
        reviewer_id: str | None = None,
        task_id: str | None = None,
        context_id: str | None = None,
    ) -> AutonomousReviewSession:
        """Start an autonomous review session.

        Args:
            author_id: Agent who wrote the code
            files: Files to review
            reviewer_id: Specific reviewer (auto-selected if None)
            task_id: Related task ID
            context_id: Related context ID

        Returns:
            Created AutonomousReviewSession
        """
        # Find reviewer if not specified
        if reviewer_id is None:
            reviewer_id = self._find_best_reviewer(author_id, files)
            if reviewer_id is None:
                raise ValueError("No available reviewer found")

        session_id = f"review-{uuid.uuid4().hex[:12]}"

        session = AutonomousReviewSession(
            session_id=session_id,
            author_id=author_id,
            reviewer_id=reviewer_id,
            files=files,
            task_id=task_id,
            context_id=context_id,
            max_iterations=self.max_iterations,
        )

        self.sessions[session_id] = session

        # Send initial review request
        await self._send_review_request(session)

        print(f"🔄 Started autonomous review session {session_id}")
        print(f"   Author: {author_id}")
        print(f"   Reviewer: {reviewer_id}")
        print(f"   Files: {', '.join(files)}")
        print(f"   Max iterations: {self.max_iterations}")

        return session

    async def _send_review_request(self, session: AutonomousReviewSession) -> None:
        """Send a review request to the reviewer."""
        iteration = session.current_iteration + 1
        previous_feedback = ""

        if session.iterations:
            last = session.iterations[-1]
            if last.issues_found:
                previous_feedback = (
                    "\n\nPrevious issues to verify:\n"
                    + "\n".join(f"- {issue}" for issue in last.issues_found)
                )

        message = (
            f"Review Request (Iteration {iteration}/{session.max_iterations}):\n"
            f"Files: {', '.join(session.files)}\n"
            f"Author: {session.author_id}"
            f"{previous_feedback}"
        )

        try:
            self.messaging.send_message(
                sender_id=session.author_id,
                recipient_id=session.reviewer_id,
                msg_type=MessageType.REVIEW_REQUEST,
                content=message,
            )
        except Exception as e:
            print(f"⚠️  Failed to send review request: {e}")

    async def submit_review(
        self,
        session_id: str,
        result: ReviewResult,
        feedback: str = "",
        issues_found: list[str] | None = None,
        suggestions: list[str] | None = None,
    ) -> ReviewIteration:
        """Submit a review for an iteration.

        Args:
            session_id: Session identifier
            result: Review result
            feedback: Detailed feedback
            issues_found: Issues that need fixing
            suggestions: Improvement suggestions

        Returns:
            Created ReviewIteration
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session not found: {session_id}")

        session = self.sessions[session_id]

        if session.is_complete:
            raise ValueError(f"Session {session_id} is already complete")

        iteration = ReviewIteration(
            iteration_number=session.current_iteration + 1,
            reviewer_id=session.reviewer_id,
            author_id=session.author_id,
            result=result,
            feedback=feedback,
            issues_found=issues_found or [],
            suggestions=suggestions or [],
        )

        session.add_iteration(iteration)

        # Notify author of review result
        await self._send_review_feedback(session, iteration)

        if result == ReviewResult.APPROVED:
            print(f"✅ Review approved on iteration {iteration.iteration_number}")
            await self._handle_approval(session)
        elif result == ReviewResult.REQUEST_CHANGES:
            if session.is_complete:
                print(f"❌ Review failed after {self.max_iterations} iterations")
                await self._handle_failure(session)
            else:
                print(f"🔄 Changes requested (iteration {iteration.iteration_number})")
                # Request next iteration after author addresses feedback
        else:  # NEEDS_DISCUSSION
            print(f"💬 Discussion needed on iteration {iteration.iteration_number}")

        return iteration

    async def _send_review_feedback(
        self,
        session: AutonomousReviewSession,
        iteration: ReviewIteration,
    ) -> None:
        """Send review feedback to the author."""
        status_emoji = {
            ReviewResult.APPROVED: "✅",
            ReviewResult.REQUEST_CHANGES: "⚠️",
            ReviewResult.NEEDS_DISCUSSION: "💬",
        }

        message = (
            f"{status_emoji[iteration.result]} Review Feedback "
            f"(Iteration {iteration.iteration_number}):\n\n"
            f"Result: {iteration.result.value}\n"
        )

        if iteration.feedback:
            message += f"\nFeedback:\n{iteration.feedback}\n"

        if iteration.issues_found:
            message += "\nIssues to fix:\n"
            for issue in iteration.issues_found:
                message += f"  - {issue}\n"

        if iteration.suggestions:
            message += "\nSuggestions:\n"
            for suggestion in iteration.suggestions:
                message += f"  - {suggestion}\n"

        try:
            msg_type = (
                MessageType.INFO
                if iteration.result == ReviewResult.APPROVED
                else MessageType.REVIEW_REQUEST
            )
            self.messaging.send_message(
                sender_id=session.reviewer_id,
                recipient_id=session.author_id,
                msg_type=msg_type,
                content=message,
            )
        except Exception as e:
            print(f"⚠️  Failed to send review feedback: {e}")

    async def _handle_approval(self, session: AutonomousReviewSession) -> None:
        """Handle successful review approval."""
        try:
            # Update learning system if available
            from claudeswarm.learning import LearningSystem

            learning = LearningSystem()
            # Record positive interaction
            learning.record_task_completed(
                task=None,  # Would need task object
                success=True,
                skills=["code-review"],
            )
        except ImportError:
            pass

        # Update context if available
        if session.context_id:
            try:
                from claudeswarm.context import ContextStore

                store = ContextStore()
                store.add_decision(
                    session.context_id,
                    decision=f"Code review approved for {', '.join(session.files)}",
                    by=session.reviewer_id,
                    reason=f"Approved after {len(session.iterations)} iterations",
                )
            except ImportError:
                pass

    async def _handle_failure(self, session: AutonomousReviewSession) -> None:
        """Handle review failure after max iterations."""
        message = (
            f"❌ Code review failed after {self.max_iterations} iterations.\n"
            f"Files: {', '.join(session.files)}\n"
            f"Consider manual review or breaking down changes."
        )

        try:
            self.messaging.send_message(
                sender_id=session.reviewer_id,
                recipient_id=session.author_id,
                msg_type=MessageType.BLOCKED,
                content=message,
            )
        except Exception as e:
            print(f"⚠️  Failed to send failure notification: {e}")

    async def request_next_iteration(self, session_id: str) -> None:
        """Request the next review iteration after author addresses feedback.

        Args:
            session_id: Session identifier
        """
        if session_id not in self.sessions:
            raise ValueError(f"Session not found: {session_id}")

        session = self.sessions[session_id]

        if session.is_complete:
            raise ValueError(f"Session {session_id} is already complete")

        # Send another review request
        await self._send_review_request(session)
        print(f"🔄 Requested iteration {session.current_iteration + 1} for {session_id}")

    def get_session(self, session_id: str) -> AutonomousReviewSession | None:
        """Get a review session by ID."""
        return self.sessions.get(session_id)

    def get_active_sessions(self) -> list[AutonomousReviewSession]:
        """Get all active (non-completed) review sessions."""
        return [s for s in self.sessions.values() if not s.is_complete]

    def get_session_summary(self, session_id: str) -> dict[str, Any] | None:
        """Get a summary of a review session."""
        session = self.sessions.get(session_id)
        if not session:
            return None

        total_issues = sum(len(i.issues_found) for i in session.iterations)
        total_suggestions = sum(len(i.suggestions) for i in session.iterations)

        return {
            "session_id": session.session_id,
            "author": session.author_id,
            "reviewer": session.reviewer_id,
            "files": session.files,
            "status": session.status,
            "iterations": session.current_iteration,
            "max_iterations": session.max_iterations,
            "total_issues_found": total_issues,
            "total_suggestions": total_suggestions,
            "approved": session.is_approved,
            "created_at": session.created_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        }
