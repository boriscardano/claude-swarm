"""Cross-platform file locking for safe concurrent file access.

This module provides a portable file locking mechanism that works on both Unix
(Linux, macOS) and Windows platforms. It uses fcntl on Unix and Win32 API on Windows.

The locking is implemented as a context manager for safe, automatic lock release:

Example:
    with FileLock('/path/to/file.json', timeout=5.0):
        # Perform file operations safely
        with open('/path/to/file.json', 'r') as f:
            data = json.load(f)

Author: Python Expert
"""

import os
import platform
import stat
import time
from contextlib import contextmanager
from pathlib import Path

from .logging_config import get_logger

logger = get_logger(__name__)

# Lock retry interval for consistent behavior across platforms
LOCK_RETRY_INTERVAL = 0.05  # 50ms between lock attempts

# Platform-specific imports
_system = platform.system()
if _system in ("Linux", "Darwin"):  # Unix-like systems
    import fcntl

    _LOCK_MODULE = "fcntl"
elif _system == "Windows":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _LOCK_MODULE = "win32"

    # Win32 API constants for LockFileEx
    LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
    LOCKFILE_EXCLUSIVE_LOCK = 0x00000002

    # Win32 API function signatures
    kernel32 = ctypes.windll.kernel32

    # LockFileEx signature
    kernel32.LockFileEx.argtypes = [
        wintypes.HANDLE,  # hFile
        wintypes.DWORD,  # dwFlags
        wintypes.DWORD,  # dwReserved
        wintypes.DWORD,  # nNumberOfBytesToLockLow
        wintypes.DWORD,  # nNumberOfBytesToLockHigh
        ctypes.POINTER(wintypes.OVERLAPPED),  # lpOverlapped
    ]
    kernel32.LockFileEx.restype = wintypes.BOOL

    # UnlockFileEx signature
    kernel32.UnlockFileEx.argtypes = [
        wintypes.HANDLE,  # hFile
        wintypes.DWORD,  # dwReserved
        wintypes.DWORD,  # nNumberOfBytesToUnlockLow
        wintypes.DWORD,  # nNumberOfBytesToUnlockHigh
        ctypes.POINTER(wintypes.OVERLAPPED),  # lpOverlapped
    ]
    kernel32.UnlockFileEx.restype = wintypes.BOOL

    # GetLastError signature
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD

    # BY_HANDLE_FILE_INFORMATION structure for GetFileInformationByHandle
    class BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("dwFileAttributes", wintypes.DWORD),
            ("ftCreationTime", wintypes.FILETIME),
            ("ftLastAccessTime", wintypes.FILETIME),
            ("ftLastWriteTime", wintypes.FILETIME),
            ("dwVolumeSerialNumber", wintypes.DWORD),
            ("nFileSizeHigh", wintypes.DWORD),
            ("nFileSizeLow", wintypes.DWORD),
            ("nNumberOfLinks", wintypes.DWORD),
            ("nFileIndexHigh", wintypes.DWORD),
            ("nFileIndexLow", wintypes.DWORD),
        ]

    # GetFileInformationByHandle signature
    kernel32.GetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(BY_HANDLE_FILE_INFORMATION),
    ]
    kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
else:
    _LOCK_MODULE = None
    logger.warning(f"File locking not supported on platform: {_system}")


class FileLockError(Exception):
    """Base exception for file locking errors."""

    pass


class FileLockTimeout(FileLockError):
    """Raised when file lock acquisition times out."""

    pass


class FileLockUnsupported(FileLockError):
    """Raised when file locking is not supported on this platform."""

    pass


class FileLock:
    """Cross-platform file locking context manager.

    Provides exclusive (write) or shared (read) locks on files using
    platform-specific locking mechanisms.

    Features:
    - Automatic lock release on context exit
    - Configurable timeout for lock acquisition
    - Cross-platform support (Unix and Windows with proper shared/exclusive locks)
    - Handles stale locks automatically
    - Lock integrity checking (detects file deletion/replacement)
    - Reentrancy protection to prevent deadlocks

    Args:
        file_path: Path to file to lock (will be created if doesn't exist)
        timeout: Maximum seconds to wait for lock (None = block forever)
        shared: If True, acquire shared (read) lock; if False, exclusive (write) lock

    Raises:
        FileLockTimeout: If lock cannot be acquired within timeout
        FileLockUnsupported: If platform doesn't support file locking
        FileLockError: If lock is already acquired or file integrity check fails

    Example:
        # Exclusive lock for writing
        with FileLock('data.json', timeout=5.0):
            with open('data.json', 'w') as f:
                json.dump(data, f)

        # Shared lock for reading
        with FileLock('data.json', timeout=5.0, shared=True):
            with open('data.json', 'r') as f:
                data = json.load(f)
    """

    def __init__(self, file_path: Path | str, timeout: float | None = 10.0, shared: bool = False):
        """Initialize file lock.

        Args:
            file_path: Path to file to lock
            timeout: Lock acquisition timeout in seconds (None = wait forever)
            shared: If True, use shared lock (read); if False, exclusive lock (write)
        """
        if _LOCK_MODULE is None:
            raise FileLockUnsupported(f"File locking not supported on platform: {_system}")

        self.file_path = Path(file_path)
        self.timeout = timeout
        self.shared = shared
        self._lock_file = None
        self._lock_fd = None
        self._file_inode = None  # Store file inode/ID for integrity checking
        self._is_locked = False  # Track lock state for reentrancy protection

    def __enter__(self):
        """Acquire the file lock.

        Raises:
            FileLockError: If lock is already acquired (reentrancy protection)
        """
        if self._is_locked:
            raise FileLockError(
                f"Lock on {self.file_path} is already acquired. "
                "Reentrancy is not supported to prevent deadlocks."
            )
        self._acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the file lock."""
        self._release()
        return False

    def _acquire(self):
        """Acquire the file lock with timeout.

        Raises:
            FileLockTimeout: If lock cannot be acquired within timeout
            FileLockError: If file integrity check fails or permissions denied
            PermissionError: If directory/file creation fails due to permissions
        """
        # Create lock file directory if needed with proper error handling
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise FileLockError(
                f"Permission denied creating directory {self.file_path.parent}. "
                "Ensure the directory is writable or exists with proper permissions."
            ) from e

        # Create lock file if it doesn't exist with secure permissions
        if not self.file_path.exists():
            try:
                self.file_path.touch()
                # Set permissions to 0o600 (rw-------) for user read/write only
                # This prevents unauthorized access to lock files
                os.chmod(self.file_path, stat.S_IRUSR | stat.S_IWUSR)
            except PermissionError as e:
                raise FileLockError(
                    f"Permission denied creating lock file {self.file_path}. "
                    "Ensure the directory is writable."
                ) from e

        start_time = time.time()

        while True:
            try:
                if _LOCK_MODULE == "fcntl":
                    self._acquire_fcntl()
                elif _LOCK_MODULE == "win32":
                    self._acquire_win32()

                # Verify file integrity after acquiring lock
                self._verify_lock_integrity()

                # Mark as locked
                self._is_locked = True

                logger.debug(
                    f"Acquired {'shared' if self.shared else 'exclusive'} lock on {self.file_path}"
                )
                return

            except OSError as e:
                # Lock is held by another process
                if self.timeout is None:
                    # Wait indefinitely
                    time.sleep(LOCK_RETRY_INTERVAL)
                    continue

                elapsed = time.time() - start_time
                if elapsed >= self.timeout:
                    raise FileLockTimeout(
                        f"Could not acquire lock on {self.file_path} within {self.timeout}s"
                    ) from e

                # Wait a bit and retry
                time.sleep(LOCK_RETRY_INTERVAL)

    def _acquire_fcntl(self):
        """Acquire lock using fcntl (Unix).

        Raises:
            IOError: If lock cannot be acquired (file handle closed on error)
        """
        # Open file in binary mode for cross-platform compatibility
        mode = "rb" if self.shared else "r+b"
        lock_file = None

        try:
            lock_file = open(self.file_path, mode)
            lock_fd = lock_file.fileno()

            # Store inode for integrity checking
            file_stat = os.fstat(lock_fd)
            self._file_inode = (file_stat.st_dev, file_stat.st_ino)

            # Select lock type
            lock_type = fcntl.LOCK_SH if self.shared else fcntl.LOCK_EX

            # Try to acquire lock (non-blocking)
            fcntl.flock(lock_fd, lock_type | fcntl.LOCK_NB)

            # Lock acquired successfully, store file handle
            self._lock_file = lock_file
            self._lock_fd = lock_fd

        except Exception:
            # Close file handle on any error to prevent leak
            if lock_file is not None:
                try:
                    lock_file.close()
                except Exception:
                    pass
            raise

    def _acquire_win32(self):
        """Acquire lock using Win32 API (Windows).

        Implements proper shared/exclusive locking using LockFileEx API.

        Raises:
            IOError: If lock cannot be acquired (file handle closed on error)
        """
        # Open file in binary mode for cross-platform compatibility
        mode = "rb" if self.shared else "r+b"
        lock_file = None

        try:
            lock_file = open(self.file_path, mode)
            lock_fd = lock_file.fileno()

            # Get Windows file handle from file descriptor
            file_handle = msvcrt.get_osfhandle(lock_fd)
            if file_handle == -1:
                raise FileLockError("Failed to get OS file handle")

            # Get proper Windows file identity using GetFileInformationByHandle
            file_info = BY_HANDLE_FILE_INFORMATION()
            result = kernel32.GetFileInformationByHandle(file_handle, ctypes.byref(file_info))
            if not result:
                error_code = kernel32.GetLastError()
                raise FileLockError(
                    f"Failed to get file information for {self.file_path}. "
                    f"Win32 error code: {error_code}"
                )

            # Store file identity using volume serial number and file index
            self._file_inode = (
                file_info.dwVolumeSerialNumber,
                file_info.nFileIndexHigh,
                file_info.nFileIndexLow,
            )

            # Set lock flags
            flags = LOCKFILE_FAIL_IMMEDIATELY
            if not self.shared:
                flags |= LOCKFILE_EXCLUSIVE_LOCK

            # Create OVERLAPPED structure for LockFileEx
            overlapped = wintypes.OVERLAPPED()
            overlapped.Offset = 0
            overlapped.OffsetHigh = 0

            # Try to acquire lock using LockFileEx
            result = kernel32.LockFileEx(
                file_handle,
                flags,
                0,  # dwReserved
                1,  # nNumberOfBytesToLockLow (lock 1 byte)
                0,  # nNumberOfBytesToLockHigh
                ctypes.byref(overlapped),
            )

            if not result:
                error_code = kernel32.GetLastError()
                raise OSError(
                    f"Failed to acquire lock on {self.file_path}. "
                    f"Win32 error code: {error_code}"
                )

            # Lock acquired successfully, store file handle
            self._lock_file = lock_file
            self._lock_fd = lock_fd

        except Exception:
            # Close file handle on any error to prevent leak
            if lock_file is not None:
                try:
                    lock_file.close()
                except Exception:
                    pass
            raise

    def _verify_lock_integrity(self):
        """Verify that lock file hasn't been deleted or replaced.

        Raises:
            FileLockError: If file was deleted or replaced during lock acquisition
        """
        if self._lock_fd is None or self._file_inode is None:
            return

        try:
            # Check if file still exists at path
            if not self.file_path.exists():
                raise FileLockError(
                    f"Lock file {self.file_path} was deleted during lock acquisition"
                )

            # Get current file identity based on platform
            if _LOCK_MODULE == "win32":
                # Use Windows file identity via GetFileInformationByHandle
                file_handle = msvcrt.get_osfhandle(self._lock_fd)
                if file_handle == -1:
                    raise FileLockError("Failed to get OS file handle for integrity check")

                file_info = BY_HANDLE_FILE_INFORMATION()
                result = kernel32.GetFileInformationByHandle(file_handle, ctypes.byref(file_info))
                if not result:
                    error_code = kernel32.GetLastError()
                    raise FileLockError(
                        f"Failed to get file information for integrity check. "
                        f"Win32 error code: {error_code}"
                    )

                current_inode = (
                    file_info.dwVolumeSerialNumber,
                    file_info.nFileIndexHigh,
                    file_info.nFileIndexLow,
                )
            else:
                # Use Unix inode for file identity
                path_stat = os.stat(self.file_path)
                current_inode = (path_stat.st_dev, path_stat.st_ino)

            # Compare with stored file identity
            if current_inode != self._file_inode:
                raise FileLockError(
                    f"Lock file {self.file_path} was replaced during lock acquisition. "
                    f"Expected identity {self._file_inode}, got {current_inode}"
                )

        except FileLockError:
            # Close file handle and re-raise
            if self._lock_file:
                try:
                    self._lock_file.close()
                except Exception:
                    pass
                self._lock_file = None
                self._lock_fd = None
            raise

    def _release(self):
        """Release the file lock."""
        if self._lock_file is None:
            return

        try:
            if _LOCK_MODULE == "fcntl":
                self._release_fcntl()
            elif _LOCK_MODULE == "win32":
                self._release_win32()

            logger.debug(f"Released lock on {self.file_path}")

        except Exception as e:
            logger.warning(f"Error releasing lock on {self.file_path}: {e}")

        finally:
            # Always close the file and reset state
            if self._lock_file:
                try:
                    self._lock_file.close()
                except Exception:
                    pass
                self._lock_file = None
                self._lock_fd = None
                self._file_inode = None
                self._is_locked = False

    def _release_fcntl(self):
        """Release lock using fcntl (Unix)."""
        if self._lock_fd is not None:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)

    def _release_win32(self):
        """Release lock using Win32 API (Windows)."""
        if self._lock_fd is not None:
            file_handle = msvcrt.get_osfhandle(self._lock_fd)
            if file_handle == -1:
                logger.warning(f"Failed to get OS file handle for {self.file_path}")
                return

            # Create OVERLAPPED structure for UnlockFileEx
            overlapped = wintypes.OVERLAPPED()
            overlapped.Offset = 0
            overlapped.OffsetHigh = 0

            # Unlock using UnlockFileEx
            result = kernel32.UnlockFileEx(
                file_handle,
                0,  # dwReserved
                1,  # nNumberOfBytesToUnlockLow
                0,  # nNumberOfBytesToUnlockHigh
                ctypes.byref(overlapped),
            )

            if not result:
                error_code = kernel32.GetLastError()
                logger.warning(
                    f"Failed to release lock on {self.file_path}. "
                    f"Win32 error code: {error_code}"
                )


@contextmanager
def file_lock(file_path: Path | str, timeout: float | None = 10.0, shared: bool = False):
    """Context manager for file locking (convenience wrapper).

    Args:
        file_path: Path to file to lock
        timeout: Lock acquisition timeout in seconds
        shared: If True, use shared lock (read); if False, exclusive lock (write)

    Yields:
        FileLock instance

    Example:
        with file_lock('data.json', timeout=5.0):
            # File is locked here
            with open('data.json', 'r') as f:
                data = json.load(f)
    """
    lock = FileLock(file_path, timeout=timeout, shared=shared)
    try:
        lock._acquire()
        yield lock
    finally:
        lock._release()
