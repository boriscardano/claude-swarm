"""Shared context store for Claude Swarm.

This module implements A2A Protocol-inspired context management for
preserving and sharing context across agent interactions.

Context enables:
- Grouping related tasks and messages
- Preserving architectural decisions
- Tracking files touched in a context
- Linking related contexts
- Summarizing work done

Example context:
    {
        "context_id": "feature-auth",
        "summary": "Implementing JWT authentication for API",
        "decisions": [
            {"decision": "Use HS256 algorithm", "by": "agent-0", "reason": "Simpler key management"}
        ],
        "files_touched": ["src/auth.py", "src/middleware.py"],
        "related_contexts": ["feature-api"]
    }
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .file_lock import FileLock, FileLockTimeout
from .logging_config import get_logger
from .project import get_project_root

__all__ = [
    "SharedContext",
    "ContextDecision",
    "ContextStore",
    "get_contexts_path",
]

# Constants
CONTEXTS_FILENAME = "CONTEXTS.json"
CONTEXT_LOCK_TIMEOUT_SECONDS = 5.0
MAX_DECISIONS_PER_CONTEXT = 100
MAX_FILES_PER_CONTEXT = 200

# Configure logging
logger = get_logger(__name__)


@dataclass
class ContextDecision:
    """A decision made within a context.

    Attributes:
        decision: What was decided
        by: Agent that made the decision
        reason: Why this decision was made
        timestamp: When the decision was made
        alternatives_considered: Other options that were considered
        metadata: Additional data
    """

    decision: str
    by: str
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    alternatives_considered: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextDecision":
        """Create from dictionary."""
        return cls(**data)


@dataclass
class SharedContext:
    """Shared context for coordinating related work.

    Attributes:
        context_id: Unique context identifier
        name: Human-readable name
        summary: Brief summary of what the context is about
        status: Current status (active, completed, archived)
        decisions: List of decisions made
        files_touched: Files modified in this context
        related_contexts: Related context IDs
        agents_involved: Agents that have contributed
        tasks: Task IDs associated with this context
        messages: Key message IDs in this context
        notes: Free-form notes
        created_at: When the context was created
        updated_at: When the context was last updated
        created_by: Agent that created the context
        metadata: Additional data
    """

    context_id: str
    name: str
    summary: str = ""
    status: str = "active"  # active, completed, archived
    decisions: list[ContextDecision] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    related_contexts: list[str] = field(default_factory=list)
    agents_involved: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_by: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_decision(
        self,
        decision: str,
        by: str,
        reason: str = "",
        alternatives: list[str] | None = None,
    ) -> ContextDecision:
        """Add a decision to the context.

        Args:
            decision: What was decided
            by: Agent making the decision
            reason: Why this decision
            alternatives: Other options considered

        Returns:
            The created ContextDecision
        """
        ctx_decision = ContextDecision(
            decision=decision,
            by=by,
            reason=reason,
            alternatives_considered=alternatives or [],
        )

        # Trim if too many decisions
        if len(self.decisions) >= MAX_DECISIONS_PER_CONTEXT:
            self.decisions = self.decisions[-(MAX_DECISIONS_PER_CONTEXT - 1) :]

        self.decisions.append(ctx_decision)
        self._touch(by)

        return ctx_decision

    def add_file(self, filepath: str, agent_id: str | None = None) -> None:
        """Add a file to the context.

        Args:
            filepath: Path to the file
            agent_id: Agent touching the file
        """
        # Normalize path
        normalized = str(Path(filepath))

        if normalized not in self.files_touched:
            if len(self.files_touched) >= MAX_FILES_PER_CONTEXT:
                self.files_touched = self.files_touched[-(MAX_FILES_PER_CONTEXT - 1) :]
            self.files_touched.append(normalized)

        if agent_id:
            self._touch(agent_id)

    def add_related_context(self, context_id: str) -> None:
        """Add a related context.

        Args:
            context_id: ID of the related context
        """
        if context_id not in self.related_contexts and context_id != self.context_id:
            self.related_contexts.append(context_id)
            self.updated_at = datetime.now(UTC).isoformat()

    def add_task(self, task_id: str) -> None:
        """Add a task to this context.

        Args:
            task_id: Task identifier
        """
        if task_id not in self.tasks:
            self.tasks.append(task_id)
            self.updated_at = datetime.now(UTC).isoformat()

    def add_message(self, msg_id: str) -> None:
        """Add a message to this context.

        Args:
            msg_id: Message identifier
        """
        if msg_id not in self.messages:
            self.messages.append(msg_id)
            self.updated_at = datetime.now(UTC).isoformat()

    def _touch(self, agent_id: str) -> None:
        """Update the context with agent activity.

        Args:
            agent_id: Agent that touched the context
        """
        if agent_id and agent_id not in self.agents_involved:
            self.agents_involved.append(agent_id)
        self.updated_at = datetime.now(UTC).isoformat()

    def complete(self, by: str, summary: str | None = None) -> None:
        """Mark the context as completed.

        Args:
            by: Agent completing the context
            summary: Final summary
        """
        self.status = "completed"
        if summary:
            self.summary = summary
        self._touch(by)

    def archive(self) -> None:
        """Archive the context."""
        self.status = "archived"
        self.updated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        # Convert decisions
        data["decisions"] = [
            d.to_dict() if isinstance(d, ContextDecision) else d
            for d in self.decisions
        ]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SharedContext":
        """Create from dictionary."""
        # Convert decisions
        decisions = [
            ContextDecision.from_dict(d) if isinstance(d, dict) else d
            for d in data.get("decisions", [])
        ]

        return cls(
            context_id=data["context_id"],
            name=data["name"],
            summary=data.get("summary", ""),
            status=data.get("status", "active"),
            decisions=decisions,
            files_touched=data.get("files_touched", []),
            related_contexts=data.get("related_contexts", []),
            agents_involved=data.get("agents_involved", []),
            tasks=data.get("tasks", []),
            messages=data.get("messages", []),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", datetime.now(UTC).isoformat()),
            updated_at=data.get("updated_at", datetime.now(UTC).isoformat()),
            created_by=data.get("created_by", ""),
            metadata=data.get("metadata", {}),
        )


def get_contexts_path(project_root: Path | None = None) -> Path:
    """Get the path to the contexts file.

    Args:
        project_root: Optional project root directory

    Returns:
        Path to CONTEXTS.json
    """
    root = get_project_root(project_root)
    return root / CONTEXTS_FILENAME


class ContextStore:
    """Store for managing shared contexts.

    Provides thread-safe CRUD operations for contexts with
    file-based persistence.
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize the context store.

        Args:
            project_root: Root directory of the project
        """
        self.project_root = get_project_root(project_root)
        self.contexts_path = get_contexts_path(self.project_root)
        self._lock = threading.Lock()

    def _read_contexts(self) -> dict[str, SharedContext]:
        """Read all contexts from file.

        Returns:
            Dictionary mapping context_id to SharedContext
        """
        if not self.contexts_path.exists():
            return {}

        try:
            with FileLock(
                self.contexts_path, timeout=CONTEXT_LOCK_TIMEOUT_SECONDS, shared=True
            ):
                with open(self.contexts_path, encoding="utf-8") as f:
                    data = json.load(f)

                return {
                    ctx_id: SharedContext.from_dict(ctx_data)
                    for ctx_id, ctx_data in data.get("contexts", {}).items()
                }

        except FileLockTimeout:
            logger.error(f"Timeout acquiring lock on {self.contexts_path}")
            return {}
        except Exception as e:
            logger.warning(f"Error reading contexts: {e}")
            return {}

    def _write_contexts(self, contexts: dict[str, SharedContext]) -> None:
        """Write all contexts to file.

        Args:
            contexts: Dictionary mapping context_id to SharedContext
        """
        self.contexts_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": "1.0",
            "updated_at": datetime.now(UTC).isoformat(),
            "contexts": {ctx_id: ctx.to_dict() for ctx_id, ctx in contexts.items()},
        }

        try:
            with FileLock(
                self.contexts_path, timeout=CONTEXT_LOCK_TIMEOUT_SECONDS, shared=False
            ):
                temp_path = self.contexts_path.with_suffix(".json.tmp")
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                temp_path.replace(self.contexts_path)

        except FileLockTimeout:
            logger.error(f"Timeout acquiring write lock on {self.contexts_path}")
            raise
        except Exception as e:
            logger.error(f"Error writing contexts: {e}")
            raise

    def create_context(
        self,
        name: str,
        created_by: str,
        summary: str = "",
        context_id: str | None = None,
        related_contexts: list[str] | None = None,
    ) -> SharedContext:
        """Create a new context.

        Args:
            name: Context name
            created_by: Agent creating the context
            summary: Initial summary
            context_id: Optional specific ID (auto-generated if not provided)
            related_contexts: Related context IDs

        Returns:
            Created SharedContext
        """
        if context_id is None:
            # Generate a readable ID based on name
            base_id = name.lower().replace(" ", "-")[:20]
            context_id = f"{base_id}-{uuid.uuid4().hex[:8]}"

        ctx = SharedContext(
            context_id=context_id,
            name=name,
            summary=summary,
            created_by=created_by,
            agents_involved=[created_by],
            related_contexts=related_contexts or [],
        )

        with self._lock:
            contexts = self._read_contexts()
            contexts[context_id] = ctx
            self._write_contexts(contexts)

        logger.info(f"Created context {context_id}: {name}")
        return ctx

    def get_context(self, context_id: str) -> SharedContext | None:
        """Get a context by ID.

        Args:
            context_id: Context identifier

        Returns:
            SharedContext if found, None otherwise
        """
        contexts = self._read_contexts()
        return contexts.get(context_id)

    def update_context(self, context: SharedContext) -> None:
        """Update a context.

        Args:
            context: Context to update
        """
        context.updated_at = datetime.now(UTC).isoformat()

        with self._lock:
            contexts = self._read_contexts()
            contexts[context.context_id] = context
            self._write_contexts(contexts)

    def delete_context(self, context_id: str) -> bool:
        """Delete a context.

        Args:
            context_id: Context identifier

        Returns:
            True if deleted, False if not found
        """
        with self._lock:
            contexts = self._read_contexts()

            if context_id not in contexts:
                return False

            del contexts[context_id]
            self._write_contexts(contexts)

        logger.info(f"Deleted context {context_id}")
        return True

    def list_contexts(
        self,
        status: str | None = None,
        agent_id: str | None = None,
        include_archived: bool = False,
    ) -> list[SharedContext]:
        """List contexts with optional filtering.

        Args:
            status: Filter by status
            agent_id: Filter by involved agent
            include_archived: Include archived contexts

        Returns:
            List of matching contexts
        """
        contexts = self._read_contexts()
        result = list(contexts.values())

        if status is not None:
            result = [c for c in result if c.status == status]

        if agent_id is not None:
            result = [c for c in result if agent_id in c.agents_involved]

        if not include_archived:
            result = [c for c in result if c.status != "archived"]

        # Sort by updated_at, most recent first
        result.sort(key=lambda c: c.updated_at, reverse=True)

        return result

    def get_active_contexts(self) -> list[SharedContext]:
        """Get all active contexts.

        Returns:
            List of active contexts
        """
        return self.list_contexts(status="active")

    def add_decision(
        self,
        context_id: str,
        decision: str,
        by: str,
        reason: str = "",
        alternatives: list[str] | None = None,
    ) -> ContextDecision | None:
        """Add a decision to a context.

        Args:
            context_id: Context identifier
            decision: What was decided
            by: Agent making the decision
            reason: Why this decision
            alternatives: Other options considered

        Returns:
            Created ContextDecision or None if context not found
        """
        with self._lock:
            contexts = self._read_contexts()

            if context_id not in contexts:
                return None

            ctx = contexts[context_id]
            ctx_decision = ctx.add_decision(decision, by, reason, alternatives)
            self._write_contexts(contexts)

        logger.debug(f"Added decision to context {context_id}: {decision[:50]}...")
        return ctx_decision

    def touch_file(
        self,
        context_id: str,
        filepath: str,
        agent_id: str | None = None,
    ) -> bool:
        """Record that a file was touched in a context.

        Args:
            context_id: Context identifier
            filepath: Path to the file
            agent_id: Agent touching the file

        Returns:
            True if recorded, False if context not found
        """
        with self._lock:
            contexts = self._read_contexts()

            if context_id not in contexts:
                return False

            ctx = contexts[context_id]
            ctx.add_file(filepath, agent_id)
            self._write_contexts(contexts)

        return True

    def link_contexts(self, context_id: str, related_id: str) -> bool:
        """Link two contexts as related.

        Creates bidirectional relationship.

        Args:
            context_id: First context
            related_id: Second context

        Returns:
            True if linked, False if either context not found
        """
        with self._lock:
            contexts = self._read_contexts()

            if context_id not in contexts or related_id not in contexts:
                return False

            contexts[context_id].add_related_context(related_id)
            contexts[related_id].add_related_context(context_id)
            self._write_contexts(contexts)

        return True

    def get_or_create_context(
        self,
        context_id: str,
        name: str,
        created_by: str,
        summary: str = "",
    ) -> SharedContext:
        """Get an existing context or create it if it doesn't exist.

        Args:
            context_id: Context identifier
            name: Context name (used if creating)
            created_by: Agent (used if creating)
            summary: Summary (used if creating)

        Returns:
            Existing or newly created context
        """
        ctx = self.get_context(context_id)
        if ctx:
            return ctx

        return self.create_context(
            name=name,
            created_by=created_by,
            summary=summary,
            context_id=context_id,
        )

    def complete_context(
        self,
        context_id: str,
        by: str,
        summary: str | None = None,
    ) -> bool:
        """Mark a context as completed.

        Args:
            context_id: Context identifier
            by: Agent completing the context
            summary: Final summary

        Returns:
            True if completed, False if not found
        """
        with self._lock:
            contexts = self._read_contexts()

            if context_id not in contexts:
                return False

            contexts[context_id].complete(by, summary)
            self._write_contexts(contexts)

        logger.info(f"Completed context {context_id}")
        return True

    def archive_context(self, context_id: str) -> bool:
        """Archive a context.

        Args:
            context_id: Context identifier

        Returns:
            True if archived, False if not found
        """
        with self._lock:
            contexts = self._read_contexts()

            if context_id not in contexts:
                return False

            contexts[context_id].archive()
            self._write_contexts(contexts)

        logger.info(f"Archived context {context_id}")
        return True

    def search_contexts(
        self,
        query: str,
        include_archived: bool = False,
    ) -> list[SharedContext]:
        """Search contexts by query.

        Searches in name, summary, and notes.

        Args:
            query: Search query (case-insensitive)
            include_archived: Include archived contexts

        Returns:
            List of matching contexts
        """
        query_lower = query.lower()
        contexts = self.list_contexts(include_archived=include_archived)

        return [
            c
            for c in contexts
            if query_lower in c.name.lower()
            or query_lower in c.summary.lower()
            or query_lower in c.notes.lower()
        ]

    def get_context_summary(self, context_id: str) -> dict[str, Any] | None:
        """Get a summary of a context.

        Args:
            context_id: Context identifier

        Returns:
            Summary dictionary or None if not found
        """
        ctx = self.get_context(context_id)
        if not ctx:
            return None

        return {
            "context_id": ctx.context_id,
            "name": ctx.name,
            "summary": ctx.summary,
            "status": ctx.status,
            "agents_count": len(ctx.agents_involved),
            "decisions_count": len(ctx.decisions),
            "files_count": len(ctx.files_touched),
            "tasks_count": len(ctx.tasks),
            "related_contexts_count": len(ctx.related_contexts),
            "created_at": ctx.created_at,
            "updated_at": ctx.updated_at,
        }
