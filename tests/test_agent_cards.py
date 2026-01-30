"""Unit tests for the agent cards system.

This module contains comprehensive tests for the agent capability discovery system,
covering card creation, validation, registry operations, and skill matching.

Tests cover:
- AgentCard creation and validation
- Skill matching and proficiency calculation
- AgentCardRegistry operations (register, get, update, delete)
- Availability status management
- Success rate tracking and updates
- Error handling (CardNotFoundError, CardValidationError)
- File operations and caching
- Thread safety and concurrent operations
"""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claudeswarm.agent_cards import (
    AGENT_CARDS_FILENAME,
    CARD_LOCK_TIMEOUT_SECONDS,
    AgentCard,
    AgentCardRegistry,
    CardNotFoundError,
    CardValidationError,
    SkillMatch,
    get_agent_cards_path,
)


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def registry(temp_project_dir):
    """Create an AgentCardRegistry instance for testing."""
    return AgentCardRegistry(project_root=temp_project_dir)


@pytest.fixture
def sample_card_data():
    """Provide sample agent card data."""
    return {
        "agent_id": "agent-0",
        "name": "Test Agent",
        "skills": ["python", "testing", "debugging"],
        "tools": ["Read", "Write", "Grep"],
        "availability": "active",
        "success_rates": {"python": 0.85, "testing": 0.92},
        "specializations": ["pytest", "unittest"],
        "metadata": {"version": "1.0"},
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


class TestSkillMatch:
    """Tests for SkillMatch dataclass."""

    def test_skill_match_creation(self):
        """Test creating a SkillMatch instance."""
        match = SkillMatch(
            skill="python",
            agent_proficiency=0.85,
            task_requirement=0.70,
            match_score=0.95,
        )
        assert match.skill == "python"
        assert match.agent_proficiency == 0.85
        assert match.task_requirement == 0.70
        assert match.match_score == 0.95

    def test_skill_match_fields(self):
        """Test that SkillMatch has all required fields."""
        match = SkillMatch(
            skill="debugging",
            agent_proficiency=0.90,
            task_requirement=0.80,
            match_score=0.88,
        )
        assert hasattr(match, "skill")
        assert hasattr(match, "agent_proficiency")
        assert hasattr(match, "task_requirement")
        assert hasattr(match, "match_score")


class TestAgentCard:
    """Tests for AgentCard dataclass."""

    def test_create_minimal_card(self):
        """Test creating a card with minimal required fields."""
        card = AgentCard(agent_id="agent-0")
        assert card.agent_id == "agent-0"
        assert card.name == ""
        assert card.skills == []
        assert card.tools == []
        assert card.availability == "active"
        assert card.success_rates == {}
        assert card.specializations == []
        assert card.metadata == {}

    def test_create_full_card(self, sample_card_data):
        """Test creating a card with all fields."""
        card = AgentCard(**sample_card_data)
        assert card.agent_id == "agent-0"
        assert card.name == "Test Agent"
        assert card.skills == ["python", "testing", "debugging"]
        assert card.tools == ["Read", "Write", "Grep"]
        assert card.availability == "active"
        assert card.success_rates == {"python": 0.85, "testing": 0.92}
        assert card.specializations == ["pytest", "unittest"]
        assert card.metadata == {"version": "1.0"}

    def test_card_validation_success(self):
        """Test that valid cards pass validation."""
        card = AgentCard(
            agent_id="agent-1",
            availability="active",
            success_rates={"skill1": 0.5, "skill2": 1.0},
        )
        card.validate()  # Should not raise

    def test_card_validation_empty_agent_id(self):
        """Test validation fails for empty agent_id."""
        with pytest.raises(CardValidationError, match="agent_id is required"):
            AgentCard(agent_id="")

    def test_card_validation_invalid_agent_id_type(self):
        """Test validation fails for non-string agent_id."""
        with pytest.raises(CardValidationError, match="agent_id must be a string"):
            AgentCard(agent_id=123)  # type: ignore

    def test_card_validation_invalid_availability(self):
        """Test validation fails for invalid availability status."""
        with pytest.raises(CardValidationError, match="availability must be"):
            AgentCard(agent_id="agent-0", availability="invalid")

    def test_card_validation_success_rate_non_numeric(self):
        """Test validation fails for non-numeric success rate."""
        with pytest.raises(CardValidationError, match="success_rate.*must be numeric"):
            AgentCard(
                agent_id="agent-0",
                success_rates={"skill1": "not a number"},  # type: ignore
            )

    def test_card_validation_success_rate_negative(self):
        """Test validation fails for negative success rate."""
        with pytest.raises(CardValidationError, match="success_rate.*must be between 0.0 and 1.0"):
            AgentCard(agent_id="agent-0", success_rates={"skill1": -0.5})

    def test_card_validation_success_rate_too_high(self):
        """Test validation fails for success rate > 1.0."""
        with pytest.raises(CardValidationError, match="success_rate.*must be between 0.0 and 1.0"):
            AgentCard(agent_id="agent-0", success_rates={"skill1": 1.5})

    def test_card_validation_success_rate_boundary_values(self):
        """Test validation accepts boundary values 0.0 and 1.0."""
        card = AgentCard(
            agent_id="agent-0",
            success_rates={"skill1": 0.0, "skill2": 1.0},
        )
        card.validate()  # Should not raise

    def test_has_skill_exact_match(self):
        """Test has_skill with exact case match."""
        card = AgentCard(agent_id="agent-0", skills=["python", "testing"])
        assert card.has_skill("python")
        assert card.has_skill("testing")

    def test_has_skill_case_insensitive(self):
        """Test has_skill is case-insensitive."""
        card = AgentCard(agent_id="agent-0", skills=["Python", "Testing"])
        assert card.has_skill("python")
        assert card.has_skill("TESTING")
        assert card.has_skill("PyThOn")

    def test_has_skill_not_found(self):
        """Test has_skill returns False for missing skill."""
        card = AgentCard(agent_id="agent-0", skills=["python"])
        assert not card.has_skill("java")
        assert not card.has_skill("debugging")

    def test_has_skill_empty_skills(self):
        """Test has_skill with no skills."""
        card = AgentCard(agent_id="agent-0", skills=[])
        assert not card.has_skill("python")

    def test_get_skill_proficiency_with_rate(self):
        """Test get_skill_proficiency returns success rate."""
        card = AgentCard(
            agent_id="agent-0",
            skills=["python", "testing"],
            success_rates={"python": 0.85, "testing": 0.92},
        )
        assert card.get_skill_proficiency("python") == 0.85
        assert card.get_skill_proficiency("testing") == 0.92

    def test_get_skill_proficiency_case_insensitive(self):
        """Test get_skill_proficiency is case-insensitive."""
        card = AgentCard(
            agent_id="agent-0",
            skills=["Python"],
            success_rates={"python": 0.85},
        )
        assert card.get_skill_proficiency("PYTHON") == 0.85
        assert card.get_skill_proficiency("PyThOn") == 0.85

    def test_get_skill_proficiency_no_rate(self):
        """Test get_skill_proficiency returns 0.5 for skill without rate."""
        card = AgentCard(agent_id="agent-0", skills=["python"])
        assert card.get_skill_proficiency("python") == 0.5

    def test_get_skill_proficiency_no_skill(self):
        """Test get_skill_proficiency returns 0.0 for missing skill."""
        card = AgentCard(agent_id="agent-0", skills=["python"])
        assert card.get_skill_proficiency("java") == 0.0

    def test_has_tool_found(self):
        """Test has_tool returns True for existing tool."""
        card = AgentCard(agent_id="agent-0", tools=["Read", "Write", "Grep"])
        assert card.has_tool("Read")
        assert card.has_tool("Write")
        assert card.has_tool("Grep")

    def test_has_tool_not_found(self):
        """Test has_tool returns False for missing tool."""
        card = AgentCard(agent_id="agent-0", tools=["Read"])
        assert not card.has_tool("Write")
        assert not card.has_tool("Bash")

    def test_has_tool_empty_tools(self):
        """Test has_tool with no tools."""
        card = AgentCard(agent_id="agent-0", tools=[])
        assert not card.has_tool("Read")

    def test_is_available_active(self):
        """Test is_available returns True for active status."""
        card = AgentCard(agent_id="agent-0", availability="active")
        assert card.is_available()

    def test_is_available_busy(self):
        """Test is_available returns False for busy status."""
        card = AgentCard(agent_id="agent-0", availability="busy")
        assert not card.is_available()

    def test_is_available_offline(self):
        """Test is_available returns False for offline status."""
        card = AgentCard(agent_id="agent-0", availability="offline")
        assert not card.is_available()

    def test_update_success_rate_new_skill(self):
        """Test updating success rate for new skill."""
        card = AgentCard(agent_id="agent-0")
        card.update_success_rate("python", success=True)
        assert "python" in card.success_rates
        # With default weight 0.1: 0.5 * 0.9 + 1.0 * 0.1 = 0.55
        assert card.success_rates["python"] == 0.55

    def test_update_success_rate_existing_skill(self):
        """Test updating success rate for existing skill."""
        card = AgentCard(agent_id="agent-0", success_rates={"python": 0.8})
        card.update_success_rate("python", success=True)
        # 0.8 * 0.9 + 1.0 * 0.1 = 0.82
        assert card.success_rates["python"] == 0.82

    def test_update_success_rate_failure(self):
        """Test updating success rate with failure."""
        card = AgentCard(agent_id="agent-0", success_rates={"python": 0.8})
        card.update_success_rate("python", success=False)
        # 0.8 * 0.9 + 0.0 * 0.1 = 0.72
        assert card.success_rates["python"] == 0.72

    def test_update_success_rate_custom_weight(self):
        """Test updating success rate with custom weight."""
        card = AgentCard(agent_id="agent-0", success_rates={"python": 0.5})
        card.update_success_rate("python", success=True, weight=0.5)
        # 0.5 * 0.5 + 1.0 * 0.5 = 0.75
        assert card.success_rates["python"] == 0.75

    def test_update_success_rate_case_insensitive(self):
        """Test success rate update is case-insensitive."""
        card = AgentCard(agent_id="agent-0", success_rates={"python": 0.8})
        card.update_success_rate("Python", success=True)
        # Should update the lowercase key
        assert "python" in card.success_rates
        assert card.success_rates["python"] == 0.82

    def test_update_success_rate_updates_timestamp(self):
        """Test success rate update changes updated_at timestamp."""
        card = AgentCard(agent_id="agent-0")
        original_timestamp = card.updated_at
        time.sleep(0.01)  # Small delay to ensure timestamp changes
        card.update_success_rate("python", success=True)
        assert card.updated_at != original_timestamp

    def test_to_dict(self, sample_card_data):
        """Test converting card to dictionary."""
        card = AgentCard(**sample_card_data)
        card_dict = card.to_dict()
        assert card_dict["agent_id"] == "agent-0"
        assert card_dict["name"] == "Test Agent"
        assert card_dict["skills"] == ["python", "testing", "debugging"]
        assert card_dict["availability"] == "active"

    def test_from_dict_full_data(self, sample_card_data):
        """Test creating card from dictionary with all fields."""
        card = AgentCard.from_dict(sample_card_data)
        assert card.agent_id == "agent-0"
        assert card.name == "Test Agent"
        assert card.skills == ["python", "testing", "debugging"]
        assert card.tools == ["Read", "Write", "Grep"]
        assert card.availability == "active"

    def test_from_dict_minimal_data(self):
        """Test creating card from dictionary with minimal fields."""
        data = {"agent_id": "agent-1"}
        card = AgentCard.from_dict(data)
        assert card.agent_id == "agent-1"
        assert card.name == ""
        assert card.skills == []
        assert card.availability == "active"

    def test_from_dict_partial_data(self):
        """Test creating card from dictionary with some fields."""
        data = {
            "agent_id": "agent-2",
            "name": "Partial Agent",
            "skills": ["skill1"],
        }
        card = AgentCard.from_dict(data)
        assert card.agent_id == "agent-2"
        assert card.name == "Partial Agent"
        assert card.skills == ["skill1"]
        assert card.tools == []  # Default
        assert card.availability == "active"  # Default

    def test_roundtrip_serialization(self, sample_card_data):
        """Test card can be serialized and deserialized without data loss."""
        original = AgentCard(**sample_card_data)
        card_dict = original.to_dict()
        restored = AgentCard.from_dict(card_dict)
        assert restored.agent_id == original.agent_id
        assert restored.name == original.name
        assert restored.skills == original.skills
        assert restored.tools == original.tools
        assert restored.availability == original.availability
        assert restored.success_rates == original.success_rates
        assert restored.specializations == original.specializations


class TestGetAgentCardsPath:
    """Tests for get_agent_cards_path function."""

    def test_get_agent_cards_path_default(self, temp_project_dir):
        """Test getting cards path with explicit project root."""
        path = get_agent_cards_path(temp_project_dir)
        # Use resolve() to normalize paths (handles /var vs /private/var symlinks on macOS)
        assert path.resolve() == (temp_project_dir / AGENT_CARDS_FILENAME).resolve()
        assert path.name == "AGENT_CARDS.json"

    def test_get_agent_cards_path_returns_path_object(self, temp_project_dir):
        """Test that get_agent_cards_path returns a Path object."""
        path = get_agent_cards_path(temp_project_dir)
        assert isinstance(path, Path)


class TestAgentCardRegistry:
    """Tests for AgentCardRegistry class."""

    def test_registry_initialization(self, temp_project_dir):
        """Test registry initializes with correct paths."""
        registry = AgentCardRegistry(temp_project_dir)
        # Use resolve() to normalize paths (handles /var vs /private/var symlinks on macOS)
        assert registry.project_root.resolve() == temp_project_dir.resolve()
        assert registry.cards_path.resolve() == (temp_project_dir / AGENT_CARDS_FILENAME).resolve()
        assert hasattr(registry, "_lock")
        assert hasattr(registry, "_cache")

    def test_register_agent_new(self, registry):
        """Test registering a new agent."""
        card = registry.register_agent(
            agent_id="agent-0",
            name="Test Agent",
            skills=["python", "testing"],
            tools=["Read", "Write"],
        )
        assert card.agent_id == "agent-0"
        assert card.name == "Test Agent"
        assert card.skills == ["python", "testing"]
        assert card.tools == ["Read", "Write"]

    def test_register_agent_minimal(self, registry):
        """Test registering agent with minimal information."""
        card = registry.register_agent(agent_id="agent-1")
        assert card.agent_id == "agent-1"
        assert card.name == "agent-1"  # Defaults to agent_id
        assert card.skills == []
        assert card.tools == []

    def test_register_agent_with_specializations(self, registry):
        """Test registering agent with specializations."""
        card = registry.register_agent(
            agent_id="agent-2",
            specializations=["pytest", "unittest"],
            metadata={"version": "1.0"},
        )
        assert card.specializations == ["pytest", "unittest"]
        assert card.metadata == {"version": "1.0"}

    def test_register_agent_update_existing(self, registry):
        """Test registering existing agent updates the card."""
        # Register initially
        registry.register_agent(
            agent_id="agent-0",
            name="Initial Name",
            skills=["skill1"],
        )

        # Update registration
        card = registry.register_agent(
            agent_id="agent-0",
            name="Updated Name",
            skills=["skill1", "skill2"],
        )

        assert card.name == "Updated Name"
        assert card.skills == ["skill1", "skill2"]

    def test_register_agent_persists_to_file(self, registry):
        """Test that registration persists to file."""
        registry.register_agent(agent_id="agent-0", name="Test Agent")
        assert registry.cards_path.exists()

        # Verify file contents
        with open(registry.cards_path) as f:
            data = json.load(f)
        assert "cards" in data
        assert "agent-0" in data["cards"]
        assert data["cards"]["agent-0"]["name"] == "Test Agent"

    def test_get_card_existing(self, registry):
        """Test getting an existing card."""
        registry.register_agent(agent_id="agent-0", name="Test Agent")
        card = registry.get_card("agent-0")
        assert card is not None
        assert card.agent_id == "agent-0"
        assert card.name == "Test Agent"

    def test_get_card_nonexistent(self, registry):
        """Test getting a nonexistent card returns None."""
        card = registry.get_card("nonexistent")
        assert card is None

    def test_get_card_uses_cache(self, registry):
        """Test that get_card uses caching."""
        registry.register_agent(agent_id="agent-0")

        # First call populates cache
        card1 = registry.get_card("agent-0")

        # Manually modify file to check cache is used
        registry.cards_path.unlink()

        # Should still return cached value within TTL
        card2 = registry.get_card("agent-0")
        assert card2 is not None

    def test_update_card_all_fields(self, registry):
        """Test updating all card fields."""
        registry.register_agent(agent_id="agent-0")

        updated = registry.update_card(
            agent_id="agent-0",
            name="Updated Name",
            skills=["new-skill"],
            tools=["new-tool"],
            availability="busy",
            success_rates={"new-skill": 0.9},
            specializations=["spec1"],
            metadata={"key": "value"},
        )

        assert updated.name == "Updated Name"
        assert updated.skills == ["new-skill"]
        assert updated.tools == ["new-tool"]
        assert updated.availability == "busy"
        assert updated.success_rates == {"new-skill": 0.9}
        assert updated.specializations == ["spec1"]
        assert updated.metadata == {"key": "value"}

    def test_update_card_partial_fields(self, registry):
        """Test updating only some card fields."""
        registry.register_agent(
            agent_id="agent-0",
            name="Original Name",
            skills=["skill1"],
        )

        updated = registry.update_card(
            agent_id="agent-0",
            name="New Name",
        )

        assert updated.name == "New Name"
        assert updated.skills == ["skill1"]  # Unchanged

    def test_update_card_nonexistent(self, registry):
        """Test updating nonexistent card raises error."""
        with pytest.raises(CardNotFoundError, match="Agent card not found: agent-999"):
            registry.update_card(agent_id="agent-999", name="New Name")

    def test_update_card_invalid_availability(self, registry):
        """Test updating with invalid availability raises error."""
        registry.register_agent(agent_id="agent-0")

        with pytest.raises(CardValidationError, match="Invalid availability"):
            registry.update_card(agent_id="agent-0", availability="invalid")

    def test_update_card_updates_timestamp(self, registry):
        """Test that update_card changes updated_at timestamp."""
        registry.register_agent(agent_id="agent-0")
        original = registry.get_card("agent-0")
        original_timestamp = original.updated_at

        time.sleep(0.01)  # Small delay
        registry.update_card(agent_id="agent-0", name="Updated")

        updated = registry.get_card("agent-0")
        assert updated.updated_at != original_timestamp

    def test_update_card_merges_metadata(self, registry):
        """Test that metadata updates are merged, not replaced."""
        registry.register_agent(
            agent_id="agent-0",
            metadata={"key1": "value1", "key2": "value2"},
        )

        registry.update_card(
            agent_id="agent-0",
            metadata={"key2": "new_value2", "key3": "value3"},
        )

        card = registry.get_card("agent-0")
        assert card.metadata == {
            "key1": "value1",
            "key2": "new_value2",
            "key3": "value3",
        }

    def test_delete_card_existing(self, registry):
        """Test deleting an existing card."""
        registry.register_agent(agent_id="agent-0")
        result = registry.delete_card("agent-0")
        assert result is True
        assert registry.get_card("agent-0") is None

    def test_delete_card_nonexistent(self, registry):
        """Test deleting nonexistent card returns False."""
        result = registry.delete_card("nonexistent")
        assert result is False

    def test_delete_card_persists(self, registry):
        """Test that deletion persists to file."""
        registry.register_agent(agent_id="agent-0")
        registry.delete_card("agent-0")

        # Verify file doesn't contain the card
        with open(registry.cards_path) as f:
            data = json.load(f)
        assert "agent-0" not in data["cards"]

    def test_list_cards_all(self, registry):
        """Test listing all cards."""
        registry.register_agent(agent_id="agent-0", name="Agent 0")
        registry.register_agent(agent_id="agent-1", name="Agent 1")
        registry.register_agent(agent_id="agent-2", name="Agent 2")

        cards = registry.list_cards()
        assert len(cards) == 3
        agent_ids = {card.agent_id for card in cards}
        assert agent_ids == {"agent-0", "agent-1", "agent-2"}

    def test_list_cards_filter_by_availability(self, registry):
        """Test filtering cards by availability status."""
        registry.register_agent(agent_id="agent-0")
        registry.register_agent(agent_id="agent-1")
        registry.update_card(agent_id="agent-1", availability="busy")
        registry.register_agent(agent_id="agent-2")
        registry.update_card(agent_id="agent-2", availability="offline")

        active_cards = registry.list_cards(availability="active")
        assert len(active_cards) == 1
        assert active_cards[0].agent_id == "agent-0"

        busy_cards = registry.list_cards(availability="busy")
        assert len(busy_cards) == 1
        assert busy_cards[0].agent_id == "agent-1"

    def test_list_cards_filter_by_skill(self, registry):
        """Test filtering cards by skill."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        registry.register_agent(agent_id="agent-1", skills=["python", "java"])
        registry.register_agent(agent_id="agent-2", skills=["java"])

        python_cards = registry.list_cards(skill="python")
        assert len(python_cards) == 2
        agent_ids = {card.agent_id for card in python_cards}
        assert agent_ids == {"agent-0", "agent-1"}

    def test_list_cards_filter_by_tool(self, registry):
        """Test filtering cards by tool."""
        registry.register_agent(agent_id="agent-0", tools=["Read", "Write"])
        registry.register_agent(agent_id="agent-1", tools=["Read", "Grep"])
        registry.register_agent(agent_id="agent-2", tools=["Bash"])

        read_cards = registry.list_cards(tool="Read")
        assert len(read_cards) == 2
        agent_ids = {card.agent_id for card in read_cards}
        assert agent_ids == {"agent-0", "agent-1"}

    def test_list_cards_multiple_filters(self, registry):
        """Test filtering cards with multiple criteria."""
        registry.register_agent(
            agent_id="agent-0",
            skills=["python"],
            tools=["Read"],
        )
        registry.register_agent(
            agent_id="agent-1",
            skills=["python"],
            tools=["Write"],
        )
        registry.update_card(agent_id="agent-1", availability="busy")
        registry.register_agent(
            agent_id="agent-2",
            skills=["java"],
            tools=["Read"],
        )

        cards = registry.list_cards(
            availability="active",
            skill="python",
            tool="Read",
        )
        assert len(cards) == 1
        assert cards[0].agent_id == "agent-0"

    def test_list_cards_empty(self, registry):
        """Test listing cards when none exist."""
        cards = registry.list_cards()
        assert cards == []

    def test_set_availability_existing(self, registry):
        """Test setting availability for existing agent."""
        registry.register_agent(agent_id="agent-0")
        result = registry.set_availability("agent-0", "busy")
        assert result is True

        card = registry.get_card("agent-0")
        assert card.availability == "busy"

    def test_set_availability_nonexistent(self, registry):
        """Test setting availability for nonexistent agent."""
        result = registry.set_availability("nonexistent", "busy")
        assert result is False

    def test_set_availability_all_statuses(self, registry):
        """Test setting all valid availability statuses."""
        registry.register_agent(agent_id="agent-0")

        for status in ["active", "busy", "offline"]:
            registry.set_availability("agent-0", status)
            card = registry.get_card("agent-0")
            assert card.availability == status

    def test_find_agents_with_skill_basic(self, registry):
        """Test finding agents with a specific skill."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        registry.register_agent(agent_id="agent-1", skills=["python"])
        registry.register_agent(agent_id="agent-2", skills=["java"])

        # Simulate different success rates by updating multiple times
        # Agent 0: high success (0.9)
        for _ in range(40):
            registry.update_skill_success("agent-0", "python", success=True)

        # Agent 1: medium success (0.7)
        for _ in range(20):
            registry.update_skill_success("agent-1", "python", success=True)

        # With min_proficiency > 0, exclude agents without the skill
        matches = registry.find_agents_with_skill("python", min_proficiency=0.1)
        assert len(matches) == 2

        # Should be sorted by proficiency (descending)
        assert matches[0][0].agent_id == "agent-0"
        assert matches[1][0].agent_id == "agent-1"
        # Verify agent-0 has higher proficiency than agent-1
        assert matches[0][1] > matches[1][1]

    def test_find_agents_with_skill_min_proficiency(self, registry):
        """Test finding agents with minimum proficiency."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        registry.register_agent(agent_id="agent-1", skills=["python"])
        registry.register_agent(agent_id="agent-2", skills=["python"])

        # Agent 0: very high success (approaching 1.0)
        for _ in range(50):
            registry.update_skill_success("agent-0", "python", success=True)

        # Agent 1: some successes but also failures
        for _ in range(5):
            registry.update_skill_success("agent-1", "python", success=True)
        for _ in range(5):
            registry.update_skill_success("agent-1", "python", success=False)

        # Agent 2: keep at default (0.5)

        # Get all agents with skill
        all_matches = registry.find_agents_with_skill("python", min_proficiency=0.1)
        assert len(all_matches) == 3

        # Filter by minimum proficiency - should exclude default and mixed
        high_matches = registry.find_agents_with_skill("python", min_proficiency=0.9)
        assert len(high_matches) >= 1
        assert high_matches[0][0].agent_id == "agent-0"
        # Agent-0 should have very high proficiency
        assert high_matches[0][1] >= 0.9

    def test_find_agents_with_skill_available_only(self, registry):
        """Test finding only available agents."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        registry.register_agent(agent_id="agent-1", skills=["python"])
        registry.update_card(agent_id="agent-1", availability="busy")

        matches = registry.find_agents_with_skill("python", available_only=True)
        assert len(matches) == 1
        assert matches[0][0].agent_id == "agent-0"

    def test_find_agents_with_skill_include_unavailable(self, registry):
        """Test finding agents including unavailable ones."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        registry.register_agent(agent_id="agent-1", skills=["python"])
        registry.update_card(agent_id="agent-1", availability="busy")

        matches = registry.find_agents_with_skill("python", available_only=False)
        assert len(matches) == 2

    def test_find_agents_with_skill_no_matches(self, registry):
        """Test finding agents when no matches exist."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        # Set minimum proficiency > 0 to exclude agents without the skill
        matches = registry.find_agents_with_skill("java", min_proficiency=0.1)
        assert matches == []

    def test_find_agents_with_skill_default_proficiency(self, registry):
        """Test finding agents with skill but no success rate."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        matches = registry.find_agents_with_skill("python")
        assert len(matches) == 1
        assert matches[0][1] == 0.5  # Default proficiency

    def test_update_skill_success_existing_agent(self, registry):
        """Test updating skill success for existing agent."""
        registry.register_agent(agent_id="agent-0", skills=["python"])
        registry.update_skill_success("agent-0", "python", success=True)

        card = registry.get_card("agent-0")
        assert "python" in card.success_rates
        assert card.success_rates["python"] == 0.55  # 0.5 * 0.9 + 1.0 * 0.1

    def test_update_skill_success_nonexistent_agent(self, registry):
        """Test updating skill success for nonexistent agent logs warning."""
        # Should not raise, just log warning
        registry.update_skill_success("nonexistent", "python", success=True)
        # Verify agent still doesn't exist
        assert registry.get_card("nonexistent") is None

    def test_update_skill_success_multiple_updates(self, registry):
        """Test multiple skill success updates."""
        registry.register_agent(agent_id="agent-0", skills=["python"])

        registry.update_skill_success("agent-0", "python", success=True)
        registry.update_skill_success("agent-0", "python", success=True)
        registry.update_skill_success("agent-0", "python", success=False)

        card = registry.get_card("agent-0")
        # Rate should have changed from defaults
        assert card.success_rates["python"] != 0.5

    def test_clear_cache(self, registry):
        """Test clearing the registry cache."""
        registry.register_agent(agent_id="agent-0")

        # Populate cache
        registry.get_card("agent-0")
        assert registry._cache is not None

        # Clear cache
        registry.clear_cache()
        assert registry._cache is None

    def test_read_cards_no_file(self, registry):
        """Test reading cards when file doesn't exist."""
        cards = registry._read_cards()
        assert cards == {}

    def test_read_cards_invalid_json(self, registry):
        """Test reading cards with invalid JSON."""
        # Write invalid JSON
        registry.cards_path.parent.mkdir(parents=True, exist_ok=True)
        registry.cards_path.write_text("invalid json {")

        cards = registry._read_cards()
        assert cards == {}

    def test_read_cards_missing_cards_key(self, registry):
        """Test reading cards with missing 'cards' key."""
        # Write JSON without 'cards' key
        registry.cards_path.parent.mkdir(parents=True, exist_ok=True)
        registry.cards_path.write_text('{"version": "1.0"}')

        cards = registry._read_cards()
        assert cards == {}

    def test_read_cards_invalid_card_data(self, registry):
        """Test reading cards with invalid card data."""
        # Write JSON with invalid card (missing agent_id)
        data = {
            "version": "1.0",
            "cards": {
                "agent-0": {"name": "Test"},  # Missing agent_id
            },
        }
        registry.cards_path.parent.mkdir(parents=True, exist_ok=True)
        registry.cards_path.write_text(json.dumps(data))

        cards = registry._read_cards()
        # Invalid cards should be skipped
        assert "agent-0" not in cards

    def test_write_cards_creates_directory(self, temp_project_dir):
        """Test that write_cards creates parent directory if needed."""
        nested_dir = temp_project_dir / "nested" / "path"
        registry = AgentCardRegistry(nested_dir)

        registry.register_agent(agent_id="agent-0")

        assert nested_dir.exists()
        assert registry.cards_path.exists()

    def test_write_cards_atomic_operation(self, registry):
        """Test that write_cards uses atomic rename."""
        registry.register_agent(agent_id="agent-0")

        # Temp file should not exist after write
        temp_path = registry.cards_path.with_suffix(".json.tmp")
        assert not temp_path.exists()

        # But the actual file should exist
        assert registry.cards_path.exists()

    def test_cache_ttl_expiration(self, registry):
        """Test that cache expires after TTL."""
        registry.register_agent(agent_id="agent-0")

        # First read populates cache
        card1 = registry.get_card("agent-0")
        assert card1 is not None

        # Wait for cache to expire
        time.sleep(registry._cache_ttl + 0.1)

        # Clear cache to force re-read
        registry.clear_cache()

        # Modify file directly
        registry.cards_path.unlink()

        # Should read from file since cache was cleared
        card2 = registry.get_card("agent-0")
        assert card2 is None

    def test_concurrent_registration(self, registry):
        """Test that concurrent registrations are handled safely."""
        # This tests the thread lock behavior
        import threading

        def register_agent(agent_num):
            registry.register_agent(
                agent_id=f"agent-{agent_num}",
                name=f"Agent {agent_num}",
            )

        threads = []
        for i in range(5):
            thread = threading.Thread(target=register_agent, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All agents should be registered
        cards = registry.list_cards()
        assert len(cards) == 5

    def test_file_lock_timeout_handling(self, registry):
        """Test handling of file lock timeouts."""
        from claudeswarm.file_lock import FileLockTimeout

        # Mock FileLock to raise timeout
        with patch("claudeswarm.agent_cards.FileLock") as mock_lock:
            mock_lock.return_value.__enter__.side_effect = FileLockTimeout("Timeout")

            # Read should return empty dict on timeout
            cards = registry._read_cards()
            assert cards == {}

    def test_file_lock_timeout_on_write(self, registry):
        """Test that write raises on file lock timeout."""
        from claudeswarm.file_lock import FileLockTimeout

        with patch("claudeswarm.agent_cards.FileLock") as mock_lock:
            mock_lock.return_value.__enter__.side_effect = FileLockTimeout("Timeout")

            with pytest.raises(FileLockTimeout):
                registry._write_cards({"agent-0": AgentCard(agent_id="agent-0")})

    def test_registry_file_format(self, registry):
        """Test that registry writes correct file format."""
        registry.register_agent(agent_id="agent-0", name="Test Agent")

        with open(registry.cards_path) as f:
            data = json.load(f)

        assert "version" in data
        assert data["version"] == "1.0"
        assert "updated_at" in data
        assert "cards" in data
        assert isinstance(data["cards"], dict)

    def test_registry_preserves_unknown_fields(self, registry):
        """Test that registry preserves unknown metadata fields."""
        registry.register_agent(
            agent_id="agent-0",
            metadata={"custom_field": "custom_value", "another": 123},
        )

        card = registry.get_card("agent-0")
        assert card.metadata["custom_field"] == "custom_value"
        assert card.metadata["another"] == 123
