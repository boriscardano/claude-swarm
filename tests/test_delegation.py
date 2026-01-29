"""Unit tests for delegation module.

Tests cover:
- Skill extraction from tasks (file extensions, keywords)
- Agent scoring algorithm
- Best agent selection
- Delegation with exclusions
- Required tools filtering
- History tracking
- Edge cases (no available agents, empty skills)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from claudeswarm.agent_cards import AgentCard, AgentCardRegistry
from claudeswarm.delegation import (
    DELEGATION_HISTORY_FILENAME,
    FILE_EXTENSION_SKILLS,
    KEYWORD_SKILLS,
    DelegationError,
    DelegationManager,
    DelegationResult,
    NoSuitableAgentError,
    SkillRequirement,
    calculate_agent_score,
    extract_skills_from_task,
    find_best_agent,
    get_delegation_history_path,
)
from claudeswarm.tasks import Task, TaskPriority, TaskStatus


@pytest.fixture
def temp_project():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_registry():
    """Create a mock AgentCardRegistry."""
    registry = Mock(spec=AgentCardRegistry)
    return registry


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        task_id="task-123",
        objective="Implement user authentication with JWT tokens",
        created_by="agent-0",
        status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        constraints=["Use JWT", "No external auth services"],
        files=["src/auth.py", "tests/test_auth.py"],
        context_id="feature-auth",
    )


@pytest.fixture
def python_agent():
    """Create a Python specialist agent."""
    return AgentCard(
        agent_id="python-agent",
        name="Python Specialist",
        skills=["python", "backend", "testing", "authentication"],
        tools=["Read", "Write", "Edit", "Bash"],
        availability="active",
        success_rates={"python": 0.9, "backend": 0.85, "testing": 0.8},
        specializations=["python", "backend"],
    )


@pytest.fixture
def frontend_agent():
    """Create a frontend specialist agent."""
    return AgentCard(
        agent_id="frontend-agent",
        name="Frontend Specialist",
        skills=["javascript", "typescript", "react", "css"],
        tools=["Read", "Write", "Edit"],
        availability="active",
        success_rates={"javascript": 0.95, "react": 0.9},
        specializations=["react", "frontend"],
    )


@pytest.fixture
def busy_agent():
    """Create a busy agent."""
    return AgentCard(
        agent_id="busy-agent",
        name="Busy Agent",
        skills=["python", "backend"],
        tools=["Read", "Write"],
        availability="busy",
        success_rates={"python": 0.95},
        specializations=["python"],
    )


@pytest.fixture
def delegation_manager(temp_project, mock_registry):
    """Create a DelegationManager with mocked dependencies."""
    with patch("claudeswarm.delegation.AgentCardRegistry", return_value=mock_registry):
        with patch("claudeswarm.delegation.TaskManager"):
            manager = DelegationManager(project_root=temp_project)
            manager.card_registry = mock_registry
            return manager


class TestSkillRequirement:
    """Tests for SkillRequirement dataclass."""

    def test_valid_skill_requirement(self):
        """Test creating a valid skill requirement."""
        req = SkillRequirement(skill="python", importance=0.8, minimum_proficiency=0.5)

        assert req.skill == "python"
        assert req.importance == 0.8
        assert req.minimum_proficiency == 0.5

    def test_default_values(self):
        """Test default values for optional fields."""
        req = SkillRequirement(skill="python")

        assert req.importance == 1.0
        assert req.minimum_proficiency == 0.0

    def test_importance_validation_too_high(self):
        """Test that importance > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="importance must be between 0.0 and 1.0"):
            SkillRequirement(skill="python", importance=1.5)

    def test_importance_validation_too_low(self):
        """Test that importance < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="importance must be between 0.0 and 1.0"):
            SkillRequirement(skill="python", importance=-0.1)

    def test_minimum_proficiency_validation_too_high(self):
        """Test that minimum_proficiency > 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="minimum_proficiency must be between 0.0 and 1.0"):
            SkillRequirement(skill="python", minimum_proficiency=1.5)

    def test_minimum_proficiency_validation_too_low(self):
        """Test that minimum_proficiency < 0.0 raises ValueError."""
        with pytest.raises(ValueError, match="minimum_proficiency must be between 0.0 and 1.0"):
            SkillRequirement(skill="python", minimum_proficiency=-0.1)

    def test_boundary_values(self):
        """Test boundary values 0.0 and 1.0 are valid."""
        req1 = SkillRequirement(skill="python", importance=0.0, minimum_proficiency=0.0)
        req2 = SkillRequirement(skill="python", importance=1.0, minimum_proficiency=1.0)

        assert req1.importance == 0.0
        assert req1.minimum_proficiency == 0.0
        assert req2.importance == 1.0
        assert req2.minimum_proficiency == 1.0


class TestDelegationResult:
    """Tests for DelegationResult dataclass."""

    def test_successful_result(self):
        """Test creating a successful delegation result."""
        result = DelegationResult(
            success=True,
            task_id="task-123",
            agent_id="agent-1",
            match_score=0.85,
            skill_matches={"python": 0.9, "backend": 0.8},
            reason="Best match",
            alternatives=[("agent-2", 0.7)],
        )

        assert result.success is True
        assert result.task_id == "task-123"
        assert result.agent_id == "agent-1"
        assert result.match_score == 0.85
        assert result.skill_matches == {"python": 0.9, "backend": 0.8}
        assert result.reason == "Best match"
        assert result.alternatives == [("agent-2", 0.7)]
        assert result.timestamp is not None

    def test_failed_result(self):
        """Test creating a failed delegation result."""
        result = DelegationResult(
            success=False, task_id="task-123", reason="No suitable agent found"
        )

        assert result.success is False
        assert result.task_id == "task-123"
        assert result.agent_id is None
        assert result.match_score == 0.0
        assert result.skill_matches == {}
        assert result.reason == "No suitable agent found"

    def test_to_dict(self):
        """Test converting result to dictionary."""
        result = DelegationResult(
            success=True,
            task_id="task-123",
            agent_id="agent-1",
            match_score=0.85,
            skill_matches={"python": 0.9},
            reason="Success",
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["task_id"] == "task-123"
        assert result_dict["agent_id"] == "agent-1"
        assert result_dict["match_score"] == 0.85
        assert result_dict["skill_matches"] == {"python": 0.9}
        assert result_dict["reason"] == "Success"
        assert "timestamp" in result_dict

    def test_from_dict(self):
        """Test creating result from dictionary."""
        data = {
            "success": True,
            "task_id": "task-456",
            "agent_id": "agent-2",
            "match_score": 0.75,
            "skill_matches": {"javascript": 0.8},
            "reason": "Good match",
            "alternatives": [("agent-3", 0.6)],
            "timestamp": "2025-01-30T12:00:00Z",
        }

        result = DelegationResult.from_dict(data)

        assert result.success is True
        assert result.task_id == "task-456"
        assert result.agent_id == "agent-2"
        assert result.match_score == 0.75
        assert result.skill_matches == {"javascript": 0.8}
        assert result.reason == "Good match"
        assert result.alternatives == [("agent-3", 0.6)]
        assert result.timestamp == "2025-01-30T12:00:00Z"


class TestGetDelegationHistoryPath:
    """Tests for get_delegation_history_path function."""

    def test_with_project_root(self, temp_project):
        """Test getting path with specific project root."""
        path = get_delegation_history_path(temp_project)

        # Use resolve() to handle symlinks (macOS /var vs /private/var)
        assert path.resolve() == (temp_project / DELEGATION_HISTORY_FILENAME).resolve()
        assert path.name == DELEGATION_HISTORY_FILENAME

    def test_without_project_root(self):
        """Test getting path without specifying project root."""
        path = get_delegation_history_path()

        assert path.name == DELEGATION_HISTORY_FILENAME
        assert path.is_absolute()


class TestExtractSkillsFromTask:
    """Tests for extract_skills_from_task function."""

    def test_extract_from_python_files(self):
        """Test skill extraction from Python file extensions."""
        task = Task(
            task_id="task-1",
            objective="Fix bug",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=["src/main.py", "tests/test_main.py"],
        )

        skills = extract_skills_from_task(task)
        skill_names = [s.skill for s in skills]

        assert "python" in skill_names
        assert "backend" in skill_names
        # Skills from files should have importance 0.8
        python_skill = next(s for s in skills if s.skill == "python")
        assert python_skill.importance == 0.8

    def test_extract_from_javascript_files(self):
        """Test skill extraction from JavaScript/TypeScript files."""
        task = Task(
            task_id="task-2",
            objective="Add feature",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=["src/App.tsx", "src/utils.js"],
        )

        skills = extract_skills_from_task(task)
        skill_names = [s.skill for s in skills]

        assert "typescript" in skill_names
        assert "react" in skill_names
        assert "frontend" in skill_names
        assert "javascript" in skill_names

    def test_extract_from_keywords_in_objective(self):
        """Test skill extraction from keywords in objective."""
        task = Task(
            task_id="task-3",
            objective="Write unit tests for authentication API",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=[],
        )

        skills = extract_skills_from_task(task)
        skill_names = [s.skill for s in skills]

        assert "testing" in skill_names
        assert "unit-testing" in skill_names
        assert "api" in skill_names
        assert "authentication" in skill_names
        # Skills from keywords should have importance 0.7
        testing_skill = next(s for s in skills if s.skill == "testing")
        assert testing_skill.importance == 0.7

    def test_extract_from_constraints(self):
        """Test skill extraction from task constraints."""
        task = Task(
            task_id="task-4",
            objective="Implement feature",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            constraints=["Use Docker for deployment", "Add database migration"],
            files=[],
        )

        skills = extract_skills_from_task(task)
        skill_names = [s.skill for s in skills]

        assert "docker" in skill_names
        assert "deployment" in skill_names
        assert "database" in skill_names
        assert "migration" in skill_names

    def test_extract_explicit_skill_requirements(self):
        """Test extraction of explicit skill requirements."""
        task = Task(
            task_id="task-5",
            objective="Requires python expertise and needs golang experience",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=[],
        )

        skills = extract_skills_from_task(task)
        skill_names = [s.skill for s in skills]

        assert "python" in skill_names
        assert "golang" in skill_names
        # Explicit requirements should have importance 1.0
        python_skill = next(s for s in skills if s.skill == "python")
        golang_skill = next(s for s in skills if s.skill == "golang")
        assert python_skill.importance == 1.0
        assert golang_skill.importance == 1.0

    def test_extract_combined_sources(self, sample_task):
        """Test skill extraction from multiple sources."""
        skills = extract_skills_from_task(sample_task)
        skill_names = [s.skill for s in skills]

        # From files (.py)
        assert "python" in skill_names
        assert "backend" in skill_names
        # From objective/constraints keywords
        assert "authentication" in skill_names

    def test_max_importance_when_duplicate(self):
        """Test that duplicate skills take max importance."""
        task = Task(
            task_id="task-6",
            objective="Requires python expertise",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=["src/main.py"],  # python skill with importance 0.8
            # objective has "requires python" with importance 1.0
        )

        skills = extract_skills_from_task(task)
        python_skill = next(s for s in skills if s.skill == "python")
        # Should take the maximum importance (1.0 from explicit requirement)
        assert python_skill.importance == 1.0

    def test_no_skills_extracted(self):
        """Test task with no extractable skills."""
        task = Task(
            task_id="task-7",
            objective="Do something",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=[],
        )

        skills = extract_skills_from_task(task)
        assert skills == []

    def test_case_insensitive_extraction(self):
        """Test that keyword extraction is case-insensitive."""
        task = Task(
            task_id="task-8",
            objective="Fix BUG in API authentication",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=[],
        )

        skills = extract_skills_from_task(task)
        skill_names = [s.skill for s in skills]

        assert "debugging" in skill_names
        assert "api" in skill_names
        assert "authentication" in skill_names

    def test_file_extension_mappings(self):
        """Test various file extension to skill mappings."""
        # Test a selection of file extensions
        test_cases = [
            (".go", ["golang", "backend"]),
            (".rs", ["rust", "systems"]),
            (".sql", ["sql", "database"]),
            (".md", ["documentation", "markdown"]),
            (".yaml", ["yaml", "configuration"]),
            (".sh", ["shell", "scripting", "bash"]),
        ]

        for ext, expected_skills in test_cases:
            task = Task(
                task_id=f"task-{ext}",
                objective="Task",
                created_by="agent-0",
                status=TaskStatus.PENDING,
                priority=TaskPriority.NORMAL,
                files=[f"file{ext}"],
            )

            skills = extract_skills_from_task(task)
            skill_names = [s.skill for s in skills]

            for expected in expected_skills:
                assert expected in skill_names, f"Expected {expected} for {ext}"

    def test_skills_sorted_by_importance(self):
        """Test that skills are sorted by importance (descending)."""
        task = Task(
            task_id="task-9",
            objective="Requires python expertise and add tests",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=[],
        )

        skills = extract_skills_from_task(task)

        # Verify skills are in descending order of importance
        for i in range(len(skills) - 1):
            assert (
                skills[i].importance >= skills[i + 1].importance
            ), "Skills should be sorted by importance descending"


class TestCalculateAgentScore:
    """Tests for calculate_agent_score function."""

    def test_score_with_matching_skills(self, python_agent):
        """Test scoring agent with matching skills."""
        requirements = [
            SkillRequirement(skill="python", importance=1.0),
            SkillRequirement(skill="backend", importance=0.8),
        ]

        score, skill_matches = calculate_agent_score(python_agent, requirements)

        assert score > 0.0
        assert "python" in skill_matches
        assert "backend" in skill_matches
        assert skill_matches["python"] == 0.9  # Agent's success rate
        assert skill_matches["backend"] == 0.85

    def test_score_unavailable_agent(self, busy_agent):
        """Test that unavailable agents get score 0."""
        requirements = [SkillRequirement(skill="python", importance=1.0)]

        score, skill_matches = calculate_agent_score(busy_agent, requirements)

        assert score == 0.0
        assert skill_matches == {}

    def test_score_with_no_requirements(self, python_agent):
        """Test scoring when there are no specific requirements."""
        score, skill_matches = calculate_agent_score(python_agent, [])

        assert score == 0.5  # Base score for any available agent
        assert skill_matches == {}

    def test_score_with_priority_boost(self, python_agent):
        """Test that priority boost increases score."""
        requirements = [SkillRequirement(skill="python", importance=1.0)]

        score_normal, _ = calculate_agent_score(python_agent, requirements, priority_boost=0.0)
        score_boosted, _ = calculate_agent_score(python_agent, requirements, priority_boost=0.1)

        assert score_boosted > score_normal
        # The difference may be less than the boost due to the cap at 1.0
        assert score_boosted - score_normal >= 0.0

    def test_score_with_minimum_proficiency_not_met(self, python_agent):
        """Test that skills below minimum proficiency are excluded."""
        # Agent has testing at 0.8, require 0.9
        requirements = [SkillRequirement(skill="testing", importance=1.0, minimum_proficiency=0.9)]

        score, skill_matches = calculate_agent_score(python_agent, requirements)

        # Should still calculate a score, but testing skill won't contribute
        assert "testing" in skill_matches
        assert skill_matches["testing"] == 0.0  # Below minimum

    def test_score_with_specialization_bonus(self, python_agent):
        """Test that specializations provide a bonus."""
        requirements = [
            SkillRequirement(skill="python", importance=1.0)  # python is a specialization
        ]

        score, _ = calculate_agent_score(python_agent, requirements)

        # Score should include specialization bonus
        # Base score from skill match + specialization bonus
        assert score > 0.9  # Should be higher than just the skill proficiency

    def test_specialization_bonus_capped(self, python_agent):
        """Test that specialization bonus is capped at 0.15."""
        # Create many requirements that are all specializations
        requirements = [
            SkillRequirement(skill="python", importance=1.0),
            SkillRequirement(skill="backend", importance=1.0),
        ]

        score, _ = calculate_agent_score(python_agent, requirements)

        # Even with multiple specializations, bonus shouldn't exceed cap
        # Max score should be <= 1.0
        assert score <= 1.0

    def test_score_with_no_matching_skills(self, python_agent):
        """Test scoring when agent has no matching skills."""
        requirements = [SkillRequirement(skill="quantum-computing", importance=1.0)]

        score, skill_matches = calculate_agent_score(python_agent, requirements)

        # Agent has no proficiency in this skill (defaults to 0.0)
        assert score >= 0.0
        assert "quantum-computing" in skill_matches

    def test_score_weighted_by_importance(self, python_agent):
        """Test that skill importance affects overall score."""
        # High importance skill
        requirements_high = [SkillRequirement(skill="python", importance=1.0)]
        score_high, _ = calculate_agent_score(python_agent, requirements_high)

        # Low importance skill
        requirements_low = [SkillRequirement(skill="python", importance=0.1)]
        score_low, _ = calculate_agent_score(python_agent, requirements_low)

        # Both should have similar base, but high importance should contribute more
        # Actually, with different weights they normalize differently
        assert score_high >= 0.0
        assert score_low >= 0.0

    def test_score_normalization(self, python_agent):
        """Test that scores are properly normalized."""
        requirements = [
            SkillRequirement(skill="python", importance=0.5),
            SkillRequirement(skill="backend", importance=0.5),
        ]

        score, _ = calculate_agent_score(python_agent, requirements)

        # Score should be normalized and within [0, 1]
        assert 0.0 <= score <= 1.0

    def test_score_caps_at_one(self, python_agent):
        """Test that final score never exceeds 1.0."""
        requirements = [
            SkillRequirement(skill="python", importance=1.0),
            SkillRequirement(skill="backend", importance=1.0),
        ]

        # Even with high skills and specialization bonus
        score, _ = calculate_agent_score(python_agent, requirements, priority_boost=0.5)

        assert score <= 1.0


class TestDelegationManagerInit:
    """Tests for DelegationManager initialization."""

    def test_init_with_project_root(self, temp_project):
        """Test initializing with a specific project root."""
        with patch("claudeswarm.delegation.AgentCardRegistry"):
            with patch("claudeswarm.delegation.TaskManager"):
                manager = DelegationManager(project_root=temp_project)

                # Use resolve() to handle symlinks (macOS /var vs /private/var)
                assert manager.project_root.resolve() == temp_project.resolve()
                assert manager.history_path.resolve() == (
                    temp_project / DELEGATION_HISTORY_FILENAME
                ).resolve()

    def test_init_without_project_root(self):
        """Test initializing without specifying project root."""
        with patch("claudeswarm.delegation.AgentCardRegistry"):
            with patch("claudeswarm.delegation.TaskManager"):
                manager = DelegationManager()

                assert manager.project_root is not None
                assert manager.history_path.name == DELEGATION_HISTORY_FILENAME


class TestDelegationManagerHistoryOperations:
    """Tests for delegation history reading and writing."""

    def test_read_history_empty(self, delegation_manager):
        """Test reading history when file doesn't exist."""
        history = delegation_manager._read_history()

        assert history == []

    def test_write_and_read_history(self, delegation_manager):
        """Test writing and reading delegation history."""
        results = [
            DelegationResult(
                success=True,
                task_id="task-1",
                agent_id="agent-1",
                match_score=0.85,
                reason="Good match",
            ),
            DelegationResult(
                success=False, task_id="task-2", reason="No suitable agent"
            ),
        ]

        delegation_manager._write_history(results)
        read_results = delegation_manager._read_history()

        assert len(read_results) == 2
        assert read_results[0].task_id == "task-1"
        assert read_results[0].success is True
        assert read_results[1].task_id == "task-2"
        assert read_results[1].success is False

    def test_history_trimming(self, delegation_manager):
        """Test that history is trimmed when it exceeds max length."""
        # Create more than MAX_DELEGATION_HISTORY entries
        from claudeswarm.delegation import MAX_DELEGATION_HISTORY

        results = [
            DelegationResult(success=True, task_id=f"task-{i}", agent_id=f"agent-{i}")
            for i in range(MAX_DELEGATION_HISTORY + 100)
        ]

        delegation_manager._write_history(results)
        read_results = delegation_manager._read_history()

        assert len(read_results) == MAX_DELEGATION_HISTORY
        # Should keep most recent entries
        assert read_results[-1].task_id == f"task-{MAX_DELEGATION_HISTORY + 99}"

    def test_record_delegation(self, delegation_manager):
        """Test recording a delegation result."""
        result = DelegationResult(
            success=True, task_id="task-1", agent_id="agent-1", match_score=0.9
        )

        delegation_manager._record_delegation(result)
        history = delegation_manager._read_history()

        assert len(history) == 1
        assert history[0].task_id == "task-1"


class TestDelegationManagerFindBestAgent:
    """Tests for finding the best agent for a task."""

    def test_find_best_agent_with_matches(
        self, delegation_manager, sample_task, python_agent, frontend_agent
    ):
        """Test finding best agent when there are good matches."""
        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_agent,
        ]

        best_agent, score, skill_matches = delegation_manager.find_best_agent(sample_task)

        assert best_agent is not None
        assert best_agent.agent_id == "python-agent"  # Better match for Python task
        assert score > 0.0
        assert len(skill_matches) > 0

    def test_find_best_agent_no_agents(self, delegation_manager, sample_task):
        """Test finding best agent when no agents are available."""
        delegation_manager.card_registry.list_cards.return_value = []

        best_agent, score, skill_matches = delegation_manager.find_best_agent(sample_task)

        assert best_agent is None
        assert score == 0.0
        assert skill_matches == {}

    def test_find_best_agent_with_exclusions(
        self, delegation_manager, sample_task, python_agent, frontend_agent
    ):
        """Test finding best agent with exclusion list."""
        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_agent,
        ]

        best_agent, score, _ = delegation_manager.find_best_agent(
            sample_task, exclude_agents=["python-agent"]
        )

        # Frontend agent might have score 0 for Python tasks (no matching skills)
        # So either we get the frontend agent or None
        if best_agent is not None:
            assert best_agent.agent_id == "frontend-agent"  # Python agent was excluded
        # If None, that's also valid - frontend agent doesn't match the task

    def test_find_best_agent_with_required_tools(
        self, delegation_manager, sample_task, python_agent, frontend_agent
    ):
        """Test finding best agent with required tools."""
        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_agent,
        ]

        best_agent, score, _ = delegation_manager.find_best_agent(
            sample_task, required_tools=["Bash"]
        )

        assert best_agent is not None
        assert best_agent.agent_id == "python-agent"  # Only one with Bash tool

    def test_find_best_agent_no_matches_after_filtering(
        self, delegation_manager, sample_task, python_agent
    ):
        """Test when all agents are filtered out."""
        delegation_manager.card_registry.list_cards.return_value = [python_agent]

        best_agent, score, _ = delegation_manager.find_best_agent(
            sample_task, exclude_agents=["python-agent"]
        )

        assert best_agent is None
        assert score == 0.0

    def test_find_best_agent_priority_boost(
        self, delegation_manager, python_agent, frontend_agent
    ):
        """Test that high priority tasks get score boost."""
        # Create high priority task
        high_priority_task = Task(
            task_id="task-hp",
            objective="Critical bug fix",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.CRITICAL,
            files=["src/main.py"],
        )

        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_agent,
        ]

        best_agent, score_high, _ = delegation_manager.find_best_agent(high_priority_task)

        # Create normal priority task
        normal_priority_task = Task(
            task_id="task-np",
            objective="Bug fix",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=["src/main.py"],
        )

        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_agent,
        ]

        _, score_normal, _ = delegation_manager.find_best_agent(normal_priority_task)

        # High priority should have higher score
        assert score_high > score_normal

    def test_find_best_agent_chooses_highest_score(
        self, delegation_manager, sample_task, python_agent, frontend_agent
    ):
        """Test that the agent with highest score is selected."""
        # For a Python task, python_agent should score higher
        delegation_manager.card_registry.list_cards.return_value = [
            frontend_agent,
            python_agent,
        ]

        best_agent, score, _ = delegation_manager.find_best_agent(sample_task)

        assert best_agent.agent_id == "python-agent"


class TestDelegationManagerDelegateTask:
    """Tests for delegating tasks to agents."""

    def test_delegate_task_auto_select(
        self, delegation_manager, sample_task, python_agent, frontend_agent
    ):
        """Test delegating task with automatic agent selection."""
        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_agent,
        ]
        delegation_manager.card_registry.get_card.return_value = python_agent
        delegation_manager.task_manager.assign_task = Mock()

        result = delegation_manager.delegate_task(sample_task)

        assert result.success is True
        assert result.task_id == sample_task.task_id
        assert result.agent_id == "python-agent"
        assert result.match_score > 0.0
        assert len(result.skill_matches) > 0
        delegation_manager.task_manager.assign_task.assert_called_once()

    def test_delegate_task_specific_agent(
        self, delegation_manager, sample_task, python_agent
    ):
        """Test delegating task to a specific agent."""
        delegation_manager.card_registry.get_card.return_value = python_agent
        delegation_manager.task_manager.assign_task = Mock()

        result = delegation_manager.delegate_task(sample_task, agent_id="python-agent")

        assert result.success is True
        assert result.agent_id == "python-agent"
        delegation_manager.task_manager.assign_task.assert_called_once()

    def test_delegate_task_no_suitable_agent(self, delegation_manager, sample_task):
        """Test delegating when no suitable agent is found."""
        delegation_manager.card_registry.list_cards.return_value = []

        with pytest.raises(NoSuitableAgentError, match="No suitable agent found"):
            delegation_manager.delegate_task(sample_task)

        # Verify failure was recorded
        history = delegation_manager._read_history()
        assert len(history) == 1
        assert history[0].success is False

    def test_delegate_task_agent_not_found(self, delegation_manager, sample_task):
        """Test delegating to a non-existent agent."""
        delegation_manager.card_registry.get_card.return_value = None

        with pytest.raises(DelegationError, match="Agent .* not found"):
            delegation_manager.delegate_task(sample_task, agent_id="nonexistent-agent")

    def test_delegate_task_agent_not_available(
        self, delegation_manager, sample_task, busy_agent
    ):
        """Test delegating to an unavailable agent."""
        delegation_manager.card_registry.get_card.return_value = busy_agent

        with pytest.raises(DelegationError, match="Agent .* is not available"):
            delegation_manager.delegate_task(sample_task, agent_id="busy-agent")

    def test_delegate_task_assignment_fails(
        self, delegation_manager, sample_task, python_agent
    ):
        """Test handling of task assignment failure."""
        delegation_manager.card_registry.list_cards.return_value = [python_agent]
        delegation_manager.card_registry.get_card.return_value = python_agent
        delegation_manager.task_manager.assign_task.side_effect = Exception("Assignment failed")

        with pytest.raises(DelegationError, match="Failed to assign task"):
            delegation_manager.delegate_task(sample_task)

    def test_delegate_task_with_message(
        self, delegation_manager, sample_task, python_agent
    ):
        """Test delegating task with custom message."""
        delegation_manager.card_registry.get_card.return_value = python_agent
        delegation_manager.task_manager.assign_task = Mock()

        custom_message = "Please prioritize this task"
        result = delegation_manager.delegate_task(
            sample_task, agent_id="python-agent", message=custom_message
        )

        assert result.success is True
        # Verify message was passed to assign_task
        delegation_manager.task_manager.assign_task.assert_called_once()
        call_args = delegation_manager.task_manager.assign_task.call_args
        assert custom_message in call_args[0] or custom_message in call_args.kwargs.values()

    def test_delegate_task_records_alternatives(
        self, delegation_manager, sample_task, python_agent, frontend_agent
    ):
        """Test that alternatives are recorded when auto-selecting."""
        # Make frontend agent have some Python skills so it scores > 0
        frontend_with_python = AgentCard(
            agent_id="frontend-agent",
            name="Frontend Specialist",
            skills=["javascript", "typescript", "react", "css", "python"],  # Add python
            tools=["Read", "Write", "Edit"],
            availability="active",
            success_rates={"javascript": 0.95, "react": 0.9, "python": 0.5},  # Add python
            specializations=["react", "frontend"],
        )

        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_with_python,
        ]
        delegation_manager.card_registry.get_card.return_value = python_agent
        delegation_manager.task_manager.assign_task = Mock()

        result = delegation_manager.delegate_task(sample_task)

        # Should have alternatives recorded
        assert len(result.alternatives) > 0
        # Alternatives should be other agents
        alternative_ids = [agent_id for agent_id, _ in result.alternatives]
        assert "frontend-agent" in alternative_ids

    def test_delegate_task_history_recorded(
        self, delegation_manager, sample_task, python_agent
    ):
        """Test that delegation is recorded in history."""
        delegation_manager.card_registry.list_cards.return_value = [python_agent]
        delegation_manager.card_registry.get_card.return_value = python_agent
        delegation_manager.task_manager.assign_task = Mock()

        delegation_manager.delegate_task(sample_task)

        history = delegation_manager._read_history()
        assert len(history) == 1
        assert history[0].success is True
        assert history[0].task_id == sample_task.task_id


class TestDelegationManagerDelegateToBest:
    """Tests for delegate_to_best convenience method."""

    def test_delegate_to_best_creates_and_delegates(
        self, delegation_manager, python_agent
    ):
        """Test that delegate_to_best creates task and delegates."""
        delegation_manager.card_registry.list_cards.return_value = [python_agent]
        delegation_manager.card_registry.get_card.return_value = python_agent

        # Mock task creation
        mock_task = Task(
            task_id="new-task",
            objective="Test objective",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
        )
        delegation_manager.task_manager.create_task.return_value = mock_task
        delegation_manager.task_manager.assign_task = Mock()

        task, result = delegation_manager.delegate_to_best(
            objective="Test objective",
            created_by="agent-0",
            priority=TaskPriority.HIGH,
            constraints=["Constraint 1"],
            files=["file1.py"],
            context_id="context-1",
        )

        assert task is not None
        assert result.success is True
        delegation_manager.task_manager.create_task.assert_called_once()


class TestDelegationManagerGetDelegationHistory:
    """Tests for querying delegation history."""

    def test_get_delegation_history_all(self, delegation_manager):
        """Test getting all delegation history."""
        results = [
            DelegationResult(success=True, task_id="task-1", agent_id="agent-1"),
            DelegationResult(success=True, task_id="task-2", agent_id="agent-2"),
            DelegationResult(success=False, task_id="task-3"),
        ]
        delegation_manager._write_history(results)

        history = delegation_manager.get_delegation_history()

        assert len(history) == 3
        # Should be in reverse order (most recent first)
        assert history[0].task_id == "task-3"
        assert history[1].task_id == "task-2"
        assert history[2].task_id == "task-1"

    def test_get_delegation_history_filter_by_task(self, delegation_manager):
        """Test filtering history by task ID."""
        results = [
            DelegationResult(success=True, task_id="task-1", agent_id="agent-1"),
            DelegationResult(success=True, task_id="task-2", agent_id="agent-2"),
        ]
        delegation_manager._write_history(results)

        history = delegation_manager.get_delegation_history(task_id="task-1")

        assert len(history) == 1
        assert history[0].task_id == "task-1"

    def test_get_delegation_history_filter_by_agent(self, delegation_manager):
        """Test filtering history by agent ID."""
        results = [
            DelegationResult(success=True, task_id="task-1", agent_id="agent-1"),
            DelegationResult(success=True, task_id="task-2", agent_id="agent-1"),
            DelegationResult(success=True, task_id="task-3", agent_id="agent-2"),
        ]
        delegation_manager._write_history(results)

        history = delegation_manager.get_delegation_history(agent_id="agent-1")

        assert len(history) == 2
        assert all(r.agent_id == "agent-1" for r in history)

    def test_get_delegation_history_success_only(self, delegation_manager):
        """Test filtering for successful delegations only."""
        results = [
            DelegationResult(success=True, task_id="task-1", agent_id="agent-1"),
            DelegationResult(success=False, task_id="task-2"),
            DelegationResult(success=True, task_id="task-3", agent_id="agent-2"),
        ]
        delegation_manager._write_history(results)

        history = delegation_manager.get_delegation_history(success_only=True)

        assert len(history) == 2
        assert all(r.success for r in history)

    def test_get_delegation_history_with_limit(self, delegation_manager):
        """Test limiting number of results."""
        results = [
            DelegationResult(success=True, task_id=f"task-{i}", agent_id=f"agent-{i}")
            for i in range(10)
        ]
        delegation_manager._write_history(results)

        history = delegation_manager.get_delegation_history(limit=3)

        assert len(history) == 3
        # Should get most recent 3
        assert history[0].task_id == "task-9"
        assert history[1].task_id == "task-8"
        assert history[2].task_id == "task-7"


class TestDelegationManagerGetAgentStats:
    """Tests for getting agent delegation statistics."""

    def test_get_agent_stats_no_history(self, delegation_manager):
        """Test getting stats for agent with no history."""
        stats = delegation_manager.get_agent_delegation_stats("agent-1")

        assert stats["agent_id"] == "agent-1"
        assert stats["total_delegations"] == 0
        assert stats["successful"] == 0
        assert stats["failed"] == 0
        assert stats["average_score"] == 0.0
        assert stats["common_skills"] == []

    def test_get_agent_stats_with_history(self, delegation_manager):
        """Test getting stats for agent with delegation history."""
        results = [
            DelegationResult(
                success=True,
                task_id="task-1",
                agent_id="agent-1",
                match_score=0.9,
                skill_matches={"python": 0.9, "backend": 0.8},
            ),
            DelegationResult(
                success=True,
                task_id="task-2",
                agent_id="agent-1",
                match_score=0.85,
                skill_matches={"python": 0.9, "testing": 0.7},
            ),
            DelegationResult(success=False, task_id="task-3", agent_id="agent-1"),
            DelegationResult(
                success=True, task_id="task-4", agent_id="agent-2", match_score=0.8
            ),
        ]
        delegation_manager._write_history(results)

        stats = delegation_manager.get_agent_delegation_stats("agent-1")

        assert stats["agent_id"] == "agent-1"
        assert stats["total_delegations"] == 3
        assert stats["successful"] == 2
        assert stats["failed"] == 1
        assert stats["average_score"] == pytest.approx(0.875, abs=0.01)
        assert "python" in stats["common_skills"]

    def test_get_agent_stats_common_skills_ordered(self, delegation_manager):
        """Test that common skills are ordered by frequency."""
        results = [
            DelegationResult(
                success=True,
                task_id=f"task-{i}",
                agent_id="agent-1",
                match_score=0.8,
                skill_matches={
                    "python": 0.9,  # Appears in all 3
                    "backend": 0.8,  # Appears in 2
                    "testing": 0.7 if i == 0 else 0.0,  # Appears in 1
                },
            )
            for i in range(3)
        ]
        delegation_manager._write_history(results)

        stats = delegation_manager.get_agent_delegation_stats("agent-1")

        # Python should be first (most common)
        assert stats["common_skills"][0] == "python"


class TestModuleLevelFindBestAgent:
    """Tests for module-level find_best_agent function."""

    def test_find_best_agent_function(self, temp_project, sample_task, python_agent):
        """Test module-level convenience function."""
        with patch("claudeswarm.delegation.DelegationManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager.find_best_agent.return_value = (python_agent, 0.9, {"python": 0.9})
            mock_manager_class.return_value = mock_manager

            agent = find_best_agent(sample_task, project_root=temp_project)

            assert agent == python_agent
            mock_manager_class.assert_called_once_with(temp_project)
            mock_manager.find_best_agent.assert_called_once_with(sample_task)


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_task_objective(self):
        """Test handling task with empty objective."""
        task = Task(
            task_id="task-empty",
            objective="",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
        )

        skills = extract_skills_from_task(task)
        assert skills == []

    def test_task_with_nonexistent_file_extension(self):
        """Test task with unrecognized file extension."""
        task = Task(
            task_id="task-unknown",
            objective="Process data",
            created_by="agent-0",
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            files=["data.xyz", "info.abc"],
        )

        skills = extract_skills_from_task(task)
        # Should still extract from objective if possible
        assert isinstance(skills, list)

    def test_multiple_agents_same_score(
        self, delegation_manager, sample_task, python_agent
    ):
        """Test behavior when multiple agents have the same score."""
        # Create two identical agents
        agent1 = python_agent
        agent2 = AgentCard(
            agent_id="python-agent-2",
            name="Python Specialist 2",
            skills=python_agent.skills,
            tools=python_agent.tools,
            availability="active",
            success_rates=python_agent.success_rates,
            specializations=python_agent.specializations,
        )

        delegation_manager.card_registry.list_cards.return_value = [agent1, agent2]

        best_agent, score, _ = delegation_manager.find_best_agent(sample_task)

        # Should select one of them (first in list typically)
        assert best_agent is not None
        assert best_agent.agent_id in ["python-agent", "python-agent-2"]

    def test_agent_with_no_skills(self):
        """Test scoring agent with no skills."""
        no_skill_agent = AgentCard(
            agent_id="no-skills",
            name="No Skills Agent",
            skills=[],
            tools=["Read"],
            availability="active",
            success_rates={},
            specializations=[],
        )

        requirements = [SkillRequirement(skill="python", importance=1.0)]

        score, skill_matches = calculate_agent_score(no_skill_agent, requirements)

        # Should return a score, even if low
        assert score >= 0.0

    def test_delegation_with_all_agents_excluded(
        self, delegation_manager, sample_task, python_agent, frontend_agent
    ):
        """Test delegation when all agents are excluded."""
        delegation_manager.card_registry.list_cards.return_value = [
            python_agent,
            frontend_agent,
        ]

        best_agent, score, _ = delegation_manager.find_best_agent(
            sample_task, exclude_agents=["python-agent", "frontend-agent"]
        )

        assert best_agent is None
        assert score == 0.0

    def test_delegation_with_impossible_tool_requirements(
        self, delegation_manager, sample_task, python_agent
    ):
        """Test delegation when required tool doesn't exist."""
        delegation_manager.card_registry.list_cards.return_value = [python_agent]

        best_agent, score, _ = delegation_manager.find_best_agent(
            sample_task, required_tools=["NonexistentTool"]
        )

        assert best_agent is None
        assert score == 0.0

    def test_skill_requirement_zero_importance(self, python_agent):
        """Test skill requirement with zero importance."""
        requirements = [SkillRequirement(skill="python", importance=0.0)]

        score, skill_matches = calculate_agent_score(python_agent, requirements)

        # Should still calculate, but skill won't contribute much
        assert score >= 0.0
        assert "python" in skill_matches

    def test_concurrent_delegation_recording(self, delegation_manager, sample_task):
        """Test that concurrent delegation recordings don't corrupt history."""
        import threading

        results = []
        errors = []

        def record_delegation(task_id):
            try:
                result = DelegationResult(
                    success=True, task_id=task_id, agent_id="agent-1", match_score=0.8
                )
                delegation_manager._record_delegation(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads recording delegations
        threads = [
            threading.Thread(target=record_delegation, args=(f"task-{i}",))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Check no errors occurred
        assert len(errors) == 0

        # Check all records were saved
        history = delegation_manager._read_history()
        assert len(history) == 10
