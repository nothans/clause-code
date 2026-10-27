"""Main CLI for Clause Code."""

import argparse
import asyncio
import getpass
import signal
import sys
from pathlib import Path
from typing import Optional

from claude_agent_sdk import ClaudeSDKError, CLINotFoundError
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markup import escape
from rich.prompt import Prompt
from rich.text import Text

from ._version import __version__
from .agent import CONTEXT_WINDOW, MODELS, ClauseAgent
from .commands import (
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
from .permissions import ToolApprover
from .render import TurnRenderer
from .theme import FestiveTheme
from .utils.config import ConfigManager


def _add_sigint_handler(loop: asyncio.AbstractEventLoop, callback) -> bool:
    """Route Ctrl+C to callback while Claude is working. Not supported on Windows."""
    try:
        loop.add_signal_handler(signal.SIGINT, callback)
    except (NotImplementedError, RuntimeError):
        return False
    return True


class ClauseCodeCLI:
    """Main CLI application for Clause Code."""

    def __init__(
        self,
        console: Optional[Console] = None,
        config_manager: Optional[ConfigManager] = None,
    ):
        """Initialize CLI."""
        self.console = console or Console()
        self.config_manager = config_manager or ConfigManager()
        self.agent: Optional[ClauseAgent] = None
        self.approver: Optional[ToolApprover] = None
        self.commands = {}
        self._approval_session: Optional[PromptSession] = None
        self._interrupt_task: Optional[asyncio.Task] = None

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

        banner = f"""[bold]═══ Clause Code v{__version__} ═══════════════════════════════════════════════════[/bold]

    Welcome back Santa's Helper!

{FestiveTheme.WELCOME_TREE}
    {model_info["emoji"]} {model_info["name"]} • Claude Agent SDK
    📁 {project}

[dim]─────────────────────────────────────────────────────────────────────────────[/dim]

    [bold]Tips for getting started[/bold]
    • Just type naturally - Claude can read, edit, and run code in this folder
    • You'll approve every file edit and shell command
    • Use [cyan]/project[/cyan] to switch folders and [cyan]/help[/cyan] for all commands

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
            "setkey": SetKeyCommand(self.config_manager, self.console, self.agent),
            "project": ProjectCommand(self.config_manager, self.console, self.agent),
            "model": ModelCommand(self.agent, self.config_manager, self.console),
            "autoaccept": AutoAcceptCommand(self.agent, self.console),
            "santa": SantaCommand(self.agent, self.config_manager, self.console),
            "grinch": GrinchCommand(self.agent, self.config_manager, self.console),
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
        renderer = TurnRenderer(self.console, self.agent.theme, lambda: self.agent.project_folder)
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

        handler_installed = _add_sigint_handler(loop, on_sigint)
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
            if handler_installed:
                loop.remove_signal_handler(signal.SIGINT)

    async def chat_loop(self):
        """Main chat loop."""
        history_file = self.config_manager.config_dir / "history"
        session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=WordCompleter(
                [f"/{cmd}" for cmd in [*self.commands, "exit", "quit"]],
                ignore_case=True,
            ),
        )

        self.console.print(
            "[bold green]🎄 Ready! What would you like to build today?[/bold green]\n"
        )

        while True:
            try:
                user_input = await session.prompt_async("🎅 > ")
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
        )
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
            self.show_main_screen()
            await self.chat_loop()
        finally:
            await self.agent.disconnect()

        self.console.print("\n[bold green]🎄 Thanks for coding with Clause Code![/bold green]")
        self.console.print("[green]❄️  May your code compile and your bugs be few![/green]\n")
        return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        prog="clause-code",
        description="The AI coding assistant that brings holiday cheer to your terminal.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--model", choices=list(MODELS), help="Model for this session")
    parser.add_argument("--project", metavar="PATH", help="Project folder for this session")
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
