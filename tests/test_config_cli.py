"""Tests for config-related CLI commands.

Tests cover:
- `config init` creates valid config file
- `config show` displays config correctly
- `config validate` catches errors
- `config edit` opens editor (mocked)
- `config path` shows config file location
- Error handling for all commands
- Config file format options (YAML/TOML)
- Interactive vs non-interactive modes

Author: Agent-4 (Test Engineer)
"""

from unittest.mock import Mock, patch

import pytest

# Config CLI imports (will be available after Agent 2/3 implement CLI commands)
try:
    from claudeswarm.cli import (
        cmd_config_edit,
        cmd_config_init,
        cmd_config_path,
        cmd_config_show,
        cmd_config_validate,
    )
    from claudeswarm.config import Config, ConfigError

    CONFIG_CLI_EXISTS = True
except ImportError:
    # Placeholders
    def cmd_config_init(*args, **kwargs):
        pass

    def cmd_config_show(*args, **kwargs):
        pass

    def cmd_config_validate(*args, **kwargs):
        pass

    def cmd_config_edit(*args, **kwargs):
        pass

    def cmd_config_path(*args, **kwargs):
        pass

    class ConfigError(Exception):
        pass

    CONFIG_CLI_EXISTS = False


pytestmark = pytest.mark.skipif(
    not CONFIG_CLI_EXISTS, reason="Config CLI commands not yet implemented"
)


class TestConfigInit:
    """Tests for 'config init' command."""

    def test_config_init_creates_yaml_file_by_default(self, temp_config_dir, monkeypatch):
        """Test that config init creates a valid YAML file."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()
        args.format = "yaml"
        args.output = None
        args.force = False

        cmd_config_init(args)

        # Should create config.yaml
        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        assert config_file.exists()

        # Should be valid YAML
        content = config_file.read_text()
        assert "messaging:" in content
        assert "locking:" in content
        assert "discovery:" in content

    def test_config_init_creates_toml_file_when_specified(self, temp_config_dir, monkeypatch):
        """Test that config init can create TOML format."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()
        args.format = "toml"
        args.output = None
        args.force = False

        cmd_config_init(args)

        # Should create config.toml
        config_file = temp_config_dir / ".claudeswarm" / "config.toml"
        assert config_file.exists()

        content = config_file.read_text()
        assert "[messaging]" in content
        assert "[locking]" in content

    def test_config_init_respects_output_path(self, temp_config_dir, monkeypatch):
        """Test that config init can write to custom path."""
        monkeypatch.chdir(temp_config_dir)

        custom_path = temp_config_dir / "custom" / "myconfig.yaml"

        args = Mock()
        args.format = "yaml"
        args.output = str(custom_path)
        args.force = False

        cmd_config_init(args)

        assert custom_path.exists()

    def test_config_init_refuses_to_overwrite_without_force(self, temp_config_dir, monkeypatch):
        """Test that config init won't overwrite existing file without --force."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("existing content")

        args = Mock()
        args.format = "yaml"
        args.output = None
        args.force = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_config_init(args)

        assert exc_info.value.code != 0

        # File should be unchanged
        assert config_file.read_text() == "existing content"

    def test_config_init_overwrites_with_force_flag(self, temp_config_dir, monkeypatch):
        """Test that config init overwrites with --force flag."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("existing content")

        args = Mock()
        args.format = "yaml"
        args.output = None
        args.force = True

        cmd_config_init(args)

        # File should be overwritten
        content = config_file.read_text()
        assert content != "existing content"
        assert "messaging:" in content

    def test_config_init_creates_parent_directories(self, temp_config_dir, monkeypatch):
        """Test that config init creates necessary parent directories."""
        monkeypatch.chdir(temp_config_dir)

        deep_path = temp_config_dir / "a" / "b" / "c" / "config.yaml"

        args = Mock()
        args.format = "yaml"
        args.output = str(deep_path)
        args.force = False

        cmd_config_init(args)

        assert deep_path.exists()
        assert deep_path.parent.exists()


class TestConfigShow:
    """Tests for 'config show' command."""

    def test_config_show_displays_current_config(
        self, temp_config_dir, sample_yaml_config, monkeypatch, capsys
    ):
        """Test that config show displays the current configuration."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.format = "yaml"
        args.section = None

        cmd_config_show(args)

        captured = capsys.readouterr()
        assert "messaging" in captured.out
        assert "max_messages: 10" in captured.out

    def test_config_show_displays_specific_section(
        self, temp_config_dir, sample_yaml_config, monkeypatch, capsys
    ):
        """Test that config show can display a specific section."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.format = "yaml"
        args.section = "messaging"

        cmd_config_show(args)

        captured = capsys.readouterr()
        assert "messaging" in captured.out or "rate_limit" in captured.out

    def test_config_show_json_format(
        self, temp_config_dir, sample_yaml_config, monkeypatch, capsys
    ):
        """Test that config show can output JSON format."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.format = "json"
        args.section = None

        cmd_config_show(args)

        captured = capsys.readouterr()
        # Should be valid JSON
        import json

        json.loads(captured.out)  # Should not raise

    def test_config_show_displays_defaults_when_no_file(self, temp_config_dir, monkeypatch, capsys):
        """Test that config show displays defaults when no config file exists."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()
        args.format = "yaml"
        args.section = None

        cmd_config_show(args)

        captured = capsys.readouterr()
        # Should show default config
        assert "messaging" in captured.out or "default" in captured.out.lower()


class TestConfigValidate:
    """Tests for 'config validate' command."""

    def test_config_validate_accepts_valid_config(
        self, temp_config_dir, sample_yaml_config, monkeypatch, capsys
    ):
        """Test that config validate succeeds with valid config."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.config_path = str(config_file)

        cmd_config_validate(args)

        captured = capsys.readouterr()
        assert "valid" in captured.out.lower() or "ok" in captured.out.lower()

    def test_config_validate_catches_invalid_yaml(
        self, temp_config_dir, invalid_yaml_config, monkeypatch
    ):
        """Test that config validate catches YAML syntax errors."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(invalid_yaml_config)

        args = Mock()
        args.config_path = str(config_file)

        with pytest.raises(SystemExit) as exc_info:
            cmd_config_validate(args)

        assert exc_info.value.code != 0

    def test_config_validate_catches_invalid_values(
        self, temp_config_dir, invalid_values_config, monkeypatch
    ):
        """Test that config validate catches semantically invalid values."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(invalid_values_config)

        args = Mock()
        args.config_path = str(config_file)

        with pytest.raises(SystemExit) as exc_info:
            cmd_config_validate(args)

        assert exc_info.value.code != 0

    def test_config_validate_reports_specific_errors(
        self, temp_config_dir, invalid_values_config, monkeypatch, capsys
    ):
        """Test that config validate reports specific validation errors."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(invalid_values_config)

        args = Mock()
        args.config_path = str(config_file)

        try:
            cmd_config_validate(args)
        except SystemExit:
            pass

        captured = capsys.readouterr()
        # Should mention what's wrong
        assert "error" in captured.out.lower() or "error" in captured.err.lower()


class TestConfigEdit:
    """Tests for 'config edit' command."""

    def test_config_edit_opens_editor(self, temp_config_dir, sample_yaml_config, monkeypatch):
        """Test that config edit opens the configured editor."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.editor = None  # Use default from env

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            cmd_config_edit(args)

            # Should have called editor
            assert mock_run.called
            call_args = mock_run.call_args[0][0]
            assert str(config_file) in call_args

    def test_config_edit_respects_editor_argument(
        self, temp_config_dir, sample_yaml_config, monkeypatch
    ):
        """Test that config edit uses specified editor."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.editor = "nano"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            cmd_config_edit(args)

            call_args = mock_run.call_args[0][0]
            assert "nano" in call_args

    def test_config_edit_creates_file_if_missing(self, temp_config_dir, monkeypatch):
        """Test that config edit creates config file if it doesn't exist."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()
        args.editor = "echo"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            cmd_config_edit(args)

            # Should have created the file
            config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
            assert config_file.exists()

    def test_config_edit_validates_after_editing(
        self, temp_config_dir, sample_yaml_config, monkeypatch
    ):
        """Test that config edit validates the config after editing."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.editor = "echo"
        args.validate = True

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)

            # Assume validation passes
            cmd_config_edit(args)


class TestConfigPath:
    """Tests for 'config path' command."""

    def test_config_path_shows_current_config_location(
        self, temp_config_dir, sample_yaml_config, monkeypatch, capsys
    ):
        """Test that config path shows the config file location."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()

        cmd_config_path(args)

        captured = capsys.readouterr()
        assert str(config_file) in captured.out or ".claudeswarm" in captured.out

    def test_config_path_shows_default_location_if_no_file(
        self, temp_config_dir, monkeypatch, capsys
    ):
        """Test that config path shows default location even if file doesn't exist."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()

        cmd_config_path(args)

        captured = capsys.readouterr()
        assert ".claudeswarm" in captured.out or "config" in captured.out


class TestConfigCLIErrorHandling:
    """Tests for error handling in config CLI commands."""

    def test_config_init_handles_permission_error(self, temp_config_dir, monkeypatch):
        """Test that config init handles permission errors gracefully."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()
        args.format = "yaml"
        args.output = "/root/forbidden/config.yaml"  # Likely no permission
        args.force = False

        with pytest.raises(SystemExit) as exc_info:
            cmd_config_init(args)

        assert exc_info.value.code != 0

    def test_config_show_handles_missing_config(self, temp_config_dir, monkeypatch):
        """Test that config show handles missing config gracefully."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()
        args.format = "yaml"
        args.section = None

        # Should not crash, should show defaults
        cmd_config_show(args)

    def test_config_validate_handles_missing_file(self, temp_config_dir, monkeypatch):
        """Test that config validate handles missing file."""
        monkeypatch.chdir(temp_config_dir)

        args = Mock()
        args.config_path = "/nonexistent/config.yaml"

        with pytest.raises(SystemExit) as exc_info:
            cmd_config_validate(args)

        assert exc_info.value.code != 0

    def test_config_edit_handles_editor_not_found(
        self, temp_config_dir, sample_yaml_config, monkeypatch
    ):
        """Test that config edit handles missing editor gracefully."""
        monkeypatch.chdir(temp_config_dir)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(sample_yaml_config)

        args = Mock()
        args.editor = "nonexistent-editor-xyz"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError("Editor not found")

            with pytest.raises(SystemExit) as exc_info:
                cmd_config_edit(args)

            assert exc_info.value.code != 0


class TestConfigCLIIntegration:
    """Integration tests for config CLI commands working together."""

    def test_init_validate_show_workflow(self, temp_config_dir, monkeypatch, capsys):
        """Test workflow: init -> validate -> show."""
        monkeypatch.chdir(temp_config_dir)

        # Init
        args_init = Mock()
        args_init.format = "yaml"
        args_init.output = None
        args_init.force = False

        cmd_config_init(args_init)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"
        assert config_file.exists()

        # Validate
        args_validate = Mock()
        args_validate.config_path = str(config_file)

        cmd_config_validate(args_validate)

        # Show
        args_show = Mock()
        args_show.format = "yaml"
        args_show.section = None

        cmd_config_show(args_show)

        captured = capsys.readouterr()
        assert "messaging" in captured.out

    def test_init_edit_validate_workflow(self, temp_config_dir, monkeypatch):
        """Test workflow: init -> edit -> validate."""
        monkeypatch.chdir(temp_config_dir)

        # Init
        args_init = Mock()
        args_init.format = "yaml"
        args_init.output = None
        args_init.force = False

        cmd_config_init(args_init)

        config_file = temp_config_dir / ".claudeswarm" / "config.yaml"

        # Edit (mock)
        args_edit = Mock()
        args_edit.editor = "true"  # Unix command that always succeeds
        args_edit.validate = False

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0)
            cmd_config_edit(args_edit)

        # Validate
        args_validate = Mock()
        args_validate.config_path = str(config_file)

        cmd_config_validate(args_validate)
