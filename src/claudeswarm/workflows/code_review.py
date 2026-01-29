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

from dataclasses import dataclass, field
from datetime import datetime

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
    created_at: datetime = field(default_factory=datetime.now)


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
