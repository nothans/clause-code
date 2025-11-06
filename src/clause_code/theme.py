"""Festive theming and messages for Clause Code."""

import random
from typing import List, Tuple


class FestiveTheme:
    """Manages holiday-themed messages and styling."""

    # Thinking states - single festive words
    THINKING_STATES: List[Tuple[str, str]] = [
        ("🎅", "Sleighing..."),
        ("🎄", "Jingling..."),
        ("⛷️", "Snowboarding..."),
        ("🎁", "Unwrapping..."),
        ("❄️", "Crystallizing..."),
        ("🦌", "Dashing..."),
        ("🎵", "Caroling..."),
        ("🍪", "Baking..."),
        ("⭐", "Twinkling..."),
        ("🔔", "Ringing..."),
        ("🛷", "Sledding..."),
        ("❄️", "Frosting..."),
        ("🎿", "Skiing..."),
        ("☃️", "Snowballing..."),
        ("🕯️", "Glowing..."),
    ]

    # Success messages
    SUCCESS_MESSAGES = [
        "🎁 Ho ho ho! Your code is ready!",
        "✨ Sprinkled some magic dust on your solution!",
        "🌟 Guided by the North Star to the answer!",
        "🎄 Delivered faster than Santa's sleigh!",
        "🎅 Perfect! Added to the nice list!",
        "❄️ Fresh code, like newly fallen snow!",
    ]

    # Error messages
    ERROR_MESSAGES = [
        "🎅 Uh oh! Looks like we're on the naughty list...",
        "❄️ Hit an icy patch! Let me try a different route...",
        "🦌 Rudolph can't light the way through this fog...",
        "🎁 This present needs more wrapping!",
    ]

    # Code analysis messages
    ANALYSIS_MESSAGES = [
        "🎅 Making a list, checking it twice...",
        "🔍 Looking for who's been naughty or nice in this codebase...",
        "📋 Checking the nice list for best practices...",
        "🎄 Inspecting the code under the tree...",
    ]

    WELCOME_TREE = """
           🌟
          /|\\
         /*|*\\
        /🎁|🎁\\
       /*🎄|🎄*\\
      /🎁🎄|🎄🎁\\
     /*🎄🎁|🎁🎄*\\
    /🎄🎁🎄|🎄🎁🎄\\
          |||
          |||
"""

    WELCOME_BANNER = """
🎄 Welcome to Clause Code! 🎅
═══════════════════════════════
     *    🎄    *
   *  🎁  *  🎁  *
 🎄  Ho Ho Ho!  🎄
═══════════════════════════════
"""

    @classmethod
    def get_thinking_state(cls) -> str:
        """Get a random festive thinking state.

        Returns:
            Formatted thinking state string
        """
        emoji, word = random.choice(cls.THINKING_STATES)
        return f"{emoji} {word}"

    @classmethod
    def get_success_message(cls) -> str:
        """Get a random success message.

        Returns:
            Success message string
        """
        return random.choice(cls.SUCCESS_MESSAGES)

    @classmethod
    def get_error_message(cls) -> str:
        """Get a random error message.

        Returns:
            Error message string
        """
        return random.choice(cls.ERROR_MESSAGES)

    @classmethod
    def get_analysis_message(cls) -> str:
        """Get a random code analysis message.

        Returns:
            Analysis message string
        """
        return random.choice(cls.ANALYSIS_MESSAGES)


class GrinchTheme:
    """Minimal theme for those who prefer less festivity."""

    @staticmethod
    def get_thinking_state() -> str:
        """Get minimal thinking state.

        Returns:
            Simple thinking message
        """
        return "⚙️ Processing..."

    @staticmethod
    def get_success_message() -> str:
        """Get minimal success message.

        Returns:
            Simple success message
        """
        return "✓ Done"

    @staticmethod
    def get_error_message() -> str:
        """Get minimal error message.

        Returns:
            Simple error message
        """
        return "✗ Error occurred"

    @staticmethod
    def get_analysis_message() -> str:
        """Get minimal analysis message.

        Returns:
            Simple analysis message
        """
        return "⚙️ Analyzing..."
