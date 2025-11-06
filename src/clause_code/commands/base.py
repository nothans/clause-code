"""Base command class for Clause Code."""

from abc import ABC, abstractmethod
from typing import Optional

from rich.console import Console


class Command(ABC):
    """Base class for all commands."""

    def __init__(self, console: Optional[Console] = None):
        """Initialize command.

        Args:
            console: Rich console for output
        """
        self.console = console or Console()

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name (without /).

        Returns:
            Command name string
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Command description.

        Returns:
            Description string
        """
        pass

    @abstractmethod
    async def execute(self, args: str = "", **kwargs) -> None:
        """Execute the command.

        Args:
            args: Command arguments as string
            **kwargs: Additional keyword arguments
        """
        pass

    def print_help(self) -> None:
        """Print command help."""
        self.console.print(f"[bold]/{self.name}[/bold] - {self.description}")
