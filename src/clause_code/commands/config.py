"""Configuration commands for Clause Code."""

import getpass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt

from ..agent import ClaudeAgent
from ..utils.config import ConfigManager
from .base import Command


class SetKeyCommand(Command):
    """Command to set/update Anthropic API key."""

    def __init__(self, config_manager: ConfigManager, console: Optional[Console] = None):
        """Initialize command.

        Args:
            config_manager: Configuration manager
            console: Rich console for output
        """
        super().__init__(console)
        self.config_manager = config_manager

    @property
    def name(self) -> str:
        return "setkey"

    @property
    def description(self) -> str:
        return "Set or update your Anthropic API key"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        self.console.print("\n[bold green]🎅 Ho ho ho! Let's set up your workshop key![/bold green]")
        self.console.print(
            "[cyan]Get your key from: https://console.anthropic.com/account/keys[/cyan]\n"
        )

        # Use getpass for secure input
        api_key = getpass.getpass("🔐 Enter your Anthropic API key (hidden): ")

        if not api_key:
            self.console.print("[yellow]❄️ No key provided. Cancelled.[/yellow]")
            return

        # Validate key format
        if not api_key.startswith("sk-ant-"):
            self.console.print(
                "[yellow]❄️ That doesn't look like a valid Anthropic key...[/yellow]"
            )
            self.console.print("[cyan]Keys should start with 'sk-ant-'[/cyan]")
            return

        # Save key
        self.config_manager.set_api_key(api_key)
        self.console.print("[bold green]✨ Your workshop key has been saved to Santa's vault![/bold green]")
        self.console.print("[green]🎄 You're all set to start coding with holiday cheer![/green]")


class ProjectCommand(Command):
    """Command to set project folder."""

    def __init__(self, config_manager: ConfigManager, console: Optional[Console] = None):
        """Initialize command.

        Args:
            config_manager: Configuration manager
            console: Rich console for output
        """
        super().__init__(console)
        self.config_manager = config_manager

    @property
    def name(self) -> str:
        return "project"

    @property
    def description(self) -> str:
        return "Set the project folder to work in"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        if args:
            # Folder provided as argument
            folder_path = args.strip()
        else:
            # Ask user for folder
            current = self.config_manager.get_project_folder()
            if current:
                self.console.print(f"[cyan]Current project folder: {current}[/cyan]")

            folder_path = Prompt.ask(
                "\n🎄 Enter the project folder path",
                default=str(current) if current else "."
            )

        # Validate and set folder
        try:
            path = Path(folder_path).expanduser().resolve()

            if not path.exists():
                create = Prompt.ask(
                    f"[yellow]📁 Folder doesn't exist. Create it?[/yellow]",
                    choices=["y", "n"],
                    default="y"
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

            # Save to config
            self.config_manager.set_project_folder(str(path))
            self.console.print(f"[bold green]🎁 Project folder set to: {path}[/bold green]")
            self.console.print("[green]🎄 All file operations will be relative to this folder![/green]")

        except Exception as e:
            self.console.print(f"[red]❌ Error: {str(e)}[/red]")


class ModelCommand(Command):
    """Command to switch Claude models."""

    def __init__(
        self,
        agent: ClaudeAgent,
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
        return "Switch between Claude models (sonnet/haiku/opus)"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        if not args:
            # Show current model and available options
            current = self.agent.model
            info = self.agent.get_model_info()
            self.console.print(f"\n[bold]Current model:[/bold] {info['emoji']} {info['name']}")
            self.console.print(f"[dim]{info['description']}[/dim]\n")

            self.console.print("[bold]Available models:[/bold]")
            for key, model_info in ClaudeAgent.MODELS.items():
                marker = "→" if key == current else " "
                self.console.print(
                    f"{marker} [cyan]{key:8}[/cyan] {model_info['emoji']} {model_info['name']}"
                )
                self.console.print(f"           {model_info['description']}")
            self.console.print("\n[dim]Usage: /model [sonnet|haiku|opus][/dim]")
            return

        # Set model
        model_name = args.strip().lower()
        if model_name in ClaudeAgent.MODELS:
            self.agent.set_model(model_name)
            self.config_manager.set_model(model_name)

            info = ClaudeAgent.MODELS[model_name]
            self.console.print(f"[bold green]{info['emoji']} Switched to {info['name']}![/bold green]")
            self.console.print(f"[green]   {info['description']}[/green]")
        else:
            self.console.print(
                f"[red]❌ Unknown model: {model_name}[/red]"
            )
            self.console.print(
                "[yellow]Available: sonnet, haiku, opus[/yellow]"
            )


class SantaCommand(Command):
    """Command to enable maximum festive mode."""

    def __init__(
        self,
        agent: ClaudeAgent,
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
        self.console.print("[green]✨ Let's spread some holiday cheer![/green]\n")


class GrinchCommand(Command):
    """Command to enable minimal mode."""

    def __init__(
        self,
        agent: ClaudeAgent,
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
        self.console.print("[dim]Festive messages disabled.[/dim]\n")


class ClearCommand(Command):
    """Command to clear the screen."""

    def __init__(self, agent: Optional[ClaudeAgent] = None, console: Optional[Console] = None):
        """Initialize command.

        Args:
            agent: Optional Claude agent (to clear history)
            console: Rich console for output
        """
        super().__init__(console)
        self.agent = agent

    @property
    def name(self) -> str:
        return "clear"

    @property
    def description(self) -> str:
        return "Clear the screen and conversation history"

    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command."""
        import os
        os.system('cls' if os.name == 'nt' else 'clear')
        if self.agent:
            self.agent.clear_history()
        self.console.print("[dim]✨ Screen cleared![/dim]")


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
        from datetime import datetime

        now = datetime.now()
        
        # Check if it's December
        if now.month != 12:
            self.console.print("\n[yellow]🎄 Advent challenges are only available during December![/yellow]")
            self.console.print("[dim]Come back in December for daily coding challenges![/dim]\n")
            return

        # Get today's day
        day = now.day
        
        # Check if it's a valid advent day (1-25)
        if day > 25:
            self.console.print("\n[green]🎅 All advent challenges complete! Merry Christmas![/green]")
            self.console.print("[dim]You can still view past challenges by typing: /advent [day][/dim]\n")
            day = 25  # Show the final challenge
        
        # If a specific day was requested
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

        # Show the challenge
        challenge = self.CHALLENGES[day]
        
        self.console.print(f"\n[bold green]🎄 Advent of Code - December {day} 🎄[/bold green]\n")
        self.console.print(f"[bold]{challenge}[/bold]\n")
        
        self.console.print("[dim]Tips:[/dim]")
        self.console.print(f"  • Just describe your solution to Clause Code")
        self.console.print(f"  • I'll help you build it step by step!")
        self.console.print(f"  • Use [cyan]/project[/cyan] to save your advent solutions\n")
        
        if not args:
            # Show progress
            completed = day - 1
            remaining = 25 - day
            if day <= 25:
                self.console.print(f"[green]Progress: {completed}/25 challenges[/green]")
                if remaining > 0:
                    self.console.print(f"[cyan]{remaining} more challenges to unlock![/cyan]\n")


class HelpCommand(Command):
    """Command to show help."""

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

        # Group commands
        config_cmds = [
            "setkey", "project", "model", "santa", "grinch"
        ]
        fun_cmds = [
            "advent"
        ]
        utility_cmds = [
            "clear", "help", "exit", "quit"
        ]

        self.console.print("[bold]Configuration:[/bold]")
        for cmd_name in config_cmds:
            if cmd_name in self.commands:
                cmd = self.commands[cmd_name]
                self.console.print(f"  [cyan]/{cmd.name:12}[/cyan] - {cmd.description}")

        self.console.print("\n[bold]Fun:[/bold]")
        for cmd_name in fun_cmds:
            if cmd_name in self.commands:
                cmd = self.commands[cmd_name]
                self.console.print(f"  [cyan]/{cmd.name:12}[/cyan] - {cmd.description}")

        self.console.print("\n[bold]Utility:[/bold]")
        for cmd_name in utility_cmds:
            if cmd_name in self.commands:
                cmd = self.commands[cmd_name]
                self.console.print(f"  [cyan]/{cmd.name:12}[/cyan] - {cmd.description}")

        self.console.print("\n[bold]Tips:[/bold]")
        self.console.print("  • Just type naturally to chat with Claude")
        self.console.print("  • Use [cyan]/project[/cyan] to set your working folder")
        self.console.print("  • Try [cyan]/advent[/cyan] for daily December challenges!")
        self.console.print("  • Code will be rendered with syntax highlighting")
        self.console.print("  • Press [cyan]Ctrl+C[/cyan] to cancel current operation")
        self.console.print("  • Press [cyan]Ctrl+D[/cyan] or type [cyan]/exit[/cyan] to quit\n")
