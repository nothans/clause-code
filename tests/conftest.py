"""Pytest configuration and fixtures."""

import io
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from rich.console import Console

from clause_code.utils.config import ConfigManager


@pytest.fixture(autouse=True)
def no_env_api_key(monkeypatch):
    """Keep a real ANTHROPIC_API_KEY in the environment out of the tests."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def no_env_output_settings(monkeypatch):
    """Keep the shell's output settings out of the tests: the app honors these on purpose."""
    for name in ("PYTHONIOENCODING", "CLAUSE_CODE_ASCII", "TERM"):
        monkeypatch.delenv(name, raising=False)


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
def recording_console():
    """A real Rich console that records plain-text output.

    It writes to memory, so its encoding is UTF-8 whatever pytest does with stdout.
    """
    return Console(
        file=io.StringIO(), record=True, width=120, force_terminal=False, color_system=None
    )


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
