"""Tests for the CLI."""

import argparse
import asyncio
import os
import signal
from unittest.mock import AsyncMock, create_autospec

import pytest
from claude_agent_sdk import AssistantMessage, CLIConnectionError, ResultMessage, ToolUseBlock

from clause_code.agent import ClauseAgent
from clause_code.cli import ClauseCodeCLI, build_parser
from clause_code.permissions import ToolApprover
from clause_code.theme import GrinchTheme


def result(**overrides):
    fields = dict(
        subtype="success",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=1,
        session_id="s",
    )
    fields.update(overrides)
    return ResultMessage(**fields)


@pytest.fixture
def cli(recording_console, config_manager, project_folder):
    cli = ClauseCodeCLI(console=recording_console, config_manager=config_manager)
    agent = create_autospec(ClauseAgent, instance=True)
    agent.project_folder = project_folder
    agent.theme = GrinchTheme
    agent.stderr_tail = []
    cli.agent = agent
    cli.approver = ToolApprover(recording_console, AsyncMock(), lambda: project_folder)
    cli.initialize_commands()
    return cli


class TestParser:
    def test_model_and_project(self):
        args = build_parser().parse_args(["--model", "haiku", "--project", "/tmp"])

        assert args.model == "haiku"
        assert args.project == "/tmp"

    def test_rejects_unknown_model(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--model", "gpt"])


class TestResolveProjectFolder:
    def test_flag_wins(self, cli, temp_dir, config_manager, project_folder):
        config_manager.set_project_folder(str(project_folder))

        assert cli.resolve_project_folder(str(temp_dir)) == temp_dir.resolve()

    def test_saved_folder(self, cli, config_manager, project_folder):
        config_manager.set_project_folder(str(project_folder))

        assert cli.resolve_project_folder(None) == project_folder.resolve()

    def test_missing_saved_folder_falls_back_to_cwd(
        self, cli, config_manager, temp_dir, monkeypatch
    ):
        config_manager.set_project_folder(str(temp_dir / "gone"))
        # Leave temp_dir before its fixture deletes it; Windows can't remove the working directory
        with monkeypatch.context() as m:
            m.chdir(temp_dir)
            assert cli.resolve_project_folder(None) == temp_dir


class TestHandleCommand:
    async def test_exit(self, cli):
        assert await cli.handle_command("/exit") is False
        assert await cli.handle_command("/quit") is False

    async def test_unknown_command(self, cli, recording_console):
        assert await cli.handle_command("/nope") is True
        assert "Unknown command: /nope" in recording_console.export_text()

    async def test_bare_slash(self, cli):
        assert await cli.handle_command("/") is True

    async def test_dispatches_with_args(self, cli):
        await cli.handle_command("/model sonnet")

        cli.agent.set_model.assert_awaited_once_with("sonnet")

    async def test_command_error_is_reported(self, cli, recording_console):
        cli.agent.new_session.side_effect = CLIConnectionError("runtime went away")

        assert await cli.handle_command("/clear") is True
        text = recording_console.export_text()
        assert "runtime went away" in text
        assert "session was closed" not in text


class TestRunTurn:
    async def test_renders_messages(self, cli, recording_console):
        async def send(prompt):
            yield result()

        cli.agent.send.side_effect = send

        await cli.run_turn("hello")

        assert "Done" in recording_console.export_text()
        assert cli.approver.before_prompt is None

    async def test_sdk_error_closes_session(self, cli, recording_console):
        async def send(prompt):
            raise CLIConnectionError("pipe closed")
            yield  # pragma: no cover

        cli.agent.send.side_effect = send

        await cli.run_turn("hello")

        assert "pipe closed" in recording_console.export_text()
        cli.agent.disconnect.assert_awaited_once()

    async def test_unexpected_error_keeps_repl_alive(self, cli, recording_console):
        async def send(prompt):
            raise RuntimeError("control protocol hiccup")
            yield  # pragma: no cover

        cli.agent.send.side_effect = send

        await cli.run_turn("hello")

        assert "control protocol hiccup" in recording_console.export_text()
        cli.agent.disconnect.assert_awaited_once()

    async def test_approval_hooks_cleared_after_turn(self, cli):
        async def send(prompt):
            assert cli.approver.before_prompt is not None
            assert cli.approver.after_prompt is not None
            yield result()

        cli.agent.send.side_effect = send

        await cli.run_turn("hello")

        assert cli.approver.before_prompt is None
        assert cli.approver.after_prompt is None

    async def test_output_waits_while_a_prompt_is_open(
        self, cli, recording_console, project_folder
    ):
        """Regression: a parallel tool call printed over an open approval prompt and restarted
        the spinner under the user's typing."""
        printed_during_prompt = []

        async def send(prompt):
            cli.approver.before_prompt()  # the first tool's approval prompt is open
            yield AssistantMessage(
                content=[
                    ToolUseBlock(
                        id="t2", name="Write", input={"file_path": str(project_folder / "b.py")}
                    )
                ],
                model="claude-opus-5-5",
            )
            printed_during_prompt.append("b.py" in recording_console.export_text(clear=False))
            cli.approver.after_prompt()  # the user answered
            yield result()

        cli.agent.send.side_effect = send

        await cli.run_turn("hello")

        assert printed_during_prompt == [False]
        assert "b.py" in recording_console.export_text()

    @pytest.mark.skipif(os.name == "nt", reason="loop signal handlers are POSIX-only")
    async def test_ctrl_c_interrupts_turn_instead_of_exiting(self, cli, recording_console):
        """Regression: in 1.x Ctrl+C mid-response escaped asyncio.run and killed the app."""
        interrupted = asyncio.Event()

        async def interrupt():
            interrupted.set()

        async def send(prompt):
            os.kill(os.getpid(), signal.SIGINT)
            await asyncio.wait_for(interrupted.wait(), timeout=5)
            yield result(terminal_reason="aborted_streaming")

        cli.agent.send.side_effect = send
        cli.agent.interrupt.side_effect = interrupt

        await cli.run_turn("write a long poem")

        cli.agent.interrupt.assert_awaited_once()
        assert "Interrupted" in recording_console.export_text()
        # The handler is removed once the turn ends
        assert signal.getsignal(signal.SIGINT) is not None


class TestRun:
    async def test_bad_project_flag(self, recording_console, config_manager, api_key, temp_dir):
        config_manager.set_api_key(api_key)
        cli = ClauseCodeCLI(console=recording_console, config_manager=config_manager)
        args = argparse.Namespace(project=str(temp_dir / "missing"), model=None)

        assert await cli.run(args) == 1
        assert "Not a folder" in recording_console.export_text()
