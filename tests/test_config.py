"""Tests for configuration management."""

import json
import os
import pytest
from pathlib import Path

from clause_code.utils.config import ClauseConfig, ConfigManager


class TestClauseConfig:
    """Test cases for ClauseConfig model."""

    def test_default_values(self):
        """Test default configuration values."""
        config = ClauseConfig()

        assert config.api_key is None
        assert config.default_model == "sonnet"
        assert config.festive_mode is True
        assert config.project_folder is None
        assert config.theme == "monokai"

    def test_custom_values(self):
        """Test configuration with custom values."""
        config = ClauseConfig(
            api_key="test-key",
            default_model="haiku",
            festive_mode=False,
            project_folder="/path/to/project",
            theme="nord"
        )

        assert config.api_key == "test-key"
        assert config.default_model == "haiku"
        assert config.festive_mode is False
        assert config.project_folder == "/path/to/project"
        assert config.theme == "nord"

    def test_model_validation(self):
        """Test that invalid model raises validation error."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            ClauseConfig(default_model="invalid")

    def test_festive_mode_string_conversion(self):
        """Test festive_mode string to boolean conversion."""
        # Test true values
        assert ClauseConfig(festive_mode="true").festive_mode is True
        assert ClauseConfig(festive_mode="1").festive_mode is True
        assert ClauseConfig(festive_mode="yes").festive_mode is True
        assert ClauseConfig(festive_mode="y").festive_mode is True

        # Test false values
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

    def test_init_default_directory(self):
        """Test that init uses default directory if none provided."""
        manager = ConfigManager()

        assert manager.config_dir == Path.home() / ".clause-code"

    def test_load_creates_default_config(self, config_manager):
        """Test that load creates default config if none exists."""
        config = config_manager.load()

        assert isinstance(config, ClauseConfig)
        assert config.default_model == "sonnet"
        assert config.festive_mode is True

    def test_save_and_load(self, config_manager):
        """Test saving and loading configuration."""
        config = ClauseConfig(
            api_key="test-key",
            default_model="haiku",
            festive_mode=False
        )

        config_manager.save(config)

        # Load in a new manager instance
        new_manager = ConfigManager(config_dir=config_manager.config_dir)
        loaded_config = new_manager.load()

        assert loaded_config.api_key == "test-key"
        assert loaded_config.default_model == "haiku"
        assert loaded_config.festive_mode is False

    def test_api_key_stored_separately(self, config_manager):
        """Test that API key is stored in separate file."""
        config = ClauseConfig(api_key="secret-key")
        config_manager.save(config)

        # Check that API key file exists
        assert config_manager.api_key_file.exists()

        # Check that config.json doesn't contain API key
        with open(config_manager.config_file, "r") as f:
            config_dict = json.load(f)
            assert "api_key" not in config_dict

        # Check that API key file contains the key
        api_key = config_manager.api_key_file.read_text().strip()
        assert api_key == "secret-key"

    def test_api_key_from_environment(self, config_manager, monkeypatch):
        """Test that API key can be loaded from environment variable."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

        config = config_manager.load()

        assert config.api_key == "env-key"

    def test_get_api_key(self, config_manager):
        """Test getting API key."""
        config = ClauseConfig(api_key="test-key")
        config_manager.save(config)

        api_key = config_manager.get_api_key()

        assert api_key == "test-key"

    def test_set_api_key(self, config_manager):
        """Test setting API key."""
        config_manager.set_api_key("new-key")

        api_key = config_manager.get_api_key()

        assert api_key == "new-key"

    def test_get_project_folder(self, config_manager):
        """Test getting project folder."""
        config = ClauseConfig(project_folder="/test/path")
        config_manager.save(config)

        folder = config_manager.get_project_folder()

        assert folder == Path("/test/path")

    def test_get_project_folder_none(self, config_manager):
        """Test getting project folder when not set."""
        folder = config_manager.get_project_folder()

        assert folder is None

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
        config = ClauseConfig(default_model="opus")
        config_manager.save(config)

        model = config_manager.get_model()

        assert model == "opus"

    def test_set_model(self, config_manager):
        """Test setting model."""
        config_manager.set_model("haiku")

        model = config_manager.get_model()

        assert model == "haiku"

    def test_is_festive_mode(self, config_manager):
        """Test checking festive mode."""
        config = ClauseConfig(festive_mode=False)
        config_manager.save(config)

        is_festive = config_manager.is_festive_mode()

        assert is_festive is False

    def test_set_festive_mode(self, config_manager):
        """Test setting festive mode."""
        config_manager.set_festive_mode(False)

        is_festive = config_manager.is_festive_mode()

        assert is_festive is False

        config_manager.set_festive_mode(True)

        is_festive = config_manager.is_festive_mode()

        assert is_festive is True

    def test_config_caching(self, config_manager):
        """Test that config is cached after first load."""
        config1 = config_manager.load()
        config2 = config_manager.load()

        # Should return the same instance
        assert config1 is config2

    def test_save_updates_cache(self, config_manager):
        """Test that save updates the cached config."""
        config1 = config_manager.load()
        assert config1.default_model == "sonnet"

        new_config = ClauseConfig(default_model="haiku")
        config_manager.save(new_config)

        # The cached config should be updated
        assert config_manager._config.default_model == "haiku"
