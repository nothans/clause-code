"""Clause Code - The AI coding assistant that brings holiday cheer to your terminal."""

from ._version import __version__
from .agent import ClauseAgent
from .theme import FestiveTheme, GrinchTheme
from .utils.config import ConfigManager

__author__ = "Hans Scharler"
__description__ = "Festive AI coding assistant powered by the Claude Agent SDK"

__all__ = [
    "__version__",
    "ClauseAgent",
    "FestiveTheme",
    "GrinchTheme",
    "ConfigManager",
]
