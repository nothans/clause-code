"""Tests for command system."""

from unittest.mock import create_autospec, patch

import pytest

from clause_code.agent import ClauseAgent
from clause_code.commands.base import Command
from clause_code.commands.config import (
    AdventCommand,
    AutoAcceptCommand,
    ClearCommand,
    GrinchCommand,
    HelpCommand,
    ModelCommand,
    ProjectCommand,
    SantaCommand,
    SetKeyCommand,
)


@pytest.fixture
def mock_agent(project_folder):
    agent = create_autospec(ClauseAgent, instance=True)
    agent.model = "opus"
    agent.model_info = {"emoji": "🎅", "name": "Claude Opus 5.5", "description": "Most capable"}
    agent.project_folder = project_folder
    agent.auto_accept_edits = False
    return agent


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

    async def test_execute_valid_key(self, config_manager, mock_console):
        """Test executing setkey with valid key."""
        command = SetKeyCommand(config_manager, mock_console)

        with patch("getpass.getpass", return_value="sk-ant-test-key-123"):
            await command.execute()

        # Check that key was saved
        assert config_manager.get_api_key() == "sk-ant-test-key-123"

        # Check that success message was printed
        assert mock_console.print.called

    async def test_execute_invalid_key_format(self, config_manager, mock_console):
        """Test executing setkey with invalid key format."""
        command = SetKeyCommand(config_manager, mock_console)

        with patch("getpass.getpass", return_value="invalid-key"):
            await command.execute()

        # Key should not be saved
        assert config_manager.get_api_key() is None

        # Should print warning message
        assert mock_console.print.called

    async def test_execute_empty_key(self, config_manager, mock_console):
        """Test executing setkey with empty key."""
        command = SetKeyCommand(config_manager, mock_console)

        with patch("getpass.getpass", return_value=""):
            await command.execute()

        # Key should not be saved
        assert config_manager.get_api_key() is None

    async def test_execute_restarts_agent(self, config_manager, mock_console, mock_agent):
        """A new key starts a new session that uses it."""
        command = SetKeyCommand(config_manager, mock_console, mock_agent)

        with patch("getpass.getpass", return_value="sk-ant-test-key-123"):
            await command.execute()

        mock_agent.set_api_key.assert_awaited_once_with("sk-ant-test-key-123")


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

    async def test_execute_with_prompt(self, config_manager, mock_console, temp_dir):
        """Test executing project command with user prompt."""
        command = ProjectCommand(config_manager, mock_console)

        test_folder = temp_dir / "prompted_project"
        test_folder.mkdir()

        with patch("rich.prompt.Prompt.ask", return_value=str(test_folder)):
            await command.execute(args="")

        # Check that folder was saved
        saved_folder = config_manager.get_project_folder()
        assert saved_folder is not None

    async def test_execute_nonexistent_folder(self, config_manager, mock_console, temp_dir):
        """Test executing project command with nonexistent folder."""
        command = ProjectCommand(config_manager, mock_console)

        nonexistent = temp_dir / "does_not_exist"

        await command.execute(args=str(nonexistent))

        # Should print warning
        assert mock_console.print.called

    async def test_execute_moves_agent(self, config_manager, mock_console, mock_agent, temp_dir):
        """Switching folders moves the agent to the new folder."""
        command = ProjectCommand(config_manager, mock_console, mock_agent)
        test_folder = temp_dir / "elsewhere"
        test_folder.mkdir()

        await command.execute(args=str(test_folder))

        mock_agent.set_project.assert_awaited_once_with(test_folder.resolve())

    async def test_execute_rejects_file(self, config_manager, mock_console, mock_agent, temp_dir):
        """A file path is not accepted as a project folder."""
        command = ProjectCommand(config_manager, mock_console, mock_agent)
        a_file = temp_dir / "file.txt"
        a_file.write_text("x")

        await command.execute(args=str(a_file))

        mock_agent.set_project.assert_not_awaited()
        assert config_manager.get_project_folder() is None


class TestModelCommand:
    """Test cases for ModelCommand."""

    async def test_switch_model(self, config_manager, mock_console, mock_agent):
        command = ModelCommand(mock_agent, config_manager, mock_console)

        await command.execute("Haiku")

        mock_agent.set_model.assert_awaited_once_with("haiku")
        assert config_manager.get_model() == "haiku"

    async def test_unknown_model(self, config_manager, mock_console, mock_agent):
        command = ModelCommand(mock_agent, config_manager, mock_console)

        await command.execute("gpt")

        mock_agent.set_model.assert_not_awaited()
        assert config_manager.get_model() == "opus"

    async def test_list_models(self, config_manager, mock_console, mock_agent):
        command = ModelCommand(mock_agent, config_manager, mock_console)

        await command.execute()

        printed = " ".join(str(c.args[0]) for c in mock_console.print.call_args_list)
        assert "Claude Opus 5.5" in printed
        assert "Claude Sonnet 5.5" in printed
        assert "Claude Haiku 5.5" in printed


class TestUsageText:
    """Usage hints with brackets must not be swallowed as Rich markup."""

    async def test_model_usage(self, config_manager, mock_agent, recording_console):
        mock_agent.model_info = {"emoji": "🎅", "name": "Claude Opus 5.5", "description": "x"}

        await ModelCommand(mock_agent, config_manager, recording_console).execute()

        assert "/model [opus|sonnet|haiku]" in recording_console.export_text()

    async def test_autoaccept_usage(self, mock_agent, recording_console):
        await AutoAcceptCommand(mock_agent, recording_console).execute("maybe")

        assert "/autoaccept [on|off]" in recording_console.export_text()


class TestModeCommands:
    """Test cases for /santa, /grinch and /autoaccept."""

    async def test_grinch_then_santa(self, config_manager, mock_console, mock_agent):
        await GrinchCommand(mock_agent, config_manager, mock_console).execute()
        mock_agent.set_festive_mode.assert_called_with(False)
        assert config_manager.is_festive_mode() is False

        await SantaCommand(mock_agent, config_manager, mock_console).execute()
        mock_agent.set_festive_mode.assert_called_with(True)
        assert config_manager.is_festive_mode() is True

    @pytest.mark.parametrize("args,expected", [("on", True), ("off", False), ("", True)])
    async def test_autoaccept(self, mock_console, mock_agent, args, expected):
        await AutoAcceptCommand(mock_agent, mock_console).execute(args)

        mock_agent.set_auto_accept.assert_awaited_once_with(expected)

    async def test_autoaccept_bad_arg(self, mock_console, mock_agent):
        await AutoAcceptCommand(mock_agent, mock_console).execute("maybe")

        mock_agent.set_auto_accept.assert_not_awaited()


class TestClearCommand:
    """Test cases for ClearCommand."""

    async def test_clear_starts_new_session(self, mock_console, mock_agent):
        await ClearCommand(mock_agent, mock_console).execute()

        mock_console.clear.assert_called_once()
        mock_agent.new_session.assert_awaited_once()


class TestHelpCommand:
    """Test cases for HelpCommand."""

    async def test_lists_every_command_and_exit(self, config_manager, mock_console, mock_agent):
        commands = {
            "setkey": SetKeyCommand(config_manager, mock_console),
            "autoaccept": AutoAcceptCommand(mock_agent, mock_console),
            "advent": AdventCommand(mock_console),
        }
        commands["help"] = HelpCommand(commands, mock_console)

        await commands["help"].execute()

        printed = " ".join(str(c.args[0]) for c in mock_console.print.call_args_list if c.args)
        for name in ("/setkey", "/autoaccept", "/advent", "/help", "/exit"):
            assert name in printed


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
            assert hasattr(command, "name")
            assert hasattr(command, "description")
            assert hasattr(command, "execute")
            assert hasattr(command, "print_help")

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
