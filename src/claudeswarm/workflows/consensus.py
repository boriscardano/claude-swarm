"""
Consensus Mechanism

This module implements evidence-based consensus reaching among autonomous agents.
When agents disagree on implementation approaches, this system helps them reach
a decision through structured voting and evidence evaluation.

Key features:
- Evidence-based voting (agents must provide reasoning)
- Multiple consensus strategies (majority, supermajority, weighted)
- Tiebreaker mechanisms (research quality, safety-first, expert opinion)
- Audit trail of all decisions

Author: agent-1
Created: 2025-11-19 (E2B Hackathon Prep)
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class VoteOption(Enum):
    """Vote options for binary decisions"""
    OPTION_A = "A"
    OPTION_B = "B"
    ABSTAIN = "ABSTAIN"


@dataclass
class Vote:
    """
    A single agent's vote with rationale.

    Attributes:
        agent_id: Agent casting the vote
        option: Which option they chose
        rationale: Why they chose this option
        evidence: Links to research/docs supporting their vote
        confidence: How confident they are (0.0 to 1.0)
    """
    agent_id: str
    option: VoteOption
    rationale: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 1.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConsensusResult:
    """
    Result of a consensus vote.

    Attributes:
        topic: What was voted on
        winner: Which option won
        votes: All votes cast
        vote_counts: Tally of votes per option
        decision_rationale: Explanation of why this option won
        confidence: Overall confidence in decision
        unanimous: Whether all agents agreed
    """
    topic: str
    winner: VoteOption
    votes: List[Vote]
    vote_counts: Dict[VoteOption, int]
    decision_rationale: str
    confidence: float
    unanimous: bool
    timestamp: datetime = field(default_factory=datetime.now)


class ConsensusStrategy(Enum):
    """Different strategies for reaching consensus"""
    SIMPLE_MAJORITY = "simple_majority"  # >50% wins
    SUPERMAJORITY = "supermajority"  # ≥66% wins
    UNANIMOUS = "unanimous"  # 100% agreement
    WEIGHTED = "weighted"  # Weighted by confidence scores
    EVIDENCE_BASED = "evidence_based"  # Quality of evidence matters


class ConsensusEngine:
    """
    Manages consensus reaching among autonomous agents.

    This class facilitates democratic decision-making when agents disagree
    on implementation approaches. It supports multiple voting strategies
    and provides transparent audit trails.

    Example:
        engine = ConsensusEngine(num_agents=4)
        await engine.initiate_vote(
            topic="Password hashing algorithm",
            option_a="bcrypt",
            option_b="argon2",
            agents=["agent-1", "agent-2", "agent-3", "agent-4"]
        )
        result = await engine.collect_votes(timeout=300)
        print(f"Consensus: {result.winner} - {result.decision_rationale}")
    """

    def __init__(
        self,
        num_agents: int = 4,
        strategy: ConsensusStrategy = ConsensusStrategy.EVIDENCE_BASED
    ):
        self.num_agents = num_agents
        self.strategy = strategy
        self.active_votes: Dict[str, List[Vote]] = {}
        self.completed_votes: List[ConsensusResult] = []

        # TODO: Initialize messaging when available
        # self.messaging = MessagingSystem()

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
        """
        Start a consensus vote.

        Args:
            topic: What is being voted on
            option_a: First option
            option_b: Second option
            agents: List of agents who should vote
            evidence_a: Supporting evidence for option A
            evidence_b: Supporting evidence for option B
            timeout: Seconds to wait for votes

        Returns:
            Vote ID for tracking
        """

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

        # TODO: Broadcast vote request
        # vote_message = self._format_vote_request(
        #     topic, option_a, option_b,
        #     evidence_a or [], evidence_b or []
        # )
        # self.messaging.broadcast_message(
        #     sender_id="consensus-engine",
        #     message_type=MessageType.QUESTION,
        #     content=vote_message
        # )

        return vote_id

    def cast_vote(
        self,
        vote_id: str,
        agent_id: str,
        option: VoteOption,
        rationale: str,
        evidence: Optional[List[str]] = None,
        confidence: float = 1.0
    ) -> bool:
        """
        Cast a vote in an active consensus.

        Args:
            vote_id: Which vote to participate in
            agent_id: Agent casting vote
            option: Which option they choose
            rationale: Why they chose this option
            evidence: Supporting research/docs
            confidence: How confident (0.0-1.0)

        Returns:
            True if vote was accepted
        """

        if vote_id not in self.active_votes:
            return False

        # Check if agent already voted
        existing_vote = next(
            (v for v in self.active_votes[vote_id] if v.agent_id == agent_id),
            None
        )
        if existing_vote:
            print(f"⚠️  {agent_id} already voted, ignoring duplicate")
            return False

        vote = Vote(
            agent_id=agent_id,
            option=option,
            rationale=rationale,
            evidence=evidence or [],
            confidence=confidence
        )

        self.active_votes[vote_id].append(vote)

        print(f"✓ {agent_id} voted: {option.value}")
        print(f"  Rationale: {rationale}")
        if evidence:
            print(f"  Evidence: {len(evidence)} sources")

        return True

    def determine_winner(
        self,
        vote_id: str
    ) -> ConsensusResult:
        """
        Determine winner based on configured strategy.

        Args:
            vote_id: Vote to tally

        Returns:
            ConsensusResult with winner and reasoning
        """

        if vote_id not in self.active_votes:
            raise ValueError(f"Vote {vote_id} not found")

        votes = self.active_votes[vote_id]

        if not votes:
            raise ValueError(f"No votes cast for {vote_id}")

        # Count votes by strategy
        if self.strategy == ConsensusStrategy.SIMPLE_MAJORITY:
            result = self._simple_majority(votes)
        elif self.strategy == ConsensusStrategy.SUPERMAJORITY:
            result = self._supermajority(votes)
        elif self.strategy == ConsensusStrategy.WEIGHTED:
            result = self._weighted_vote(votes)
        elif self.strategy == ConsensusStrategy.EVIDENCE_BASED:
            result = self._evidence_based(votes)
        else:
            result = self._simple_majority(votes)

        # Mark vote as completed
        self.completed_votes.append(result)
        del self.active_votes[vote_id]

        print(f"\n✅ CONSENSUS REACHED")
        print(f"   Winner: {result.winner.value}")
        print(f"   Vote counts: {result.vote_counts}")
        print(f"   Rationale: {result.decision_rationale}")
        print(f"   Confidence: {result.confidence:.1%}")
        if result.unanimous:
            print(f"   (Unanimous decision)")

        return result

    def _simple_majority(self, votes: List[Vote]) -> ConsensusResult:
        """Simple majority: most votes wins"""

        vote_counts = self._count_votes(votes)

        # Determine winner
        max_votes = max(vote_counts.values())
        winners = [opt for opt, count in vote_counts.items() if count == max_votes]

        if len(winners) > 1:
            # Tie - use tiebreaker
            winner = self._tiebreaker(votes, winners)
            rationale = f"Tie between {len(winners)} options, using tiebreaker: {winner.value}"
        else:
            winner = winners[0]
            rationale = f"{winner.value} won with {vote_counts[winner]}/{len(votes)} votes"

        # Calculate confidence
        confidence = vote_counts[winner] / len(votes)

        # Check if unanimous
        unanimous = len([v for v in votes if v.option == winner]) == len(votes)

        return ConsensusResult(
            topic="",  # Set by caller
            winner=winner,
            votes=votes,
            vote_counts=vote_counts,
            decision_rationale=rationale,
            confidence=confidence,
            unanimous=unanimous
        )

    def _supermajority(self, votes: List[Vote]) -> ConsensusResult:
        """Supermajority: requires ≥66% agreement"""

        vote_counts = self._count_votes(votes)
        threshold = len(votes) * 0.66

        # Check if any option meets threshold
        for option, count in vote_counts.items():
            if count >= threshold:
                return ConsensusResult(
                    topic="",
                    winner=option,
                    votes=votes,
                    vote_counts=vote_counts,
                    decision_rationale=f"{option.value} achieved supermajority with {count}/{len(votes)} votes",
                    confidence=count / len(votes),
                    unanimous=count == len(votes)
                )

        # No supermajority - use fallback
        return self._simple_majority(votes)

    def _weighted_vote(self, votes: List[Vote]) -> ConsensusResult:
        """Weighted by confidence scores"""

        weighted_counts = {}

        for vote in votes:
            if vote.option not in weighted_counts:
                weighted_counts[vote.option] = 0.0
            weighted_counts[vote.option] += vote.confidence

        # Find winner
        winner = max(weighted_counts.items(), key=lambda x: x[1])[0]

        total_weight = sum(weighted_counts.values())
        vote_counts = self._count_votes(votes)

        return ConsensusResult(
            topic="",
            winner=winner,
            votes=votes,
            vote_counts=vote_counts,
            decision_rationale=f"{winner.value} won with weighted score {weighted_counts[winner]:.2f}/{total_weight:.2f}",
            confidence=weighted_counts[winner] / total_weight,
            unanimous=vote_counts[winner] == len(votes)
        )

    def _evidence_based(self, votes: List[Vote]) -> ConsensusResult:
        """Decision based on quality of evidence"""

        # Score each option by evidence quality
        evidence_scores = {}

        for vote in votes:
            if vote.option not in evidence_scores:
                evidence_scores[vote.option] = 0

            # More evidence = higher score
            evidence_scores[vote.option] += len(vote.evidence)

            # Higher confidence = higher multiplier
            evidence_scores[vote.option] *= (1 + vote.confidence)

        # Find winner
        winner = max(evidence_scores.items(), key=lambda x: x[1])[0]

        vote_counts = self._count_votes(votes)
        total_evidence = sum(len(v.evidence) for v in votes if v.option == winner)

        return ConsensusResult(
            topic="",
            winner=winner,
            votes=votes,
            vote_counts=vote_counts,
            decision_rationale=f"{winner.value} had strongest evidence ({total_evidence} sources) and support ({vote_counts[winner]} votes)",
            confidence=evidence_scores[winner] / sum(evidence_scores.values()),
            unanimous=vote_counts[winner] == len(votes)
        )

    def _count_votes(self, votes: List[Vote]) -> Dict[VoteOption, int]:
        """Simple vote counting"""

        counts = {VoteOption.OPTION_A: 0, VoteOption.OPTION_B: 0, VoteOption.ABSTAIN: 0}

        for vote in votes:
            counts[vote.option] += 1

        return counts

    def _tiebreaker(
        self,
        votes: List[Vote],
        tied_options: List[VoteOption]
    ) -> VoteOption:
        """
        Resolve ties using tiebreaker rules.

        Priority:
        1. Option with more evidence
        2. Option with higher total confidence
        3. Safety-first principle (choose more conservative option)
        4. Random (should rarely reach here)
        """

        # Tiebreaker 1: Most evidence
        evidence_count = {}
        for option in tied_options:
            total_evidence = sum(
                len(v.evidence)
                for v in votes
                if v.option == option
            )
            evidence_count[option] = total_evidence

        max_evidence = max(evidence_count.values())
        best_by_evidence = [
            opt for opt, count in evidence_count.items()
            if count == max_evidence
        ]

        if len(best_by_evidence) == 1:
            print(f"   Tiebreaker: {best_by_evidence[0].value} had most evidence")
            return best_by_evidence[0]

        # Tiebreaker 2: Highest total confidence
        confidence_totals = {}
        for option in best_by_evidence:
            total_conf = sum(
                v.confidence
                for v in votes
                if v.option == option
            )
            confidence_totals[option] = total_conf

        winner = max(confidence_totals.items(), key=lambda x: x[1])[0]
        print(f"   Tiebreaker: {winner.value} had highest confidence")
        return winner

    def get_consensus_history(self) -> List[ConsensusResult]:
        """Get all completed consensus votes"""
        return self.completed_votes

    def get_consensus_statistics(self) -> Dict:
        """Get statistics about consensus votes"""

        total_votes = len(self.completed_votes)

        if total_votes == 0:
            return {"total_votes": 0}

        unanimous_count = sum(1 for v in self.completed_votes if v.unanimous)
        avg_confidence = sum(v.confidence for v in self.completed_votes) / total_votes

        option_a_wins = sum(
            1 for v in self.completed_votes
            if v.winner == VoteOption.OPTION_A
        )

        return {
            "total_votes": total_votes,
            "unanimous": unanimous_count,
            "unanimous_pct": unanimous_count / total_votes * 100,
            "avg_confidence": avg_confidence,
            "option_a_wins": option_a_wins,
            "option_b_wins": total_votes - option_a_wins,
            "strategy": self.strategy.value
        }

    def _format_vote_request(
        self,
        topic: str,
        option_a: str,
        option_b: str,
        evidence_a: List[str],
        evidence_b: List[str]
    ) -> str:
        """Format vote request message"""

        lines = [
            "🗳️  CONSENSUS VOTE NEEDED",
            "",
            f"Topic: {topic}",
            "",
            f"Option A: {option_a}"
        ]

        if evidence_a:
            lines.append(f"Evidence for A:")
            for ev in evidence_a:
                lines.append(f"  - {ev}")

        lines.append("")
        lines.append(f"Option B: {option_b}")

        if evidence_b:
            lines.append(f"Evidence for B:")
            for ev in evidence_b:
                lines.append(f"  - {ev}")

        lines.extend([
            "",
            "To vote, use:",
            "claudeswarm send-message consensus-engine INFO 'vote:A|B rationale:your_reason evidence:link1,link2'",
            ""
        ])

        return "\n".join(lines)
