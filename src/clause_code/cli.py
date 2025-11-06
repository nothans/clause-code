"""Main CLI for Clause Code."""

import asyncio
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .agent import ClaudeAgent
from .commands import (
    AdventCommand,
    ClearCommand,
    GrinchCommand,
    HelpCommand,
    ModelCommand,
    ProjectCommand,
    SantaCommand,
    SetKeyCommand,
)
from .theme import FestiveTheme
from .utils.config import ConfigManager
from .utils.file_writer import FileExtractor


class ClauseCodeCLI:
    """Main CLI application for Clause Code."""

    def __init__(self):
        """Initialize CLI."""
        self.console = Console()
        self.config_manager = ConfigManager()
        self.agent = None
        self.commands = {}
        self.running = False

    def show_welcome(self):
        """Show festive welcome screen."""
        self.console.clear()
        self.console.print(FestiveTheme.WELCOME_TREE, style="green", justify="center")
        self.console.print(
            "[bold green]Clause Code v1.0.0[/bold green]", justify="center"
        )
        self.console.print(
            "[dim]The AI coding assistant with holiday cheer[/dim]\n",
            justify="center",
        )

    def show_main_screen(self):
        """Show main interface screen."""
        model_info = self.agent.get_model_info()
        project = self.config_manager.get_project_folder()

        banner = f"""[bold]═══ Clause Code v1.0.0 ═══════════════════════════════════════════════════[/bold]

    Welcome back Santa's Helper!

{FestiveTheme.WELCOME_TREE}
    {model_info['emoji']} {model_info['name']} • Anthropic API
    {f"📁 {project}" if project else "📁 No project folder set"}

[dim]─────────────────────────────────────────────────────────────────────────────[/dim]

    [bold]Tips for getting started[/bold]
    • Use [cyan]/project[/cyan] to set your working folder
    • Use [cyan]/help[/cyan] to see all commands
    • Just type naturally to chat with Claude
    • Code will be rendered with syntax highlighting

    [bold]Current Settings[/bold]
    Model: {model_info['name']}
    Mode: {"🎅 Festive" if self.agent.festive_mode else "⚙️ Minimal"}
    Context: 200K tokens • Output: {model_info['max_tokens']//1000}K tokens

[dim]═════════════════════════════════════════════════════════════════════════════[/dim]
"""
        self.console.print(banner)

    async def setup_first_run(self) -> bool:
        """Setup for first run.

        Returns:
            True if setup successful, False otherwise
        """
        self.show_welcome()

        self.console.print(FestiveTheme.WELCOME_BANNER)
        self.console.print("[bold]Let's get your workshop set up![/bold]\n")

        # Check API key
        api_key = self.config_manager.get_api_key()
        if not api_key:
            self.console.print(
                "[yellow]🎅 I don't see an API key configured yet.[/yellow]"
            )
            self.console.print(
                "[cyan]Get your key from: https://console.anthropic.com/account/keys[/cyan]\n"
            )

            import getpass

            api_key = getpass.getpass("🔐 Enter your Anthropic API key (hidden): ")

            if not api_key or not api_key.startswith("sk-ant-"):
                self.console.print(
                    "[red]❌ Invalid or missing API key. Please run 'clause-code' again.[/red]"
                )
                return False

            self.config_manager.set_api_key(api_key)
            self.console.print(
                "[green]✨ API key saved![/green]\n"
            )

        # Check project folder
        project = self.config_manager.get_project_folder()
        if not project:
            self.console.print(
                "[yellow]📁 No project folder configured.[/yellow]"
            )
            set_project = Prompt.ask(
                "Would you like to set a project folder now?",
                choices=["y", "n"],
                default="y",
            )

            if set_project.lower() == "y":
                folder_path = Prompt.ask(
                    "🎄 Enter project folder path", default="."
                )
                try:
                    path = Path(folder_path).expanduser().resolve()
                    if not path.exists():
                        create = Prompt.ask(
                            "Create folder?", choices=["y", "n"], default="y"
                        )
                        if create.lower() == "y":
                            path.mkdir(parents=True, exist_ok=True)
                    self.config_manager.set_project_folder(str(path))
                    self.console.print(f"[green]✨ Project folder set: {path}[/green]")
                except Exception as e:
                    self.console.print(f"[yellow]⚠️  {e}[/yellow]")

        # Ask about festive mode
        config = self.config_manager.load()
        festive = Prompt.ask(
            "\n❄️  Enable festive mode?", choices=["y", "n"], default="y"
        )
        if festive.lower() == "n":
            config.festive_mode = False
            self.config_manager.save(config)

        self.console.print(
            "\n[bold green]✨ Configuration saved to ~/.clause-code/config.json[/bold green]"
        )
        self.console.print(
            "[green]🎄 Your workshop is ready! Let's start coding with holiday cheer![/green]\n"
        )

        return True

    def initialize_commands(self):
        """Initialize all commands."""
        # Help command needs reference to all commands, so we create it last
        self.commands = {
            "setkey": SetKeyCommand(self.config_manager, self.console),
            "project": ProjectCommand(self.config_manager, self.console),
            "model": ModelCommand(self.agent, self.config_manager, self.console),
            "santa": SantaCommand(self.agent, self.config_manager, self.console),
            "grinch": GrinchCommand(self.agent, self.config_manager, self.console),
            "advent": AdventCommand(self.console),
            "clear": ClearCommand(self.agent, self.console),
        }

        # Add help command
        self.commands["help"] = HelpCommand(self.commands, self.console)

    async def handle_command(self, command_line: str) -> bool:
        """Handle a slash command.

        Args:
            command_line: Command line starting with /

        Returns:
            True to continue, False to exit
        """
        parts = command_line[1:].split(maxsplit=1)
        cmd_name = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Handle exit/quit
        if cmd_name in ["exit", "quit"]:
            return False

        # Handle other commands
        if cmd_name in self.commands:
            try:
                await self.commands[cmd_name].execute(args)
            except Exception as e:
                self.console.print(f"[red]❌ Error: {e}[/red]")
        else:
            self.console.print(
                f"[yellow]❓ Unknown command: /{cmd_name}[/yellow]"
            )
            self.console.print("[dim]Type /help to see available commands[/dim]")

        return True

    async def chat_loop(self):
        """Main chat loop."""
        # Set up prompt session with history
        history_file = self.config_manager.config_dir / "history"
        session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=WordCompleter(
                [f"/{cmd}" for cmd in self.commands.keys()],
                ignore_case=True,
            ),
        )

        self.console.print(
            "[bold green]🎄 Ready! What would you like to build today?[/bold green]\n"
        )

        while self.running:
            try:
                # Get user input
                user_input = await session.prompt_async("🎅 > ")

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    should_continue = await self.handle_command(user_input)
                    if not should_continue:
                        break
                    continue

                # Chat with Claude
                try:
                    # Get current project folder
                    project_folder = self.config_manager.get_project_folder()
                    
                    full_response = []
                    async for chunk in self.agent.chat(
                        user_input, 
                        project_folder=str(project_folder) if project_folder else None
                    ):
                        self.console.print(chunk, end="")
                        full_response.append(chunk)

                    self.console.print()  # New line after response
                    
                    # Auto-write files if project folder is set
                    if project_folder:
                        response_text = "".join(full_response)
                        file_extractor = FileExtractor(self.console)
                        files = file_extractor.extract_files(response_text)
                        
                        if files:
                            self.console.print(f"\n[bold cyan]📁 Writing {len(files)} file(s) to project...[/bold cyan]")
                            created = file_extractor.write_files(files, project_folder)
                            if created:
                                self.console.print(f"[bold green]✨ Successfully created {len(created)} file(s)![/bold green]\n")

                except KeyboardInterrupt:
                    self.console.print("\n[dim]⚠️  Cancelled[/dim]")
                    continue

            except KeyboardInterrupt:
                self.console.print("\n[dim]Use /exit or Ctrl+D to quit[/dim]")
                continue
            except EOFError:
                break

    async def run(self):
        """Run the CLI application."""
        try:
            # Check if first run needed
            config = self.config_manager.load()
            if not config.api_key:
                success = await self.setup_first_run()
                if not success:
                    return 1
                config = self.config_manager.load()

            # Initialize agent
            self.agent = ClaudeAgent(
                api_key=config.api_key,
                model=config.default_model,
                festive_mode=config.festive_mode,
                console=self.console,
            )

            # Initialize commands
            self.initialize_commands()

            # Show main screen
            self.show_main_screen()

            # Check if project folder is set
            if not config.project_folder:
                self.console.print(
                    "[yellow]💡 Tip: Use [cyan]/project[/cyan] to set a working folder for file operations[/yellow]\n"
                )

            # Start chat loop
            self.running = True
            await self.chat_loop()

            # Goodbye message
            self.console.print(
                "\n[bold green]🎄 Thanks for coding with Clause Code![/bold green]"
            )
            self.console.print(
                "[green]❄️  May your code compile and your bugs be few![/green]\n"
            )

            return 0

        except Exception as e:
            self.console.print(f"\n[red]❌ Fatal error: {e}[/red]")
            return 1


def main():
    """Main entry point."""
    cli = ClauseCodeCLI()
    exit_code = asyncio.run(cli.run())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
