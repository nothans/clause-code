"""Tests for configuration management."""

import json
import os
import stat
from pathlib import Path

import pytest

from clause_code.utils.config import ClauseConfig, ConfigManager


class TestClauseConfig:
    """Test cases for ClauseConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ClauseConfig()

        assert config.default_model == "opus"
        assert config.festive_mode is True
        assert config.project_folder is None

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = ClauseConfig(
            default_model="haiku",
            festive_mode=False,
            project_folder="/path/to/project",
        )

        assert config.default_model == "haiku"
        assert config.festive_mode is False
        assert config.project_folder == "/path/to/project"

    def test_no_api_key_field(self):
        """The API key never lives on the config model, so it can't reach config.json."""
        assert "api_key" not in ClauseConfig.model_fields

    def test_ignores_old_keys(self):
        """Config files from 1.x (with a theme key) still load."""
        config = ClauseConfig(**{"default_model": "sonnet", "theme": "monokai"})

        assert config.default_model == "sonnet"

    def test_model_validation(self):
        """Test that invalid model raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ClauseConfig(default_model="invalid")

    def test_festive_mode_string_conversion(self):
        """Test festive_mode string to boolean conversion."""
        assert ClauseConfig(festive_mode="true").festive_mode is True
        assert ClauseConfig(festive_mode="1").festive_mode is True
        assert ClauseConfig(festive_mode="yes").festive_mode is True
        assert ClauseConfig(festive_mode="y").festive_mode is True

        assert ClauseConfig(festive_mode="false").festive_mode is False
        assert ClauseConfig(festive_mode="0").festive_mode is False
        assert ClauseConfig(festive_mode="no").festive_mode is False


class TestConfigManager:
    """Test cases for ConfigManager class."""

    def test_init_creates_directory(self, temp_dir):
        """Test that init creates config directory."""
        config_dir = temp_dir / ".clause-code-test"
        assert not config_dir.exists()

        manager = ConfigManager(config_dir=config_dir)

        assert config_dir.exists()
        assert manager.config_dir == config_dir

    def test_load_creates_default_config(self, config_manager):
        """Test that load creates default config if none exists."""
        config = config_manager.load()

        assert isinstance(config, ClauseConfig)
        assert config.default_model == "opus"
        assert config.festive_mode is True

    def test_save_and_load(self, config_manager):
        """Test saving and loading configuration."""
        config_manager.save(ClauseConfig(default_model="haiku", festive_mode=False))

        loaded = ConfigManager(config_dir=config_manager.config_dir).load()

        assert loaded.default_model == "haiku"
        assert loaded.festive_mode is False

    def test_api_key_stored_separately(self, config_manager):
        """Test that API key is stored in a separate file."""
        config_manager.set_api_key("secret-key")
        config_manager.set_model("haiku")

        assert config_manager.api_key_file.read_text() == "secret-key"
        with open(config_manager.config_file, "r") as f:
            assert "api_key" not in json.load(f)

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
    def test_api_key_file_owner_only(self, config_manager):
        """The key file is created readable by the owner only."""
        config_manager.set_api_key("secret-key")

        assert stat.S_IMODE(config_manager.api_key_file.stat().st_mode) == 0o600

    def test_api_key_from_environment(self, config_manager, monkeypatch):
        """Test that API key can be loaded from environment variable."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

        assert config_manager.get_api_key() == "env-key"

    def test_environment_key_wins_over_file(self, config_manager, monkeypatch):
        """A key in the environment overrides the saved key."""
        config_manager.set_api_key("file-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

        assert config_manager.get_api_key() == "env-key"

    def test_environment_key_never_written(self, config_manager, monkeypatch):
        """Saving settings must not copy an environment key to disk."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

        config_manager.set_model("haiku")
        config_manager.set_festive_mode(False)

        assert not config_manager.api_key_file.exists()
        assert "env-key" not in config_manager.config_file.read_text()

    def test_get_api_key_none(self, config_manager):
        """No key anywhere returns None."""
        assert config_manager.get_api_key() is None

    def test_set_api_key(self, config_manager):
        """Test setting API key."""
        config_manager.set_api_key("new-key")

        assert config_manager.get_api_key() == "new-key"

    def test_get_project_folder(self, config_manager):
        """Test getting project folder."""
        config_manager.save(ClauseConfig(project_folder="/test/path"))

        assert config_manager.get_project_folder() == Path("/test/path")

    def test_get_project_folder_none(self, config_manager):
        """Test getting project folder when not set."""
        assert config_manager.get_project_folder() is None

    def test_set_project_folder(self, config_manager, temp_dir):
        """Test setting project folder."""
        test_folder = temp_dir / "project"
        test_folder.mkdir()

        config_manager.set_project_folder(str(test_folder))

        folder = config_manager.get_project_folder()
        assert folder is not None
        assert folder.name == "project"

    def test_set_project_folder_expands_home(self, config_manager):
        """Test that project folder expands ~ to home directory."""
        config_manager.set_project_folder("~/test")

        folder = config_manager.get_project_folder()
        assert folder is not None
        assert "~" not in str(folder)
        assert str(Path.home()) in str(folder)

    def test_get_model(self, config_manager):
        """Test getting model."""
        config_manager.save(ClauseConfig(default_model="sonnet"))

        assert config_manager.get_model() == "sonnet"

    def test_set_model(self, config_manager):
        """Test setting model."""
        config_manager.set_model("haiku")

        assert config_manager.get_model() == "haiku"

    def test_is_festive_mode(self, config_manager):
        """Test checking festive mode."""
        config_manager.save(ClauseConfig(festive_mode=False))

        assert config_manager.is_festive_mode() is False

    def test_set_festive_mode(self, config_manager):
        """Test setting festive mode."""
        config_manager.set_festive_mode(False)
        assert config_manager.is_festive_mode() is False

        config_manager.set_festive_mode(True)
        assert config_manager.is_festive_mode() is True

    def test_config_caching(self, config_manager):
        """Test that config is cached after first load."""
        assert config_manager.load() is config_manager.load()

    def test_save_updates_cache(self, config_manager):
        """Test that save updates the cached config."""
        assert config_manager.load().default_model == "opus"

        config_manager.save(ClauseConfig(default_model="haiku"))

        assert config_manager.load().default_model == "haiku"
