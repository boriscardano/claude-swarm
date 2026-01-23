"""
Comprehensive unit tests for the utils module.

Tests cover:
- atomic_write() with various scenarios
- Concurrent write operations (threading)
- Error handling (disk full, permissions, etc.)
- load_json() and save_json()
- format_timestamp() and parse_timestamp()
- Edge cases and error conditions

Author: Agent-TestCoverage
"""

import json
import threading
import time
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest

from claudeswarm.utils import (
    atomic_write,
    format_timestamp,
    get_or_create_secret,
    load_json,
    parse_timestamp,
    save_json,
)


class TestAtomicWrite:
    """Tests for atomic_write function."""

    def test_atomic_write_basic(self, tmp_path):
        """Test basic atomic write operation."""
        filepath = tmp_path / "test.txt"
        content = "Hello, World!"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_atomic_write_creates_parent_dirs(self, tmp_path):
        """Test that atomic_write creates parent directories."""
        filepath = tmp_path / "subdir" / "nested" / "test.txt"
        content = "Test content"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_atomic_write_overwrites_existing(self, tmp_path):
        """Test that atomic_write overwrites existing files."""
        filepath = tmp_path / "test.txt"
        filepath.write_text("Old content")

        atomic_write(filepath, "New content")

        assert filepath.read_text() == "New content"

    def test_atomic_write_multiline(self, tmp_path):
        """Test atomic write with multiline content."""
        filepath = tmp_path / "test.txt"
        content = "Line 1\nLine 2\nLine 3\n"

        atomic_write(filepath, content)

        assert filepath.read_text() == content

    def test_atomic_write_unicode(self, tmp_path):
        """Test atomic write with unicode content."""
        filepath = tmp_path / "test.txt"
        content = "Hello 世界 🌍"

        atomic_write(filepath, content)

        assert filepath.read_text() == content

    def test_atomic_write_empty_string(self, tmp_path):
        """Test atomic write with empty string."""
        filepath = tmp_path / "test.txt"

        atomic_write(filepath, "")

        assert filepath.exists()
        assert filepath.read_text() == ""

    def test_atomic_write_large_content(self, tmp_path):
        """Test atomic write with large content."""
        filepath = tmp_path / "test.txt"
        content = "x" * 1_000_000  # 1MB of data

        atomic_write(filepath, content)

        assert filepath.read_text() == content

    def test_atomic_write_concurrent_writes(self, tmp_path):
        """Test concurrent writes to different files."""
        num_threads = 10
        threads = []

        def write_file(index):
            filepath = tmp_path / f"file_{index}.txt"
            content = f"Content {index}"
            atomic_write(filepath, content)

        for i in range(num_threads):
            thread = threading.Thread(target=write_file, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all files were written correctly
        for i in range(num_threads):
            filepath = tmp_path / f"file_{i}.txt"
            assert filepath.exists()
            assert filepath.read_text() == f"Content {i}"

    def test_atomic_write_same_file_sequential(self, tmp_path):
        """Test sequential writes to the same file."""
        filepath = tmp_path / "test.txt"

        for i in range(100):
            atomic_write(filepath, f"Version {i}")

        assert filepath.read_text() == "Version 99"

    def test_atomic_write_race_condition(self, tmp_path):
        """Test that atomic_write handles race conditions properly."""
        filepath = tmp_path / "test.txt"
        num_threads = 20
        threads = []
        results = []

        def write_file(value):
            atomic_write(filepath, str(value))
            results.append(value)

        for i in range(num_threads):
            thread = threading.Thread(target=write_file, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # File should contain one of the written values
        final_content = filepath.read_text()
        assert final_content.isdigit()
        assert int(final_content) in range(num_threads)

    def test_atomic_write_tmp_file_cleanup_on_error(self, tmp_path):
        """Test that temp files are cleaned up on error."""
        filepath = tmp_path / "test.txt"

        with patch("os.fdopen", side_effect=OSError("Mock error")):
            with pytest.raises(IOError):
                atomic_write(filepath, "content")

        # Verify no temp files left behind
        temp_files = list(tmp_path.glob("tmp*"))
        assert len(temp_files) == 0

    def test_atomic_write_permission_error(self, tmp_path):
        """Test atomic write with permission error."""
        filepath = tmp_path / "test.txt"
        filepath.write_text("initial")
        filepath.chmod(0o444)  # Read-only

        # Make parent directory read-only too
        tmp_path.chmod(0o555)

        try:
            with pytest.raises((OSError, PermissionError)):
                atomic_write(filepath, "new content")
        finally:
            # Restore permissions for cleanup
            tmp_path.chmod(0o755)
            filepath.chmod(0o644)

    def test_atomic_write_disk_full_simulation(self, tmp_path):
        """Test atomic write when disk is full (simulated)."""
        filepath = tmp_path / "test.txt"

        with patch("os.fdopen") as mock_fdopen:
            mock_file = Mock()
            mock_file.write.side_effect = OSError("No space left on device")
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_fdopen.return_value = mock_file

            with pytest.raises(OSError) as exc_info:
                atomic_write(filepath, "content")

            assert "No space left on device" in str(exc_info.value)

    def test_atomic_write_preserves_atomicity(self, tmp_path):
        """Test that writes are truly atomic (no partial writes visible)."""
        filepath = tmp_path / "test.txt"
        _ = "x" * 100000
        observed_states = []

        def writer():
            for i in range(10):
                atomic_write(filepath, f"{i}" * 100000)
                time.sleep(0.001)

        def reader():
            for _ in range(50):
                if filepath.exists():
                    content = filepath.read_text()
                    observed_states.append(len(content))
                time.sleep(0.001)

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        time.sleep(0.0001)  # Let writer start first
        reader_thread.start()

        writer_thread.join()
        reader_thread.join()

        # All observed states should be complete writes (100000 bytes)
        # No partial writes should be visible
        for state in observed_states:
            assert state == 100000 or state == 0, f"Partial write detected: {state} bytes"

    def test_atomic_write_special_characters(self, tmp_path):
        """Test atomic write with special characters in content."""
        filepath = tmp_path / "test.txt"
        content = "Special: \n\t\0 chars"

        atomic_write(filepath, content)

        assert filepath.read_text() == content

    def test_atomic_write_path_object(self, tmp_path):
        """Test atomic write with Path object."""
        filepath = tmp_path / "test.txt"
        content = "Path object test"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert filepath.read_text() == content

    def test_atomic_write_exception_cleanup_failure(self, tmp_path):
        """Test atomic write when cleanup also fails."""
        filepath = tmp_path / "test.txt"

        with patch("os.fdopen") as mock_fdopen:
            mock_file = Mock()
            mock_file.write.side_effect = RuntimeError("Write error")
            mock_file.__enter__ = Mock(return_value=mock_file)
            mock_file.__exit__ = Mock(return_value=False)
            mock_fdopen.return_value = mock_file

            with patch("os.unlink", side_effect=OSError("Cleanup failed")):
                with pytest.raises(RuntimeError) as exc_info:
                    atomic_write(filepath, "content")

                assert "Write error" in str(exc_info.value)

    def test_atomic_write_handles_temp_file_cleanup_on_any_error(self, tmp_path):
        """Test that temp file cleanup is attempted even if unlink fails."""
        filepath = tmp_path / "test.txt"

        with patch("tempfile.mkstemp") as mock_mkstemp:
            mock_fd = 999
            mock_tmp_path = str(tmp_path / "tmpfile")
            mock_mkstemp.return_value = (mock_fd, mock_tmp_path)

            with patch("os.fdopen", side_effect=OSError("Mock IO error")):
                with patch("os.unlink") as mock_unlink:
                    mock_unlink.side_effect = OSError("Unlink failed")

                    with pytest.raises(IOError):
                        atomic_write(filepath, "content")

                    # unlink should have been called (even though it failed)
                    mock_unlink.assert_called_once_with(mock_tmp_path)


class TestLoadJson:
    """Tests for load_json function."""

    def test_load_json_basic(self, tmp_path):
        """Test basic JSON loading."""
        filepath = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        filepath.write_text(json.dumps(data))

        result = load_json(filepath)

        assert result == data

    def test_load_json_complex_structure(self, tmp_path):
        """Test loading complex JSON structure."""
        filepath = tmp_path / "test.json"
        data = {
            "agents": [
                {"id": "agent-1", "status": "active"},
                {"id": "agent-2", "status": "idle"},
            ],
            "metadata": {"version": "1.0", "timestamp": "2021-01-01"},
        }
        filepath.write_text(json.dumps(data))

        result = load_json(filepath)

        assert result == data
        assert len(result["agents"]) == 2

    def test_load_json_empty_object(self, tmp_path):
        """Test loading empty JSON object."""
        filepath = tmp_path / "test.json"
        filepath.write_text("{}")

        result = load_json(filepath)

        assert result == {}

    def test_load_json_array(self, tmp_path):
        """Test loading JSON array."""
        filepath = tmp_path / "test.json"
        data = [1, 2, 3, 4, 5]
        filepath.write_text(json.dumps(data))

        result = load_json(filepath)

        assert result == data

    def test_load_json_file_not_found(self, tmp_path):
        """Test loading non-existent JSON file."""
        filepath = tmp_path / "nonexistent.json"

        with pytest.raises(FileNotFoundError):
            load_json(filepath)

    def test_load_json_invalid_json(self, tmp_path):
        """Test loading invalid JSON."""
        filepath = tmp_path / "test.json"
        filepath.write_text("not valid json {]")

        with pytest.raises(json.JSONDecodeError):
            load_json(filepath)

    def test_load_json_unicode(self, tmp_path):
        """Test loading JSON with unicode."""
        filepath = tmp_path / "test.json"
        data = {"message": "Hello 世界 🌍"}
        filepath.write_text(json.dumps(data, ensure_ascii=False))

        result = load_json(filepath)

        assert result == data


class TestSaveJson:
    """Tests for save_json function."""

    def test_save_json_basic(self, tmp_path):
        """Test basic JSON saving."""
        filepath = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        save_json(filepath, data)

        assert filepath.exists()
        loaded = json.loads(filepath.read_text())
        assert loaded == data

    def test_save_json_creates_dirs(self, tmp_path):
        """Test that save_json creates parent directories."""
        filepath = tmp_path / "subdir" / "nested" / "test.json"
        data = {"test": "data"}

        save_json(filepath, data)

        assert filepath.exists()
        loaded = json.loads(filepath.read_text())
        assert loaded == data

    def test_save_json_pretty_format(self, tmp_path):
        """Test that JSON is saved with pretty formatting."""
        filepath = tmp_path / "test.json"
        data = {"key1": "value1", "key2": "value2"}

        save_json(filepath, data)

        content = filepath.read_text()
        # Should be indented (pretty-printed)
        assert "  " in content or "\n" in content

    def test_save_json_overwrites(self, tmp_path):
        """Test that save_json overwrites existing files."""
        filepath = tmp_path / "test.json"
        filepath.write_text('{"old": "data"}')

        save_json(filepath, {"new": "data"})

        loaded = json.loads(filepath.read_text())
        assert loaded == {"new": "data"}

    def test_save_json_empty_dict(self, tmp_path):
        """Test saving empty dictionary."""
        filepath = tmp_path / "test.json"

        save_json(filepath, {})

        assert filepath.exists()
        loaded = json.loads(filepath.read_text())
        assert loaded == {}

    def test_save_json_list(self, tmp_path):
        """Test saving list."""
        filepath = tmp_path / "test.json"
        data = [1, 2, 3, 4, 5]

        save_json(filepath, data)

        loaded = json.loads(filepath.read_text())
        assert loaded == data

    def test_save_json_unicode(self, tmp_path):
        """Test saving JSON with unicode."""
        filepath = tmp_path / "test.json"
        data = {"message": "Hello 世界 🌍"}

        save_json(filepath, data)

        loaded = json.loads(filepath.read_text())
        assert loaded == data

    def test_save_json_atomic(self, tmp_path):
        """Test that save_json uses atomic write."""
        filepath = tmp_path / "test.json"

        with patch("claudeswarm.utils.atomic_write") as mock_atomic:
            save_json(filepath, {"test": "data"})
            mock_atomic.assert_called_once()


class TestFormatTimestamp:
    """Tests for format_timestamp function."""

    def test_format_timestamp_basic(self):
        """Test basic timestamp formatting."""
        dt = datetime(2021, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = format_timestamp(dt)

        assert "2021-01-01" in result
        assert "12:00:00" in result

    def test_format_timestamp_with_microseconds(self):
        """Test formatting timestamp with microseconds."""
        dt = datetime(2021, 1, 1, 12, 0, 0, 123456, tzinfo=UTC)
        result = format_timestamp(dt)

        assert isinstance(result, str)
        assert "2021-01-01" in result

    def test_format_timestamp_timezone_aware(self):
        """Test formatting timezone-aware datetime."""
        dt = datetime(2021, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = format_timestamp(dt)

        assert isinstance(result, str)
        # Should be ISO 8601 format
        assert "T" in result or " " in result

    def test_format_timestamp_iso_format(self):
        """Test that format uses ISO 8601 format."""
        dt = datetime(2021, 6, 15, 14, 30, 45, tzinfo=UTC)
        result = format_timestamp(dt)

        # Should be parseable back
        parsed = datetime.fromisoformat(result)
        assert parsed.year == 2021
        assert parsed.month == 6
        assert parsed.day == 15


class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    def test_parse_timestamp_basic(self):
        """Test basic timestamp parsing."""
        ts_str = "2021-01-01T12:00:00+00:00"
        result = parse_timestamp(ts_str)

        assert result.year == 2021
        assert result.month == 1
        assert result.day == 1
        assert result.hour == 12

    def test_parse_timestamp_without_timezone(self):
        """Test parsing timestamp without timezone."""
        ts_str = "2021-01-01T12:00:00"
        result = parse_timestamp(ts_str)

        assert result.year == 2021
        assert result.month == 1

    def test_parse_timestamp_with_microseconds(self):
        """Test parsing timestamp with microseconds."""
        ts_str = "2021-01-01T12:00:00.123456+00:00"
        result = parse_timestamp(ts_str)

        assert result.year == 2021
        assert result.microsecond == 123456

    def test_parse_timestamp_roundtrip(self):
        """Test format/parse roundtrip."""
        original = datetime(2021, 6, 15, 14, 30, 45, 123456, tzinfo=UTC)
        formatted = format_timestamp(original)
        parsed = parse_timestamp(formatted)

        # Should be close (microseconds might differ due to format)
        assert parsed.year == original.year
        assert parsed.month == original.month
        assert parsed.day == original.day
        assert parsed.hour == original.hour
        assert parsed.minute == original.minute
        assert parsed.second == original.second

    def test_parse_timestamp_invalid_format(self):
        """Test parsing invalid timestamp format."""
        with pytest.raises(ValueError):
            parse_timestamp("not a timestamp")

    def test_parse_timestamp_empty_string(self):
        """Test parsing empty string."""
        with pytest.raises(ValueError):
            parse_timestamp("")


class TestGetOrCreateSecret:
    """Tests for get_or_create_secret function."""

    def test_create_new_secret(self, tmp_path):
        """Test creating a new secret when file doesn't exist."""
        secret_file = tmp_path / "secret"

        secret = get_or_create_secret(secret_file)

        assert isinstance(secret, bytes)
        assert len(secret) == 32  # 256 bits
        assert secret_file.exists()
        # Check file has restrictive permissions
        assert oct(secret_file.stat().st_mode)[-3:] == "600"

    def test_read_existing_secret(self, tmp_path):
        """Test reading existing secret from file."""
        secret_file = tmp_path / "secret"
        original_secret = b"x" * 32

        # Create secret file
        secret_file.write_bytes(original_secret)

        secret = get_or_create_secret(secret_file)

        assert secret == original_secret

    def test_regenerate_if_secret_too_short(self, tmp_path):
        """Test that corrupted secret file raises OSError instead of silently regenerating."""
        secret_file = tmp_path / "secret"
        short_secret = b"short"

        # Create invalid secret file
        secret_file.write_bytes(short_secret)

        # Should raise OSError with helpful message instead of silently regenerating
        with pytest.raises(OSError) as exc_info:
            get_or_create_secret(secret_file)

        assert "Corrupted secret file" in str(exc_info.value)
        assert "too short" in str(exc_info.value)
        assert "delete the file" in str(exc_info.value)

    def test_secret_persists_across_calls(self, tmp_path):
        """Test that secret persists across multiple calls."""
        secret_file = tmp_path / "secret"

        secret1 = get_or_create_secret(secret_file)
        secret2 = get_or_create_secret(secret_file)

        assert secret1 == secret2

    def test_secret_with_subdirectory(self, tmp_path):
        """Test creating secret with subdirectory."""
        secret_file = tmp_path / "subdir" / "nested" / "secret"

        secret = get_or_create_secret(secret_file)

        assert isinstance(secret, bytes)
        assert len(secret) == 32
        assert secret_file.exists()

    def test_secret_default_path(self, tmp_path):
        """Test using default secret path."""
        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = tmp_path

            secret = get_or_create_secret(None)

            assert isinstance(secret, bytes)
            assert len(secret) == 32

            # Check default location
            default_secret = tmp_path / ".claude-swarm" / "secret"
            assert default_secret.exists()

    def test_secret_file_permissions(self, tmp_path):
        """Test that secret file has correct permissions."""
        secret_file = tmp_path / "secret"

        get_or_create_secret(secret_file)

        # File should be readable/writable by owner only
        mode = secret_file.stat().st_mode
        assert mode & 0o600 == 0o600  # Owner read/write
        assert mode & 0o177 == 0  # No permissions for group/others

    def test_secret_write_failure(self, tmp_path):
        """Test handling write failure."""
        secret_file = tmp_path / "readonly" / "secret"
        secret_file.parent.mkdir()
        secret_file.parent.chmod(0o555)  # Read-only directory

        try:
            with pytest.raises(OSError) as exc_info:
                get_or_create_secret(secret_file)

            assert "Failed to write secret file" in str(exc_info.value)
        finally:
            # Restore permissions for cleanup
            secret_file.parent.chmod(0o755)

    def test_secret_read_corrupted_file(self, tmp_path):
        """Test handling corrupted secret file raises OSError with helpful message."""
        secret_file = tmp_path / "secret"
        # Create empty file that will fail validation
        secret_file.write_bytes(b"")

        # Should raise OSError with helpful message instead of silently regenerating
        with pytest.raises(OSError) as exc_info:
            get_or_create_secret(secret_file)

        assert "Corrupted secret file" in str(exc_info.value)
        assert "too short" in str(exc_info.value)
        assert "delete the file" in str(exc_info.value)


class TestIntegration:
    """Integration tests combining multiple utility functions."""

    def test_save_and_load_json_roundtrip(self, tmp_path):
        """Test saving and loading JSON roundtrip."""
        filepath = tmp_path / "test.json"
        original_data = {
            "agents": [
                {"id": "agent-1", "status": "active"},
                {"id": "agent-2", "status": "idle"},
            ],
            "timestamp": "2021-01-01T12:00:00+00:00",
            "metadata": {"version": "1.0"},
        }

        save_json(filepath, original_data)
        loaded_data = load_json(filepath)

        assert loaded_data == original_data

    def test_concurrent_save_json(self, tmp_path):
        """Test concurrent JSON saves to different files."""
        num_threads = 10
        threads = []

        def save_file(index):
            filepath = tmp_path / f"file_{index}.json"
            data = {"index": index, "data": f"content_{index}"}
            save_json(filepath, data)

        for i in range(num_threads):
            thread = threading.Thread(target=save_file, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all files were saved correctly
        for i in range(num_threads):
            filepath = tmp_path / f"file_{i}.json"
            data = load_json(filepath)
            assert data["index"] == i
            assert data["data"] == f"content_{i}"

    def test_atomic_write_with_timestamp(self, tmp_path):
        """Test atomic write with formatted timestamp."""
        filepath = tmp_path / "log.txt"
        dt = datetime(2021, 1, 1, 12, 0, 0, tzinfo=UTC)
        content = f"Log entry at {format_timestamp(dt)}"

        atomic_write(filepath, content)

        assert filepath.exists()
        assert "2021-01-01" in filepath.read_text()
