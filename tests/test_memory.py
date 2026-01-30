"""Unit tests for memory.py module.

Tests cover:
- AgentMemory creation and operations
- Task history tracking
- Pattern learning
- Relationship tracking
- Path validation for agent IDs
- Knowledge storage
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from claudeswarm.memory import (
    MEMORY_DIR,
    MAX_KNOWLEDGE_ITEMS,
    MAX_PATTERNS,
    MAX_TASK_HISTORY,
    AgentMemory,
    AgentRelationship,
    LearnedPattern,
    MemoryStore,
    TaskMemory,
    get_memory_path,
)


class TestTaskMemory:
    """Tests for TaskMemory dataclass."""

    def test_creation_minimal(self):
        """Test TaskMemory creation with minimal parameters."""
        task = TaskMemory(
            task_id="task-1",
            objective="Fix bug",
            outcome="completed",
        )

        assert task.task_id == "task-1"
        assert task.objective == "Fix bug"
        assert task.outcome == "completed"
        assert task.skills_used == []
        assert task.files_touched == []
        assert task.duration_seconds == 0.0
        assert task.lessons_learned == []
        assert isinstance(task.timestamp, str)

    def test_creation_full(self):
        """Test TaskMemory creation with all parameters."""
        task = TaskMemory(
            task_id="task-1",
            objective="Fix bug",
            outcome="completed",
            skills_used=["python", "debugging"],
            files_touched=["src/main.py"],
            duration_seconds=120.5,
            lessons_learned=["Check edge cases"],
        )

        assert task.skills_used == ["python", "debugging"]
        assert task.files_touched == ["src/main.py"]
        assert task.duration_seconds == 120.5
        assert task.lessons_learned == ["Check edge cases"]

    def test_to_dict(self):
        """Test conversion to dictionary."""
        task = TaskMemory(
            task_id="task-1",
            objective="Fix bug",
            outcome="completed",
        )

        result = task.to_dict()

        assert result["task_id"] == "task-1"
        assert result["objective"] == "Fix bug"
        assert result["outcome"] == "completed"
        assert "timestamp" in result

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "task_id": "task-1",
            "objective": "Fix bug",
            "outcome": "completed",
            "skills_used": ["python"],
            "files_touched": ["src/main.py"],
            "duration_seconds": 120.5,
            "lessons_learned": ["Test thoroughly"],
            "timestamp": "2024-01-01T00:00:00Z",
        }

        task = TaskMemory.from_dict(data)

        assert task.task_id == "task-1"
        assert task.skills_used == ["python"]
        assert task.timestamp == "2024-01-01T00:00:00Z"


class TestLearnedPattern:
    """Tests for LearnedPattern dataclass."""

    def test_creation_minimal(self):
        """Test LearnedPattern creation with minimal parameters."""
        pattern = LearnedPattern(
            pattern_id="pattern-1",
            pattern_type="approach",
            description="Use type hints",
        )

        assert pattern.pattern_id == "pattern-1"
        assert pattern.pattern_type == "approach"
        assert pattern.description == "Use type hints"
        assert pattern.context == ""
        assert pattern.effectiveness == 0.5
        assert pattern.occurrences == 1

    def test_creation_full(self):
        """Test LearnedPattern creation with all parameters."""
        pattern = LearnedPattern(
            pattern_id="pattern-1",
            pattern_type="approach",
            description="Use type hints",
            context="Python development",
            effectiveness=0.8,
            occurrences=5,
        )

        assert pattern.context == "Python development"
        assert pattern.effectiveness == 0.8
        assert pattern.occurrences == 5

    def test_reinforce_with_success(self):
        """Test reinforcing pattern with successful outcome."""
        pattern = LearnedPattern(
            pattern_id="pattern-1",
            pattern_type="approach",
            description="Use type hints",
            effectiveness=0.5,
            occurrences=1,
        )

        initial_effectiveness = pattern.effectiveness
        pattern.reinforce(success=True)

        assert pattern.occurrences == 2
        assert pattern.effectiveness > initial_effectiveness

    def test_reinforce_with_failure(self):
        """Test reinforcing pattern with failed outcome."""
        pattern = LearnedPattern(
            pattern_id="pattern-1",
            pattern_type="approach",
            description="Use type hints",
            effectiveness=0.7,
            occurrences=1,
        )

        initial_effectiveness = pattern.effectiveness
        pattern.reinforce(success=False)

        assert pattern.occurrences == 2
        assert pattern.effectiveness < initial_effectiveness

    def test_reinforce_updates_last_seen(self):
        """Test that reinforce updates last_seen timestamp."""
        pattern = LearnedPattern(
            pattern_id="pattern-1",
            pattern_type="approach",
            description="Use type hints",
        )

        original_last_seen = pattern.last_seen
        pattern.reinforce(success=True)

        assert pattern.last_seen != original_last_seen

    def test_to_dict(self):
        """Test conversion to dictionary."""
        pattern = LearnedPattern(
            pattern_id="pattern-1",
            pattern_type="approach",
            description="Use type hints",
        )

        result = pattern.to_dict()

        assert result["pattern_id"] == "pattern-1"
        assert result["pattern_type"] == "approach"
        assert result["description"] == "Use type hints"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "pattern_id": "pattern-1",
            "pattern_type": "approach",
            "description": "Use type hints",
            "context": "Python",
            "effectiveness": 0.8,
            "occurrences": 5,
            "created_at": "2024-01-01T00:00:00Z",
            "last_seen": "2024-01-02T00:00:00Z",
        }

        pattern = LearnedPattern.from_dict(data)

        assert pattern.pattern_id == "pattern-1"
        assert pattern.effectiveness == 0.8
        assert pattern.occurrences == 5


class TestAgentRelationship:
    """Tests for AgentRelationship dataclass."""

    def test_creation_defaults(self):
        """Test AgentRelationship creation with defaults."""
        rel = AgentRelationship(agent_id="agent-1")

        assert rel.agent_id == "agent-1"
        assert rel.trust_score == 0.5
        assert rel.reliability_score == 0.5
        assert rel.speed_score == 0.5
        assert rel.collaboration_count == 0
        assert rel.positive_interactions == 0
        assert rel.negative_interactions == 0
        assert rel.strengths == []
        assert rel.last_interaction is None
        assert rel.notes == ""

    def test_record_positive_interaction(self):
        """Test recording a positive interaction."""
        rel = AgentRelationship(agent_id="agent-1")

        rel.record_interaction(positive=True, note="Great work")

        assert rel.collaboration_count == 1
        assert rel.positive_interactions == 1
        assert rel.negative_interactions == 0
        assert rel.trust_score > 0.5
        assert "Great work" in rel.notes
        assert rel.last_interaction is not None

    def test_record_negative_interaction(self):
        """Test recording a negative interaction."""
        rel = AgentRelationship(agent_id="agent-1")

        rel.record_interaction(positive=False, note="Missed deadline")

        assert rel.collaboration_count == 1
        assert rel.positive_interactions == 0
        assert rel.negative_interactions == 1
        assert rel.trust_score < 0.5
        assert "Missed deadline" in rel.notes

    def test_record_multiple_interactions(self):
        """Test recording multiple interactions updates scores."""
        rel = AgentRelationship(agent_id="agent-1")

        # Record several positive interactions
        for _ in range(5):
            rel.record_interaction(positive=True)

        # Record one negative
        rel.record_interaction(positive=False)

        assert rel.collaboration_count == 6
        assert rel.positive_interactions == 5
        assert rel.negative_interactions == 1
        # Should still have high trust (5/6 positive)
        assert rel.trust_score > 0.6

    def test_add_strength(self):
        """Test adding a strength."""
        rel = AgentRelationship(agent_id="agent-1")

        rel.add_strength("Python expert")

        assert "Python expert" in rel.strengths

    def test_add_strength_no_duplicates(self):
        """Test that duplicate strengths are not added."""
        rel = AgentRelationship(agent_id="agent-1")

        rel.add_strength("Python expert")
        rel.add_strength("Python expert")

        assert rel.strengths.count("Python expert") == 1

    def test_to_dict(self):
        """Test conversion to dictionary."""
        rel = AgentRelationship(agent_id="agent-1")
        rel.add_strength("Fast")

        result = rel.to_dict()

        assert result["agent_id"] == "agent-1"
        assert result["strengths"] == ["Fast"]

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "agent_id": "agent-1",
            "trust_score": 0.8,
            "reliability_score": 0.9,
            "speed_score": 0.7,
            "collaboration_count": 10,
            "positive_interactions": 8,
            "negative_interactions": 2,
            "strengths": ["Fast", "Reliable"],
            "last_interaction": "2024-01-01T00:00:00Z",
            "notes": "Great agent",
        }

        rel = AgentRelationship.from_dict(data)

        assert rel.agent_id == "agent-1"
        assert rel.trust_score == 0.8
        assert rel.strengths == ["Fast", "Reliable"]


class TestAgentMemory:
    """Tests for AgentMemory dataclass."""

    def test_creation_minimal(self):
        """Test AgentMemory creation with minimal parameters."""
        memory = AgentMemory(agent_id="agent-0")

        assert memory.agent_id == "agent-0"
        assert memory.task_history == []
        assert memory.patterns == []
        assert memory.relationships == {}
        assert memory.knowledge == {}
        assert memory.preferences == {}

    def test_remember_task(self):
        """Test remembering a task."""
        memory = AgentMemory(agent_id="agent-0")

        task = memory.remember_task(
            task_id="task-1",
            objective="Fix bug",
            outcome="completed",
            skills_used=["python"],
            files_touched=["src/main.py"],
            duration_seconds=120.5,
            lessons=["Test edge cases"],
        )

        assert len(memory.task_history) == 1
        assert task.task_id == "task-1"
        assert memory.task_history[0] == task

    def test_remember_task_adds_to_front(self):
        """Test that new tasks are added to front of history."""
        memory = AgentMemory(agent_id="agent-0")

        memory.remember_task("task-1", "Objective 1", "completed")
        memory.remember_task("task-2", "Objective 2", "completed")

        # Most recent should be first
        assert memory.task_history[0].task_id == "task-2"
        assert memory.task_history[1].task_id == "task-1"

    def test_remember_task_trims_history(self):
        """Test that task history is trimmed when exceeding MAX_TASK_HISTORY."""
        memory = AgentMemory(agent_id="agent-0")

        # Add more than MAX_TASK_HISTORY tasks
        for i in range(MAX_TASK_HISTORY + 5):
            memory.remember_task(f"task-{i}", f"Objective {i}", "completed")

        # Should keep only MAX_TASK_HISTORY tasks
        assert len(memory.task_history) == MAX_TASK_HISTORY
        # Most recent should be kept
        assert memory.task_history[0].task_id == f"task-{MAX_TASK_HISTORY + 4}"

    def test_learn_pattern_new(self):
        """Test learning a new pattern."""
        memory = AgentMemory(agent_id="agent-0")

        pattern = memory.learn_pattern(
            pattern_type="approach",
            description="Use type hints",
            context="Python development",
            effectiveness=0.8,
        )

        assert len(memory.patterns) == 1
        assert pattern.description == "Use type hints"
        assert pattern.effectiveness == 0.8

    def test_learn_pattern_reinforces_existing(self):
        """Test that learning same pattern reinforces it."""
        memory = AgentMemory(agent_id="agent-0")

        # Learn pattern twice
        pattern1 = memory.learn_pattern("approach", "Use type hints")
        pattern2 = memory.learn_pattern("approach", "Use type hints")

        # Should have same pattern ID and only one pattern
        assert pattern1.pattern_id == pattern2.pattern_id
        assert len(memory.patterns) == 1
        assert pattern2.occurrences == 2

    def test_learn_pattern_trims_when_exceeds_max(self):
        """Test that patterns are trimmed when exceeding MAX_PATTERNS."""
        memory = AgentMemory(agent_id="agent-0")

        # Add more than MAX_PATTERNS patterns
        for i in range(MAX_PATTERNS + 5):
            pattern = memory.learn_pattern("approach", f"Pattern {i}")
            # Set varying effectiveness
            pattern.effectiveness = 0.1 + (i / (MAX_PATTERNS + 5)) * 0.8

        # Should keep only MAX_PATTERNS patterns
        assert len(memory.patterns) == MAX_PATTERNS
        # Should keep most effective patterns
        assert all(p.effectiveness >= 0.1 for p in memory.patterns)

    def test_get_relationship_new(self):
        """Test getting a new relationship."""
        memory = AgentMemory(agent_id="agent-0")

        rel = memory.get_relationship("agent-1")

        assert rel.agent_id == "agent-1"
        assert "agent-1" in memory.relationships

    def test_get_relationship_existing(self):
        """Test getting an existing relationship."""
        memory = AgentMemory(agent_id="agent-0")

        # Create relationship
        rel1 = memory.get_relationship("agent-1")
        rel1.trust_score = 0.9

        # Get again
        rel2 = memory.get_relationship("agent-1")

        assert rel2.trust_score == 0.9
        assert rel1 is rel2

    def test_record_interaction(self):
        """Test recording an interaction with another agent."""
        memory = AgentMemory(agent_id="agent-0")

        memory.record_interaction("agent-1", positive=True, note="Good work")

        rel = memory.relationships["agent-1"]
        assert rel.positive_interactions == 1
        assert "Good work" in rel.notes

    def test_store_knowledge(self):
        """Test storing knowledge."""
        memory = AgentMemory(agent_id="agent-0")

        memory.store_knowledge("api_key", "secret123")

        assert memory.knowledge["api_key"] == "secret123"

    def test_store_knowledge_trims_when_exceeds_max(self):
        """Test that knowledge is trimmed when exceeding MAX_KNOWLEDGE_ITEMS."""
        memory = AgentMemory(agent_id="agent-0")

        # Add more than MAX_KNOWLEDGE_ITEMS items
        for i in range(MAX_KNOWLEDGE_ITEMS + 10):
            memory.store_knowledge(f"key-{i}", f"value-{i}")

        # Should keep only MAX_KNOWLEDGE_ITEMS items
        assert len(memory.knowledge) <= MAX_KNOWLEDGE_ITEMS

    def test_recall_knowledge_existing(self):
        """Test recalling existing knowledge."""
        memory = AgentMemory(agent_id="agent-0")

        memory.store_knowledge("api_key", "secret123")
        result = memory.recall_knowledge("api_key")

        assert result == "secret123"

    def test_recall_knowledge_nonexistent(self):
        """Test recalling nonexistent knowledge."""
        memory = AgentMemory(agent_id="agent-0")

        result = memory.recall_knowledge("nonexistent")

        assert result is None

    def test_get_effective_patterns(self):
        """Test getting effective patterns."""
        memory = AgentMemory(agent_id="agent-0")

        # Add patterns with varying effectiveness
        p1 = memory.learn_pattern("approach", "Pattern 1")
        p1.effectiveness = 0.8

        p2 = memory.learn_pattern("approach", "Pattern 2")
        p2.effectiveness = 0.4

        p3 = memory.learn_pattern("approach", "Pattern 3")
        p3.effectiveness = 0.9

        result = memory.get_effective_patterns()

        # Should only return patterns with effectiveness > 0.6
        assert len(result) == 2
        assert p1 in result
        assert p3 in result
        assert p2 not in result

    def test_get_effective_patterns_filtered_by_type(self):
        """Test getting effective patterns filtered by type."""
        memory = AgentMemory(agent_id="agent-0")

        p1 = memory.learn_pattern("approach", "Pattern 1")
        p1.effectiveness = 0.8

        p2 = memory.learn_pattern("anti-pattern", "Pattern 2")
        p2.effectiveness = 0.8

        result = memory.get_effective_patterns(pattern_type="approach")

        assert len(result) == 1
        assert p1 in result

    def test_get_trusted_agents(self):
        """Test getting trusted agents."""
        memory = AgentMemory(agent_id="agent-0")

        # Create relationships with varying trust
        rel1 = memory.get_relationship("agent-1")
        rel1.trust_score = 0.8

        rel2 = memory.get_relationship("agent-2")
        rel2.trust_score = 0.4

        rel3 = memory.get_relationship("agent-3")
        rel3.trust_score = 0.9

        result = memory.get_trusted_agents(min_trust=0.6)

        assert len(result) == 2
        assert "agent-1" in result
        assert "agent-3" in result
        assert "agent-2" not in result

    def test_get_best_agents_for_skill(self):
        """Test getting best agents for a skill."""
        memory = AgentMemory(agent_id="agent-0")

        # Create relationships with strengths
        rel1 = memory.get_relationship("agent-1")
        rel1.add_strength("Python")
        rel1.reliability_score = 0.8

        rel2 = memory.get_relationship("agent-2")
        rel2.add_strength("Python")
        rel2.reliability_score = 0.9

        rel3 = memory.get_relationship("agent-3")
        rel3.add_strength("JavaScript")
        rel3.reliability_score = 0.95

        result = memory.get_best_agents_for_skill("Python")

        # Should return agents with Python skill, sorted by reliability
        assert len(result) == 2
        assert result[0] == ("agent-2", 0.9)
        assert result[1] == ("agent-1", 0.8)

    def test_to_dict(self):
        """Test conversion to dictionary."""
        memory = AgentMemory(agent_id="agent-0")
        memory.remember_task("task-1", "Fix bug", "completed")
        memory.learn_pattern("approach", "Use type hints")
        memory.record_interaction("agent-1", positive=True)
        memory.store_knowledge("key", "value")

        result = memory.to_dict()

        assert result["agent_id"] == "agent-0"
        assert len(result["task_history"]) == 1
        assert len(result["patterns"]) == 1
        assert "agent-1" in result["relationships"]
        assert result["knowledge"]["key"] == "value"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "agent_id": "agent-0",
            "task_history": [
                {
                    "task_id": "task-1",
                    "objective": "Fix bug",
                    "outcome": "completed",
                    "skills_used": [],
                    "files_touched": [],
                    "duration_seconds": 0.0,
                    "lessons_learned": [],
                    "timestamp": "2024-01-01T00:00:00Z",
                }
            ],
            "patterns": [],
            "relationships": {},
            "knowledge": {"key": "value"},
            "preferences": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
        }

        memory = AgentMemory.from_dict(data)

        assert memory.agent_id == "agent-0"
        assert len(memory.task_history) == 1
        assert memory.knowledge["key"] == "value"


class TestGetMemoryPath:
    """Tests for get_memory_path function."""

    @patch("claudeswarm.memory.get_project_root")
    def test_get_memory_path_default(self, mock_get_root):
        """Test getting memory path with default project root."""
        mock_get_root.return_value = Path("/project")

        result = get_memory_path()

        assert result == Path("/project") / MEMORY_DIR
        mock_get_root.assert_called_once_with(None)

    @patch("claudeswarm.memory.get_project_root")
    def test_get_memory_path_custom_root(self, mock_get_root):
        """Test getting memory path with custom project root."""
        custom_root = Path("/custom")
        mock_get_root.return_value = custom_root

        result = get_memory_path(custom_root)

        assert result == custom_root / MEMORY_DIR
        mock_get_root.assert_called_once_with(custom_root)


class TestMemoryStore:
    """Tests for MemoryStore class."""

    @pytest.fixture
    def temp_project(self, tmp_path):
        """Create a temporary project directory."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        return project_root

    @pytest.fixture
    def store(self, temp_project):
        """Create a MemoryStore instance."""
        return MemoryStore(temp_project)

    def test_initialization(self, temp_project):
        """Test MemoryStore initialization."""
        store = MemoryStore(temp_project)

        assert store.project_root == temp_project
        assert store.memory_dir == temp_project / MEMORY_DIR
        assert store.memory_dir.exists()

    def test_get_memory_file_valid_agent_id(self, store):
        """Test getting memory file path with valid agent ID."""
        result = store._get_memory_file("agent-0")

        assert result == store.memory_dir / "agent-0.json"

    def test_get_memory_file_rejects_invalid_characters(self, store):
        """Test that invalid characters in agent_id are rejected."""
        with pytest.raises(ValueError, match="Invalid agent_id"):
            store._get_memory_file("agent/0")

        with pytest.raises(ValueError, match="Invalid agent_id"):
            store._get_memory_file("agent:0")

        with pytest.raises(ValueError, match="Invalid agent_id"):
            store._get_memory_file("agent\\0")

    def test_get_memory_file_rejects_path_traversal(self, store):
        """Test that path traversal attempts are rejected."""
        with pytest.raises(ValueError, match="Invalid agent_id"):
            store._get_memory_file("../../../etc/passwd")

    def test_get_memory_new_agent(self, store):
        """Test getting memory for new agent creates it."""
        memory = store.get_memory("agent-0")

        assert memory.agent_id == "agent-0"
        # Should be persisted
        memory_file = store.memory_dir / "agent-0.json"
        assert memory_file.exists()

    def test_get_memory_existing_agent(self, store):
        """Test getting memory for existing agent."""
        # Create memory
        memory1 = store.get_memory("agent-0")
        memory1.store_knowledge("key", "value")
        store.save_memory(memory1)

        # Get again
        memory2 = store.get_memory("agent-0")

        assert memory2.knowledge["key"] == "value"

    def test_save_memory(self, store):
        """Test saving an agent's memory."""
        memory = AgentMemory(agent_id="agent-0")
        memory.store_knowledge("key", "value")

        store.save_memory(memory)

        # Verify file was written
        memory_file = store.memory_dir / "agent-0.json"
        assert memory_file.exists()

        # Verify content
        with open(memory_file) as f:
            data = json.load(f)
        assert data["agent_id"] == "agent-0"
        assert data["knowledge"]["key"] == "value"

    def test_delete_memory_existing(self, store):
        """Test deleting an existing memory."""
        # Create memory
        store.get_memory("agent-0")

        # Delete it
        result = store.delete_memory("agent-0")

        assert result is True
        memory_file = store.memory_dir / "agent-0.json"
        assert not memory_file.exists()

    def test_delete_memory_nonexistent(self, store):
        """Test deleting a nonexistent memory."""
        result = store.delete_memory("nonexistent")

        assert result is False

    def test_list_agents_with_memory_empty(self, store):
        """Test listing agents when none exist."""
        result = store.list_agents_with_memory()

        assert result == []

    def test_list_agents_with_memory(self, store):
        """Test listing agents with memory."""
        # Create memories for multiple agents
        store.get_memory("agent-0")
        store.get_memory("agent-1")
        store.get_memory("agent-2")

        result = store.list_agents_with_memory()

        assert len(result) == 3
        assert "agent-0" in result
        assert "agent-1" in result
        assert "agent-2" in result
        # Should be sorted
        assert result == sorted(result)

    def test_remember_task(self, store):
        """Test convenience method to remember a task."""
        task_memory = store.remember_task(
            agent_id="agent-0",
            task_id="task-1",
            objective="Fix bug",
            outcome="completed",
            skills_used=["python"],
            files_touched=["src/main.py"],
            duration_seconds=120.5,
            lessons=["Test edge cases"],
        )

        assert task_memory.task_id == "task-1"

        # Verify persistence
        memory = store.get_memory("agent-0")
        assert len(memory.task_history) == 1

    def test_learn_pattern(self, store):
        """Test convenience method to learn a pattern."""
        pattern = store.learn_pattern(
            agent_id="agent-0",
            pattern_type="approach",
            description="Use type hints",
            context="Python",
            effectiveness=0.8,
        )

        assert pattern.description == "Use type hints"

        # Verify persistence
        memory = store.get_memory("agent-0")
        assert len(memory.patterns) == 1

    def test_record_interaction(self, store):
        """Test convenience method to record an interaction."""
        store.record_interaction(
            agent_id="agent-0",
            other_agent_id="agent-1",
            positive=True,
            note="Great work",
        )

        # Verify persistence
        memory = store.get_memory("agent-0")
        assert "agent-1" in memory.relationships
        assert memory.relationships["agent-1"].positive_interactions == 1

    def test_get_memory_summary(self, store):
        """Test getting a memory summary."""
        # Create memory with data
        memory = store.get_memory("agent-0")
        memory.remember_task("task-1", "Fix bug", "completed")
        memory.learn_pattern("approach", "Use type hints")
        memory.record_interaction("agent-1", positive=True)
        memory.store_knowledge("key", "value")
        store.save_memory(memory)

        summary = store.get_memory_summary("agent-0")

        assert summary["agent_id"] == "agent-0"
        assert summary["tasks_remembered"] == 1
        assert summary["patterns_learned"] == 1
        assert summary["relationships_count"] == 1
        assert summary["knowledge_items"] == 1
        assert "created_at" in summary
        assert "updated_at" in summary
        assert "trusted_agents" in summary

    @patch("claudeswarm.memory.FileLock")
    def test_read_memory_handles_lock_timeout(self, mock_filelock, store):
        """Test that read_memory handles lock timeout gracefully."""
        from claudeswarm.file_lock import FileLockTimeout

        # Create memory file
        store.get_memory("agent-0")

        # Make FileLock raise timeout
        mock_filelock.side_effect = FileLockTimeout("Timeout")

        # Should return None on timeout
        result = store._read_memory("agent-0")
        assert result is None

    def test_read_memory_handles_missing_file(self, store):
        """Test that read_memory handles missing file gracefully."""
        result = store._read_memory("nonexistent")

        assert result is None
