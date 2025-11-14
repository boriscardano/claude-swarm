"""Distributed file locking system for Claude Swarm.

This module provides functionality to:
- Acquire and release exclusive file locks
- Detect and resolve lock conflicts
- Handle stale lock cleanup
- Support glob pattern locking
- Query lock status and holders
- Prevent concurrent file editing conflicts

Lock files are stored in .agent_locks/ directory with format:
{hash(filepath)}.lock -> JSON with agent_id, filepath, locked_at, reason
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

from .config import get_config
from .project import get_project_root
from .validators import (
    ValidationError,
    validate_agent_id,
    validate_file_path,
    validate_timeout,
    normalize_path,
)

__all__ = [
    "FileLock",
    "LockConflict",
    "LockManager",
    "LOCK_DIR",
    "STALE_LOCK_TIMEOUT",
]

# Default lock directory name
LOCK_DIR = ".agent_locks"

# Stale lock timeout in seconds (5 minutes)
# NOTE: This constant is kept for backward compatibility.
# Default timeout now comes from configuration (config.locking.stale_timeout)
STALE_LOCK_TIMEOUT = 300


@dataclass
class FileLock:
    """Represents an active file lock.

    Attributes:
        agent_id: ID of the agent holding the lock
        filepath: Path to the locked file
        locked_at: Unix timestamp when lock was acquired
        reason: Human-readable reason for the lock
    """

    agent_id: str
    filepath: str
    locked_at: float
    reason: str

    def is_stale(self, timeout: Optional[int] = None) -> bool:
        """Check if this lock is stale (older than timeout).

        Args:
            timeout: Number of seconds after which a lock is considered stale
                    (None = use configured stale_timeout)

        Returns:
            True if the lock is older than the timeout, False otherwise
        """
        if timeout is None:
            timeout = get_config().locking.stale_timeout
        return (time.time() - self.locked_at) > timeout

    def age_seconds(self) -> float:
        """Get the age of this lock in seconds.

        Returns:
            Number of seconds since the lock was acquired
        """
        return time.time() - self.locked_at

    def to_dict(self) -> dict:
        """Convert lock to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FileLock:
        """Create FileLock from dictionary."""
        return cls(**data)


@dataclass
class LockConflict:
    """Represents a failed lock acquisition due to existing lock.

    Attributes:
        filepath: Path that couldn't be locked
        current_holder: Agent ID holding the lock
        locked_at: When the current lock was acquired
        reason: Why the file is currently locked
    """

    filepath: str
    current_holder: str
    locked_at: datetime
    reason: str


class LockManager:
    """Manages file locks for agent coordination.

    This class provides methods to acquire, release, and query file locks.
    Locks are stored as JSON files in a dedicated directory.
    """

    def __init__(self, lock_dir: str = LOCK_DIR, project_root: Optional[Path] = None):
        """Initialize the lock manager.

        Args:
            lock_dir: Name of the directory to store lock files
            project_root: Root directory of the project (defaults to auto-detected project root)
        """
        self.project_root = get_project_root(project_root)
        self.lock_dir = self.project_root / lock_dir
        self._lock = threading.Lock()  # Protect lock refresh operations
        self._ensure_lock_directory()

    def _ensure_lock_directory(self) -> None:
        """Create the lock directory if it doesn't exist."""
        self.lock_dir.mkdir(exist_ok=True, parents=True)

    def _validate_filepath(self, filepath: str) -> None:
        """Validate that filepath is within the project root to prevent path traversal.

        Args:
            filepath: Path to validate

        Raises:
            ValueError: If filepath is outside the project root
        """
        # Resolve the filepath to its absolute path
        try:
            # Handle both absolute and relative paths
            if Path(filepath).is_absolute():
                resolved_path = Path(filepath).resolve()
            else:
                resolved_path = (self.project_root / filepath).resolve()

            # Check if resolved path starts with project root
            # This prevents path traversal attacks using .. or symlinks
            if not str(resolved_path).startswith(str(self.project_root.resolve())):
                raise ValueError(
                    f"Path traversal detected: '{filepath}' resolves to '{resolved_path}' "
                    f"which is outside project root '{self.project_root.resolve()}'"
                )
        except (OSError, RuntimeError) as e:
            # Handle cases where path doesn't exist or has symlink loops
            # For glob patterns or non-existent files, we still want to validate the base path
            # Just check that the path doesn't contain obvious traversal attempts
            if '..' in filepath or filepath.startswith('/'):
                # For absolute paths, just ensure they're under project root
                if filepath.startswith('/'):
                    if not filepath.startswith(str(self.project_root.resolve())):
                        raise ValueError(
                            f"Absolute path '{filepath}' is outside project root '{self.project_root.resolve()}'"
                        )
            # For other paths, allow them as they'll be treated as patterns or relative paths

    def _get_lock_filename(self, filepath: str) -> str:
        """Generate a unique lock filename for a given filepath.

        Uses SHA256 hash of the filepath to create a safe filename.

        Args:
            filepath: Path to the file to be locked

        Returns:
            Filename for the lock file (e.g., "abc123def456.lock")

        Raises:
            ValueError: If filepath is outside the project root
        """
        # Validate filepath to prevent path traversal attacks
        self._validate_filepath(filepath)

        # Normalize the filepath
        normalized = str(Path(filepath).as_posix())
        # Create hash
        hash_obj = hashlib.sha256(normalized.encode())
        return f"{hash_obj.hexdigest()}.lock"

    def _get_lock_path(self, filepath: str) -> Path:
        """Get the full path to a lock file.

        Args:
            filepath: Path to the file to be locked

        Returns:
            Full path to the lock file
        """
        return self.lock_dir / self._get_lock_filename(filepath)

    def _read_lock(self, lock_path: Path) -> Optional[FileLock]:
        """Read a lock file and return the FileLock object.

        Args:
            lock_path: Path to the lock file

        Returns:
            FileLock object if the file exists and is valid, None otherwise
        """
        try:
            if not lock_path.exists():
                return None

            with lock_path.open("r") as f:
                data = json.load(f)

            return FileLock.from_dict(data)
        except (json.JSONDecodeError, KeyError, OSError):
            # Lock file is corrupted or unreadable
            return None

    def _write_lock(self, lock_path: Path, lock: FileLock) -> bool:
        """Write a lock to a file atomically.

        Uses exclusive file creation to ensure atomicity.

        Args:
            lock_path: Path to the lock file
            lock: FileLock object to write

        Returns:
            True if the lock was written successfully, False if file already exists
        """
        try:
            # Use 'x' mode for exclusive creation (fails if file exists)
            with lock_path.open("x") as f:
                json.dump(lock.to_dict(), f, indent=2)
            return True
        except FileExistsError:
            return False
        except OSError:
            return False

    def _check_glob_conflicts(self, filepath: str, agent_id: str) -> list[LockConflict]:
        """Check if the filepath conflicts with any existing glob patterns.

        Args:
            filepath: Path to check for conflicts
            agent_id: ID of the agent requesting the lock

        Returns:
            List of LockConflict objects for any conflicts found
        """
        conflicts = []

        # Get all existing locks
        all_locks = self.list_all_locks()

        for lock in all_locks:
            # Skip our own locks
            if lock.agent_id == agent_id:
                continue

            # Check if the lock's filepath is a pattern that matches our filepath
            # or if our filepath is a pattern that matches the lock's filepath
            if fnmatch(filepath, lock.filepath) or fnmatch(lock.filepath, filepath):
                conflicts.append(
                    LockConflict(
                        filepath=lock.filepath,
                        current_holder=lock.agent_id,
                        locked_at=datetime.fromtimestamp(lock.locked_at, tz=timezone.utc),
                        reason=lock.reason,
                    )
                )

        return conflicts

    def acquire_lock(
        self,
        filepath: str,
        agent_id: str,
        reason: str = "",
        timeout: Optional[int] = None,
    ) -> tuple[bool, Optional[LockConflict]]:
        """Acquire a lock on a file.

        Args:
            filepath: Path to the file to lock (can be a glob pattern)
            agent_id: Unique identifier of the agent acquiring the lock
            reason: Human-readable explanation for the lock
            timeout: Timeout in seconds for considering locks stale (None = use config)

        Returns:
            Tuple of (success, conflict):
                - (True, None) if lock acquired successfully
                - (False, LockConflict) if lock held by another agent

        Raises:
            ValidationError: If inputs are invalid
        """
        # Validate inputs
        agent_id = validate_agent_id(agent_id)
        # Use config default if timeout not specified
        if timeout is None:
            timeout = get_config().locking.stale_timeout
        timeout = validate_timeout(timeout)
        # Normalize filepath for cross-platform compatibility
        filepath = str(normalize_path(filepath))

        lock_path = self._get_lock_path(filepath)

        # Check for existing lock
        existing_lock = self._read_lock(lock_path)

        # Handle corrupted lock files
        if lock_path.exists() and existing_lock is None:
            # File exists but couldn't be read - it's corrupted, remove it
            try:
                lock_path.unlink()
            except OSError:
                pass  # Ignore errors removing corrupted file

        if existing_lock:
            # Check if it's our own lock
            if existing_lock.agent_id == agent_id:
                # Refresh the lock timestamp with proper locking to prevent TOCTOU
                with self._lock:
                    # Re-read to ensure no one else modified it
                    existing_lock = self._read_lock(lock_path)
                    if existing_lock and existing_lock.agent_id == agent_id:
                        # Refresh the lock timestamp
                        existing_lock.locked_at = time.time()
                        existing_lock.reason = reason

                        # Write to temp file first, then atomic rename
                        # This eliminates the race window between unlink() and write
                        temp_lock_path = lock_path.with_suffix('.lock.tmp')
                        try:
                            # Write updated lock to temp file
                            with temp_lock_path.open('w') as f:
                                json.dump(existing_lock.to_dict(), f, indent=2)

                            # Atomic rename (os.replace is atomic on POSIX and Windows)
                            os.replace(str(temp_lock_path), str(lock_path))
                        except Exception:
                            # Clean up temp file on failure
                            if temp_lock_path.exists():
                                try:
                                    temp_lock_path.unlink()
                                except OSError:
                                    pass
                            raise
                        return True, None
                    else:
                        # Someone else acquired or deleted the lock between our checks
                        existing_lock_new = self._read_lock(lock_path)
                        if existing_lock_new and existing_lock_new.agent_id != agent_id:
                            conflict = LockConflict(
                                filepath=existing_lock_new.filepath,
                                current_holder=existing_lock_new.agent_id,
                                locked_at=datetime.fromtimestamp(
                                    existing_lock_new.locked_at, tz=timezone.utc
                                ),
                                reason=existing_lock_new.reason,
                            )
                            return False, conflict
                        # If lock was deleted, treat as if it didn't exist and continue
                        # to re-acquire it below
                        if existing_lock_new is None:
                            existing_lock = None

            # Check if the lock is stale (only if it still exists)
            if existing_lock and existing_lock.is_stale(timeout):
                # Auto-release stale lock
                try:
                    lock_path.unlink()
                except FileNotFoundError:
                    # Lock was already deleted by another process
                    pass
            elif existing_lock:
                # Active lock held by another agent
                conflict = LockConflict(
                    filepath=existing_lock.filepath,
                    current_holder=existing_lock.agent_id,
                    locked_at=datetime.fromtimestamp(
                        existing_lock.locked_at, tz=timezone.utc
                    ),
                    reason=existing_lock.reason,
                )
                return False, conflict

        # Check for glob pattern conflicts
        glob_conflicts = self._check_glob_conflicts(filepath, agent_id)
        if glob_conflicts:
            return False, glob_conflicts[0]  # Return first conflict

        # Create new lock
        new_lock = FileLock(
            agent_id=agent_id,
            filepath=filepath,
            locked_at=time.time(),
            reason=reason,
        )

        success = self._write_lock(lock_path, new_lock)
        if not success:
            # Race condition: another agent acquired the lock between our checks
            existing_lock = self._read_lock(lock_path)
            if existing_lock and existing_lock.agent_id != agent_id:
                conflict = LockConflict(
                    filepath=existing_lock.filepath,
                    current_holder=existing_lock.agent_id,
                    locked_at=datetime.fromtimestamp(
                        existing_lock.locked_at, tz=timezone.utc
                    ),
                    reason=existing_lock.reason,
                )
                return False, conflict

        return success, None

    def release_lock(self, filepath: str, agent_id: str) -> bool:
        """Release a lock on a file.

        Args:
            filepath: Path to the file to unlock
            agent_id: Unique identifier of the agent releasing the lock

        Returns:
            True if lock was released successfully, False otherwise
            (False may indicate lock doesn't exist or is owned by another agent)
        """
        lock_path = self._get_lock_path(filepath)

        # Check if lock exists
        existing_lock = self._read_lock(lock_path)
        if not existing_lock:
            # Lock doesn't exist - consider this a successful release
            return True

        # Verify ownership
        if existing_lock.agent_id != agent_id:
            # Lock is owned by another agent
            return False

        # Remove lock file
        try:
            lock_path.unlink()
            return True
        except FileNotFoundError:
            # Lock was already deleted - consider this successful
            return True
        except OSError:
            return False

    def who_has_lock(self, filepath: str) -> Optional[FileLock]:
        """Check who currently holds a lock on a file.

        Args:
            filepath: Path to the file to check

        Returns:
            FileLock object if the file is locked, None otherwise
            (stale locks are automatically cleaned up and return None)
        """
        lock_path = self._get_lock_path(filepath)
        lock = self._read_lock(lock_path)

        if lock and lock.is_stale():
            # Clean up stale lock
            try:
                lock_path.unlink()
            except FileNotFoundError:
                # Lock was already deleted by another process
                pass
            except OSError:
                pass
            return None

        return lock

    def list_all_locks(self, include_stale: bool = False) -> list[FileLock]:
        """List all active locks.

        Args:
            include_stale: If True, include stale locks in the results

        Returns:
            List of FileLock objects for all active (and optionally stale) locks
        """
        locks = []

        for lock_file in self.lock_dir.glob("*.lock"):
            lock = self._read_lock(lock_file)
            if lock:
                if include_stale or not lock.is_stale():
                    locks.append(lock)
                elif lock.is_stale():
                    # Clean up stale lock
                    try:
                        lock_file.unlink()
                    except FileNotFoundError:
                        # Lock was already deleted by another process
                        pass
                    except OSError:
                        pass

        return locks

    def cleanup_stale_locks(self, timeout: Optional[int] = None) -> int:
        """Clean up all stale locks.

        Args:
            timeout: Number of seconds after which a lock is considered stale
                    (None = use configured stale_timeout)

        Returns:
            Number of locks cleaned up
        """
        if timeout is None:
            timeout = get_config().locking.stale_timeout

        count = 0

        for lock_file in self.lock_dir.glob("*.lock"):
            lock = self._read_lock(lock_file)
            if lock and lock.is_stale(timeout):
                try:
                    lock_file.unlink()
                    count += 1
                except FileNotFoundError:
                    # Lock was already deleted by another process
                    pass
                except OSError:
                    pass

        return count

    def cleanup_agent_locks(self, agent_id: str) -> int:
        """Clean up all locks held by a specific agent.

        Useful when an agent terminates or is removed.

        Args:
            agent_id: ID of the agent whose locks should be released

        Returns:
            Number of locks cleaned up
        """
        count = 0

        for lock_file in self.lock_dir.glob("*.lock"):
            lock = self._read_lock(lock_file)
            if lock and lock.agent_id == agent_id:
                try:
                    lock_file.unlink()
                    count += 1
                except FileNotFoundError:
                    # Lock was already deleted by another process
                    pass
                except OSError:
                    pass

        return count
