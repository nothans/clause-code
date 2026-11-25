"""Tests for the CLI."""

import argparse
import asyncio
import signal
from unittest.mock import AsyncMock, create_autospec

import pytest
from claude_agent_sdk import AssistantMessage, CLIConnectionError, ResultMessage, ToolUseBlock

from clause_code.agent import ClauseAgent
from clause_code.cli import (
    PICK,
    ClauseCodeCLI,
    build_parser,
    command_completer,
    install_sigint,
)
from clause_code.permissions import ToolApprover
from clause_code.theme import FestiveTheme, GrinchTheme


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
    agent.background_tasks = {}
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

    async def test_ctrl_c_interrupts_turn_instead_of_exiting(self, cli, recording_console):
        """Regression: in 1.x Ctrl+C mid-response escaped asyncio.run and killed the app.
        Until 3.0 it still did on Windows, where the event loop has no signal handlers."""
        before = signal.getsignal(signal.SIGINT)
        interrupted = asyncio.Event()

        async def interrupt():
            interrupted.set()

        async def send(prompt):
            signal.raise_signal(signal.SIGINT)
            await asyncio.wait_for(interrupted.wait(), timeout=5)
            yield result(terminal_reason="aborted_streaming")

        cli.agent.send.side_effect = send
        cli.agent.interrupt.side_effect = interrupt

        await cli.run_turn("write a long poem")

        cli.agent.interrupt.assert_awaited_once()
        assert "Interrupted" in recording_console.export_text()
        # Ctrl+C goes back to what it did before once the turn ends
        assert signal.getsignal(signal.SIGINT) == before


class TestRun:
    async def test_bad_project_flag(self, recording_console, config_manager, api_key, temp_dir):
        config_manager.set_api_key(api_key)
        cli = ClauseCodeCLI(console=recording_console, config_manager=config_manager)
        args = argparse.Namespace(project=str(temp_dir / "missing"), model=None)

        assert await cli.run(args) == 1
        assert "Not a folder" in recording_console.export_text()


class TestInstallSigint:
    def test_falls_back_to_a_signal_handler(self):
        """Windows event loops cannot add signal handlers; Ctrl+C must still reach the turn."""

        class NoSignals:
            def __init__(self):
                self.calls = []

            def add_signal_handler(self, *args):
                raise NotImplementedError

            def call_soon_threadsafe(self, callback):
                self.calls.append(callback)

        loop = NoSignals()
        before = signal.getsignal(signal.SIGINT)
        hit = []

        restore = install_sigint(loop, lambda: hit.append(True))
        try:
            handler = signal.getsignal(signal.SIGINT)
            assert handler is not before
            handler(signal.SIGINT, None)
            loop.calls[0]()
            assert hit == [True]
        finally:
            restore()
        assert signal.getsignal(signal.SIGINT) == before


class TestParserV3:
    def test_continue(self):
        assert build_parser().parse_args(["-c"]).continue_last is True

    def test_resume_by_id(self):
        assert build_parser().parse_args(["--resume", "abc"]).resume == "abc"

    def test_resume_picks(self):
        assert build_parser().parse_args(["--resume"]).resume == PICK

    def test_continue_and_resume_conflict(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["-c", "--resume", "abc"])


class TestStatusLine:
    @pytest.fixture
    def lit_cli(self, cli):
        from datetime import datetime, timedelta, timezone

        from clause_code.cheerlights import Color, Setter

        cli.agent.model_info = {"name": "Claude Opus 5.5"}
        cli.agent.plan_mode = False
        cli.agent.auto_accept_edits = False
        cli.cheerlights.status = "live"
        cli.cheerlights.current = Color(
            "yellow", "#ffff00", datetime.now(timezone.utc) - timedelta(minutes=4)
        )
        cli.cheerlights.setter = Setter("cymplecy.bsky.social", "https://bsky.app/x")
        return cli

    def text(self, formatted):
        return "".join(fragment for _, fragment in formatted)

    def test_plain(self, cli):
        cli.agent.model_info = {"name": "Claude Opus 5.5"}
        cli.agent.plan_mode = False
        cli.agent.auto_accept_edits = True

        assert self.text(cli.toolbar()) == " Claude Opus 5.5 · edits: auto"

    def test_plan_mode(self, cli):
        cli.agent.model_info = {"name": "Claude Opus 5.5"}
        cli.agent.plan_mode = True

        assert "plan mode" in self.text(cli.toolbar())

    def test_cheerlights(self, lit_cli):
        formatted = lit_cli.toolbar()

        assert self.text(formatted).endswith(" yellow  set 4 min ago by @cymplecy.bsky.social")
        chip = next(style for style, text in formatted if text == " yellow ")
        # Dark ink on a yellow chip, so it reads on any terminal background
        assert "bg:#ffff00" in chip and "fg:#252525" in chip

    def test_cheerlights_offline(self, lit_cli):
        lit_cli.cheerlights.status = "offline"
        assert self.text(lit_cli.toolbar()).endswith("(offline)")

    def test_cheerlights_before_first_read(self, lit_cli):
        lit_cli.cheerlights.current = None
        lit_cli.cheerlights.status = "connecting"
        assert "finding the lights" in self.text(lit_cli.toolbar())

    def test_prompt_bulb(self, lit_cli):
        lit_cli.agent.theme = FestiveTheme
        assert self.text(lit_cli.prompt_message()) == " ● " + " 🎅 > "
        # The bulb hangs on the dark strip, so a yellow or white bulb shows on light themes
        assert lit_cli.prompt_message()[0][0] == "bold #ffff00 bg:#252525"

    def test_prompt_follows_the_theme(self, cli):
        cli.agent.theme = FestiveTheme
        assert self.text(cli.prompt_message()) == "🎅 > "
        cli.agent.theme = GrinchTheme
        assert self.text(cli.prompt_message()) == "> "

    def test_prompt_in_ascii(self, lit_cli):
        """A terminal that cannot show the bulb or Santa gets ASCII, not a crash."""
        import io

        from rich.console import Console

        ascii_file = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
        lit_cli.console = Console(file=ascii_file)
        lit_cli.agent.theme = FestiveTheme
        assert self.text(lit_cli.prompt_message()) == " o " + " > "
        assert self.text(lit_cli.toolbar()).isascii()


class TestCommandCompleter:
    """Regression: in 2.0 "/c" completed nothing, and every space in a sentence popped up
    the whole command list."""

    def complete(self, text):
        from prompt_toolkit.completion import CompleteEvent
        from prompt_toolkit.document import Document

        completer = command_completer(["check", "cheerlights", "plan", "exit"])
        return [c.text for c in completer.get_completions(Document(text), CompleteEvent())]

    def test_slash_prefix_completes(self):
        assert self.complete("/c") == ["/check", "/cheerlights"]

    def test_case_insensitive(self):
        assert self.complete("/PL") == ["/plan"]

    def test_sentences_stay_quiet(self):
        assert self.complete("make the sleigh ") == []
        assert self.complete("fix the ch") == []
