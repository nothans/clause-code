"""Commands that steer the session: plan mode, resume, undo, check, context, compact."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.text import Text

from ..agent import SESSION_TAG, ClauseAgent
from ..cheerlights import ago
from .base import Command

RunTurn = Callable[[str], Awaitable[None]]

CHECK_PROMPT = (
    "Use the checker agent to review the changes made in this conversation so far. "
    "Pass it what was asked and which files changed. Then report its verdict (NICE, NAUGHTY, "
    "or UNSURE) first, "
    "followed by its findings, without fixing anything yet."
)


class PlanCommand(Command):
    """Plan mode: Claude reads and proposes a plan, and builds only after you approve it."""

    def __init__(self, agent: ClauseAgent, console: Optional[Console] = None):
        super().__init__(console)
        self.agent = agent

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return "Plan first: Claude reads and proposes, you approve before it builds (on/off)"

    async def execute(self, args: str = "", **kwargs) -> None:
        arg = args.strip().lower()
        if arg in ("on", "off"):
            enabled = arg == "on"
        elif not arg:
            enabled = not self.agent.plan_mode
        else:
            self.console.print("[yellow]Usage: /plan \\[on|off][/yellow]")
            return
        await self.agent.set_plan_mode(enabled)
        if enabled:
            self.console.print("[bold green]🗺️ Plan mode on.[/bold green]")
            self.console.print(
                "[dim]Claude reads and plans but changes nothing. When the plan is ready "
                "you approve it, and then it builds.[/dim]"
            )
        else:
            self.console.print("[green]🗺️ Plan mode off.[/green]")


class ResumeCommand(Command):
    """Pick up an earlier conversation in this folder."""

    def __init__(self, agent: ClauseAgent, console: Optional[Console] = None):
        super().__init__(console)
        self.agent = agent

    @property
    def name(self) -> str:
        return "resume"

    @property
    def description(self) -> str:
        return "Pick up an earlier conversation in this folder"

    async def execute(self, args: str = "", **kwargs) -> None:
        sessions = [
            s
            for s in await self.agent.recent_sessions(limit=20)
            if s.session_id != self.agent.session_id
        ][:10]
        if not sessions:
            self.console.print("[dim]No earlier conversations in this folder yet.[/dim]")
            return

        choice = args.strip()
        if not choice:
            now = datetime.now(timezone.utc)
            self.console.print("\n[bold]Earlier conversations in this folder:[/bold]")
            for i, info in enumerate(sessions, 1):
                when = ago(datetime.fromtimestamp(info.last_modified / 1000, timezone.utc), now)
                mark = "🎄" if info.tag == SESSION_TAG else "  "
                title = (info.custom_title or info.summary or info.first_prompt or "").strip()
                line = Text(f"{i:>3}. {mark} ")
                line.append(f"{when:<12}", style="dim")
                line.append(title.splitlines()[0][:70] if title else "(untitled)")
                self.console.print(line)
            self.console.print(
                "[dim]🎄 = started in Clause Code; the rest are Claude Code sessions.[/dim]"
            )
            choice = Prompt.ask(
                "Resume which? (number, Enter to cancel)", default="", show_default=False
            ).strip()
            if not choice:
                return

        picked = None
        if choice.isdigit() and 1 <= int(choice) <= len(sessions):
            picked = sessions[int(choice) - 1]
        else:
            picked = next((s for s in sessions if s.session_id.startswith(choice)), None)
        if picked is None:
            self.console.print(Text(f"❓ No conversation matches {choice!r}", style="yellow"))
            return

        await self.agent.resume(picked.session_id)
        title = (picked.summary or picked.first_prompt or picked.session_id).strip()
        self.console.print(Text(f"🎁 Resumed: {title.splitlines()[0][:80]}", style="bold green"))


class UndoCommand(Command):
    """Roll back the file edits from Claude's last turn."""

    def __init__(self, agent: ClauseAgent, console: Optional[Console] = None):
        super().__init__(console)
        self.agent = agent

    @property
    def name(self) -> str:
        return "undo"

    @property
    def description(self) -> str:
        return "Restore the files Claude edited in its last turn (again to go further back)"

    async def execute(self, args: str = "", **kwargs) -> None:
        if not await self.agent.undo():
            self.console.print("[dim]Nothing to undo in this conversation.[/dim]")
            return
        self.console.print(
            "[bold green]⏪ Files are back to how they were before your last message.[/bold green]"
        )
        self.console.print(
            "[dim]Shell command effects are not undone. Claude is told on your next message.[/dim]"
        )


class CheckCommand(Command):
    """Have an independent checker review the session's changes."""

    def __init__(self, run_turn: RunTurn, console: Optional[Console] = None):
        super().__init__(console)
        self.run_turn = run_turn

    @property
    def name(self) -> str:
        return "check"

    @property
    def description(self) -> str:
        return "Check it twice: a fresh reviewer that did not write the code checks it"

    async def execute(self, args: str = "", **kwargs) -> None:
        focus = f" Focus on: {args.strip()}" if args.strip() else ""
        await self.run_turn(CHECK_PROMPT + focus)


class ContextCommand(Command):
    """Show how full the context window is."""

    BAR = 30
    # Reported as categories, but they are room, not usage
    NOT_USAGE = {"Free space", "Autocompact buffer"}

    def __init__(self, agent: ClauseAgent, console: Optional[Console] = None):
        super().__init__(console)
        self.agent = agent

    @property
    def name(self) -> str:
        return "context"

    @property
    def description(self) -> str:
        return "How full Claude's stocking (context window) is"

    async def execute(self, args: str = "", **kwargs) -> None:
        usage = await self.agent.context_usage()
        total, limit = usage.get("totalTokens", 0), usage.get("maxTokens") or 1
        share = usage.get("percentage", total / limit * 100)
        filled = min(round(share / 100 * self.BAR), self.BAR)
        bar = Text("  ")
        bar.append("█" * filled, style="green" if share < 70 else "yellow")
        bar.append("░" * (self.BAR - filled), style="dim")
        bar.append(f"  {share:.0f}% · {total:,} of {limit:,} tokens")
        self.console.print("\n[bold]🧦 Claude's stocking[/bold]")
        self.console.print(bar)
        categories = sorted(
            (
                c
                for c in usage.get("categories", [])
                if c.get("tokens") and c.get("name") not in self.NOT_USAGE
            ),
            key=lambda c: c["tokens"],
            reverse=True,
        )
        for category in categories[:6]:
            self.console.print(
                Text(f"    {category['name']:<28} {category['tokens']:>9,}", style="dim")
            )
        if usage.get("isAutoCompactEnabled"):
            self.console.print(
                "[dim]  When it fills up, the conversation is compacted into a summary, and "
                "Clause Code tells you. /compact does it now.[/dim]\n"
            )


class CompactCommand(Command):
    """Compact the conversation now."""

    def __init__(self, run_turn: RunTurn, console: Optional[Console] = None):
        super().__init__(console)
        self.run_turn = run_turn

    @property
    def name(self) -> str:
        return "compact"

    @property
    def description(self) -> str:
        return "Pack the conversation down into a summary (optional: what to keep)"

    async def execute(self, args: str = "", **kwargs) -> None:
        await self.run_turn(f"/compact {args.strip()}".strip())
