"""Shared coordination file management for Claude Swarm.

This module provides functionality to:
- Initialize and maintain COORDINATION.md file
- Parse and update specific sections atomically
- Integrate with file locking system
- Query current work, blocked items, review queue
- Preserve markdown formatting during updates

The coordination file serves as a shared workspace where agents can
communicate their current work, blockers, and coordination needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .locking import LockManager
from .utils import atomic_write

__all__ = [
    "CoordinationFile",
    "CoordinationSection",
    "init_coordination_file",
    "update_section",
    "get_section",
    "get_current_work",
    "get_blocked_items",
    "get_review_queue",
    "get_decisions",
    "add_current_work",
    "add_blocked_item",
    "add_review_item",
    "add_decision",
]

# Constants
COORDINATION_FILENAME = "COORDINATION.md"
LOCK_TIMEOUT = 10  # seconds


@dataclass
class CoordinationSection:
    """Represents a section in the coordination file.

    Attributes:
        name: Section name (e.g., "Sprint Goals")
        content: Section content (markdown text)
        start_line: Line number where section starts
        end_line: Line number where section ends
    """

    name: str
    content: str
    start_line: int
    end_line: int


class CoordinationFile:
    """Manages the shared COORDINATION.md file with atomic updates and locking.

    This class provides high-level operations on the coordination file,
    ensuring thread-safe access through file locking and atomic writes.
    """

    def __init__(
        self,
        project_root: Optional[Path] = None,
        agent_id: Optional[str] = None,
        lock_manager: Optional[LockManager] = None,
    ):
        """Initialize the coordination file manager.

        Args:
            project_root: Root directory of the project (defaults to current directory)
            agent_id: Unique identifier of the agent (required for locking)
            lock_manager: Custom lock manager instance (creates default if not provided)
        """
        self.project_root = project_root or Path.cwd()
        self.filepath = self.project_root / COORDINATION_FILENAME
        self.agent_id = agent_id or "default-agent"
        self.lock_manager = lock_manager or LockManager(project_root=self.project_root)

    @staticmethod
    def get_template(project_name: str = "Project") -> str:
        """Generate the coordination file template.

        Args:
            project_name: Name of the project

        Returns:
            Markdown template string
        """
        return f"""# Coordination File - {project_name}

## Sprint Goals

- Add sprint goals here
- Each goal should be specific and measurable

## Current Work

| Agent | Task | Status | Started |
|-------|------|--------|---------|
| example-agent | Example task | In Progress | {datetime.now(timezone.utc).strftime('%Y-%m-%d')} |

## Blocked Items

- **Task Name**: Reason for blocking (Agent: agent-id)

## Code Review Queue

- **PR #123**: Description (Author: agent-1, Reviewer: agent-2, Status: Pending)

## Decisions

- **[{datetime.now(timezone.utc).strftime('%Y-%m-%d')}]** Decision made: Rationale and context
"""

    def init_file(self, project_name: str = "Project", force: bool = False) -> bool:
        """Initialize a new COORDINATION.md file with template.

        Args:
            project_name: Name of the project for the template
            force: If True, overwrite existing file

        Returns:
            True if file was created, False if it already exists

        Raises:
            FileExistsError: If file exists and force is False
        """
        if self.filepath.exists() and not force:
            raise FileExistsError(
                f"Coordination file already exists at {self.filepath}. "
                "Use force=True to overwrite."
            )

        template = self.get_template(project_name)

        # Write atomically using atomic_write from utils
        atomic_write(self.filepath, template)
        return True

    def _parse_sections(self, content: str) -> dict[str, CoordinationSection]:
        """Parse the coordination file into sections.

        Args:
            content: Full content of the coordination file

        Returns:
            Dictionary mapping section names to CoordinationSection objects
        """
        sections: dict[str, CoordinationSection] = {}
        lines = content.split("\n")

        current_section: Optional[str] = None
        section_start = 0
        section_lines: list[str] = []

        for i, line in enumerate(lines):
            # Match level-2 headers (## Section Name)
            if line.startswith("## "):
                # Save previous section if exists
                if current_section:
                    sections[current_section] = CoordinationSection(
                        name=current_section,
                        content="\n".join(section_lines).strip(),
                        start_line=section_start,
                        end_line=i - 1,
                    )

                # Start new section
                current_section = line[3:].strip()
                section_start = i
                section_lines = []
            elif current_section:
                section_lines.append(line)

        # Save last section
        if current_section:
            sections[current_section] = CoordinationSection(
                name=current_section,
                content="\n".join(section_lines).strip(),
                start_line=section_start,
                end_line=len(lines) - 1,
            )

        return sections

    def _rebuild_content(
        self, sections: dict[str, CoordinationSection], original_content: str
    ) -> str:
        """Rebuild the coordination file content from sections.

        Args:
            sections: Dictionary of sections to include
            original_content: Original file content for preserving structure

        Returns:
            Rebuilt markdown content
        """
        lines = original_content.split("\n")
        result: list[str] = []

        # Keep the title line (first line)
        if lines:
            result.append(lines[0])

        # Add each section
        for section_name, section in sections.items():
            result.append("")  # Blank line before section
            result.append(f"## {section_name}")
            if section.content:
                result.append("")  # Blank line after header
                result.append(section.content)

        return "\n".join(result)

    def read_file(self) -> str:
        """Read the coordination file content.

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If coordination file doesn't exist
        """
        if not self.filepath.exists():
            raise FileNotFoundError(
                f"Coordination file not found at {self.filepath}. "
                "Call init_file() first."
            )

        return self.filepath.read_text(encoding="utf-8")

    def get_section(self, section_name: str) -> Optional[str]:
        """Get the content of a specific section.

        Args:
            section_name: Name of the section (e.g., "Current Work")

        Returns:
            Section content as string, or None if section doesn't exist
        """
        try:
            content = self.read_file()
            sections = self._parse_sections(content)
            section = sections.get(section_name)
            return section.content if section else None
        except FileNotFoundError:
            return None

    def update_section(
        self, section_name: str, new_content: str, reason: str = "updating section"
    ) -> bool:
        """Update a specific section atomically with locking.

        Args:
            section_name: Name of the section to update
            new_content: New content for the section
            reason: Reason for the update (for lock tracking)

        Returns:
            True if update succeeded, False otherwise

        Raises:
            FileNotFoundError: If coordination file doesn't exist
            RuntimeError: If lock cannot be acquired
        """
        # Acquire lock
        success, conflict = self.lock_manager.acquire_lock(
            str(self.filepath), self.agent_id, reason=reason, timeout=LOCK_TIMEOUT
        )

        if not success:
            raise RuntimeError(
                f"Cannot acquire lock on {self.filepath}. "
                f"Locked by {conflict.current_holder if conflict else 'unknown'}: "
                f"{conflict.reason if conflict else 'unknown reason'}"
            )

        try:
            # Read current content
            content = self.read_file()

            # Parse sections
            sections = self._parse_sections(content)

            # Update target section
            if section_name in sections:
                sections[section_name].content = new_content.strip()
            else:
                # Create new section
                sections[section_name] = CoordinationSection(
                    name=section_name, content=new_content.strip(), start_line=-1, end_line=-1
                )

            # Rebuild content
            new_file_content = self._rebuild_content(sections, content)

            # Write atomically using atomic_write from utils
            atomic_write(self.filepath, new_file_content)
            return True

        finally:
            # Always release lock
            self.lock_manager.release_lock(str(self.filepath), self.agent_id)

    def append_to_section(self, section_name: str, line: str, reason: str = "appending") -> bool:
        """Append a line to a section atomically.

        Args:
            section_name: Name of the section
            line: Line to append
            reason: Reason for the update

        Returns:
            True if append succeeded, False otherwise
        """
        current_content = self.get_section(section_name) or ""
        if current_content:
            new_content = f"{current_content}\n{line}"
        else:
            new_content = line

        return self.update_section(section_name, new_content, reason=reason)


# Module-level convenience functions using default instance
_default_coordination: Optional[CoordinationFile] = None


def _get_default_coordination(project_root: Optional[Path] = None) -> CoordinationFile:
    """Get or create default coordination file instance."""
    global _default_coordination
    if _default_coordination is None or (
        project_root is not None and _default_coordination.project_root != project_root
    ):
        _default_coordination = CoordinationFile(project_root=project_root)
    return _default_coordination


def _reset_default_coordination() -> None:
    """Reset the default coordination instance. Used for testing."""
    global _default_coordination
    _default_coordination = None


def init_coordination_file(
    project_name: str = "Project", force: bool = False, project_root: Optional[Path] = None
) -> bool:
    """Initialize a new COORDINATION.md file with template sections.

    Args:
        project_name: Name of the project
        force: If True, overwrite existing file
        project_root: Root directory of the project

    Returns:
        True if file was created

    Raises:
        FileExistsError: If COORDINATION.md already exists and force is False
    """
    coord = CoordinationFile(project_root=project_root)
    return coord.init_file(project_name=project_name, force=force)


def update_section(
    section: str,
    content: str,
    agent_id: Optional[str] = None,
    reason: str = "updating section",
    project_root: Optional[Path] = None,
) -> bool:
    """Update a specific section of the coordination file.

    Acquires lock, updates section, releases lock atomically.

    Args:
        section: Section name (e.g., "Current Work")
        content: New content for the section
        agent_id: Agent identifier (for locking)
        reason: Reason for update
        project_root: Root directory of the project

    Returns:
        True if update succeeded

    Raises:
        ValueError: If section name is invalid
        RuntimeError: If lock cannot be acquired within timeout
    """
    if not section:
        raise ValueError("Section name cannot be empty")

    coord = _get_default_coordination(project_root=project_root)
    if agent_id:
        coord.agent_id = agent_id

    return coord.update_section(section, content, reason=reason)


def get_section(section: str, project_root: Optional[Path] = None) -> Optional[str]:
    """Get content of a specific section.

    Args:
        section: Section name
        project_root: Root directory of the project

    Returns:
        Section content or None if not found
    """
    coord = _get_default_coordination(project_root=project_root)
    return coord.get_section(section)


def get_current_work(project_root: Optional[Path] = None) -> list[str]:
    """Get list of items in the Current Work section.

    Args:
        project_root: Root directory of the project

    Returns:
        List of current work items (table rows)
    """
    content = get_section("Current Work", project_root=project_root)
    if not content:
        return []

    # Parse table rows (skip header and separator)
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    # Skip table header (2 lines)
    data_lines = [line for line in lines[2:] if line.startswith("|")]

    return data_lines


def get_blocked_items(project_root: Optional[Path] = None) -> list[str]:
    """Get list of blocked items from the Blocked section.

    Args:
        project_root: Root directory of the project

    Returns:
        List of blocked items
    """
    content = get_section("Blocked Items", project_root=project_root)
    if not content:
        return []

    # Parse list items
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    return [line for line in lines if line.startswith("-") or line.startswith("*")]


def get_review_queue(project_root: Optional[Path] = None) -> list[str]:
    """Get list of items in the Code Review Queue section.

    Args:
        project_root: Root directory of the project

    Returns:
        List of items awaiting review
    """
    content = get_section("Code Review Queue", project_root=project_root)
    if not content:
        return []

    # Parse list items
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    return [line for line in lines if line.startswith("-") or line.startswith("*")]


def get_decisions(project_root: Optional[Path] = None) -> list[str]:
    """Get list of decisions from the Decisions section.

    Args:
        project_root: Root directory of the project

    Returns:
        List of decisions made
    """
    content = get_section("Decisions", project_root=project_root)
    if not content:
        return []

    # Parse list items
    lines = [line.strip() for line in content.split("\n") if line.strip()]
    return [line for line in lines if line.startswith("-") or line.startswith("*")]


def add_current_work(
    agent: str,
    task: str,
    status: str = "In Progress",
    agent_id: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """Add a new work item to the Current Work table.

    Args:
        agent: Agent name
        task: Task description
        status: Task status (default: "In Progress")
        agent_id: Agent identifier for locking
        project_root: Root directory of the project

    Returns:
        True if added successfully
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_row = f"| {agent} | {task} | {status} | {today} |"

    coord = _get_default_coordination(project_root=project_root)
    if agent_id:
        coord.agent_id = agent_id

    return coord.append_to_section("Current Work", new_row, reason="adding work item")


def add_blocked_item(
    task: str,
    reason: str,
    agent: str,
    agent_id: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """Add a blocked item to the Blocked Items section.

    Args:
        task: Task name
        reason: Reason for blocking
        agent: Agent reporting the block
        agent_id: Agent identifier for locking
        project_root: Root directory of the project

    Returns:
        True if added successfully
    """
    new_item = f"- **{task}**: {reason} (Agent: {agent})"

    coord = _get_default_coordination(project_root=project_root)
    if agent_id:
        coord.agent_id = agent_id

    return coord.append_to_section("Blocked Items", new_item, reason="adding blocked item")


def add_review_item(
    pr_number: str,
    description: str,
    author: str,
    reviewer: str = "TBD",
    status: str = "Pending",
    agent_id: Optional[str] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """Add a code review item to the Code Review Queue.

    Args:
        pr_number: Pull request number (e.g., "#123")
        description: PR description
        author: PR author
        reviewer: Assigned reviewer
        status: Review status
        agent_id: Agent identifier for locking
        project_root: Root directory of the project

    Returns:
        True if added successfully
    """
    new_item = (
        f"- **PR {pr_number}**: {description} "
        f"(Author: {author}, Reviewer: {reviewer}, Status: {status})"
    )

    coord = _get_default_coordination(project_root=project_root)
    if agent_id:
        coord.agent_id = agent_id

    return coord.append_to_section("Code Review Queue", new_item, reason="adding review item")


def add_decision(
    decision: str, rationale: str, agent_id: Optional[str] = None, project_root: Optional[Path] = None
) -> bool:
    """Add a decision to the Decisions section.

    Args:
        decision: Decision made
        rationale: Rationale for the decision
        agent_id: Agent identifier for locking
        project_root: Root directory of the project

    Returns:
        True if added successfully
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_item = f"- **[{today}]** {decision}: {rationale}"

    coord = _get_default_coordination(project_root=project_root)
    if agent_id:
        coord.agent_id = agent_id

    return coord.append_to_section("Decisions", new_item, reason="adding decision")
