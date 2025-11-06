"""Tests for command system."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from clause_code.commands.base import Command
from clause_code.commands.config import SetKeyCommand, ProjectCommand


class MockCommand(Command):
    """Mock command for testing base class."""

    @property
    def name(self) -> str:
        return "mock"

    @property
    def description(self) -> str:
        return "A mock command for testing"

    async def execute(self, args: str = "", **kwargs) -> None:
        pass


class TestCommandBase:
    """Test cases for Command base class."""

    def test_init_with_console(self, mock_console):
        """Test command initialization with console."""
        command = MockCommand(console=mock_console)

        assert command.console == mock_console

    def test_init_without_console(self):
        """Test command initialization creates console if not provided."""
        command = MockCommand()

        assert command.console is not None

    def test_name_property(self):
        """Test command name property."""
        command = MockCommand()

        assert command.name == "mock"

    def test_description_property(self):
        """Test command description property."""
        command = MockCommand()

        assert command.description == "A mock command for testing"

    def test_print_help(self, mock_console):
        """Test print_help method."""
        command = MockCommand(console=mock_console)

        command.print_help()

        # Should have called console.print with command info
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "/mock" in call_args
        assert "testing" in call_args


class TestSetKeyCommand:
    """Test cases for SetKeyCommand."""

    def test_name(self, config_manager, mock_console):
        """Test command name."""
        command = SetKeyCommand(config_manager, mock_console)

        assert command.name == "setkey"

    def test_description(self, config_manager, mock_console):
        """Test command description."""
        command = SetKeyCommand(config_manager, mock_console)

        assert "API key" in command.description

    @pytest.mark.asyncio
    async def test_execute_valid_key(self, config_manager, mock_console):
        """Test executing setkey with valid key."""
        command = SetKeyCommand(config_manager, mock_console)

        with patch('getpass.getpass', return_value='sk-ant-test-key-123'):
            await command.execute()

        # Check that key was saved
        assert config_manager.get_api_key() == 'sk-ant-test-key-123'

        # Check that success message was printed
        assert mock_console.print.called

    @pytest.mark.asyncio
    async def test_execute_invalid_key_format(self, config_manager, mock_console):
        """Test executing setkey with invalid key format."""
        command = SetKeyCommand(config_manager, mock_console)

        with patch('getpass.getpass', return_value='invalid-key'):
            await command.execute()

        # Key should not be saved
        assert config_manager.get_api_key() is None

        # Should print warning message
        assert mock_console.print.called

    @pytest.mark.asyncio
    async def test_execute_empty_key(self, config_manager, mock_console):
        """Test executing setkey with empty key."""
        command = SetKeyCommand(config_manager, mock_console)

        with patch('getpass.getpass', return_value=''):
            await command.execute()

        # Key should not be saved
        assert config_manager.get_api_key() is None


class TestProjectCommand:
    """Test cases for ProjectCommand."""

    def test_name(self, config_manager, mock_console):
        """Test command name."""
        command = ProjectCommand(config_manager, mock_console)

        assert command.name == "project"

    def test_description(self, config_manager, mock_console):
        """Test command description."""
        command = ProjectCommand(config_manager, mock_console)

        assert "project folder" in command.description.lower()

    @pytest.mark.asyncio
    async def test_execute_with_args(self, config_manager, mock_console, temp_dir):
        """Test executing project command with folder argument."""
        command = ProjectCommand(config_manager, mock_console)

        test_folder = temp_dir / "test_project"
        test_folder.mkdir()

        await command.execute(args=str(test_folder))

        # Check that folder was saved
        saved_folder = config_manager.get_project_folder()
        assert saved_folder is not None
        assert saved_folder.name == "test_project"

    @pytest.mark.asyncio
    async def test_execute_with_prompt(self, config_manager, mock_console, temp_dir):
        """Test executing project command with user prompt."""
        command = ProjectCommand(config_manager, mock_console)

        test_folder = temp_dir / "prompted_project"
        test_folder.mkdir()

        with patch('rich.prompt.Prompt.ask', return_value=str(test_folder)):
            await command.execute(args="")

        # Check that folder was saved
        saved_folder = config_manager.get_project_folder()
        assert saved_folder is not None

    @pytest.mark.asyncio
    async def test_execute_nonexistent_folder(self, config_manager, mock_console, temp_dir):
        """Test executing project command with nonexistent folder."""
        command = ProjectCommand(config_manager, mock_console)

        nonexistent = temp_dir / "does_not_exist"

        await command.execute(args=str(nonexistent))

        # Should print warning
        assert mock_console.print.called


class TestCommandRegistry:
    """Test cases for command registration and lookup."""

    def test_command_interface_compliance(self, config_manager, mock_console):
        """Test that all commands implement the Command interface."""
        commands = [
            SetKeyCommand(config_manager, mock_console),
            ProjectCommand(config_manager, mock_console),
        ]

        for command in commands:
            # All commands should have these properties/methods
            assert hasattr(command, 'name')
            assert hasattr(command, 'description')
            assert hasattr(command, 'execute')
            assert hasattr(command, 'print_help')

            # Name and description should be strings
            assert isinstance(command.name, str)
            assert isinstance(command.description, str)
            assert len(command.name) > 0
            assert len(command.description) > 0

    def test_unique_command_names(self, config_manager, mock_console):
        """Test that all commands have unique names."""
        commands = [
            SetKeyCommand(config_manager, mock_console),
            ProjectCommand(config_manager, mock_console),
        ]

        names = [cmd.name for cmd in commands]

        # All names should be unique
        assert len(names) == len(set(names))
