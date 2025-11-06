"""Pytest configuration and fixtures."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from rich.console import Console

from clause_code.utils.config import ConfigManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def config_dir(temp_dir):
    """Create a temporary config directory."""
    config_path = temp_dir / ".clause-code"
    config_path.mkdir(exist_ok=True)
    return config_path


@pytest.fixture
def config_manager(config_dir):
    """Create a ConfigManager instance with temporary directory."""
    return ConfigManager(config_dir=config_dir)


@pytest.fixture
def mock_console():
    """Create a mock Rich console."""
    return Mock(spec=Console)


@pytest.fixture
def api_key():
    """Provide a test API key."""
    return "sk-ant-test-key-1234567890"


@pytest.fixture
def project_folder(temp_dir):
    """Create a temporary project folder."""
    project = temp_dir / "test_project"
    project.mkdir(exist_ok=True)
    return project
