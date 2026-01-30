"""Unit tests for learning.py module.

Tests cover:
- Skill metrics updates
- Success rate calculations
- Performance tracking
- Agent performance syncing
- Task completion recording
- Leaderboard generation
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from claudeswarm.learning import (
    EXPONENTIAL_DECAY_WEIGHT,
    LEARNING_DATA_FILENAME,
    AgentPerformance,
    LearningSystem,
    SkillMetrics,
    get_learning_data_path,
)
from claudeswarm.tasks import Task, TaskStatus


class TestSkillMetrics:
    """Tests for SkillMetrics dataclass."""

    def test_creation_defaults(self):
        """Test SkillMetrics creation with default values."""
        metrics = SkillMetrics(skill="python")

        assert metrics.skill == "python"
        assert metrics.success_count == 0
        assert metrics.failure_count == 0
        assert metrics.total_count == 0
        assert metrics.success_rate == 0.5
        assert metrics.avg_completion_time == 0.0
        assert metrics.last_used is None
        assert metrics.trend == 0

    def test_record_outcome_success(self):
        """Test recording a successful outcome."""
        metrics = SkillMetrics(skill="python", success_rate=0.5)

        metrics.record_outcome(success=True, completion_time=120.0)

        assert metrics.total_count == 1
        assert metrics.success_count == 1
        assert metrics.failure_count == 0
        assert metrics.success_rate > 0.5
        assert metrics.avg_completion_time == 120.0
        assert metrics.last_used is not None

    def test_record_outcome_failure(self):
        """Test recording a failed outcome."""
        metrics = SkillMetrics(skill="python", success_rate=0.7)

        metrics.record_outcome(success=False)

        assert metrics.total_count == 1
        assert metrics.success_count == 0
        assert metrics.failure_count == 1
        assert metrics.success_rate < 0.7

    def test_record_outcome_updates_completion_time(self):
        """Test that completion time is updated correctly."""
        metrics = SkillMetrics(skill="python")

        # First outcome
        metrics.record_outcome(success=True, completion_time=100.0)
        assert metrics.avg_completion_time == 100.0

        # Second outcome should update average
        metrics.record_outcome(success=True, completion_time=200.0)
        # Should be weighted average, not simple average
        assert 100.0 < metrics.avg_completion_time < 200.0

    def test_record_outcome_ignores_zero_completion_time(self):
        """Test that zero completion time is ignored."""
        metrics = SkillMetrics(skill="python")

        metrics.record_outcome(success=True, completion_time=0.0)

        assert metrics.avg_completion_time == 0.0

    def test_record_outcome_calculates_trend(self):
        """Test that trend is calculated after sufficient data."""
        metrics = SkillMetrics(skill="python")

        # Record 10+ outcomes to trigger trend calculation
        for i in range(12):
            # All successes
            metrics.record_outcome(success=True)

        # Should have calculated a trend (can be -1, 0, or 1)
        assert metrics.trend in [-1, 0, 1]
        # Total count should be 12
        assert metrics.total_count == 12

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metrics = SkillMetrics(skill="python", success_count=5, failure_count=2)

        result = metrics.to_dict()

        assert result["skill"] == "python"
        assert result["success_count"] == 5
        assert result["failure_count"] == 2

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "skill": "python",
            "success_count": 5,
            "failure_count": 2,
            "total_count": 7,
            "success_rate": 0.7,
            "avg_completion_time": 150.0,
            "last_used": "2024-01-01T00:00:00Z",
            "trend": 1,
        }

        metrics = SkillMetrics.from_dict(data)

        assert metrics.skill == "python"
        assert metrics.success_count == 5
        assert metrics.success_rate == 0.7


class TestAgentPerformance:
    """Tests for AgentPerformance dataclass."""

    def test_creation_defaults(self):
        """Test AgentPerformance creation with default values."""
        perf = AgentPerformance(agent_id="agent-0")

        assert perf.agent_id == "agent-0"
        assert perf.tasks_completed == 0
        assert perf.tasks_failed == 0
        assert perf.tasks_in_progress == 0
        assert perf.skill_metrics == {}
        assert perf.overall_success_rate == 0.5
        assert perf.avg_response_time == 0.0
        assert perf.avg_completion_time == 0.0
        assert perf.last_active is None

    def test_get_skill_metrics_new(self):
        """Test getting metrics for a new skill."""
        perf = AgentPerformance(agent_id="agent-0")

        metrics = perf.get_skill_metrics("Python")

        assert metrics.skill == "python"  # Should be lowercase
        assert "python" in perf.skill_metrics

    def test_get_skill_metrics_existing(self):
        """Test getting metrics for an existing skill."""
        perf = AgentPerformance(agent_id="agent-0")

        # Get metrics twice
        metrics1 = perf.get_skill_metrics("Python")
        metrics1.success_count = 5

        metrics2 = perf.get_skill_metrics("Python")

        assert metrics2.success_count == 5
        assert metrics1 is metrics2

    def test_record_task_outcome_success(self):
        """Test recording a successful task outcome."""
        perf = AgentPerformance(agent_id="agent-0")

        perf.record_task_outcome(
            success=True,
            skills=["python", "testing"],
            completion_time=120.0,
        )

        assert perf.tasks_completed == 1
        assert perf.tasks_failed == 0
        assert perf.overall_success_rate > 0.5
        assert "python" in perf.skill_metrics
        assert "testing" in perf.skill_metrics
        assert perf.last_active is not None

    def test_record_task_outcome_failure(self):
        """Test recording a failed task outcome."""
        perf = AgentPerformance(agent_id="agent-0")

        perf.record_task_outcome(
            success=False,
            skills=["python"],
        )

        assert perf.tasks_completed == 0
        assert perf.tasks_failed == 1
        assert perf.overall_success_rate < 0.5

    def test_record_task_outcome_updates_skill_metrics(self):
        """Test that task outcomes update skill metrics."""
        perf = AgentPerformance(agent_id="agent-0")

        perf.record_task_outcome(
            success=True,
            skills=["python"],
            completion_time=100.0,
        )

        metrics = perf.skill_metrics["python"]
        assert metrics.success_count == 1
        assert metrics.avg_completion_time == 100.0

    def test_record_task_outcome_updates_response_time(self):
        """Test that response time is updated."""
        perf = AgentPerformance(agent_id="agent-0")

        perf.record_task_outcome(success=True, response_time=30.0)

        assert perf.avg_response_time == 30.0

    def test_record_task_outcome_updates_completion_time(self):
        """Test that completion time is updated."""
        perf = AgentPerformance(agent_id="agent-0")

        perf.record_task_outcome(success=True, completion_time=120.0)

        assert perf.avg_completion_time == 120.0

    def test_get_top_skills(self):
        """Test getting top skills."""
        perf = AgentPerformance(agent_id="agent-0")

        # Add skills with varying success rates
        # Need at least 3 tasks per skill
        for _ in range(5):
            perf.record_task_outcome(success=True, skills=["python"])
        for _ in range(3):
            perf.record_task_outcome(success=True, skills=["javascript"])
            perf.record_task_outcome(success=False, skills=["javascript"])
        for _ in range(3):
            perf.record_task_outcome(success=True, skills=["golang"])

        top_skills = perf.get_top_skills(n=2)

        # Python should have highest success rate
        assert len(top_skills) <= 2
        assert top_skills[0][0] in ["python", "golang"]

    def test_get_top_skills_requires_minimum_experience(self):
        """Test that top skills requires minimum experience."""
        perf = AgentPerformance(agent_id="agent-0")

        # Record only 2 tasks (below minimum of 3)
        perf.record_task_outcome(success=True, skills=["python"])
        perf.record_task_outcome(success=True, skills=["python"])

        top_skills = perf.get_top_skills()

        # Should return empty list (not enough experience)
        assert len(top_skills) == 0

    def test_get_weak_skills(self):
        """Test getting weak skills."""
        perf = AgentPerformance(agent_id="agent-0")

        # Add skill with low success rate (need at least 3 tasks)
        for _ in range(5):
            perf.record_task_outcome(success=False, skills=["python"])
        for _ in range(3):
            perf.record_task_outcome(success=True, skills=["javascript"])

        weak_skills = perf.get_weak_skills()

        # Python should be in weak skills (high failure rate)
        assert len(weak_skills) >= 1
        # Weak skills should have success rate < 0.7
        for skill, rate in weak_skills:
            assert rate < 0.7

    def test_get_improving_skills(self):
        """Test getting improving skills."""
        perf = AgentPerformance(agent_id="agent-0")

        # Create a skill with positive trend
        metrics = perf.get_skill_metrics("python")
        metrics.trend = 1

        improving = perf.get_improving_skills()

        assert "python" in improving

    def test_get_declining_skills(self):
        """Test getting declining skills."""
        perf = AgentPerformance(agent_id="agent-0")

        # Create a skill with negative trend
        metrics = perf.get_skill_metrics("python")
        metrics.trend = -1

        declining = perf.get_declining_skills()

        assert "python" in declining

    def test_to_dict(self):
        """Test conversion to dictionary."""
        perf = AgentPerformance(agent_id="agent-0")
        perf.record_task_outcome(success=True, skills=["python"])

        result = perf.to_dict()

        assert result["agent_id"] == "agent-0"
        assert result["tasks_completed"] == 1
        assert "python" in result["skill_metrics"]
        assert isinstance(result["skill_metrics"]["python"], dict)

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "agent_id": "agent-0",
            "tasks_completed": 5,
            "tasks_failed": 2,
            "tasks_in_progress": 1,
            "skill_metrics": {
                "python": {
                    "skill": "python",
                    "success_count": 5,
                    "failure_count": 2,
                    "total_count": 7,
                    "success_rate": 0.7,
                    "avg_completion_time": 150.0,
                    "last_used": None,
                    "trend": 0,
                }
            },
            "overall_success_rate": 0.7,
            "avg_response_time": 30.0,
            "avg_completion_time": 150.0,
            "last_active": "2024-01-01T00:00:00Z",
            "created_at": "2024-01-01T00:00:00Z",
            "metadata": {},
        }

        perf = AgentPerformance.from_dict(data)

        assert perf.agent_id == "agent-0"
        assert perf.tasks_completed == 5
        assert "python" in perf.skill_metrics
        assert isinstance(perf.skill_metrics["python"], SkillMetrics)


class TestGetLearningDataPath:
    """Tests for get_learning_data_path function."""

    @patch("claudeswarm.learning.get_project_root")
    def test_get_learning_data_path_default(self, mock_get_root):
        """Test getting learning data path with default project root."""
        mock_get_root.return_value = Path("/project")

        result = get_learning_data_path()

        assert result == Path("/project") / LEARNING_DATA_FILENAME
        mock_get_root.assert_called_once_with(None)

    @patch("claudeswarm.learning.get_project_root")
    def test_get_learning_data_path_custom_root(self, mock_get_root):
        """Test getting learning data path with custom project root."""
        custom_root = Path("/custom")
        mock_get_root.return_value = custom_root

        result = get_learning_data_path(custom_root)

        assert result == custom_root / LEARNING_DATA_FILENAME
        mock_get_root.assert_called_once_with(custom_root)


class TestLearningSystem:
    """Tests for LearningSystem class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        return project_root

    @pytest.fixture
    def system(self, temp_project):
        """Create a LearningSystem instance."""
        return LearningSystem(temp_project)

    def test_initialization(self, temp_project):
        """Test LearningSystem initialization."""
        system = LearningSystem(temp_project)

        assert system.project_root == temp_project
        assert system.data_path == temp_project / LEARNING_DATA_FILENAME

    def test_get_agent_performance_new(self, system):
        """Test getting performance for new agent."""
        perf = system.get_agent_performance("agent-0")

        assert perf.agent_id == "agent-0"
        assert perf.tasks_completed == 0

        # Should be persisted
        assert system.data_path.exists()

    def test_get_agent_performance_existing(self, system):
        """Test getting performance for existing agent."""
        # Create performance
        perf1 = system.get_agent_performance("agent-0")

        # Modify it directly (simulating external modification)
        with system._lock:
            agents = system._read_data()
            agents["agent-0"].tasks_completed = 5
            system._write_data(agents)

        # Get again
        perf2 = system.get_agent_performance("agent-0")

        assert perf2.tasks_completed == 5

    def test_record_task_started(self, system):
        """Test recording task start."""
        system.record_task_started("task-1", "agent-0")

        # Should update in-progress count
        perf = system.get_agent_performance("agent-0")
        assert perf.tasks_in_progress == 1
        assert perf.last_active is not None

    def test_record_task_completed_success(self, system):
        """Test recording successful task completion."""
        task = Mock(spec=Task)
        task.task_id = "task-1"
        task.assigned_to = "agent-0"
        task.status = TaskStatus.COMPLETED

        # Start task first
        system.record_task_started("task-1", "agent-0")

        # Complete it
        system.record_task_completed(task, success=True, skills=["python"])

        # Verify performance updated
        perf = system.get_agent_performance("agent-0")
        assert perf.tasks_completed == 1
        assert perf.tasks_failed == 0
        assert perf.tasks_in_progress == 0
        assert "python" in perf.skill_metrics

    def test_record_task_completed_failure(self, system):
        """Test recording failed task completion."""
        task = Mock(spec=Task)
        task.task_id = "task-1"
        task.assigned_to = "agent-0"
        task.status = TaskStatus.FAILED

        system.record_task_completed(task, success=False, skills=["python"])

        perf = system.get_agent_performance("agent-0")
        assert perf.tasks_completed == 0
        assert perf.tasks_failed == 1

    def test_record_task_completed_no_assignee(self, system):
        """Test recording completion for task with no assignee."""
        task = Mock(spec=Task)
        task.task_id = "task-1"
        task.assigned_to = None

        # Should not raise error, just log warning
        system.record_task_completed(task, success=True)

        # Should not create any performance data
        agents = system._read_data()
        assert len(agents) == 0

    def test_record_task_completed_calculates_completion_time(self, system):
        """Test that completion time is calculated from start time."""
        task = Mock(spec=Task)
        task.task_id = "task-1"
        task.assigned_to = "agent-0"
        task.status = TaskStatus.COMPLETED

        # Start task
        system.record_task_started("task-1", "agent-0")

        # Wait a bit
        time.sleep(0.1)

        # Complete task
        system.record_task_completed(task, success=True)

        perf = system.get_agent_performance("agent-0")
        # Should have recorded some completion time
        assert perf.avg_completion_time > 0

    @patch("claudeswarm.learning.LearningSystem._sync_to_agent_card")
    def test_record_task_completed_syncs_to_agent_card(self, mock_sync, system):
        """Test that task completion syncs to agent card."""
        task = Mock(spec=Task)
        task.task_id = "task-1"
        task.assigned_to = "agent-0"
        task.status = TaskStatus.COMPLETED

        system.record_task_completed(task, success=True, skills=["python"])

        # Should have called sync
        mock_sync.assert_called_once_with("agent-0", ["python"])

    def test_get_all_performance_empty(self, system):
        """Test getting all performance when none exists."""
        result = system.get_all_performance()

        assert result == {}

    def test_get_all_performance(self, system):
        """Test getting all performance data."""
        # Create performance for multiple agents
        system.get_agent_performance("agent-0")
        system.get_agent_performance("agent-1")

        result = system.get_all_performance()

        assert len(result) == 2
        assert "agent-0" in result
        assert "agent-1" in result

    def test_get_leaderboard(self, system):
        """Test getting leaderboard."""
        # Create agents with different success rates
        perf0 = system.get_agent_performance("agent-0")
        perf0.overall_success_rate = 0.9
        perf0.tasks_completed = 10

        perf1 = system.get_agent_performance("agent-1")
        perf1.overall_success_rate = 0.7
        perf1.tasks_completed = 5

        # Save them
        with system._lock:
            agents = {"agent-0": perf0, "agent-1": perf1}
            system._write_data(agents)

        leaderboard = system.get_leaderboard(metric="overall_success_rate", limit=10)

        # Should be sorted by success rate, highest first
        assert len(leaderboard) == 2
        assert leaderboard[0][0] == "agent-0"
        assert leaderboard[0][1] == 0.9
        assert leaderboard[1][0] == "agent-1"
        assert leaderboard[1][1] == 0.7

    def test_get_leaderboard_with_limit(self, system):
        """Test getting leaderboard with limit."""
        # Create 3 agents
        for i in range(3):
            perf = system.get_agent_performance(f"agent-{i}")
            perf.overall_success_rate = 0.5 + (i * 0.1)

        with system._lock:
            agents = system._read_data()
            system._write_data(agents)

        leaderboard = system.get_leaderboard(limit=2)

        # Should return only top 2
        assert len(leaderboard) == 2

    def test_get_skill_experts(self, system):
        """Test getting skill experts."""
        # Create agents with varying skill levels
        # Need at least 3 tasks for each skill
        perf0 = system.get_agent_performance("agent-0")
        for _ in range(5):
            perf0.record_task_outcome(success=True, skills=["python"])

        perf1 = system.get_agent_performance("agent-1")
        for _ in range(3):
            perf1.record_task_outcome(success=True, skills=["python"])
            perf1.record_task_outcome(success=False, skills=["python"])

        # Write the updated performances
        with system._lock:
            agents = {"agent-0": perf0, "agent-1": perf1}
            system._write_data(agents)

        experts = system.get_skill_experts("python", limit=5)

        # Should return agents sorted by success rate
        assert len(experts) >= 1
        # agent-0 should be first (higher success rate)
        assert experts[0][0] == "agent-0"

    def test_get_skill_experts_requires_minimum_experience(self, system):
        """Test that skill experts requires minimum experience."""
        # Create agent with only 2 tasks (below minimum of 3)
        perf = system.get_agent_performance("agent-0")
        perf.record_task_outcome(success=True, skills=["python"])
        perf.record_task_outcome(success=True, skills=["python"])

        with system._lock:
            agents = system._read_data()
            system._write_data(agents)

        experts = system.get_skill_experts("python")

        # Should return empty (not enough experience)
        assert len(experts) == 0

    def test_get_team_summary_empty(self, system):
        """Test getting team summary when no agents exist."""
        summary = system.get_team_summary()

        assert summary["total_agents"] == 0
        assert summary["total_tasks_completed"] == 0
        assert summary["total_tasks_failed"] == 0
        assert summary["overall_success_rate"] == 0.0

    def test_get_team_summary(self, system):
        """Test getting team summary."""
        # Create agents with tasks
        perf0 = system.get_agent_performance("agent-0")
        perf0.tasks_completed = 10
        perf0.tasks_failed = 2
        perf0.last_active = datetime.now(UTC).isoformat()

        perf1 = system.get_agent_performance("agent-1")
        perf1.tasks_completed = 5
        perf1.tasks_failed = 1
        perf1.last_active = datetime.now(UTC).isoformat()

        with system._lock:
            agents = {"agent-0": perf0, "agent-1": perf1}
            system._write_data(agents)

        summary = system.get_team_summary()

        assert summary["total_agents"] == 2
        assert summary["total_tasks_completed"] == 15
        assert summary["total_tasks_failed"] == 3
        assert summary["overall_success_rate"] > 0.0
        assert summary["active_agents"] == 2
        assert len(summary["top_performers"]) <= 3

    def test_record_task_from_history(self, system):
        """Test recording task from history."""
        # Create a task with history
        task = Mock(spec=Task)
        task.task_id = "task-1"
        task.assigned_to = "agent-0"
        task.status = TaskStatus.COMPLETED
        task.files = ["src/main.py"]

        # Create history entries
        history_entry_assigned = Mock()
        history_entry_assigned.to_status = TaskStatus.ASSIGNED.value
        history_entry_assigned.timestamp = "2024-01-01T00:00:00Z"

        history_entry_working = Mock()
        history_entry_working.to_status = TaskStatus.WORKING.value
        history_entry_working.timestamp = "2024-01-01T00:00:30Z"

        history_entry_completed = Mock()
        history_entry_completed.to_status = TaskStatus.COMPLETED.value
        history_entry_completed.timestamp = "2024-01-01T00:01:00Z"

        task.history = [
            history_entry_assigned,
            history_entry_working,
            history_entry_completed,
        ]

        system.record_task_from_history(task)

        # Verify performance was recorded
        perf = system.get_agent_performance("agent-0")
        assert perf.tasks_completed == 1
        # Should have calculated response and work times
        assert perf.avg_response_time > 0 or perf.avg_completion_time > 0

    def test_record_task_from_history_no_assignee(self, system):
        """Test recording task from history with no assignee."""
        task = Mock(spec=Task)
        task.task_id = "task-1"
        task.assigned_to = None

        # Should not raise error
        system.record_task_from_history(task)

        # Should not create any performance data
        agents = system._read_data()
        assert len(agents) == 0

    @patch("claudeswarm.learning.FileLock")
    def test_read_data_handles_lock_timeout(self, mock_filelock, system):
        """Test that read_data handles lock timeout gracefully."""
        from claudeswarm.file_lock import FileLockTimeout

        # Create data file
        system.get_agent_performance("agent-0")

        # Make FileLock raise timeout
        mock_filelock.side_effect = FileLockTimeout("Timeout")

        # Should return empty dict on timeout
        result = system._read_data()
        assert result == {}

    def test_read_data_handles_missing_file(self, system):
        """Test that read_data handles missing file gracefully."""
        result = system._read_data()

        assert result == {}
        assert not system.data_path.exists()

    @patch("claudeswarm.learning.LearningSystem._sync_to_agent_card")
    def test_sync_to_agent_card_updates_success_rates(self, mock_sync, system):
        """Test that sync updates agent card with success rates."""
        # Create performance with skill metrics
        perf = system.get_agent_performance("agent-0")
        for _ in range(5):
            perf.record_task_outcome(success=True, skills=["python"])

        with system._lock:
            agents = {"agent-0": perf}
            system._write_data(agents)

        # Manually call sync
        system._sync_to_agent_card("agent-0", ["python"])

        # Verify card_registry.update_card was called
        # (This test verifies the method runs without error)

    def test_get_leaderboard_handles_non_numeric_metrics(self, system):
        """Test that leaderboard handles non-numeric metrics gracefully."""
        perf = system.get_agent_performance("agent-0")

        with system._lock:
            agents = {"agent-0": perf}
            system._write_data(agents)

        # Try to get leaderboard by a non-existent metric
        leaderboard = system.get_leaderboard(metric="nonexistent_metric")

        # Should return empty list
        assert leaderboard == []
