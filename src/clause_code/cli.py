"""Main CLI for Clause Code."""

import argparse
import asyncio
import getpass
import signal
import sys
import threading
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Optional

from claude_agent_sdk import ClaudeSDKError, CLINotFoundError
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt
from rich.text import Text

from ._version import __version__
from .agent import CONTEXT_WINDOW, MODELS, ClauseAgent
from .cheerlights import BlueskyPoster, CheerLights, ago, ink_for
from .commands import (
    AdventCommand,
    AutoAcceptCommand,
    CheckCommand,
    CheerLightsCommand,
    ClearCommand,
    CompactCommand,
    ContextCommand,
    GrinchCommand,
    HelpCommand,
    ModelCommand,
    PlanCommand,
    ProjectCommand,
    ResumeCommand,
    SantaCommand,
    SetKeyCommand,
    SnowCommand,
    UndoCommand,
)
from .commands.cheerlights import color_line
from .permissions import ToolApprover
from .render import TurnRenderer
from .theme import FestiveTheme, christmas_countdown
from .utils.config import ConfigManager

PROMPT_STYLE = Style.from_dict({"bottom-toolbar": "noreverse"})


def command_completer(names: list[str]) -> WordCompleter:
    """Complete slash commands, and stay out of the way in ordinary messages.

    The whole line is matched, so "/c" offers /check and /cheerlights, while a space in
    a sentence does not pop up the command list.
    """
    return WordCompleter([f"/{name}" for name in names], ignore_case=True, sentence=True)


def install_sigint(loop: asyncio.AbstractEventLoop, callback: Callable[[], None]):
    """Route Ctrl+C to ``callback`` while Claude is working, instead of quitting.

    Uses the event loop's signal handler where there is one (POSIX), and a plain
    signal handler that hands off to the loop elsewhere (Windows).

    Returns:
        A function that puts the previous Ctrl+C behavior back, or None if
        Ctrl+C could not be routed
    """
    previous = signal.getsignal(signal.SIGINT)
    try:
        loop.add_signal_handler(signal.SIGINT, callback)
    except (NotImplementedError, RuntimeError):
        pass
    else:

        def restore():
            # remove_signal_handler resets SIGINT to Python's default handler; put back
            # whatever was there before (asyncio.run's own handler, in the app)
            loop.remove_signal_handler(signal.SIGINT)
            if previous is not None:
                signal.signal(signal.SIGINT, previous)

        return restore
    if threading.current_thread() is not threading.main_thread():
        return None

    def handler(signum, frame):
        loop.call_soon_threadsafe(callback)

    signal.signal(signal.SIGINT, handler)
    return lambda: signal.signal(signal.SIGINT, previous)


class ClauseCodeCLI:
    """Main CLI application for Clause Code."""

    def __init__(
        self,
        console: Optional[Console] = None,
        config_manager: Optional[ConfigManager] = None,
        cheerlights: Optional[CheerLights] = None,
    ):
        """Initialize CLI."""
        self.console = console or Console()
        self.config_manager = config_manager or ConfigManager()
        self.cheerlights = cheerlights or CheerLights(poster=BlueskyPoster.from_env())
        self.agent: Optional[ClauseAgent] = None
        self.approver: Optional[ToolApprover] = None
        self.commands = {}
        self._approval_session: Optional[PromptSession] = None
        self._prompt_session: Optional[PromptSession] = None
        self._interrupt_task: Optional[asyncio.Task] = None
        self.cheerlights.add_listener(lambda color: self._refresh_prompt())

    # CheerLights mode

    @property
    def cheerlights_mode(self) -> bool:
        """Whether the UI follows the live CheerLights color."""
        return self.cheerlights.following

    def accent(self) -> Optional[str]:
        """The live CheerLights hex in CheerLights mode, else None."""
        if self.cheerlights_mode and self.cheerlights.current is not None:
            return self.cheerlights.current.hex
        return None

    def _refresh_prompt(self) -> None:
        session = self._prompt_session
        if session is not None and session.app.is_running:
            session.app.invalidate()

    async def _cheerlights_toggled(self, enabled: bool) -> None:
        self._refresh_prompt()

    def prompt_message(self) -> FormattedText:
        """The input prompt; its bulb wears the CheerLights color in CheerLights mode."""
        hex_value = self.accent()
        if hex_value:
            return FormattedText([(f"bold {hex_value}", "● "), ("", "🎅 > ")])
        return FormattedText([("", "🎅 > ")])

    def toolbar(self) -> FormattedText:
        """The status line under the prompt: model, permission mode, and CheerLights."""
        agent = self.agent
        if agent is None:
            return FormattedText([])
        mode = (
            "plan mode"
            if agent.plan_mode
            else ("edits: auto" if agent.auto_accept_edits else "edits: ask")
        )
        parts = [("fg:ansibrightblack", f" {agent.model_info['name']} · {mode}")]
        if self.cheerlights_mode:
            parts.append(("fg:ansibrightblack", " · "))
            parts.extend(self._cheerlights_status())
        return FormattedText(parts)

    def _cheerlights_status(self) -> list[tuple[str, str]]:
        cheer = self.cheerlights
        color = cheer.current
        if color is None:
            if cheer.status == "offline":
                return [("fg:ansiyellow", "🎄 lights out of reach")]
            return [("fg:ansibrightblack", "🎄 finding the lights...")]
        chip = f"bg:{color.hex} fg:{ink_for(color.hex)} bold"
        who = f"by @{cheer.setter.handle}" if cheer.setter else "by someone, somewhere"
        rest = f" set {ago(color.set_at, cheer.now())} {who}"
        if cheer.status == "offline":
            rest += " (offline)"
        return [(chip, f" {color.name} "), ("fg:ansibrightblack", rest)]

    # Screens

    def show_welcome(self):
        """Show festive welcome screen."""
        self.console.clear()
        self.console.print(FestiveTheme.WELCOME_TREE, style="green", justify="center")
        self.console.print(f"[bold green]Clause Code v{__version__}[/bold green]", justify="center")
        self.console.print(
            "[dim]The AI coding assistant with holiday cheer[/dim]\n",
            justify="center",
        )

    def show_main_screen(self):
        """Show main interface screen."""
        model_info = self.agent.model_info
        project = escape(str(self.agent.project_folder))
        mode = "🎅 Festive" if self.agent.festive_mode else "⚙️ Minimal"
        countdown = f"\n    {christmas_countdown(date.today())}" if self.agent.festive_mode else ""

        banner = f"""[bold]═══ Clause Code v{__version__} ═══════════════════════════════════════════════════[/bold]

    Welcome back Santa's Helper!{countdown}

{FestiveTheme.WELCOME_TREE}
    {model_info["emoji"]} {model_info["name"]} • Claude Agent SDK
    📁 {project}

[dim]─────────────────────────────────────────────────────────────────────────────[/dim]

    [bold]Tips for getting started[/bold]
    • Just type naturally - Claude can read, edit, and run code in this folder
    • You approve every edit and every command that changes things; [cyan]/undo[/cyan] rolls back edits
    • [cyan]/plan[/cyan] to plan before building, [cyan]/cheerlights[/cyan] for the lights, [cyan]/help[/cyan] for the rest

    [bold]Current Settings[/bold]
    Model: {model_info["name"]} • Context: {CONTEXT_WINDOW} tokens
    Mode: {mode}

[dim]═════════════════════════════════════════════════════════════════════════════[/dim]
"""
        self.console.print(banner)

    def setup_first_run(self) -> bool:
        """Ask for an API key and preferences on first run.

        Returns:
            True if setup successful, False otherwise
        """
        self.show_welcome()

        self.console.print(FestiveTheme.WELCOME_BANNER)
        self.console.print("[bold]Let's get your workshop set up![/bold]\n")

        self.console.print("[yellow]🎅 I don't see an API key configured yet.[/yellow]")
        self.console.print(
            "[cyan]Get your key from: https://console.anthropic.com/account/keys[/cyan]\n"
        )
        api_key = getpass.getpass("🔐 Enter your Anthropic API key (hidden): ").strip()

        if not api_key.startswith("sk-ant-"):
            self.console.print(
                "[red]❌ Invalid or missing API key. Please run 'clause-code' again.[/red]"
            )
            return False

        self.config_manager.set_api_key(api_key)
        self.console.print("[green]✨ API key saved![/green]\n")

        festive = Prompt.ask("❄️  Enable festive mode?", choices=["y", "n"], default="y")
        if festive.lower() == "n":
            self.config_manager.set_festive_mode(False)

        self.console.print(
            "\n[bold green]✨ Configuration saved to ~/.clause-code/config.json[/bold green]"
        )
        self.console.print(
            "[green]🎄 Your workshop is ready! Let's start coding with holiday cheer![/green]\n"
        )
        return True

    def resolve_project_folder(self, override: Optional[str]) -> Path:
        """Pick the project folder: --project, then the saved folder, then the cwd."""
        if override:
            return Path(override).expanduser().resolve()
        saved = self.config_manager.get_project_folder()
        if saved and saved.is_dir():
            return saved
        return Path.cwd()

    def initialize_commands(self):
        """Initialize all commands."""
        self.commands = {
            "plan": PlanCommand(self.agent, self.console),
            "autoaccept": AutoAcceptCommand(self.agent, self.console),
            "undo": UndoCommand(self.agent, self.console),
            "check": CheckCommand(self.run_turn, self.console),
            "resume": ResumeCommand(self.agent, self.console),
            "context": ContextCommand(self.agent, self.console),
            "compact": CompactCommand(self.run_turn, self.console),
            "setkey": SetKeyCommand(self.config_manager, self.console, self.agent),
            "project": ProjectCommand(self.config_manager, self.console, self.agent),
            "model": ModelCommand(self.agent, self.config_manager, self.console),
            "santa": SantaCommand(self.agent, self.config_manager, self.console),
            "grinch": GrinchCommand(self.agent, self.config_manager, self.console),
            "cheerlights": CheerLightsCommand(
                self.cheerlights, self.config_manager, self.console, self._cheerlights_toggled
            ),
            "snow": SnowCommand(self.console, lambda: self.agent.festive_mode, self.accent),
            "advent": AdventCommand(self.console),
            "clear": ClearCommand(self.agent, self.console),
        }
        # Help needs every other command, so it is added last
        self.commands["help"] = HelpCommand(self.commands, self.console)

    async def ask_approval(self, prompt: str) -> str:
        """Ask the user a yes/no question while Claude waits."""
        if self._approval_session is None:
            self._approval_session = PromptSession()
        return await self._approval_session.prompt_async(prompt)

    async def handle_command(self, command_line: str) -> bool:
        """Handle a slash command.

        Args:
            command_line: Command line starting with /

        Returns:
            True to continue, False to exit
        """
        parts = command_line[1:].split(maxsplit=1)
        if not parts:
            return True
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd_name in ["exit", "quit"]:
            return False

        if cmd_name in self.commands:
            try:
                await self.commands[cmd_name].execute(args)
            except ClaudeSDKError as e:
                self.print_sdk_error(e)
            except Exception as e:
                self.console.print(Text(f"❌ Error: {e}", style="red"))
        else:
            self.console.print(Text(f"❓ Unknown command: /{cmd_name}", style="yellow"))
            self.console.print("[dim]Type /help to see available commands[/dim]")

        return True

    def print_sdk_error(self, error: Exception) -> None:
        """Explain an SDK failure and show the runtime's last log lines."""
        self.console.print(Text(f"❌ {error}", style="red"))
        for line in list(self.agent.stderr_tail)[-5:]:
            self.console.print(Text(line, style="dim"))

    async def run_turn(self, prompt: str) -> None:
        """Send a prompt and render Claude's work until the turn ends."""
        renderer = TurnRenderer(
            self.console,
            self.agent.theme,
            lambda: self.agent.project_folder,
            cheerlights=self.cheerlights if self.cheerlights_mode else None,
            background=lambda: self.agent.background_tasks,
        )
        self.approver.before_prompt = renderer.hold
        self.approver.after_prompt = renderer.release
        loop = asyncio.get_running_loop()
        interrupting = False

        def on_sigint():
            nonlocal interrupting
            if interrupting:
                return
            interrupting = True
            renderer.pause()
            self.console.print(Text("⏸  Interrupting...", style="dim"))
            self._interrupt_task = loop.create_task(self.agent.interrupt())

        restore_sigint = install_sigint(loop, on_sigint)
        try:
            renderer.start()
            async for message in self.agent.send(prompt):
                renderer.handle(message)
        except Exception as e:
            # Keep the REPL alive; the session may be broken, so start fresh next time
            renderer.pause()
            self.print_sdk_error(e)
            self.console.print(
                "[dim]The session was closed; your next message starts a new one.[/dim]"
            )
            await self.agent.disconnect()
        finally:
            renderer.finish()
            self.approver.before_prompt = None
            self.approver.after_prompt = None
            if restore_sigint:
                restore_sigint()

    async def chat_loop(self):
        """Main chat loop."""
        history_file = self.config_manager.config_dir / "history"
        session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=command_completer([*self.commands, "exit", "quit"]),
            bottom_toolbar=self.toolbar,
            style=PROMPT_STYLE,
            # Keeps "set 4 min ago" current while the prompt waits
            refresh_interval=5,
        )
        self._prompt_session = session

        self.console.print(
            "[bold green]🎄 Ready! What would you like to build today?[/bold green]\n"
        )

        while True:
            try:
                user_input = await session.prompt_async(self.prompt_message)
            except KeyboardInterrupt:
                self.console.print("[dim]Use /exit or Ctrl+D to quit[/dim]")
                continue
            except EOFError:
                break

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                if not await self.handle_command(user_input):
                    break
                continue

            await self.run_turn(user_input)

    async def run(self, args: argparse.Namespace) -> int:
        """Run the CLI application."""
        if not self.config_manager.get_api_key() and not self.setup_first_run():
            return 1

        project_folder = self.resolve_project_folder(args.project)
        if not project_folder.is_dir():
            self.console.print(Text(f"❌ Not a folder: {project_folder}", style="red"))
            return 1

        resume = getattr(args, "resume", None)
        config = self.config_manager.load()
        self.approver = ToolApprover(
            self.console, self.ask_approval, lambda: self.agent.project_folder
        )
        self.agent = ClauseAgent(
            project_folder,
            model=args.model or config.default_model,
            festive_mode=config.festive_mode,
            api_key=self.config_manager.get_api_key(),
            approver=self.approver,
            cheerlights=self.cheerlights,
            resume=resume if resume and resume != PICK else None,
            continue_last=bool(getattr(args, "continue_last", False)),
            launcher_dir=self.config_manager.config_dir,
        )
        self.approver.on_plan_approved = self.agent.plan_approved
        self.initialize_commands()

        try:
            with self.console.status("🦌 Harnessing the reindeer..."):
                await self.agent.connect()
        except CLINotFoundError:
            self.console.print(
                "[red]❌ The Claude Code runtime that ships with claude-agent-sdk is missing.[/red]"
            )
            self.console.print(
                "[dim]Try reinstalling: pip install --force-reinstall claude-agent-sdk[/dim]"
            )
            return 1
        except ClaudeSDKError as e:
            self.console.print(Text(f"❌ Could not start Claude: {e}", style="red"))
            return 1

        try:
            if config.cheerlights_mode:
                await self.cheerlights.start_live()
            self.show_main_screen()
            if config.cheerlights_mode:
                await self._show_cheerlights_line()
            if resume == PICK:
                await self.handle_command("/resume")
            elif resume or getattr(args, "continue_last", False):
                self.console.print("[green]🎁 Picked up where you left off.[/green]")
            await self.chat_loop()
        finally:
            await self.cheerlights.stop_live()
            await self.agent.disconnect()

        self.console.print("\n[bold green]🎄 Thanks for coding with Clause Code![/bold green]")
        self.console.print("[green]❄️  May your code compile and your bugs be few![/green]\n")
        return 0

    async def _show_cheerlights_line(self) -> None:
        # Wait briefly for the first read so the welcome shows the color, never long
        for _ in range(30):
            if self.cheerlights.current is not None or self.cheerlights.status == "offline":
                break
            await asyncio.sleep(0.1)
        if self.cheerlights.current is not None:
            self.console.print(
                color_line(self.cheerlights, self.cheerlights.current, self.cheerlights.setter)
            )
            self.console.print()


# --resume with no session ID: choose from a list
PICK = "__pick__"


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="clause-code",
        description="The AI coding assistant that brings holiday cheer to your terminal.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--model", choices=list(MODELS), help="Model for this session")
    parser.add_argument("--project", metavar="PATH", help="Project folder for this session")
    resume = parser.add_mutually_exclusive_group()
    resume.add_argument(
        "-c",
        "--continue",
        dest="continue_last",
        action="store_true",
        help="Continue the most recent conversation in the project folder",
    )
    resume.add_argument(
        "-r",
        "--resume",
        nargs="?",
        const=PICK,
        metavar="SESSION_ID",
        help="Resume a conversation by ID, or choose from a list",
    )
    return parser


def main(argv: Optional[list[str]] = None):
    """Main entry point."""
    args = build_parser().parse_args(argv)
    try:
        exit_code = asyncio.run(ClauseCodeCLI().run(args))
    except KeyboardInterrupt:
        exit_code = 130
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
