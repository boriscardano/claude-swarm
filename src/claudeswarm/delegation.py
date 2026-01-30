"""Skill-based task delegation system for Claude Swarm.

This module implements intelligent task routing based on agent capabilities.
It uses agent cards to match tasks with the best-suited agents based on:
- Required skills and agent proficiency
- Historical success rates
- Current availability
- Tool requirements
- Specializations

The delegation system enables autonomous agent coordination by:
1. Analyzing task requirements (keywords, file types, complexity)
2. Querying agent cards for skill matches
3. Calculating match scores using multiple factors
4. Delegating to the best-matched available agent

Example usage:
    delegation_manager = DelegationManager()
    best_agent = delegation_manager.find_best_agent(task)
    if best_agent:
        delegation_manager.delegate_task(task, best_agent.agent_id)
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agent_cards import AgentCard, AgentCardRegistry
from .file_lock import FileLock, FileLockTimeout
from .logging_config import get_logger
from .project import get_project_root
from .tasks import Task, TaskManager, TaskPriority

__all__ = [
    "DelegationManager",
    "DelegationResult",
    "SkillRequirement",
    "find_best_agent",
    "get_delegation_history_path",
    "DelegationError",
    "NoSuitableAgentError",
]

# Constants
DELEGATION_HISTORY_FILENAME = "DELEGATION_HISTORY.json"
DELEGATION_LOCK_TIMEOUT_SECONDS = 5.0
MAX_DELEGATION_HISTORY = 1000  # Max entries to keep

# Skill extraction patterns
FILE_EXTENSION_SKILLS = {
    ".py": ["python", "backend"],
    ".js": ["javascript", "frontend"],
    ".ts": ["typescript", "frontend"],
    ".tsx": ["typescript", "react", "frontend"],
    ".jsx": ["javascript", "react", "frontend"],
    ".go": ["golang", "backend"],
    ".rs": ["rust", "systems"],
    ".java": ["java", "backend"],
    ".kt": ["kotlin", "android"],
    ".swift": ["swift", "ios"],
    ".css": ["css", "styling", "frontend"],
    ".scss": ["sass", "styling", "frontend"],
    ".html": ["html", "frontend"],
    ".sql": ["sql", "database"],
    ".md": ["documentation", "markdown"],
    ".yaml": ["yaml", "configuration"],
    ".yml": ["yaml", "configuration"],
    ".json": ["json", "configuration"],
    ".toml": ["toml", "configuration"],
    ".sh": ["shell", "scripting", "bash"],
    ".dockerfile": ["docker", "devops"],
}

KEYWORD_SKILLS = {
    "test": ["testing"],
    "spec": ["testing"],
    "unit": ["testing", "unit-testing"],
    "integration": ["testing", "integration-testing"],
    "api": ["api", "backend"],
    "auth": ["authentication", "security"],
    "login": ["authentication"],
    "security": ["security"],
    "database": ["database"],
    "db": ["database"],
    "migration": ["database", "migration"],
    "docker": ["docker", "devops"],
    "deploy": ["deployment", "devops"],
    "ci": ["ci-cd", "devops"],
    "performance": ["performance", "optimization"],
    "refactor": ["refactoring", "code-quality"],
    "bug": ["debugging"],
    "fix": ["debugging"],
    "review": ["code-review"],
    "document": ["documentation"],
    "config": ["configuration"],
    "setup": ["configuration", "setup"],
}

# Configure logging
logger = get_logger(__name__)


class DelegationError(Exception):
    """Base exception for delegation errors."""

    pass


class NoSuitableAgentError(DelegationError):
    """Raised when no suitable agent can be found for a task."""

    pass


@dataclass
class SkillRequirement:
    """Represents a skill requirement for a task.

    Attributes:
        skill: The skill name
        importance: How important this skill is (0.0-1.0)
        minimum_proficiency: Minimum required proficiency (0.0-1.0)
    """

    skill: str
    importance: float = 1.0
    minimum_proficiency: float = 0.0

    def __post_init__(self):
        """Validate fields."""
        if not 0.0 <= self.importance <= 1.0:
            raise ValueError(f"importance must be between 0.0 and 1.0, got {self.importance}")
        if not 0.0 <= self.minimum_proficiency <= 1.0:
            raise ValueError(
                f"minimum_proficiency must be between 0.0 and 1.0, got {self.minimum_proficiency}"
            )


@dataclass
class DelegationResult:
    """Result of a delegation attempt.

    Attributes:
        success: Whether delegation was successful
        task_id: ID of the delegated task
        agent_id: ID of the agent the task was delegated to
        match_score: Overall match score (0.0-1.0)
        skill_matches: Individual skill match scores
        reason: Explanation for the delegation decision
        alternatives: Other agents that were considered
        timestamp: When the delegation occurred
    """

    success: bool
    task_id: str
    agent_id: str | None = None
    match_score: float = 0.0
    skill_matches: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "match_score": self.match_score,
            "skill_matches": self.skill_matches,
            "reason": self.reason,
            "alternatives": self.alternatives,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DelegationResult:
        """Create from dictionary."""
        return cls(**data)


def get_delegation_history_path(project_root: Path | None = None) -> Path:
    """Get the path to the delegation history file.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to DELEGATION_HISTORY.json
    """
    root = get_project_root(project_root)
    return root / DELEGATION_HISTORY_FILENAME


def extract_skills_from_task(task: Task) -> list[SkillRequirement]:
    """Extract skill requirements from a task.

    Analyzes the task objective, constraints, and files to determine
    what skills are needed.

    Args:
        task: The task to analyze

    Returns:
        List of skill requirements
    """
    skills: dict[str, float] = {}  # skill -> max importance

    # Extract skills from files
    for filepath in task.files:
        ext = Path(filepath).suffix.lower()
        if ext in FILE_EXTENSION_SKILLS:
            for skill in FILE_EXTENSION_SKILLS[ext]:
                skills[skill] = max(skills.get(skill, 0), 0.8)

    # Extract skills from objective and constraints
    text = f"{task.objective} {' '.join(task.constraints)}".lower()

    for keyword, keyword_skills in KEYWORD_SKILLS.items():
        if keyword in text:
            for skill in keyword_skills:
                skills[skill] = max(skills.get(skill, 0), 0.7)

    # Check for explicit skill mentions in objective
    # Pattern: requires [skill], needs [skill], [skill] expertise
    skill_pattern = r"(?:requires?|needs?|expertise in|experience with)\s+(\w+)"
    for match in re.finditer(skill_pattern, text):
        skill = match.group(1)
        skills[skill] = max(skills.get(skill, 0), 1.0)

    # Convert to SkillRequirement objects
    return [
        SkillRequirement(skill=skill, importance=importance)
        for skill, importance in sorted(skills.items(), key=lambda x: -x[1])
    ]


def calculate_agent_score(
    agent: AgentCard,
    requirements: list[SkillRequirement],
    priority_boost: float = 0.0,
) -> tuple[float, dict[str, float]]:
    """Calculate how well an agent matches task requirements.

    The scoring considers:
    - Skill matches weighted by importance
    - Historical success rates
    - Specialization bonuses
    - Availability

    Args:
        agent: The agent to evaluate
        requirements: List of skill requirements
        priority_boost: Additional boost for high-priority tasks

    Returns:
        Tuple of (overall_score, skill_matches)
    """
    if not agent.is_available():
        return 0.0, {}

    if not requirements:
        # No specific requirements - any available agent works
        return 0.5 + priority_boost, {}

    total_score = 0.0
    total_weight = 0.0
    skill_matches = {}

    for req in requirements:
        weight = req.importance
        proficiency = agent.get_skill_proficiency(req.skill)

        # Check minimum proficiency
        if proficiency < req.minimum_proficiency:
            skill_matches[req.skill] = 0.0
            continue

        # Calculate skill score
        skill_score = proficiency * weight
        skill_matches[req.skill] = proficiency

        total_score += skill_score
        total_weight += weight

    # Normalize score
    if total_weight > 0:
        base_score = total_score / total_weight
    else:
        base_score = 0.5

    # Specialization bonus
    specialization_bonus = 0.0
    for req in requirements:
        if req.skill.lower() in [s.lower() for s in agent.specializations]:
            specialization_bonus += 0.05 * req.importance

    # Cap specialization bonus
    specialization_bonus = min(specialization_bonus, 0.15)

    final_score = min(1.0, base_score + specialization_bonus + priority_boost)
    return final_score, skill_matches


class DelegationManager:
    """Manages task delegation between agents.

    Provides functionality to:
    - Find the best agent for a task
    - Delegate tasks with tracking
    - Query delegation history
    - Learn from delegation outcomes
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize the delegation manager.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = get_project_root(project_root)
        self.history_path = get_delegation_history_path(self.project_root)
        self.card_registry = AgentCardRegistry(self.project_root)
        self.task_manager = TaskManager(self.project_root)
        self._lock = threading.Lock()

    def _read_history(self) -> list[DelegationResult]:
        """Read delegation history from file.

        Returns:
            List of delegation results
        """
        if not self.history_path.exists():
            return []

        try:
            with FileLock(self.history_path, timeout=DELEGATION_LOCK_TIMEOUT_SECONDS, shared=True):
                with open(self.history_path, encoding="utf-8") as f:
                    data = json.load(f)

                return [DelegationResult.from_dict(entry) for entry in data.get("history", [])]

        except FileLockTimeout:
            logger.error(f"Timeout acquiring lock on {self.history_path}")
            return []
        except Exception as e:
            logger.warning(f"Error reading delegation history: {e}")
            return []

    def _write_history(self, history: list[DelegationResult]) -> None:
        """Write delegation history to file.

        Args:
            history: List of delegation results
        """
        self.history_path.parent.mkdir(parents=True, exist_ok=True)

        # Trim history if too long
        if len(history) > MAX_DELEGATION_HISTORY:
            history = history[-MAX_DELEGATION_HISTORY:]

        data = {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "history": [result.to_dict() for result in history],
        }

        try:
            with FileLock(
                self.history_path, timeout=DELEGATION_LOCK_TIMEOUT_SECONDS, shared=False
            ):
                temp_path = self.history_path.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                temp_path.replace(self.history_path)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring write lock on {self.history_path}")
            raise
        except Exception as e:
            logger.error(f"Error writing delegation history: {e}")
            raise

    def _record_delegation(self, result: DelegationResult) -> None:
        """Record a delegation result to history.

        Args:
            result: Delegation result to record
        """
        with self._lock:
            history = self._read_history()
            history.append(result)
            self._write_history(history)

    def find_best_agent(
        self,
        task: Task,
        exclude_agents: list[str] | None = None,
        required_tools: list[str] | None = None,
    ) -> tuple[AgentCard | None, float, dict[str, float]]:
        """Find the best agent for a task.

        Args:
            task: The task to find an agent for
            exclude_agents: Agent IDs to exclude from consideration
            required_tools: Tools the agent must have

        Returns:
            Tuple of (best_agent, match_score, skill_matches) or (None, 0.0, {})
        """
        exclude_agents = exclude_agents or []
        required_tools = required_tools or []

        # Get all available agents
        agents = self.card_registry.list_cards(availability="active")

        if not agents:
            logger.warning("No active agents available for delegation")
            return None, 0.0, {}

        # Filter by exclusions
        agents = [a for a in agents if a.agent_id not in exclude_agents]

        # Filter by required tools
        if required_tools:
            agents = [a for a in agents if all(a.has_tool(t) for t in required_tools)]

        if not agents:
            logger.warning("No agents match the required criteria")
            return None, 0.0, {}

        # Extract skill requirements
        requirements = extract_skills_from_task(task)

        # Calculate priority boost
        priority_boost = {
            TaskPriority.CRITICAL: 0.1,
            TaskPriority.HIGH: 0.05,
            TaskPriority.NORMAL: 0.0,
            TaskPriority.LOW: -0.05,
        }.get(task.priority, 0.0)

        # Score each agent
        scored_agents = []
        for agent in agents:
            score, skill_matches = calculate_agent_score(agent, requirements, priority_boost)
            if score > 0:
                scored_agents.append((agent, score, skill_matches))

        if not scored_agents:
            logger.warning("No agents have sufficient skills for this task")
            return None, 0.0, {}

        # Sort by score descending
        scored_agents.sort(key=lambda x: x[1], reverse=True)

        best_agent, best_score, best_matches = scored_agents[0]
        logger.info(
            f"Best agent for task {task.task_id}: {best_agent.agent_id} "
            f"(score: {best_score:.2f})"
        )

        return best_agent, best_score, best_matches

    def delegate_task(
        self,
        task: Task,
        agent_id: str | None = None,
        message: str = "",
    ) -> DelegationResult:
        """Delegate a task to an agent.

        If agent_id is not specified, finds the best agent automatically.

        Args:
            task: The task to delegate
            agent_id: Specific agent to delegate to (optional)
            message: Delegation message

        Returns:
            DelegationResult with delegation details

        Raises:
            NoSuitableAgentError: If no suitable agent found and none specified
        """
        # Find requirements for recording
        requirements = extract_skills_from_task(task)
        skill_matches = {}
        alternatives = []

        if agent_id is None:
            # Find best agent automatically
            best_agent, score, skill_matches = self.find_best_agent(task)

            if best_agent is None:
                result = DelegationResult(
                    success=False,
                    task_id=task.task_id,
                    reason="No suitable agent found for this task",
                )
                self._record_delegation(result)
                raise NoSuitableAgentError(result.reason)

            agent_id = best_agent.agent_id

            # Get alternatives
            agents = self.card_registry.list_cards(availability="active")
            for agent in agents:
                if agent.agent_id != agent_id:
                    alt_score, _ = calculate_agent_score(agent, requirements)
                    if alt_score > 0:
                        alternatives.append((agent.agent_id, alt_score))
            alternatives.sort(key=lambda x: x[1], reverse=True)
            alternatives = alternatives[:3]  # Top 3 alternatives

            match_score = score
        else:
            # Use specified agent
            agent = self.card_registry.get_card(agent_id)
            if agent is None:
                result = DelegationResult(
                    success=False,
                    task_id=task.task_id,
                    agent_id=agent_id,
                    reason=f"Agent {agent_id} not found",
                )
                self._record_delegation(result)
                raise DelegationError(result.reason)

            if not agent.is_available():
                result = DelegationResult(
                    success=False,
                    task_id=task.task_id,
                    agent_id=agent_id,
                    reason=f"Agent {agent_id} is not available",
                )
                self._record_delegation(result)
                raise DelegationError(result.reason)

            match_score, skill_matches = calculate_agent_score(agent, requirements)

        # Assign the task
        try:
            self.task_manager.assign_task(
                task.task_id,
                agent_id,
                message or f"Delegated based on skill match (score: {match_score:.2f})",
            )
        except Exception as e:
            result = DelegationResult(
                success=False,
                task_id=task.task_id,
                agent_id=agent_id,
                reason=f"Failed to assign task: {e}",
            )
            self._record_delegation(result)
            raise DelegationError(result.reason) from e

        # Record successful delegation
        result = DelegationResult(
            success=True,
            task_id=task.task_id,
            agent_id=agent_id,
            match_score=match_score,
            skill_matches=skill_matches,
            reason=f"Task delegated to {agent_id}",
            alternatives=alternatives,
        )
        self._record_delegation(result)

        logger.info(f"Task {task.task_id} delegated to {agent_id} (score: {match_score:.2f})")
        return result

    def delegate_to_best(
        self,
        objective: str,
        created_by: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        constraints: list[str] | None = None,
        files: list[str] | None = None,
        context_id: str | None = None,
    ) -> tuple[Task, DelegationResult]:
        """Create a task and delegate it to the best agent.

        Convenience method that combines task creation and delegation.

        Args:
            objective: Task objective
            created_by: Agent creating the task
            priority: Task priority
            constraints: Task constraints
            files: Relevant files
            context_id: Context for grouping

        Returns:
            Tuple of (created_task, delegation_result)
        """
        # Create the task
        task = self.task_manager.create_task(
            objective=objective,
            created_by=created_by,
            priority=priority,
            constraints=constraints,
            files=files,
            context_id=context_id,
        )

        # Delegate to best agent
        result = self.delegate_task(task)

        return task, result

    def get_delegation_history(
        self,
        task_id: str | None = None,
        agent_id: str | None = None,
        success_only: bool = False,
        limit: int | None = None,
    ) -> list[DelegationResult]:
        """Get delegation history with optional filtering.

        Args:
            task_id: Filter by task ID
            agent_id: Filter by agent ID
            success_only: Only return successful delegations
            limit: Maximum number of results

        Returns:
            List of delegation results
        """
        history = self._read_history()

        if task_id is not None:
            history = [r for r in history if r.task_id == task_id]

        if agent_id is not None:
            history = [r for r in history if r.agent_id == agent_id]

        if success_only:
            history = [r for r in history if r.success]

        # Most recent first
        history.reverse()

        if limit is not None:
            history = history[:limit]

        return history

    def get_agent_delegation_stats(self, agent_id: str) -> dict[str, Any]:
        """Get delegation statistics for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary with delegation statistics
        """
        history = self.get_delegation_history(agent_id=agent_id)

        if not history:
            return {
                "agent_id": agent_id,
                "total_delegations": 0,
                "successful": 0,
                "failed": 0,
                "average_score": 0.0,
                "common_skills": [],
            }

        successful = [r for r in history if r.success]
        failed = [r for r in history if not r.success]

        # Calculate average score
        scores = [r.match_score for r in successful if r.match_score > 0]
        avg_score = sum(scores) / len(scores) if scores else 0.0

        # Find common skills
        skill_counts: dict[str, int] = {}
        for result in successful:
            for skill in result.skill_matches:
                skill_counts[skill] = skill_counts.get(skill, 0) + 1

        common_skills = sorted(skill_counts.items(), key=lambda x: -x[1])[:5]

        return {
            "agent_id": agent_id,
            "total_delegations": len(history),
            "successful": len(successful),
            "failed": len(failed),
            "average_score": round(avg_score, 3),
            "common_skills": [skill for skill, _ in common_skills],
        }


# Module-level convenience function
def find_best_agent(
    task: Task,
    project_root: Path | None = None,
) -> AgentCard | None:
    """Find the best agent for a task.

    Convenience function that creates a DelegationManager and finds the best agent.

    Args:
        task: The task to find an agent for
        project_root: Optional project root

    Returns:
        Best matching AgentCard or None
    """
    manager = DelegationManager(project_root)
    agent, _, _ = manager.find_best_agent(task)
    return agent
