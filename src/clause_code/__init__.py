"""Clause Code - The AI coding assistant that brings holiday cheer to your terminal."""

__version__ = "1.0.0"
__author__ = "Clause Code Team"
__description__ = "Festive AI coding assistant powered by Claude"

from .agent import ClaudeAgent
from .theme import FestiveTheme, GrinchTheme
from .utils.config import ConfigManager

__all__ = [
    "ClaudeAgent",
    "FestiveTheme",
    "GrinchTheme",
    "ConfigManager",
]
