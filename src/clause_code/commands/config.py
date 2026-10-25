"""Configuration commands for Clause Code."""

import getpass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt

from ..agent import MODELS, ClauseAgent
from ..utils.config import ConfigManager
from .base import Command


class SetKeyCommand(Command):
    """Command to set/update Anthropic API key."""

    def __init__(
        self,
        config_manager: ConfigManager,
        console: Optional[Console] = None,
        agent: Optional[ClauseAgent] = None,
    ):
        """Initialize command.

        Args:
            config_manager: Configuration manager
            console: Rich console for output
            agent: Agent to restart with the new key
        """
        super().__init__(console)
        self.config_manager = config_manager
        self.agent = agent

    @property
    def name(self) -> str:
        return "setkey"

    @property
    def description(self) -> str:
        return "Set or update your Anthropic API key"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        self.console.print(
            "\n[bold green]🎅 Ho ho ho! Let's set up your workshop key![/bold green]"
        )
        self.console.print(
            "[cyan]Get your key from: https://console.anthropic.com/account/keys[/cyan]\n"
        )

        api_key = getpass.getpass("🔐 Enter your Anthropic API key (hidden): ").strip()

        if not api_key:
            self.console.print("[yellow]❄️ No key provided. Cancelled.[/yellow]")
            return

        if not api_key.startswith("sk-ant-"):
            self.console.print("[yellow]❄️ That doesn't look like a valid Anthropic key...[/yellow]")
            self.console.print("[cyan]Keys should start with 'sk-ant-'[/cyan]")
            return

        self.config_manager.set_api_key(api_key)
        self.console.print(
            "[bold green]✨ Your workshop key has been saved to Santa's vault![/bold green]"
        )
        self.console.print("[dim]Stored in ~/.clause-code/.api_key (readable only by you)[/dim]")
        if self.agent:
            await self.agent.set_api_key(api_key)
            self.console.print("[green]🎄 Started a new session with the new key.[/green]")


class ProjectCommand(Command):
    """Command to set project folder."""

    def __init__(
        self,
        config_manager: ConfigManager,
        console: Optional[Console] = None,
        agent: Optional[ClauseAgent] = None,
    ):
        """Initialize command.

        Args:
            config_manager: Configuration manager
            console: Rich console for output
            agent: Agent to move to the new folder
        """
        super().__init__(console)
        self.config_manager = config_manager
        self.agent = agent

    @property
    def name(self) -> str:
        return "project"

    @property
    def description(self) -> str:
        return "Set the project folder to work in"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        if args:
            folder_path = args.strip()
        else:
            current = self.agent.project_folder if self.agent else None
            current = current or self.config_manager.get_project_folder()
            if current:
                self.console.print(f"[cyan]Current project folder: {current}[/cyan]")

            folder_path = Prompt.ask(
                "\n🎄 Enter the project folder path",
                default=str(current) if current else ".",
            )

        try:
            path = Path(folder_path).expanduser().resolve()

            if not path.exists():
                create = Prompt.ask(
                    "[yellow]📁 Folder doesn't exist. Create it?[/yellow]",
                    choices=["y", "n"],
                    default="y",
                )
                if create.lower() == "y":
                    path.mkdir(parents=True, exist_ok=True)
                    self.console.print(f"[green]✨ Created folder: {path}[/green]")
                else:
                    self.console.print("[yellow]❄️ Cancelled.[/yellow]")
                    return

            if not path.is_dir():
                self.console.print("[red]❌ Path exists but is not a directory![/red]")
                return

            self.config_manager.set_project_folder(str(path))
            if self.agent:
                await self.agent.set_project(path)
            self.console.print(f"[bold green]🎁 Project folder set to: {path}[/bold green]")
            self.console.print("[green]🎄 Started a new session in this folder.[/green]")

        except OSError as e:
            self.console.print(f"[red]❌ Error: {e}[/red]")


class ModelCommand(Command):
    """Command to switch Claude models."""

    def __init__(
        self,
        agent: ClauseAgent,
        config_manager: ConfigManager,
        console: Optional[Console] = None,
    ):
        """Initialize command.

        Args:
            agent: Claude agent
            config_manager: Configuration manager
            console: Rich console for output
        """
        super().__init__(console)
        self.agent = agent
        self.config_manager = config_manager

    @property
    def name(self) -> str:
        return "model"

    @property
    def description(self) -> str:
        return "Switch between Claude models (opus/sonnet/haiku)"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        if not args:
            current = self.agent.model
            info = self.agent.model_info
            self.console.print(f"\n[bold]Current model:[/bold] {info['emoji']} {info['name']}")
            self.console.print(f"[dim]{info['description']}[/dim]\n")

            self.console.print("[bold]Available models:[/bold]")
            for key, model_info in MODELS.items():
                marker = "→" if key == current else " "
                self.console.print(
                    f"{marker} [cyan]{key:8}[/cyan] {model_info['emoji']} {model_info['name']}"
                )
                self.console.print(f"           {model_info['description']}")
            self.console.print("\n[dim]Usage: /model \\[opus|sonnet|haiku][/dim]")
            return

        model_name = args.strip().lower()
        if model_name in MODELS:
            await self.agent.set_model(model_name)
            self.config_manager.set_model(model_name)

            info = MODELS[model_name]
            self.console.print(
                f"[bold green]{info['emoji']} Switched to {info['name']}![/bold green]"
            )
            self.console.print(f"[green]   {info['description']}[/green]")
        else:
            self.console.print(f"[red]❌ Unknown model: {model_name}[/red]")
            self.console.print(f"[yellow]Available: {', '.join(MODELS)}[/yellow]")


class SantaCommand(Command):
    """Command to enable maximum festive mode."""

    def __init__(
        self,
        agent: ClauseAgent,
        config_manager: ConfigManager,
        console: Optional[Console] = None,
    ):
        """Initialize command.

        Args:
            agent: Claude agent
            config_manager: Configuration manager
            console: Rich console for output
        """
        super().__init__(console)
        self.agent = agent
        self.config_manager = config_manager

    @property
    def name(self) -> str:
        return "santa"

    @property
    def description(self) -> str:
        return "Enable maximum festive mode 🎅"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        self.agent.set_festive_mode(True)
        self.config_manager.set_festive_mode(True)
        self.console.print("\n[bold red]🎅 HO HO HO![/bold red]")
        self.console.print("[bold green]🎄 Maximum festive mode activated![/bold green]")
        self.console.print("[dim]Claude's own tone follows from the next /clear.[/dim]\n")


class GrinchCommand(Command):
    """Command to enable minimal mode."""

    def __init__(
        self,
        agent: ClauseAgent,
        config_manager: ConfigManager,
        console: Optional[Console] = None,
    ):
        """Initialize command.

        Args:
            agent: Claude agent
            config_manager: Configuration manager
            console: Rich console for output
        """
        super().__init__(console)
        self.agent = agent
        self.config_manager = config_manager

    @property
    def name(self) -> str:
        return "grinch"

    @property
    def description(self) -> str:
        return "Enable minimal mode (less festive)"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        self.agent.set_festive_mode(False)
        self.config_manager.set_festive_mode(False)
        self.console.print("\n[dim]⚙️ Minimal mode enabled.[/dim]")
        self.console.print("[dim]Claude's own tone follows from the next /clear.[/dim]\n")


class AutoAcceptCommand(Command):
    """Command to auto-accept file edits inside the project folder."""

    def __init__(self, agent: ClauseAgent, console: Optional[Console] = None):
        """Initialize command.

        Args:
            agent: Claude agent
            console: Rich console for output
        """
        super().__init__(console)
        self.agent = agent

    @property
    def name(self) -> str:
        return "autoaccept"

    @property
    def description(self) -> str:
        return "Let the elves apply file edits without asking (on/off)"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        arg = args.strip().lower()
        if arg in ("on", "off"):
            enabled = arg == "on"
        elif not arg:
            enabled = not self.agent.auto_accept_edits
        else:
            self.console.print("[yellow]Usage: /autoaccept \\[on|off][/yellow]")
            return

        await self.agent.set_auto_accept(enabled)
        if enabled:
            self.console.print(
                "[bold green]🧝 Auto-accept on: file edits apply without asking.[/bold green]"
            )
            self.console.print(
                "[dim]Shell commands still ask, and writes outside the project are always blocked.[/dim]"
            )
        else:
            self.console.print("[green]🔐 Auto-accept off: you'll approve each edit.[/green]")


class ClearCommand(Command):
    """Command to clear the screen and start a new session."""

    def __init__(self, agent: Optional[ClauseAgent] = None, console: Optional[Console] = None):
        """Initialize command.

        Args:
            agent: Optional Claude agent (to start a new session)
            console: Rich console for output
        """
        super().__init__(console)
        self.agent = agent

    @property
    def name(self) -> str:
        return "clear"

    @property
    def description(self) -> str:
        return "Clear the screen and start a new conversation"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        self.console.clear()
        if self.agent:
            await self.agent.new_session()
        self.console.print("[dim]✨ Fresh snow! New conversation started.[/dim]")


class AdventCommand(Command):
    """Command to show daily December coding challenges."""

    # 25 Daily December Challenges
    CHALLENGES = {
        1: "🎄 Day 1: Create a function that prints a Christmas tree of any height",
        2: "🎁 Day 2: Build a gift list manager with add, remove, and search features",
        3: "⭐ Day 3: Generate a random Christmas carol lyrics line",
        4: "🕯️ Day 4: Create an advent calendar countdown that shows days until Christmas",
        5: "❄️ Day 5: Build a snowflake pattern generator using ASCII art",
        6: "🎅 Day 6: Create a Santa's nice/naughty list classifier",
        7: "🦌 Day 7: Simulate reindeer racing with random speed calculations",
        8: "🔔 Day 8: Build a musical note player that plays 'Jingle Bells'",
        9: "🍪 Day 9: Create a cookie recipe calculator with ingredient scaling",
        10: "🎵 Day 10: Generate Christmas-themed ASCII art banner",
        11: "⛄ Day 11: Build a snowman builder with customizable features",
        12: "🎁 Day 12: Create a secret Santa gift exchange randomizer",
        13: "🌟 Day 13: Build a star constellation display for the night sky",
        14: "🎀 Day 14: Create a gift wrapping calculator for various box sizes",
        15: "🕊️ Day 15: Simulate the 12 Days of Christmas song generator",
        16: "🧦 Day 16: Build a stocking stuffer suggestion generator",
        17: "🏠 Day 17: Create a gingerbread house design planner",
        18: "🎺 Day 18: Build a Christmas light pattern animator",
        19: "📜 Day 19: Create a Christmas story generator with random elements",
        20: "🎪 Day 20: Build a toy workshop inventory management system",
        21: "⛷️ Day 21: Create a winter sports scoreboard tracker",
        22: "🎭 Day 22: Build a Christmas movie recommendation engine",
        23: "🍷 Day 23: Create a holiday recipe collection with search",
        24: "🌙 Day 24: Build a Christmas Eve countdown timer with animations",
        25: "🎄 Day 25: Create a complete Christmas morning surprise simulator!",
    }

    @property
    def name(self) -> str:
        return "advent"

    @property
    def description(self) -> str:
        return "Get your daily December coding challenge 🎄"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        now = datetime.now()

        if now.month != 12:
            self.console.print(
                "\n[yellow]🎄 Advent challenges are only available during December![/yellow]"
            )
            self.console.print("[dim]Come back in December for daily coding challenges![/dim]\n")
            return

        day = now.day

        if day > 25:
            self.console.print(
                "\n[green]🎅 All advent challenges complete! Merry Christmas![/green]"
            )
            self.console.print(
                "[dim]You can still view past challenges by typing: /advent \\[day][/dim]\n"
            )
            day = 25

        if args:
            try:
                requested_day = int(args)
                if 1 <= requested_day <= 25:
                    day = requested_day
                else:
                    self.console.print("[yellow]Please specify a day between 1 and 25[/yellow]")
                    return
            except ValueError:
                self.console.print("[yellow]Please specify a valid day number[/yellow]")
                return

        challenge = self.CHALLENGES[day]

        self.console.print(f"\n[bold green]🎄 Advent Calendar - December {day} 🎄[/bold green]\n")
        self.console.print(f"[bold]{challenge}[/bold]\n")

        self.console.print("[dim]Tips:[/dim]")
        self.console.print("  • Just describe your solution to Clause Code")
        self.console.print("  • I'll help you build it step by step!")
        self.console.print("  • Use [cyan]/project[/cyan] to save your advent solutions\n")

        if not args:
            completed = day - 1
            remaining = 25 - day
            self.console.print(f"[green]Progress: {completed}/25 challenges[/green]")
            if remaining > 0:
                self.console.print(f"[cyan]{remaining} more challenges to unlock![/cyan]\n")


class HelpCommand(Command):
    """Command to show help."""

    GROUPS = {
        "Configuration": ["setkey", "project", "model", "autoaccept", "santa", "grinch"],
        "Fun": ["advent"],
        "Utility": ["clear", "help"],
    }

    def __init__(self, commands: dict, console: Optional[Console] = None):
        """Initialize command.

        Args:
            commands: Dictionary of available commands
            console: Rich console for output
        """
        super().__init__(console)
        self.commands = commands

    @property
    def name(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "Show available commands"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        self.console.print("\n[bold green]🎄 Clause Code Commands 🎅[/bold green]\n")

        for group, names in self.GROUPS.items():
            self.console.print(f"[bold]{group}:[/bold]")
            for cmd_name in names:
                if cmd_name in self.commands:
                    cmd = self.commands[cmd_name]
                    self.console.print(f"  [cyan]/{cmd.name:12}[/cyan] - {cmd.description}")
            if group == "Utility":
                self.console.print(f"  [cyan]/{'exit, /quit':12}[/cyan] - Exit Clause Code")
            self.console.print()

        self.console.print("[bold]Tips:[/bold]")
        self.console.print(
            "  • Just type naturally - Claude can read, edit, and run code in your project"
        )
        self.console.print("  • You'll be asked before any file edit or shell command")
        self.console.print("  • Try [cyan]/advent[/cyan] for daily December challenges!")
        self.console.print("  • Press [cyan]Ctrl+C[/cyan] to interrupt Claude mid-turn")
        self.console.print("  • Press [cyan]Ctrl+D[/cyan] or type [cyan]/exit[/cyan] to quit\n")
