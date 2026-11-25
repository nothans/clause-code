"""Festive theming and messages for Clause Code."""

import random
from datetime import date
from typing import List, Optional, Tuple

TASK_STATES = {
    "started": "🧝 An elf started on",
    "completed": "🧝 An elf finished:",
    "failed": "🧝 An elf hit a snag:",
    "stopped": "🧝 An elf was called back:",
    "waiting": "🧝 Waiting for an elf:",
}


def sleeps_until_christmas(today: date) -> int:
    """Days from today until the next December 25 (0 on Christmas Day)."""
    christmas = date(today.year, 12, 25)
    if today > christmas:
        christmas = date(today.year + 1, 12, 25)
    return (christmas - today).days


def christmas_countdown(today: date) -> str:
    """A line for the welcome screen."""
    sleeps = sleeps_until_christmas(today)
    if sleeps == 0:
        return "🎁 Merry Christmas!"
    if sleeps == 1:
        return "🌟 Christmas Eve: one more sleep!"
    return f"🎄 {sleeps} sleeps until Christmas"


def snowfall(width: int, height: int, frames: int, seed: Optional[int] = None) -> List[List[str]]:
    """Frames of falling snow, each a list of text rows.

    Flakes fall one row per frame and drift a little; snow that lands builds up on
    the bottom row.
    """
    rng = random.Random(seed)
    flakes: List[List[int]] = []  # [column, row]
    ground = [0] * width
    shapes = "*❄·+"
    out: List[List[str]] = []
    for _ in range(frames):
        for _ in range(max(width // 12, 1)):
            flakes.append([rng.randrange(width), 0])
        moved = []
        for col, row in flakes:
            col = min(max(col + rng.choice((-1, 0, 0, 1)), 0), width - 1)
            row += 1
            if row >= height - 1:
                ground[col] = 1
            else:
                moved.append([col, row])
        flakes = moved
        grid = [[" "] * width for _ in range(height)]
        for col, row in flakes:
            grid[row][col] = shapes[(col + row) % len(shapes)]
        grid[height - 1] = ["█" if g else " " for g in ground]
        out.append(["".join(r) for r in grid])
    return out


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

    # How each tool call is announced while Claude works
    TOOL_LABELS = {
        "Read": "📜 Reading",
        "Write": "🎁 Wrapping up",
        "Edit": "✂️ Re-wrapping",
        "MultiEdit": "✂️ Re-wrapping",
        "NotebookEdit": "✂️ Re-wrapping",
        "Bash": "🔔 Running",
        "Grep": "🔍 Checking it twice:",
        "Glob": "🗺️ Mapping",
        "WebFetch": "🦌 Fetching",
        "WebSearch": "🌟 Searching the skies for",
        "Agent": "🧝 Sending an elf to",
        "Task": "🧝 Sending an elf to",
        "TodoWrite": "📋 Updating the list",
        "PowerShell": "🔔 Running",
        "ExitPlanMode": "🗺️ Handing over the plan",
        "PlanFile": "🗺️ Sketching the plan",
        "ToolSearch": "🧰 Unpacking",
        "mcp__cheerlights__get_color": "🎄 Checking the lights",
        "mcp__cheerlights__get_history": "🎄 Reading the lights' diary",
        "mcp__cheerlights__set_color": "🎄 Changing the lights to",
    }

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

    @classmethod
    def get_tool_label(cls, tool_name: str) -> str:
        """Get the festive label for a tool call.

        Args:
            tool_name: Name of the tool Claude is using

        Returns:
            Label shown before the tool's target
        """
        return cls.TOOL_LABELS.get(tool_name, f"🛠️ Using {tool_name}")

    @classmethod
    def get_task_label(cls, state: str) -> str:
        """Label for a background task starting or ending."""
        return TASK_STATES.get(state, "🧝 An elf says:")

    @classmethod
    def get_compaction_label(cls) -> str:
        """Label shown when the conversation is compacted."""
        return "🛷 The sleigh was full, so the conversation was packed down"


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

    @staticmethod
    def get_tool_label(tool_name: str) -> str:
        """Get minimal tool label.

        Args:
            tool_name: Name of the tool Claude is using

        Returns:
            The tool name
        """
        return f"→ {tool_name}"

    @staticmethod
    def get_task_label(state: str) -> str:
        """Minimal label for a background task starting or ending."""
        return f"→ background task {state}:"

    @staticmethod
    def get_compaction_label() -> str:
        """Minimal compaction label."""
        return "Conversation compacted"
