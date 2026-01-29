"""Capability learning system for Claude Swarm.

This module tracks agent performance and learns capabilities over time.
It maintains statistics about task outcomes to improve future delegation
decisions and provide insights into agent strengths.

Features:
- Track task success/failure per agent
- Update skill scores based on outcomes
- Store metrics: tasks_completed, tasks_failed, skill_scores, avg_response_time
- Analyze performance trends over time
- Provide agent capability insights

The learning system enables:
- Continuous improvement of delegation accuracy
- Discovery of hidden agent strengths
- Identification of skill gaps
- Performance-based agent selection
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agent_cards import AgentCardRegistry
from .file_lock import FileLock, FileLockTimeout
from .logging_config import get_logger
from .project import get_project_root
from .tasks import Task, TaskStatus

__all__ = [
    "AgentPerformance",
    "SkillMetrics",
    "LearningSystem",
    "get_learning_data_path",
]

# Constants
LEARNING_DATA_FILENAME = "LEARNING_DATA.json"
LEARNING_LOCK_TIMEOUT_SECONDS = 5.0
MAX_HISTORY_ENTRIES_PER_SKILL = 100  # Max outcomes to track per skill
EXPONENTIAL_DECAY_WEIGHT = 0.1  # Weight for exponential moving average

# Configure logging
logger = get_logger(__name__)


@dataclass
class SkillMetrics:
    """Metrics for a specific skill.

    Attributes:
        skill: Skill name
        success_count: Number of successful tasks
        failure_count: Number of failed tasks
        total_count: Total tasks attempted
        success_rate: Calculated success rate (0.0-1.0)
        avg_completion_time: Average time to complete tasks (seconds)
        last_used: When this skill was last used
        trend: Recent trend direction (-1, 0, or 1)
    """

    skill: str
    success_count: int = 0
    failure_count: int = 0
    total_count: int = 0
    success_rate: float = 0.5  # Default neutral rate
    avg_completion_time: float = 0.0
    last_used: str | None = None
    trend: int = 0  # -1 = declining, 0 = stable, 1 = improving

    def record_outcome(
        self,
        success: bool,
        completion_time: float | None = None,
    ) -> None:
        """Record a task outcome for this skill.

        Args:
            success: Whether the task was successful
            completion_time: Time to complete the task (seconds)
        """
        self.total_count += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1

        # Update success rate using exponential moving average
        new_value = 1.0 if success else 0.0
        self.success_rate = (
            self.success_rate * (1 - EXPONENTIAL_DECAY_WEIGHT)
            + new_value * EXPONENTIAL_DECAY_WEIGHT
        )
        self.success_rate = round(self.success_rate, 4)

        # Update completion time average
        if completion_time is not None and completion_time > 0:
            if self.avg_completion_time == 0:
                self.avg_completion_time = completion_time
            else:
                self.avg_completion_time = (
                    self.avg_completion_time * (1 - EXPONENTIAL_DECAY_WEIGHT)
                    + completion_time * EXPONENTIAL_DECAY_WEIGHT
                )

        self.last_used = datetime.now(UTC).isoformat()

        # Calculate trend (simple: compare last 5 to previous 5)
        # This is a simplified trend - could be made more sophisticated
        if self.total_count >= 10:
            recent_rate = self.success_rate
            # Approximate historical rate from counts
            historical_rate = self.success_count / self.total_count if self.total_count > 0 else 0.5
            diff = recent_rate - historical_rate
            if diff > 0.1:
                self.trend = 1
            elif diff < -0.1:
                self.trend = -1
            else:
                self.trend = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkillMetrics:
        """Create from dictionary."""
        return cls(**data)


@dataclass
class AgentPerformance:
    """Performance data for an agent.

    Attributes:
        agent_id: Agent identifier
        tasks_completed: Total successful tasks
        tasks_failed: Total failed tasks
        tasks_in_progress: Currently assigned tasks
        skill_metrics: Metrics per skill
        overall_success_rate: Overall success rate
        avg_response_time: Average time from assignment to start
        avg_completion_time: Average time from start to completion
        last_active: Last activity timestamp
        created_at: When tracking started
        metadata: Additional data
    """

    agent_id: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    tasks_in_progress: int = 0
    skill_metrics: dict[str, SkillMetrics] = field(default_factory=dict)
    overall_success_rate: float = 0.5
    avg_response_time: float = 0.0
    avg_completion_time: float = 0.0
    last_active: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_skill_metrics(self, skill: str) -> SkillMetrics:
        """Get or create metrics for a skill.

        Args:
            skill: Skill name

        Returns:
            SkillMetrics for the skill
        """
        skill_lower = skill.lower()
        if skill_lower not in self.skill_metrics:
            self.skill_metrics[skill_lower] = SkillMetrics(skill=skill_lower)
        return self.skill_metrics[skill_lower]

    def record_task_outcome(
        self,
        success: bool,
        skills: list[str] | None = None,
        response_time: float | None = None,
        completion_time: float | None = None,
    ) -> None:
        """Record a task outcome.

        Args:
            success: Whether the task was successful
            skills: Skills used in the task
            response_time: Time from assignment to start (seconds)
            completion_time: Time from start to completion (seconds)
        """
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1

        # Update overall success rate
        total = self.tasks_completed + self.tasks_failed
        if total > 0:
            new_value = 1.0 if success else 0.0
            self.overall_success_rate = (
                self.overall_success_rate * (1 - EXPONENTIAL_DECAY_WEIGHT)
                + new_value * EXPONENTIAL_DECAY_WEIGHT
            )
            self.overall_success_rate = round(self.overall_success_rate, 4)

        # Update skill metrics
        if skills:
            for skill in skills:
                metrics = self.get_skill_metrics(skill)
                metrics.record_outcome(success, completion_time)

        # Update time averages
        if response_time is not None and response_time > 0:
            if self.avg_response_time == 0:
                self.avg_response_time = response_time
            else:
                self.avg_response_time = (
                    self.avg_response_time * (1 - EXPONENTIAL_DECAY_WEIGHT)
                    + response_time * EXPONENTIAL_DECAY_WEIGHT
                )

        if completion_time is not None and completion_time > 0:
            if self.avg_completion_time == 0:
                self.avg_completion_time = completion_time
            else:
                self.avg_completion_time = (
                    self.avg_completion_time * (1 - EXPONENTIAL_DECAY_WEIGHT)
                    + completion_time * EXPONENTIAL_DECAY_WEIGHT
                )

        self.last_active = datetime.now(UTC).isoformat()

    def get_top_skills(self, n: int = 5) -> list[tuple[str, float]]:
        """Get the agent's top skills by success rate.

        Args:
            n: Number of skills to return

        Returns:
            List of (skill, success_rate) tuples
        """
        skills_with_experience = [
            (skill, metrics.success_rate)
            for skill, metrics in self.skill_metrics.items()
            if metrics.total_count >= 3  # Require minimum experience
        ]
        skills_with_experience.sort(key=lambda x: x[1], reverse=True)
        return skills_with_experience[:n]

    def get_weak_skills(self, n: int = 5) -> list[tuple[str, float]]:
        """Get skills that need improvement.

        Args:
            n: Number of skills to return

        Returns:
            List of (skill, success_rate) tuples
        """
        skills_with_experience = [
            (skill, metrics.success_rate)
            for skill, metrics in self.skill_metrics.items()
            if metrics.total_count >= 3 and metrics.success_rate < 0.7
        ]
        skills_with_experience.sort(key=lambda x: x[1])
        return skills_with_experience[:n]

    def get_improving_skills(self) -> list[str]:
        """Get skills that are improving.

        Returns:
            List of skill names with positive trend
        """
        return [
            skill
            for skill, metrics in self.skill_metrics.items()
            if metrics.trend > 0
        ]

    def get_declining_skills(self) -> list[str]:
        """Get skills that are declining.

        Returns:
            List of skill names with negative trend
        """
        return [
            skill
            for skill, metrics in self.skill_metrics.items()
            if metrics.trend < 0
        ]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert SkillMetrics objects
        data["skill_metrics"] = {
            skill: metrics.to_dict() if isinstance(metrics, SkillMetrics) else metrics
            for skill, metrics in self.skill_metrics.items()
        }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentPerformance:
        """Create from dictionary."""
        # Convert skill_metrics dicts to SkillMetrics objects
        skill_metrics = {}
        for skill, metrics_data in data.get("skill_metrics", {}).items():
            if isinstance(metrics_data, dict):
                skill_metrics[skill] = SkillMetrics.from_dict(metrics_data)
            else:
                skill_metrics[skill] = metrics_data

        return cls(
            agent_id=data["agent_id"],
            tasks_completed=data.get("tasks_completed", 0),
            tasks_failed=data.get("tasks_failed", 0),
            tasks_in_progress=data.get("tasks_in_progress", 0),
            skill_metrics=skill_metrics,
            overall_success_rate=data.get("overall_success_rate", 0.5),
            avg_response_time=data.get("avg_response_time", 0.0),
            avg_completion_time=data.get("avg_completion_time", 0.0),
            last_active=data.get("last_active"),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            metadata=data.get("metadata", {}),
        )


def get_learning_data_path(project_root: Path | None = None) -> Path:
    """Get the path to the learning data file.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to LEARNING_DATA.json
    """
    root = get_project_root(project_root)
    return root / LEARNING_DATA_FILENAME


class LearningSystem:
    """System for learning agent capabilities over time.

    Tracks task outcomes, updates skill scores, and provides
    insights into agent performance.
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize the learning system.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = get_project_root(project_root)
        self.data_path = get_learning_data_path(self.project_root)
        self.card_registry = AgentCardRegistry(self.project_root)
        self._lock = threading.Lock()
        self._task_start_times: dict[str, float] = {}  # task_id -> start_time

    def _read_data(self) -> dict[str, AgentPerformance]:
        """Read learning data from file.

        Returns:
            Dictionary mapping agent_id to AgentPerformance
        """
        if not self.data_path.exists():
            return {}

        try:
            with FileLock(self.data_path, timeout=LEARNING_LOCK_TIMEOUT_SECONDS, shared=True):
                with open(self.data_path, encoding="utf-8") as f:
                    data = json.load(f)

                return {
                    agent_id: AgentPerformance.from_dict(perf_data)
                    for agent_id, perf_data in data.get("agents", {}).items()
                }

        except FileLockTimeout:
            logger.error(f"Timeout acquiring lock on {self.data_path}")
            return {}
        except Exception as e:
            logger.warning(f"Error reading learning data: {e}")
            return {}

    def _write_data(self, agents: dict[str, AgentPerformance]) -> None:
        """Write learning data to file.

        Args:
            agents: Dictionary mapping agent_id to AgentPerformance
        """
        self.data_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "agents": {agent_id: perf.to_dict() for agent_id, perf in agents.items()},
        }

        try:
            with FileLock(self.data_path, timeout=LEARNING_LOCK_TIMEOUT_SECONDS, shared=False):
                temp_path = self.data_path.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                temp_path.replace(self.data_path)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring write lock on {self.data_path}")
            raise
        except Exception as e:
            logger.error(f"Error writing learning data: {e}")
            raise

    def get_agent_performance(self, agent_id: str) -> AgentPerformance:
        """Get or create performance data for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentPerformance for the agent
        """
        with self._lock:
            agents = self._read_data()
            if agent_id not in agents:
                agents[agent_id] = AgentPerformance(agent_id=agent_id)
                self._write_data(agents)
            return agents[agent_id]

    def record_task_started(self, task_id: str, agent_id: str) -> None:
        """Record that a task has started.

        Args:
            task_id: Task identifier
            agent_id: Agent working on the task
        """
        self._task_start_times[task_id] = time.time()

        with self._lock:
            agents = self._read_data()
            if agent_id not in agents:
                agents[agent_id] = AgentPerformance(agent_id=agent_id)
            agents[agent_id].tasks_in_progress += 1
            agents[agent_id].last_active = datetime.now(UTC).isoformat()
            self._write_data(agents)

        logger.debug(f"Recorded task start: {task_id} by {agent_id}")

    def record_task_completed(
        self,
        task: Task,
        success: bool,
        skills: list[str] | None = None,
    ) -> None:
        """Record a task completion.

        Args:
            task: The completed task
            success: Whether the task was successful
            skills: Skills used in the task
        """
        agent_id = task.assigned_to
        if not agent_id:
            logger.warning(f"Cannot record completion: task {task.task_id} has no assignee")
            return

        # Calculate completion time
        completion_time = None
        if task.task_id in self._task_start_times:
            completion_time = time.time() - self._task_start_times[task.task_id]
            del self._task_start_times[task.task_id]

        with self._lock:
            agents = self._read_data()
            if agent_id not in agents:
                agents[agent_id] = AgentPerformance(agent_id=agent_id)

            perf = agents[agent_id]

            # Decrement in-progress count (prevent negative values)
            perf.tasks_in_progress = max(0, perf.tasks_in_progress - 1)

            # Record the outcome
            perf.record_task_outcome(
                success=success,
                skills=skills,
                completion_time=completion_time,
            )

            self._write_data(agents)

        # Update agent card with new success rates
        self._sync_to_agent_card(agent_id, skills or [])

        logger.info(
            f"Recorded task completion: {task.task_id} by {agent_id} "
            f"(success={success}, skills={skills})"
        )

    def _sync_to_agent_card(self, agent_id: str, skills: list[str]) -> None:
        """Sync learned success rates to agent card.

        Args:
            agent_id: Agent identifier
            skills: Skills to sync
        """
        try:
            perf = self.get_agent_performance(agent_id)

            # Update success rates in agent card
            success_rates = {}
            for skill in skills:
                skill_lower = skill.lower()
                if skill_lower in perf.skill_metrics:
                    success_rates[skill_lower] = perf.skill_metrics[skill_lower].success_rate

            if success_rates:
                self.card_registry.update_card(agent_id, success_rates=success_rates)

        except Exception as e:
            logger.warning(f"Failed to sync learning to agent card: {e}")

    def get_all_performance(self) -> dict[str, AgentPerformance]:
        """Get performance data for all agents.

        Returns:
            Dictionary mapping agent_id to AgentPerformance
        """
        return self._read_data()

    def get_leaderboard(
        self,
        metric: str = "overall_success_rate",
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Get agent leaderboard by a metric.

        Args:
            metric: Metric to rank by
            limit: Maximum number of agents to return

        Returns:
            List of (agent_id, metric_value) tuples
        """
        agents = self._read_data()

        results = []
        for agent_id, perf in agents.items():
            if hasattr(perf, metric):
                value = getattr(perf, metric)
                if isinstance(value, (int, float)):
                    results.append((agent_id, value))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_skill_experts(self, skill: str, limit: int = 5) -> list[tuple[str, float]]:
        """Get top agents for a specific skill.

        Args:
            skill: Skill name
            limit: Maximum number of agents to return

        Returns:
            List of (agent_id, success_rate) tuples
        """
        agents = self._read_data()
        skill_lower = skill.lower()

        results = []
        for agent_id, perf in agents.items():
            if skill_lower in perf.skill_metrics:
                metrics = perf.skill_metrics[skill_lower]
                if metrics.total_count >= 3:  # Require minimum experience
                    results.append((agent_id, metrics.success_rate))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_team_summary(self) -> dict[str, Any]:
        """Get a summary of team performance.

        Returns:
            Dictionary with team-level statistics
        """
        agents = self._read_data()

        if not agents:
            return {
                "total_agents": 0,
                "total_tasks_completed": 0,
                "total_tasks_failed": 0,
                "overall_success_rate": 0.0,
                "active_agents": 0,
                "top_performers": [],
                "improving_agents": [],
            }

        total_completed = sum(a.tasks_completed for a in agents.values())
        total_failed = sum(a.tasks_failed for a in agents.values())
        total = total_completed + total_failed

        # Find active agents (active in last 24 hours)
        now = datetime.now(UTC)
        active_count = 0
        for perf in agents.values():
            if perf.last_active:
                try:
                    last_active = datetime.fromisoformat(perf.last_active)
                    if (now - last_active).total_seconds() < 86400:
                        active_count += 1
                except (ValueError, TypeError):
                    pass

        # Get top performers
        leaderboard = self.get_leaderboard(limit=3)

        # Find improving agents
        improving = []
        for agent_id, perf in agents.items():
            improving_skills = perf.get_improving_skills()
            if improving_skills:
                improving.append(agent_id)

        return {
            "total_agents": len(agents),
            "total_tasks_completed": total_completed,
            "total_tasks_failed": total_failed,
            "overall_success_rate": round(total_completed / total, 3) if total > 0 else 0.0,
            "active_agents": active_count,
            "top_performers": leaderboard,
            "improving_agents": improving[:5],
        }

    def record_task_from_history(self, task: Task) -> None:
        """Record task outcome from task history.

        Analyzes task history to record the outcome with timing information.

        Args:
            task: Task with history
        """
        if not task.assigned_to:
            return

        # Find relevant history entries
        assignment_time = None
        start_time = None
        completion_time = None

        for entry in task.history:
            if entry.to_status == TaskStatus.ASSIGNED.value:
                try:
                    assignment_time = datetime.fromisoformat(entry.timestamp)
                except (ValueError, TypeError):
                    pass
            elif entry.to_status == TaskStatus.WORKING.value:
                try:
                    start_time = datetime.fromisoformat(entry.timestamp)
                except (ValueError, TypeError):
                    pass
            elif entry.to_status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value):
                try:
                    completion_time = datetime.fromisoformat(entry.timestamp)
                except (ValueError, TypeError):
                    pass

        # Calculate times
        response_time = None
        if assignment_time and start_time:
            response_time = (start_time - assignment_time).total_seconds()

        work_time = None
        if start_time and completion_time:
            work_time = (completion_time - start_time).total_seconds()

        # Determine success
        success = task.status == TaskStatus.COMPLETED

        # Extract skills from task (this would need skill extraction logic)
        # For now, we'll use file extensions as a proxy
        skills = []
        for filepath in task.files:
            ext = Path(filepath).suffix.lower()
            # Map extension to skill (simplified)
            ext_skills = {
                ".py": "python",
                ".js": "javascript",
                ".ts": "typescript",
                ".go": "golang",
            }
            if ext in ext_skills:
                skills.append(ext_skills[ext])

        # Record with full timing
        with self._lock:
            agents = self._read_data()
            if task.assigned_to not in agents:
                agents[task.assigned_to] = AgentPerformance(agent_id=task.assigned_to)

            perf = agents[task.assigned_to]
            perf.record_task_outcome(
                success=success,
                skills=skills if skills else None,
                response_time=response_time,
                completion_time=work_time,
            )

            self._write_data(agents)

        logger.debug(
            f"Recorded task from history: {task.task_id} by {task.assigned_to} "
            f"(success={success})"
        )
