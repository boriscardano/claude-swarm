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
from .logging_config import get_logger
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
# DEPRECATED: This constant is kept for backward compatibility only.
# New code should use configuration instead: get_config().locking.stale_timeout
# This constant will be removed in version 1.0.0
# Migration: Replace `STALE_LOCK_TIMEOUT` with `get_config().locking.stale_timeout`
STALE_LOCK_TIMEOUT = 300

# Configure logging
logger = get_logger(__name__)


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

        This method implements comprehensive path validation to prevent:
        - Path traversal attacks using .. or /../
        - Symlink attacks that escape the project root
        - Null byte injection
        - URL-encoded path traversal attempts
        - Absolute paths outside project root

        Args:
            filepath: Path to validate

        Raises:
            ValueError: If filepath is outside the project root or contains malicious patterns
        """
        # 1. Check for null bytes (common injection technique)
        if '\x00' in filepath:
            raise ValueError(
                f"Path contains null bytes: '{filepath}'"
            )

        # 2. Check for URL-encoded path traversal attempts
        import urllib.parse
        decoded_path = urllib.parse.unquote(filepath)
        if decoded_path != filepath and ('..' in decoded_path or '\x00' in decoded_path):
            raise ValueError(
                f"URL-encoded path traversal detected: '{filepath}'"
            )

        # 3. Resolve the project root once (for performance and consistency)
        try:
            project_root_resolved = self.project_root.resolve(strict=False)
        except (OSError, RuntimeError) as e:
            raise ValueError(f"Cannot resolve project root: {e}")

        # 4. Handle the filepath based on whether it's absolute or relative
        try:
            path_obj = Path(filepath)

            # Determine the full path to validate
            if path_obj.is_absolute():
                # Absolute path: resolve it directly
                resolved_path = path_obj.resolve(strict=False)
            else:
                # Relative path: resolve it relative to project root
                resolved_path = (self.project_root / path_obj).resolve(strict=False)

            # 5. Verify the resolved path is within project root using relative_to()
            # This is the most secure method as it handles symlinks, .., and edge cases
            try:
                resolved_path.relative_to(project_root_resolved)
            except ValueError:
                raise ValueError(
                    f"Path traversal detected: '{filepath}' resolves to '{resolved_path}' "
                    f"which is outside project root '{project_root_resolved}'"
                )

        except (OSError, RuntimeError) as e:
            # If path resolution fails (e.g., broken symlinks, permission errors),
            # FAIL CLOSED for security. Do not attempt string-based validation.
            # Rationale: String validation can be bypassed with Unicode homoglyphs,
            # null bytes, and other encoding tricks. The safe approach is to reject
            # any path that cannot be properly resolved and validated.
            raise ValueError(
                f"Cannot resolve path '{filepath}': {e}. "
                f"Path validation requires resolvable paths for security."
            )

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
                # ========================================================================
                # LOCK REFRESH WITH TOCTOU PREVENTION
                # ========================================================================
                # This implements a thread-safe lock refresh pattern using atomic writes
                # to prevent Time-of-Check-Time-of-Use (TOCTOU) race conditions.
                #
                # WHY THIS PATTERN IS NECESSARY:
                # Without atomic operations, there's a dangerous race window between:
                # 1. Reading the lock file to verify ownership
                # 2. Deleting the old lock file
                # 3. Writing the new lock file
                #
                # During this window, another process could:
                # - Steal the lock if the file is deleted first
                # - Corrupt the lock state if writes overlap
                # - Create an inconsistent lock state
                #
                # SOLUTION - THREE LAYERS OF PROTECTION:
                #
                # Layer 1: Thread-level locking (self._lock)
                # Prevents race conditions between threads in the same process.
                # This is fast but only protects within one Python process.
                #
                # Layer 2: Double-check pattern (re-read after acquiring lock)
                # After acquiring thread lock, we re-read the file to catch any changes
                # made by other processes while we were waiting for the thread lock.
                # This prevents acting on stale data.
                #
                # Layer 3: Atomic write via temp file + rename
                # Instead of delete-then-write (which has a race window), we:
                # 1. Write updated lock to .lock.tmp file
                # 2. Use os.replace() to atomically rename temp file over original
                #
                # os.replace() is atomic on both POSIX and Windows, meaning:
                # - The operation either fully succeeds or fully fails
                # - No other process can observe a half-completed state
                # - No window exists where the lock file is missing
                # - The file is never empty or partially written
                #
                # This guarantees that other processes always see either:
                # - The old valid lock, OR
                # - The new valid lock
                # Never an inconsistent or missing state.
                #
                # FAILURE HANDLING:
                # If any operation fails, we clean up the temp file to avoid leaving
                # stale .lock.tmp files that could cause confusion.
                # ========================================================================
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
                            logger.debug(f"Lock refreshed on '{filepath}' by {agent_id}")
                        except Exception as e:
                            # Clean up temp file on failure
                            if temp_lock_path.exists():
                                try:
                                    temp_lock_path.unlink()
                                except OSError:
                                    pass
                            logger.error(f"Failed to refresh lock on '{filepath}' for {agent_id}: {e}")
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
                logger.info(
                    f"Removing stale lock on '{filepath}' held by {existing_lock.agent_id} "
                    f"(age: {existing_lock.age_seconds():.1f}s)"
                )
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
        if success:
            logger.info(f"Lock acquired on '{filepath}' by {agent_id} (reason: {reason})")
        else:
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
            logger.warning(
                f"Cannot release lock on '{filepath}': {agent_id} does not own it "
                f"(held by {existing_lock.agent_id})"
            )
            return False

        # Remove lock file
        try:
            lock_path.unlink()
            logger.info(f"Lock released on '{filepath}' by {agent_id}")
            return True
        except FileNotFoundError:
            # Lock was already deleted - consider this successful
            logger.debug(f"Lock on '{filepath}' already released (file not found)")
            return True
        except OSError as e:
            logger.error(f"Failed to release lock on '{filepath}' for {agent_id}: {e}")
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
                    logger.debug(
                        f"Cleaned up stale lock on '{lock.filepath}' held by {lock.agent_id} "
                        f"(age: {lock.age_seconds():.1f}s)"
                    )
                except FileNotFoundError:
                    # Lock was already deleted by another process
                    pass
                except OSError as e:
                    logger.warning(f"Failed to cleanup stale lock {lock_file}: {e}")

        if count > 0:
            logger.info(f"Cleaned up {count} stale lock(s)")

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
                    logger.debug(f"Cleaned up lock on '{lock.filepath}' held by {agent_id}")
                except FileNotFoundError:
                    # Lock was already deleted by another process
                    pass
                except OSError as e:
                    logger.warning(f"Failed to cleanup lock {lock_file} for {agent_id}: {e}")

        if count > 0:
            logger.info(f"Cleaned up {count} lock(s) for agent {agent_id}")

        return count
