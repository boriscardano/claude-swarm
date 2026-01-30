"""Agent Cards system for Claude Swarm.

This module implements A2A Protocol-inspired Agent Cards for capability discovery.
Each agent registers a card advertising its skills, tools, and availability,
enabling intelligent task delegation based on agent capabilities.

Agent Cards support:
- Skill declaration with proficiency levels
- Tool availability tracking
- Availability status (active, busy, offline)
- Success rate tracking per skill
- Specialization metadata

Example card:
    {
        "agent_id": "agent-0",
        "name": "Architect Agent",
        "skills": ["architecture", "design", "planning"],
        "tools": ["Read", "Grep", "Glob"],
        "availability": "active",
        "success_rates": {"architecture": 0.92, "debugging": 0.75},
        "specializations": ["python", "typescript"],
        "metadata": {"created_at": "2025-01-01T00:00:00Z"}
    }
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .file_lock import FileLock, FileLockTimeout
from .logging_config import get_logger
from .project import get_project_root

__all__ = [
    "AgentCard",
    "AgentCardRegistry",
    "get_agent_cards_path",
    "SkillMatch",
    "CardNotFoundError",
    "CardValidationError",
]

# Constants
AGENT_CARDS_FILENAME = "AGENT_CARDS.json"
CARD_LOCK_TIMEOUT_SECONDS = 5.0

# Configure logging
logger = get_logger(__name__)


class CardNotFoundError(Exception):
    """Raised when an agent card is not found."""

    pass


class CardValidationError(Exception):
    """Raised when agent card validation fails."""

    pass


@dataclass
class SkillMatch:
    """Represents a skill match between a task requirement and an agent's capability.

    Attributes:
        skill: The skill being matched
        agent_proficiency: Agent's proficiency level (0.0-1.0)
        task_requirement: Required level for the task (0.0-1.0)
        match_score: Calculated match score
    """

    skill: str
    agent_proficiency: float
    task_requirement: float
    match_score: float


@dataclass
class AgentCard:
    """Represents an agent's capability card.

    Attributes:
        agent_id: Unique identifier for the agent (e.g., "agent-0")
        name: Human-readable name for the agent
        skills: List of skills the agent possesses
        tools: List of tools the agent has access to
        availability: Current availability status
        success_rates: Success rate per skill (0.0-1.0)
        specializations: Areas of specialization
        metadata: Additional metadata
        created_at: When the card was created
        updated_at: When the card was last updated
    """

    agent_id: str
    name: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    availability: str = "active"  # active, busy, offline
    success_rates: dict[str, float] = field(default_factory=dict)
    specializations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self):
        """Validate card after initialization."""
        self.validate()

    def validate(self) -> None:
        """Validate the agent card.

        Raises:
            CardValidationError: If validation fails
        """
        if not self.agent_id:
            raise CardValidationError("agent_id is required")

        if not isinstance(self.agent_id, str):
            raise CardValidationError(f"agent_id must be a string, got {type(self.agent_id)}")

        if self.availability not in ("active", "busy", "offline"):
            raise CardValidationError(
                f"availability must be 'active', 'busy', or 'offline', got '{self.availability}'"
            )

        # Validate success rates are between 0 and 1
        for skill, rate in self.success_rates.items():
            if not isinstance(rate, (int, float)):
                raise CardValidationError(
                    f"success_rate for '{skill}' must be numeric, got {type(rate)}"
                )
            if not 0.0 <= rate <= 1.0:
                raise CardValidationError(
                    f"success_rate for '{skill}' must be between 0.0 and 1.0, got {rate}"
                )

    def has_skill(self, skill: str) -> bool:
        """Check if agent has a specific skill.

        Args:
            skill: Skill name to check

        Returns:
            True if agent has the skill
        """
        skill_lower = skill.lower()
        return any(s.lower() == skill_lower for s in self.skills)

    def get_skill_proficiency(self, skill: str) -> float:
        """Get proficiency level for a skill.

        Args:
            skill: Skill name

        Returns:
            Proficiency level (0.0-1.0), defaults to 0.5 if skill exists but no rate
        """
        skill_lower = skill.lower()

        # Check if skill exists
        if not self.has_skill(skill):
            return 0.0

        # Look for matching success rate (case-insensitive)
        for rate_skill, rate in self.success_rates.items():
            if rate_skill.lower() == skill_lower:
                return rate

        # Skill exists but no rate - return default
        return 0.5

    def has_tool(self, tool: str) -> bool:
        """Check if agent has access to a specific tool.

        Args:
            tool: Tool name to check

        Returns:
            True if agent has access to the tool
        """
        return tool in self.tools

    def is_available(self) -> bool:
        """Check if agent is available for new tasks.

        Returns:
            True if agent is available (status is 'active')
        """
        return self.availability == "active"

    def update_success_rate(self, skill: str, success: bool, weight: float = 0.1) -> None:
        """Update success rate for a skill using exponential moving average.

        Args:
            skill: Skill to update
            success: Whether the task was successful
            weight: Weight for new observation (0.0-1.0)
        """
        skill_lower = skill.lower()
        current_rate = self.success_rates.get(skill_lower, 0.5)
        new_value = 1.0 if success else 0.0
        updated_rate = current_rate * (1 - weight) + new_value * weight
        self.success_rates[skill_lower] = round(updated_rate, 4)
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert card to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentCard:
        """Create AgentCard from dictionary.

        Args:
            data: Dictionary containing card data

        Returns:
            AgentCard instance
        """
        # Handle legacy format or missing fields
        return cls(
            agent_id=data["agent_id"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            skills=data.get("skills", []),
            tools=data.get("tools", []),
            availability=data.get("availability", "active"),
            success_rates=data.get("success_rates", {}),
            specializations=data.get("specializations", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
        )


def get_agent_cards_path(project_root: Path | None = None) -> Path:
    """Get the path to the agent cards file.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to AGENT_CARDS.json in project root
    """
    root = get_project_root(project_root)
    return root / AGENT_CARDS_FILENAME


class AgentCardRegistry:
    """Registry for managing agent cards.

    Provides thread-safe CRUD operations for agent cards with
    file-based persistence and locking.
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize the agent card registry.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = get_project_root(project_root)
        self.cards_path = get_agent_cards_path(self.project_root)
        self._lock = threading.Lock()
        self._cache: dict[str, AgentCard] | None = None
        self._cache_time: float = 0.0
        self._cache_ttl: float = 5.0  # Cache TTL in seconds

    def _read_cards(self) -> dict[str, AgentCard]:
        """Read all cards from file with locking.

        Returns:
            Dictionary mapping agent_id to AgentCard
        """
        if not self.cards_path.exists():
            return {}

        try:
            with FileLock(self.cards_path, timeout=CARD_LOCK_TIMEOUT_SECONDS, shared=True):
                with open(self.cards_path, encoding="utf-8") as f:
                    data = json.load(f)

                cards = {}
                for agent_id, card_data in data.get("cards", {}).items():
                    try:
                        cards[agent_id] = AgentCard.from_dict(card_data)
                    except (CardValidationError, KeyError) as e:
                        logger.warning(f"Invalid card for {agent_id}: {e}")
                        continue

                return cards

        except FileLockTimeout:
            logger.error(f"Timeout acquiring lock on {self.cards_path}")
            return {}
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Invalid JSON in cards file: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error reading cards file: {e}")
            return {}

    def _write_cards(self, cards: dict[str, AgentCard]) -> None:
        """Write all cards to file with locking.

        Args:
            cards: Dictionary mapping agent_id to AgentCard
        """
        # Ensure parent directory exists
        self.cards_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "cards": {agent_id: card.to_dict() for agent_id, card in cards.items()},
        }

        try:
            with FileLock(self.cards_path, timeout=CARD_LOCK_TIMEOUT_SECONDS, shared=False):
                # Write to temp file first for atomicity
                temp_path = self.cards_path.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

                # Atomic rename
                temp_path.replace(self.cards_path)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring write lock on {self.cards_path}")
            raise
        except Exception as e:
            logger.error(f"Error writing cards file: {e}")
            raise

        # Invalidate cache
        self._cache = None

    def _get_cached_cards(self) -> dict[str, AgentCard]:
        """Get cards from cache or read from file.

        Returns:
            Dictionary mapping agent_id to AgentCard
        """
        now = time.time()

        with self._lock:
            if self._cache is not None and (now - self._cache_time) < self._cache_ttl:
                return self._cache.copy()

            cards = self._read_cards()
            self._cache = cards
            self._cache_time = now
            return cards.copy()

    def register_agent(
        self,
        agent_id: str,
        name: str = "",
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        specializations: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentCard:
        """Register a new agent or update existing registration.

        Args:
            agent_id: Unique agent identifier
            name: Human-readable name
            skills: List of skills
            tools: List of available tools
            specializations: Areas of specialization
            metadata: Additional metadata

        Returns:
            Created or updated AgentCard
        """
        with self._lock:
            cards = self._read_cards()

            if agent_id in cards:
                # Update existing card
                card = cards[agent_id]
                if name:
                    card.name = name
                if skills is not None:
                    card.skills = skills
                if tools is not None:
                    card.tools = tools
                if specializations is not None:
                    card.specializations = specializations
                if metadata is not None:
                    card.metadata.update(metadata)
                card.updated_at = datetime.now(UTC).isoformat()
                logger.info(f"Updated card for agent {agent_id}")
            else:
                # Create new card
                card = AgentCard(
                    agent_id=agent_id,
                    name=name or agent_id,
                    skills=skills or [],
                    tools=tools or [],
                    specializations=specializations or [],
                    metadata=metadata or {},
                )
                cards[agent_id] = card
                logger.info(f"Registered new agent {agent_id}")

            self._write_cards(cards)
            return card

    def update_card(
        self,
        agent_id: str,
        name: str | None = None,
        skills: list[str] | None = None,
        tools: list[str] | None = None,
        availability: str | None = None,
        success_rates: dict[str, float] | None = None,
        specializations: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AgentCard:
        """Update an existing agent card.

        Args:
            agent_id: Agent identifier
            name: New name (optional)
            skills: New skills list (optional)
            tools: New tools list (optional)
            availability: New availability status (optional)
            success_rates: New success rates (optional)
            specializations: New specializations (optional)
            metadata: Metadata to merge (optional)

        Returns:
            Updated AgentCard

        Raises:
            CardNotFoundError: If agent not found
        """
        with self._lock:
            cards = self._read_cards()

            if agent_id not in cards:
                raise CardNotFoundError(f"Agent card not found: {agent_id}")

            card = cards[agent_id]

            if name is not None:
                card.name = name
            if skills is not None:
                card.skills = skills
            if tools is not None:
                card.tools = tools
            if availability is not None:
                if availability not in ("active", "busy", "offline"):
                    raise CardValidationError(
                        f"Invalid availability: {availability}. "
                        "Must be 'active', 'busy', or 'offline'"
                    )
                card.availability = availability
            if success_rates is not None:
                card.success_rates.update(success_rates)
            if specializations is not None:
                card.specializations = specializations
            if metadata is not None:
                card.metadata.update(metadata)

            card.updated_at = datetime.now(UTC).isoformat()
            self._write_cards(cards)

            logger.debug(f"Updated card for agent {agent_id}")
            return card

    def get_card(self, agent_id: str) -> AgentCard | None:
        """Get an agent's card.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentCard if found, None otherwise
        """
        cards = self._get_cached_cards()
        return cards.get(agent_id)

    def list_cards(
        self,
        availability: str | None = None,
        skill: str | None = None,
        tool: str | None = None,
    ) -> list[AgentCard]:
        """List agent cards with optional filtering.

        Args:
            availability: Filter by availability status
            skill: Filter by skill
            tool: Filter by tool

        Returns:
            List of matching AgentCards
        """
        cards = self._get_cached_cards()
        result = list(cards.values())

        if availability is not None:
            result = [c for c in result if c.availability == availability]

        if skill is not None:
            result = [c for c in result if c.has_skill(skill)]

        if tool is not None:
            result = [c for c in result if c.has_tool(tool)]

        return result

    def delete_card(self, agent_id: str) -> bool:
        """Delete an agent's card.

        Args:
            agent_id: Agent identifier

        Returns:
            True if card was deleted, False if not found
        """
        with self._lock:
            cards = self._read_cards()

            if agent_id not in cards:
                return False

            del cards[agent_id]
            self._write_cards(cards)

            logger.info(f"Deleted card for agent {agent_id}")
            return True

    def set_availability(self, agent_id: str, availability: str) -> bool:
        """Set an agent's availability status.

        Args:
            agent_id: Agent identifier
            availability: New status ('active', 'busy', 'offline')

        Returns:
            True if updated, False if agent not found
        """
        try:
            self.update_card(agent_id, availability=availability)
            return True
        except CardNotFoundError:
            return False

    def find_agents_with_skill(
        self,
        skill: str,
        min_proficiency: float = 0.0,
        available_only: bool = True,
    ) -> list[tuple[AgentCard, float]]:
        """Find agents with a specific skill.

        Args:
            skill: Skill to search for
            min_proficiency: Minimum proficiency level (0.0-1.0)
            available_only: Only return available agents

        Returns:
            List of (AgentCard, proficiency) tuples, sorted by proficiency
        """
        cards = self._get_cached_cards()
        matches = []

        for card in cards.values():
            if available_only and not card.is_available():
                continue

            proficiency = card.get_skill_proficiency(skill)
            if proficiency >= min_proficiency:
                matches.append((card, proficiency))

        # Sort by proficiency descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def update_skill_success(
        self,
        agent_id: str,
        skill: str,
        success: bool,
    ) -> None:
        """Update an agent's success rate for a skill.

        Args:
            agent_id: Agent identifier
            skill: Skill that was used
            success: Whether the task was successful
        """
        with self._lock:
            cards = self._read_cards()

            if agent_id not in cards:
                logger.warning(f"Cannot update success rate: agent {agent_id} not found")
                return

            card = cards[agent_id]
            card.update_success_rate(skill, success)
            self._write_cards(cards)

            logger.debug(
                f"Updated success rate for {agent_id}/{skill}: "
                f"success={success}, new_rate={card.success_rates.get(skill.lower())}"
            )

    def clear_cache(self) -> None:
        """Clear the card cache."""
        with self._lock:
            self._cache = None
