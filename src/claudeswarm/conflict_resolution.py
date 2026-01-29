"""Autonomous conflict resolution system for Claude Swarm.

This module implements strategies for resolving conflicts between agents
without human intervention. It handles:
- File lock conflicts
- Resource contention
- Task priority disputes
- Merge conflicts

Resolution Strategies (in order of preference):
1. Priority-based: Higher priority task wins
2. Seniority: Agent working longer gets precedence
3. Merge: If changes are compatible, auto-merge
4. Negotiation: Agents negotiate through protocol
5. Escalation: Only escalate to human if all strategies fail

The system uses a negotiation protocol where:
1. Conflict is detected
2. Agents exchange their task context
3. Resolution strategy is applied
4. Winner proceeds, loser backs off or waits
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from .file_lock import FileLock, FileLockTimeout
from .locking import LockConflict, LockManager
from .logging_config import get_logger
from .project import get_project_root
from .tasks import Task, TaskManager, TaskPriority

__all__ = [
    "ResolutionStrategy",
    "ConflictType",
    "Conflict",
    "Resolution",
    "ConflictResolver",
    "get_conflict_log_path",
    "NegotiationMessage",
]

# Constants
CONFLICT_LOG_FILENAME = "CONFLICT_LOG.json"
CONFLICT_LOCK_TIMEOUT_SECONDS = 5.0
MAX_CONFLICT_LOG_ENTRIES = 500
NEGOTIATION_TIMEOUT_SECONDS = 30.0
MAX_NEGOTIATION_ROUNDS = 5

# Configure logging
logger = get_logger(__name__)


class ConflictType(Enum):
    """Types of conflicts that can occur."""

    FILE_LOCK = "file_lock"  # Two agents want to edit same file
    RESOURCE = "resource"  # Generic resource contention
    TASK_CLAIM = "task_claim"  # Two agents claim same task
    MERGE = "merge"  # Conflicting changes to same code


class ResolutionStrategy(Enum):
    """Strategies for resolving conflicts."""

    PRIORITY = "priority"  # Higher priority task wins
    SENIORITY = "seniority"  # Agent working longer wins
    MERGE = "merge"  # Auto-merge if possible
    NEGOTIATION = "negotiation"  # Agents negotiate
    ESCALATE = "escalate"  # Escalate to human
    YIELD = "yield"  # Requesting agent yields
    WAIT = "wait"  # Requesting agent waits


@dataclass
class NegotiationMessage:
    """Message exchanged during conflict negotiation.

    Attributes:
        from_agent: Agent sending the message
        to_agent: Agent receiving the message
        conflict_id: ID of the conflict being negotiated
        round_number: Current negotiation round
        action: Proposed action (yield, insist, compromise)
        task_priority: Priority of the agent's task
        task_started_at: When the agent started working
        files_involved: Files the agent is working on
        proposal: Specific proposal for resolution
        metadata: Additional data
    """

    from_agent: str
    to_agent: str
    conflict_id: str
    round_number: int
    action: str  # yield, insist, compromise
    task_priority: str = "normal"
    task_started_at: str | None = None
    files_involved: list[str] = field(default_factory=list)
    proposal: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NegotiationMessage:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class Conflict:
    """Represents a detected conflict.

    Attributes:
        conflict_id: Unique conflict identifier
        conflict_type: Type of conflict
        agents_involved: List of agent IDs involved
        resource: The contested resource (file path, task ID, etc.)
        detected_at: When the conflict was detected
        status: Current status (pending, resolving, resolved, escalated)
        resolution: How the conflict was resolved
        negotiations: History of negotiation messages
        metadata: Additional data
    """

    conflict_id: str
    conflict_type: ConflictType
    agents_involved: list[str]
    resource: str
    detected_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "pending"  # pending, resolving, resolved, escalated
    resolution: Resolution | None = None
    negotiations: list[NegotiationMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Handle type conversions."""
        if isinstance(self.conflict_type, str):
            self.conflict_type = ConflictType(self.conflict_type)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type.value,
            "agents_involved": self.agents_involved,
            "resource": self.resource,
            "detected_at": self.detected_at,
            "status": self.status,
            "metadata": self.metadata,
        }
        if self.resolution:
            data["resolution"] = self.resolution.to_dict()
        data["negotiations"] = [n.to_dict() for n in self.negotiations]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conflict:
        """Create from dictionary."""
        resolution = None
        if "resolution" in data and data["resolution"]:
            resolution = Resolution.from_dict(data["resolution"])

        negotiations = [NegotiationMessage.from_dict(n) for n in data.get("negotiations", [])]

        return cls(
            conflict_id=data["conflict_id"],
            conflict_type=ConflictType(data["conflict_type"]),
            agents_involved=data["agents_involved"],
            resource=data["resource"],
            detected_at=data.get("detected_at", datetime.now(UTC).isoformat()),
            status=data.get("status", "pending"),
            resolution=resolution,
            negotiations=negotiations,
            metadata=data.get("metadata", {}),
        )


@dataclass
class Resolution:
    """Result of conflict resolution.

    Attributes:
        conflict_id: ID of the resolved conflict
        strategy_used: Strategy that resolved the conflict
        winner: Agent that won the resource
        loser_action: What the losing agent should do
        resolved_at: When resolution occurred
        reason: Explanation of the resolution
        automatic: Whether resolution was automatic
        metadata: Additional data
    """

    conflict_id: str
    strategy_used: ResolutionStrategy
    winner: str
    loser_action: str  # yield, wait, retry
    resolved_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reason: str = ""
    automatic: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Handle type conversions."""
        if isinstance(self.strategy_used, str):
            self.strategy_used = ResolutionStrategy(self.strategy_used)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "conflict_id": self.conflict_id,
            "strategy_used": self.strategy_used.value,
            "winner": self.winner,
            "loser_action": self.loser_action,
            "resolved_at": self.resolved_at,
            "reason": self.reason,
            "automatic": self.automatic,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Resolution:
        """Create from dictionary."""
        return cls(**data)


def get_conflict_log_path(project_root: Path | None = None) -> Path:
    """Get the path to the conflict log file.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to CONFLICT_LOG.json
    """
    root = get_project_root(project_root)
    return root / CONFLICT_LOG_FILENAME


class ConflictResolver:
    """Resolves conflicts between agents autonomously.

    Implements a hierarchy of resolution strategies and manages
    the negotiation protocol between agents.
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize the conflict resolver.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = get_project_root(project_root)
        self.log_path = get_conflict_log_path(self.project_root)
        self.lock_manager = LockManager(project_root=self.project_root)
        self.task_manager = TaskManager(self.project_root)
        self._lock = threading.Lock()
        self._active_conflicts: dict[str, Conflict] = {}
        self._pending_negotiations: dict[str, list[NegotiationMessage]] = {}

    def _read_log(self) -> list[Conflict]:
        """Read conflict log from file.

        Returns:
            List of conflicts
        """
        if not self.log_path.exists():
            return []

        try:
            with FileLock(self.log_path, timeout=CONFLICT_LOCK_TIMEOUT_SECONDS, shared=True):
                with open(self.log_path, encoding="utf-8") as f:
                    data = json.load(f)
                return [Conflict.from_dict(c) for c in data.get("conflicts", [])]

        except FileLockTimeout:
            logger.error(f"Timeout acquiring lock on {self.log_path}")
            return []
        except Exception as e:
            logger.warning(f"Error reading conflict log: {e}")
            return []

    def _write_log(self, conflicts: list[Conflict]) -> None:
        """Write conflict log to file.

        Args:
            conflicts: List of conflicts
        """
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # Trim if too long
        if len(conflicts) > MAX_CONFLICT_LOG_ENTRIES:
            conflicts = conflicts[-MAX_CONFLICT_LOG_ENTRIES:]

        data = {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "conflicts": [c.to_dict() for c in conflicts],
        }

        try:
            with FileLock(self.log_path, timeout=CONFLICT_LOCK_TIMEOUT_SECONDS, shared=False):
                temp_path = self.log_path.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                temp_path.replace(self.log_path)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring write lock on {self.log_path}")
            raise
        except Exception as e:
            logger.error(f"Error writing conflict log: {e}")
            raise

    def _record_conflict(self, conflict: Conflict) -> None:
        """Record a conflict to the log.

        Args:
            conflict: Conflict to record
        """
        with self._lock:
            conflicts = self._read_log()
            conflicts.append(conflict)
            self._write_log(conflicts)

    def _update_conflict(self, conflict: Conflict) -> None:
        """Update an existing conflict in the log.

        Args:
            conflict: Conflict to update
        """
        with self._lock:
            conflicts = self._read_log()
            for i, c in enumerate(conflicts):
                if c.conflict_id == conflict.conflict_id:
                    conflicts[i] = conflict
                    break
            else:
                conflicts.append(conflict)
            self._write_log(conflicts)

    def detect_file_lock_conflict(
        self,
        filepath: str,
        requesting_agent: str,
        lock_conflict: LockConflict,
    ) -> Conflict:
        """Create a conflict record from a lock conflict.

        Args:
            filepath: Path to the contested file
            requesting_agent: Agent that tried to acquire lock
            lock_conflict: The lock conflict from locking system

        Returns:
            Conflict record
        """
        import uuid

        conflict = Conflict(
            conflict_id=str(uuid.uuid4()),
            conflict_type=ConflictType.FILE_LOCK,
            agents_involved=[requesting_agent, lock_conflict.current_holder],
            resource=filepath,
            metadata={
                "locked_at": lock_conflict.locked_at.isoformat(),
                "lock_reason": lock_conflict.reason,
            },
        )

        self._active_conflicts[conflict.conflict_id] = conflict
        self._record_conflict(conflict)

        logger.info(
            f"Detected file lock conflict: {filepath} "
            f"(requested by {requesting_agent}, held by {lock_conflict.current_holder})"
        )

        return conflict

    def resolve_by_priority(
        self,
        conflict: Conflict,
        requesting_task: Task | None,
        holding_task: Task | None,
    ) -> Resolution | None:
        """Try to resolve conflict by task priority.

        Args:
            conflict: The conflict to resolve
            requesting_task: Task of the requesting agent
            holding_task: Task of the current holder

        Returns:
            Resolution if priority comparison works, None otherwise
        """
        if not requesting_task or not holding_task:
            return None

        priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.NORMAL: 2,
            TaskPriority.LOW: 3,
        }

        req_priority = priority_order.get(requesting_task.priority, 2)
        hold_priority = priority_order.get(holding_task.priority, 2)

        if req_priority < hold_priority:
            # Requesting agent has higher priority
            winner = conflict.agents_involved[0]  # Requester
            reason = (
                f"Task priority: {requesting_task.priority.value} > {holding_task.priority.value}"
            )
            loser_action = "yield"
        elif hold_priority < req_priority:
            # Holder has higher priority
            winner = conflict.agents_involved[1]  # Holder
            reason = (
                f"Task priority: {holding_task.priority.value} > {requesting_task.priority.value}"
            )
            loser_action = "wait"
        else:
            # Same priority - can't resolve by priority alone
            return None

        return Resolution(
            conflict_id=conflict.conflict_id,
            strategy_used=ResolutionStrategy.PRIORITY,
            winner=winner,
            loser_action=loser_action,
            reason=reason,
        )

    def resolve_by_seniority(
        self,
        conflict: Conflict,
    ) -> Resolution:
        """Resolve conflict by seniority (first to start wins).

        Args:
            conflict: The conflict to resolve

        Returns:
            Resolution based on seniority
        """
        # The holder (second agent) was there first
        winner = conflict.agents_involved[1]

        return Resolution(
            conflict_id=conflict.conflict_id,
            strategy_used=ResolutionStrategy.SENIORITY,
            winner=winner,
            loser_action="wait",
            reason="Current holder has seniority (was working first)",
        )

    def _get_agent_task(self, agent_id: str) -> Task | None:
        """Get the active task for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Active task or None
        """
        tasks = self.task_manager.get_agent_tasks(agent_id)
        # Return the most recently assigned active task
        active_tasks = [t for t in tasks if t.is_active()]
        return active_tasks[0] if active_tasks else None

    def resolve_conflict(
        self,
        conflict: Conflict,
        strategies: list[ResolutionStrategy] | None = None,
    ) -> Resolution:
        """Resolve a conflict using the specified strategies.

        Tries strategies in order until one succeeds.

        Args:
            conflict: The conflict to resolve
            strategies: Strategies to try (default: priority, seniority)

        Returns:
            Resolution result
        """
        if strategies is None:
            strategies = [
                ResolutionStrategy.PRIORITY,
                ResolutionStrategy.SENIORITY,
            ]

        conflict.status = "resolving"

        # Get tasks for involved agents
        tasks = {}
        for agent_id in conflict.agents_involved:
            tasks[agent_id] = self._get_agent_task(agent_id)

        requesting_agent = conflict.agents_involved[0]
        holding_agent = conflict.agents_involved[1] if len(conflict.agents_involved) > 1 else None

        requesting_task = tasks.get(requesting_agent)
        holding_task = tasks.get(holding_agent) if holding_agent else None

        resolution = None

        for strategy in strategies:
            if strategy == ResolutionStrategy.PRIORITY:
                resolution = self.resolve_by_priority(conflict, requesting_task, holding_task)
            elif strategy == ResolutionStrategy.SENIORITY:
                resolution = self.resolve_by_seniority(conflict)
            elif strategy == ResolutionStrategy.YIELD:
                # Requester yields
                resolution = Resolution(
                    conflict_id=conflict.conflict_id,
                    strategy_used=ResolutionStrategy.YIELD,
                    winner=holding_agent or requesting_agent,
                    loser_action="yield",
                    reason="Requester chose to yield",
                )

            if resolution:
                break

        # Fallback to seniority if nothing worked
        if not resolution:
            resolution = self.resolve_by_seniority(conflict)

        # Update conflict
        conflict.resolution = resolution
        conflict.status = "resolved"
        self._update_conflict(conflict)

        # Clean up
        if conflict.conflict_id in self._active_conflicts:
            del self._active_conflicts[conflict.conflict_id]

        logger.info(
            f"Resolved conflict {conflict.conflict_id}: "
            f"{resolution.winner} wins via {resolution.strategy_used.value}"
        )

        return resolution

    def handle_lock_conflict(
        self,
        filepath: str,
        requesting_agent: str,
        lock_conflict: LockConflict,
    ) -> Resolution:
        """Handle a file lock conflict automatically.

        This is the main entry point for handling lock conflicts.
        It detects the conflict, applies resolution strategies,
        and returns the result.

        Args:
            filepath: Path to the contested file
            requesting_agent: Agent that tried to acquire lock
            lock_conflict: The lock conflict

        Returns:
            Resolution with winner and loser action
        """
        conflict = self.detect_file_lock_conflict(filepath, requesting_agent, lock_conflict)
        return self.resolve_conflict(conflict)

    def negotiate(
        self,
        conflict: Conflict,
        message: NegotiationMessage,
    ) -> Resolution | None:
        """Process a negotiation message.

        Args:
            conflict: The conflict being negotiated
            message: Negotiation message from an agent

        Returns:
            Resolution if negotiation concludes, None if ongoing
        """
        conflict.negotiations.append(message)

        # Get messages from both agents
        agent_messages: dict[str, list[NegotiationMessage]] = {}
        for neg in conflict.negotiations:
            if neg.from_agent not in agent_messages:
                agent_messages[neg.from_agent] = []
            agent_messages[neg.from_agent].append(neg)

        # Check if both agents have responded in the current round
        current_round = message.round_number
        round_messages = [n for n in conflict.negotiations if n.round_number == current_round]

        if len(round_messages) < 2:
            # Wait for other agent's response
            return None

        # Both have responded - evaluate
        actions = {n.from_agent: n.action for n in round_messages}

        # Resolution rules:
        # - If one yields, other wins
        # - If both yield, use priority
        # - If both insist, check if max rounds reached
        # - If both compromise, try to merge

        yielders = [a for a, action in actions.items() if action == "yield"]
        insisters = [a for a, action in actions.items() if action == "insist"]

        if len(yielders) == 1:
            # One yielded
            winner = [a for a in actions if a not in yielders][0]
            loser = yielders[0]
            resolution = Resolution(
                conflict_id=conflict.conflict_id,
                strategy_used=ResolutionStrategy.NEGOTIATION,
                winner=winner,
                loser_action="yield",
                reason=f"{loser} yielded during negotiation",
            )
        elif len(yielders) == 2:
            # Both yielded - use priority
            return self.resolve_conflict(
                conflict,
                strategies=[ResolutionStrategy.PRIORITY, ResolutionStrategy.SENIORITY],
            )
        elif len(insisters) == 2:
            # Stalemate
            if current_round >= MAX_NEGOTIATION_ROUNDS:
                # Max rounds reached - escalate or use seniority
                logger.warning(
                    f"Negotiation stalemate after {current_round} rounds, using seniority"
                )
                return self.resolve_by_seniority(conflict)
            # Continue negotiation
            return None
        else:
            # Mixed - treat compromise as partial yield
            # Whoever insisted wins
            if insisters:
                winner = insisters[0]
                loser = [a for a in actions if a not in insisters][0]
                resolution = Resolution(
                    conflict_id=conflict.conflict_id,
                    strategy_used=ResolutionStrategy.NEGOTIATION,
                    winner=winner,
                    loser_action="wait",
                    reason=f"{winner} insisted while {loser} compromised",
                )
            else:
                # Default to seniority
                return self.resolve_by_seniority(conflict)

        conflict.resolution = resolution
        conflict.status = "resolved"
        self._update_conflict(conflict)

        return resolution

    def get_active_conflicts(self) -> list[Conflict]:
        """Get all active (unresolved) conflicts.

        Returns:
            List of active conflicts
        """
        conflicts = self._read_log()
        return [c for c in conflicts if c.status in ("pending", "resolving")]

    def get_conflict_history(
        self,
        agent_id: str | None = None,
        resource: str | None = None,
        limit: int = 50,
    ) -> list[Conflict]:
        """Get conflict history with optional filtering.

        Args:
            agent_id: Filter by involved agent
            resource: Filter by resource
            limit: Maximum number of results

        Returns:
            List of conflicts
        """
        conflicts = self._read_log()

        if agent_id:
            conflicts = [c for c in conflicts if agent_id in c.agents_involved]

        if resource:
            conflicts = [c for c in conflicts if c.resource == resource]

        # Most recent first
        conflicts.reverse()

        return conflicts[:limit]

    def get_conflict_stats(self) -> dict[str, Any]:
        """Get conflict resolution statistics.

        Returns:
            Dictionary with statistics
        """
        conflicts = self._read_log()

        if not conflicts:
            return {
                "total_conflicts": 0,
                "resolved": 0,
                "pending": 0,
                "escalated": 0,
                "resolution_strategies": {},
                "conflict_types": {},
                "avg_resolution_time_seconds": 0,
            }

        resolved = [c for c in conflicts if c.status == "resolved"]
        pending = [c for c in conflicts if c.status in ("pending", "resolving")]
        escalated = [c for c in conflicts if c.status == "escalated"]

        # Count strategies used
        strategy_counts: dict[str, int] = {}
        for c in resolved:
            if c.resolution:
                strategy = c.resolution.strategy_used.value
                strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1

        # Count conflict types
        type_counts: dict[str, int] = {}
        for c in conflicts:
            ctype = c.conflict_type.value
            type_counts[ctype] = type_counts.get(ctype, 0) + 1

        # Calculate average resolution time
        resolution_times = []
        for c in resolved:
            if c.resolution:
                try:
                    detected = datetime.fromisoformat(c.detected_at)
                    resolved_at = datetime.fromisoformat(c.resolution.resolved_at)
                    resolution_times.append((resolved_at - detected).total_seconds())
                except (ValueError, TypeError):
                    pass

        avg_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0

        return {
            "total_conflicts": len(conflicts),
            "resolved": len(resolved),
            "pending": len(pending),
            "escalated": len(escalated),
            "resolution_strategies": strategy_counts,
            "conflict_types": type_counts,
            "avg_resolution_time_seconds": round(avg_time, 2),
        }
