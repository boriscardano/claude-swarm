"""Agent memory system for Claude Swarm.

This module provides persistent memory for each agent, enabling them to:
- Remember recent task history
- Learn patterns from past experiences
- Track relationships with other agents
- Store and retrieve knowledge

Agent memory consists of:
- Task history: Recent tasks worked on
- Learned patterns: What worked, what didn't
- Relationship scores: Trust and reliability of other agents
- Knowledge base: Key facts and insights

Example memory:
    {
        "agent_id": "agent-0",
        "task_history": [...],
        "patterns": {
            "successful_approaches": [...],
            "failed_approaches": [...]
        },
        "relationships": {
            "agent-1": {"trust": 0.85, "reliability": 0.9}
        }
    }
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .file_lock import FileLock, FileLockTimeout
from .logging_config import get_logger
from .project import get_project_root

__all__ = [
    "AgentMemory",
    "TaskMemory",
    "LearnedPattern",
    "AgentRelationship",
    "MemoryStore",
    "get_memory_path",
]

# Constants
MEMORY_DIR = ".agent_memory"
MEMORY_LOCK_TIMEOUT_SECONDS = 5.0
MAX_TASK_HISTORY = 50
MAX_PATTERNS = 100
MAX_KNOWLEDGE_ITEMS = 200

# Configure logging
logger = get_logger(__name__)


@dataclass
class TaskMemory:
    """Memory of a task worked on.

    Attributes:
        task_id: Task identifier
        objective: What the task was about
        outcome: How it ended (completed, failed, etc.)
        skills_used: Skills applied to the task
        files_touched: Files modified
        duration_seconds: How long it took
        lessons_learned: Key takeaways
        timestamp: When the task was completed
    """

    task_id: str
    objective: str
    outcome: str  # completed, failed, blocked, etc.
    skills_used: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    lessons_learned: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskMemory":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class LearnedPattern:
    """A pattern learned from experience.

    Attributes:
        pattern_id: Unique pattern identifier
        pattern_type: Type of pattern (approach, anti-pattern, optimization)
        description: What the pattern is
        context: When to apply this pattern
        effectiveness: How effective it is (0.0-1.0)
        occurrences: How many times it's been observed
        created_at: When first observed
        last_seen: When last observed
    """

    pattern_id: str
    pattern_type: str  # approach, anti-pattern, optimization
    description: str
    context: str = ""
    effectiveness: float = 0.5
    occurrences: int = 1
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_seen: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def reinforce(self, success: bool) -> None:
        """Reinforce or weaken the pattern based on outcome.

        Args:
            success: Whether applying the pattern succeeded
        """
        self.occurrences += 1
        self.last_seen = datetime.now(UTC).isoformat()

        # Update effectiveness using exponential moving average
        new_value = 1.0 if success else 0.0
        weight = 0.2
        self.effectiveness = self.effectiveness * (1 - weight) + new_value * weight
        self.effectiveness = round(self.effectiveness, 4)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnedPattern":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class AgentRelationship:
    """Relationship with another agent.

    Attributes:
        agent_id: The other agent's ID
        trust_score: How much we trust this agent (0.0-1.0)
        reliability_score: How reliable the agent is (0.0-1.0)
        speed_score: How fast the agent responds (0.0-1.0)
        collaboration_count: Number of collaborations
        positive_interactions: Count of positive interactions
        negative_interactions: Count of negative interactions
        strengths: Known strengths of this agent
        last_interaction: Last interaction timestamp
        notes: Free-form notes about the agent
    """

    agent_id: str
    trust_score: float = 0.5
    reliability_score: float = 0.5
    speed_score: float = 0.5
    collaboration_count: int = 0
    positive_interactions: int = 0
    negative_interactions: int = 0
    strengths: list[str] = field(default_factory=list)
    last_interaction: str | None = None
    notes: str = ""

    def record_interaction(self, positive: bool, note: str = "") -> None:
        """Record an interaction with this agent.

        Args:
            positive: Whether the interaction was positive
            note: Optional note about the interaction
        """
        self.collaboration_count += 1

        if positive:
            self.positive_interactions += 1
        else:
            self.negative_interactions += 1

        # Update trust and reliability scores
        total = self.positive_interactions + self.negative_interactions
        if total > 0:
            positive_ratio = self.positive_interactions / total
            # Blend with existing score (weighted average)
            weight = min(0.3, 5 / total)  # Less weight for new data as history grows
            self.trust_score = self.trust_score * (1 - weight) + positive_ratio * weight
            self.reliability_score = self.reliability_score * (1 - weight) + positive_ratio * weight

        self.last_interaction = datetime.now(UTC).isoformat()

        if note:
            if self.notes:
                self.notes += f"\n{note}"
            else:
                self.notes = note

    def add_strength(self, strength: str) -> None:
        """Add a known strength.

        Args:
            strength: The strength to add
        """
        if strength and strength not in self.strengths:
            self.strengths.append(strength)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentRelationship":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class AgentMemory:
    """Complete memory for an agent.

    Attributes:
        agent_id: Agent identifier
        task_history: Recent tasks worked on
        patterns: Learned patterns
        relationships: Relationships with other agents
        knowledge: Key facts and insights
        preferences: Agent preferences
        created_at: When memory was initialized
        updated_at: Last update time
    """

    agent_id: str
    task_history: list[TaskMemory] = field(default_factory=list)
    patterns: list[LearnedPattern] = field(default_factory=list)
    relationships: dict[str, AgentRelationship] = field(default_factory=dict)
    knowledge: dict[str, Any] = field(default_factory=dict)
    preferences: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def remember_task(
        self,
        task_id: str,
        objective: str,
        outcome: str,
        skills_used: list[str] | None = None,
        files_touched: list[str] | None = None,
        duration_seconds: float = 0.0,
        lessons: list[str] | None = None,
    ) -> TaskMemory:
        """Remember a completed task.

        Args:
            task_id: Task identifier
            objective: What the task was about
            outcome: How it ended
            skills_used: Skills applied
            files_touched: Files modified
            duration_seconds: How long it took
            lessons: Lessons learned

        Returns:
            Created TaskMemory
        """
        memory = TaskMemory(
            task_id=task_id,
            objective=objective,
            outcome=outcome,
            skills_used=skills_used or [],
            files_touched=files_touched or [],
            duration_seconds=duration_seconds,
            lessons_learned=lessons or [],
        )

        # Add to history (most recent first)
        self.task_history.insert(0, memory)

        # Trim history
        if len(self.task_history) > MAX_TASK_HISTORY:
            self.task_history = self.task_history[:MAX_TASK_HISTORY]

        self._touch()
        return memory

    def learn_pattern(
        self,
        pattern_type: str,
        description: str,
        context: str = "",
        effectiveness: float = 0.5,
    ) -> LearnedPattern:
        """Learn a new pattern or reinforce existing one.

        Args:
            pattern_type: Type of pattern
            description: What the pattern is
            context: When to apply
            effectiveness: Initial effectiveness

        Returns:
            Created or updated LearnedPattern
        """
        import hashlib

        # Generate ID from description
        pattern_id = hashlib.md5(description.encode()).hexdigest()[:12]

        # Check if pattern exists
        for pattern in self.patterns:
            if pattern.pattern_id == pattern_id:
                pattern.reinforce(effectiveness > 0.5)
                self._touch()
                return pattern

        # Create new pattern
        pattern = LearnedPattern(
            pattern_id=pattern_id,
            pattern_type=pattern_type,
            description=description,
            context=context,
            effectiveness=effectiveness,
        )

        self.patterns.append(pattern)

        # Trim patterns
        if len(self.patterns) > MAX_PATTERNS:
            # Remove least effective patterns
            self.patterns.sort(key=lambda p: p.effectiveness, reverse=True)
            self.patterns = self.patterns[:MAX_PATTERNS]

        self._touch()
        return pattern

    def get_relationship(self, agent_id: str) -> AgentRelationship:
        """Get or create relationship with another agent.

        Args:
            agent_id: The other agent's ID

        Returns:
            AgentRelationship
        """
        if agent_id not in self.relationships:
            self.relationships[agent_id] = AgentRelationship(agent_id=agent_id)
        return self.relationships[agent_id]

    def record_interaction(
        self,
        agent_id: str,
        positive: bool,
        note: str = "",
    ) -> None:
        """Record an interaction with another agent.

        Args:
            agent_id: The other agent's ID
            positive: Whether the interaction was positive
            note: Optional note
        """
        relationship = self.get_relationship(agent_id)
        relationship.record_interaction(positive, note)
        self._touch()

    def store_knowledge(self, key: str, value: Any) -> None:
        """Store a piece of knowledge.

        Args:
            key: Knowledge key
            value: Knowledge value
        """
        self.knowledge[key] = value

        # Trim knowledge
        if len(self.knowledge) > MAX_KNOWLEDGE_ITEMS:
            # Remove oldest items (assumes keys are somewhat ordered)
            keys = list(self.knowledge.keys())
            for key in keys[:-MAX_KNOWLEDGE_ITEMS]:
                del self.knowledge[key]

        self._touch()

    def recall_knowledge(self, key: str) -> Any:
        """Recall a piece of knowledge.

        Args:
            key: Knowledge key

        Returns:
            Stored value or None
        """
        return self.knowledge.get(key)

    def get_effective_patterns(self, pattern_type: str | None = None) -> list[LearnedPattern]:
        """Get patterns that work well.

        Args:
            pattern_type: Optional filter by type

        Returns:
            List of effective patterns (effectiveness > 0.6)
        """
        patterns = self.patterns
        if pattern_type:
            patterns = [p for p in patterns if p.pattern_type == pattern_type]

        return [p for p in patterns if p.effectiveness > 0.6]

    def get_trusted_agents(self, min_trust: float = 0.6) -> list[str]:
        """Get agents we trust.

        Args:
            min_trust: Minimum trust score

        Returns:
            List of trusted agent IDs
        """
        return [
            rel.agent_id
            for rel in self.relationships.values()
            if rel.trust_score >= min_trust
        ]

    def get_best_agents_for_skill(self, skill: str) -> list[tuple[str, float]]:
        """Get agents known to be good at a skill.

        Args:
            skill: The skill to search for

        Returns:
            List of (agent_id, reliability_score) tuples
        """
        skill_lower = skill.lower()
        results = []

        for rel in self.relationships.values():
            if any(s.lower() == skill_lower for s in rel.strengths):
                results.append((rel.agent_id, rel.reliability_score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "agent_id": self.agent_id,
            "task_history": [t.to_dict() for t in self.task_history],
            "patterns": [p.to_dict() for p in self.patterns],
            "relationships": {
                k: v.to_dict() for k, v in self.relationships.items()
            },
            "knowledge": self.knowledge,
            "preferences": self.preferences,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMemory":
        """Create from dictionary."""
        return cls(
            agent_id=data["agent_id"],
            task_history=[
                TaskMemory.from_dict(t) for t in data.get("task_history", [])
            ],
            patterns=[
                LearnedPattern.from_dict(p) for p in data.get("patterns", [])
            ],
            relationships={
                k: AgentRelationship.from_dict(v)
                for k, v in data.get("relationships", {}).items()
            },
            knowledge=data.get("knowledge", {}),
            preferences=data.get("preferences", {}),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
        )


def get_memory_path(project_root: Path | None = None) -> Path:
    """Get the path to the memory directory.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to .agent_memory directory
    """
    root = get_project_root(project_root)
    return root / MEMORY_DIR


class MemoryStore:
    """Store for managing agent memories.

    Each agent has its own memory file stored in the .agent_memory directory.
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize the memory store.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = get_project_root(project_root)
        self.memory_dir = get_memory_path(self.project_root)
        self._lock = threading.Lock()
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        """Ensure the memory directory exists."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _get_memory_file(self, agent_id: str) -> Path:
        """Get the path to an agent's memory file.

        Args:
            agent_id: Agent identifier

        Returns:
            Path to the memory file
        """
        # Sanitize agent_id for filename
        safe_id = agent_id.replace("/", "_").replace("\\", "_")
        return self.memory_dir / f"{safe_id}.json"

    def _read_memory(self, agent_id: str) -> AgentMemory | None:
        """Read an agent's memory from file.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentMemory if exists, None otherwise
        """
        memory_file = self._get_memory_file(agent_id)

        if not memory_file.exists():
            return None

        try:
            with FileLock(memory_file, timeout=MEMORY_LOCK_TIMEOUT_SECONDS, shared=True):
                with open(memory_file, encoding="utf-8") as f:
                    data = json.load(f)
                return AgentMemory.from_dict(data)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring lock on {memory_file}")
            return None
        except Exception as e:
            logger.warning(f"Error reading memory for {agent_id}: {e}")
            return None

    def _write_memory(self, memory: AgentMemory) -> None:
        """Write an agent's memory to file.

        Args:
            memory: AgentMemory to write
        """
        self._ensure_directory()
        memory_file = self._get_memory_file(memory.agent_id)

        try:
            with FileLock(memory_file, timeout=MEMORY_LOCK_TIMEOUT_SECONDS, shared=False):
                temp_path = memory_file.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(memory.to_dict(), f, indent=2)
                temp_path.replace(memory_file)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring write lock on {memory_file}")
            raise
        except Exception as e:
            logger.error(f"Error writing memory for {memory.agent_id}: {e}")
            raise

    def get_memory(self, agent_id: str) -> AgentMemory:
        """Get or create an agent's memory.

        Args:
            agent_id: Agent identifier

        Returns:
            AgentMemory (creates new if doesn't exist)
        """
        with self._lock:
            memory = self._read_memory(agent_id)
            if memory is None:
                memory = AgentMemory(agent_id=agent_id)
                self._write_memory(memory)
            return memory

    def save_memory(self, memory: AgentMemory) -> None:
        """Save an agent's memory.

        Args:
            memory: AgentMemory to save
        """
        with self._lock:
            self._write_memory(memory)

    def delete_memory(self, agent_id: str) -> bool:
        """Delete an agent's memory.

        Args:
            agent_id: Agent identifier

        Returns:
            True if deleted, False if not found
        """
        memory_file = self._get_memory_file(agent_id)

        if not memory_file.exists():
            return False

        try:
            memory_file.unlink()
            logger.info(f"Deleted memory for {agent_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting memory for {agent_id}: {e}")
            return False

    def list_agents_with_memory(self) -> list[str]:
        """List all agents that have memory stored.

        Returns:
            List of agent IDs
        """
        self._ensure_directory()
        agent_ids = []

        for file in self.memory_dir.glob("*.json"):
            if file.suffix == ".json":
                agent_id = file.stem
                agent_ids.append(agent_id)

        return sorted(agent_ids)

    def remember_task(
        self,
        agent_id: str,
        task_id: str,
        objective: str,
        outcome: str,
        skills_used: list[str] | None = None,
        files_touched: list[str] | None = None,
        duration_seconds: float = 0.0,
        lessons: list[str] | None = None,
    ) -> TaskMemory:
        """Convenience method to remember a task for an agent.

        Args:
            agent_id: Agent identifier
            task_id: Task identifier
            objective: What the task was about
            outcome: How it ended
            skills_used: Skills applied
            files_touched: Files modified
            duration_seconds: How long it took
            lessons: Lessons learned

        Returns:
            Created TaskMemory
        """
        memory = self.get_memory(agent_id)
        task_memory = memory.remember_task(
            task_id=task_id,
            objective=objective,
            outcome=outcome,
            skills_used=skills_used,
            files_touched=files_touched,
            duration_seconds=duration_seconds,
            lessons=lessons,
        )
        self.save_memory(memory)
        return task_memory

    def learn_pattern(
        self,
        agent_id: str,
        pattern_type: str,
        description: str,
        context: str = "",
        effectiveness: float = 0.5,
    ) -> LearnedPattern:
        """Convenience method to learn a pattern for an agent.

        Args:
            agent_id: Agent identifier
            pattern_type: Type of pattern
            description: What the pattern is
            context: When to apply
            effectiveness: Initial effectiveness

        Returns:
            Created or updated LearnedPattern
        """
        memory = self.get_memory(agent_id)
        pattern = memory.learn_pattern(
            pattern_type=pattern_type,
            description=description,
            context=context,
            effectiveness=effectiveness,
        )
        self.save_memory(memory)
        return pattern

    def record_interaction(
        self,
        agent_id: str,
        other_agent_id: str,
        positive: bool,
        note: str = "",
    ) -> None:
        """Convenience method to record an interaction.

        Args:
            agent_id: Agent recording the interaction
            other_agent_id: The other agent
            positive: Whether the interaction was positive
            note: Optional note
        """
        memory = self.get_memory(agent_id)
        memory.record_interaction(other_agent_id, positive, note)
        self.save_memory(memory)

    def get_memory_summary(self, agent_id: str) -> dict[str, Any]:
        """Get a summary of an agent's memory.

        Args:
            agent_id: Agent identifier

        Returns:
            Summary dictionary
        """
        memory = self.get_memory(agent_id)

        return {
            "agent_id": agent_id,
            "tasks_remembered": len(memory.task_history),
            "patterns_learned": len(memory.patterns),
            "relationships_count": len(memory.relationships),
            "knowledge_items": len(memory.knowledge),
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
            "effective_patterns": len(memory.get_effective_patterns()),
            "trusted_agents": memory.get_trusted_agents(),
        }
