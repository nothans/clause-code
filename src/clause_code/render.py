"""Render Claude Agent SDK messages in the terminal."""

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from claude_agent_sdk import (
    AssistantMessage,
    Message,
    RateLimitEvent,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TextBlock,
    ToolUseBlock,
)
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.status import Status
from rich.text import Text

from .cheerlights import CheerLights, glow, ink_for, readable
from .permissions import display_path, is_plan_file
from .theme import chip, strand

API_ERRORS = {
    "authentication_failed": "🔑 Authentication failed. Check your API key with /setkey.",
    "billing_error": "💳 There is a billing problem with your Anthropic account.",
    "rate_limit": "⏳ Rate limit reached. Please wait a moment and try again.",
    "invalid_request": "The API rejected the request.",
    "server_error": "The Anthropic API had a server error. Please try again shortly.",
}

INTERRUPTED_REASONS = {"aborted_streaming", "aborted_tools"}

SUMMARY_WIDTH = 80


def summarize_tool_input(tool_name: str, tool_input: dict[str, Any], root: Path) -> str:
    """One-line summary of what a tool call targets.

    Args:
        tool_name: Tool name
        tool_input: Tool input
        root: Project folder, used to shorten paths

    Returns:
        Short description such as a path, command, or search pattern
    """
    if tool_name == "ToolSearch":
        # "select:mcp__cheerlights__get_color,ExitPlanMode" -> "get_color, ExitPlanMode"
        query = str(tool_input.get("query", "")).removeprefix("select:")
        return ", ".join(name.rsplit("__", 1)[-1] for name in query.split(",") if name)
    for key in ("file_path", "notebook_path"):
        if tool_input.get(key):
            if is_plan_file(tool_input[key]):
                return Path(tool_input[key]).name
            return display_path(tool_input[key], root)
    for key in ("command", "pattern", "url", "query", "description", "color"):
        if tool_input.get(key):
            value = str(tool_input[key]).strip().splitlines()[0]
            if len(value) > SUMMARY_WIDTH:
                value = value[: SUMMARY_WIDTH - 1] + "…"
            return value
    return ""


class TurnRenderer:
    """Shows one turn of Claude's work: a spinner, streamed text, and tool calls.

    Model output is always rendered as Text or Markdown, never as Rich markup,
    so brackets in code (``arr[i]``, ``x[/]``) print as written.
    """

    def __init__(
        self,
        console: Console,
        theme,
        get_root: Callable[[], Path],
        *,
        cheerlights: Optional[CheerLights] = None,
        background: Callable[[], dict[str, str]] = dict,
    ):
        """Initialize renderer.

        Args:
            console: Rich console for output
            theme: FestiveTheme or GrinchTheme
            get_root: Returns the current project folder
            cheerlights: When set (CheerLights mode), the UI takes the live color and the
                end of a turn shows what the lights did meanwhile
            background: Returns the background tasks the turn is still waiting for
        """
        self.console = console
        self.theme = theme
        self.get_root = get_root
        self.cheerlights = cheerlights
        self.background = background
        self._started = datetime.now(timezone.utc)
        # A turn can span several results when it waits for background work
        self._spent_ms = 0
        self._spent_usd: Optional[float] = None
        # Subagent lines that arrived mid-sentence, shown when the sentence ends
        self._after_text: list = []
        self._status: Optional[Status] = None
        self._live: Optional[Live] = None
        self._buffer = ""
        self._streamed_ids: set[str] = set()
        self._api_error_shown = False
        # While an approval prompt is open, output is queued and the spinner stays off
        self._held = False
        self._deferred: list = []

    # Spinner and live preview. Rich allows one live display at a time.

    def start(self) -> None:
        """Show the thinking spinner."""
        if self._held:
            return
        if self._status is None and self._live is None:
            self._status = self.console.status(
                Text(self.theme.get_thinking_state(), style=f"italic {self._accent('green')}"),
                spinner_style=self._accent("green"),
            )
            self._status.start()

    def pause(self) -> None:
        """Stop any live display, e.g. before asking the user something."""
        self._flush_text()
        if self._status is not None:
            self._status.stop()
            self._status = None

    def hold(self) -> None:
        """Keep the prompt line clear while the user is asked something.

        Parallel tool calls keep streaming while the first one waits for approval;
        their output is queued until release() instead of printing over the prompt.
        """
        self.pause()
        self._held = True

    def release(self) -> None:
        """Print what arrived during the prompt and resume the spinner."""
        self._held = False
        for renderable in self._deferred:
            self.console.print(renderable)
        self._deferred.clear()
        self.start()

    def finish(self) -> None:
        """Clean up at the end of a turn."""
        self._held = False
        self.pause()
        for renderable in self._deferred:
            self.console.print(renderable)
        self._deferred.clear()

    def _print(self, renderable) -> None:
        if self._held:
            self._deferred.append(renderable)
        else:
            self.console.print(renderable)

    def _preview(self) -> Text:
        # While streaming, show the tail of the text; the full reply is printed
        # as Markdown once the block is complete.
        height = max(self.console.size.height - 4, 5)
        tail = "\n".join(self._buffer.splitlines()[-height:])
        return Text(tail, style="dim")

    def _append_text(self, text: str) -> None:
        if self._held:
            self._buffer += text
            return
        if self._status is not None:
            self._status.stop()
            self._status = None
        self._buffer += text
        if self._live is None:
            self._live = Live(
                self._preview(), console=self.console, transient=True, refresh_per_second=8
            )
            self._live.start()
        else:
            self._live.update(self._preview())

    def _flush_text(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None
        if self._buffer.strip():
            self._print(Markdown(self._buffer))
        self._buffer = ""
        for line in self._after_text:
            self._print(line)
        self._after_text.clear()

    def _accent(self, default: str) -> str:
        """The live CheerLights color in CheerLights mode, otherwise the theme's color.

        Only the spinner wears it. Tool labels and the footer keep their own colors, so a
        red light never makes a finished turn look like an error.
        """
        if self.cheerlights is not None and self.cheerlights.current is not None:
            hex_value = self.cheerlights.current.hex
            return readable(hex_value) if hex_value else default
        return default

    # Messages

    def handle(self, message: Message) -> None:
        """Render one SDK message."""
        if isinstance(message, StreamEvent):
            self._handle_stream_event(message)
        elif isinstance(message, AssistantMessage):
            self._handle_assistant(message)
        elif isinstance(message, ResultMessage):
            self._handle_result(message)
        elif isinstance(message, (TaskStartedMessage, TaskNotificationMessage)):
            self._handle_task(message)
        elif isinstance(message, SystemMessage) and message.subtype == "compact_boundary":
            self._handle_compaction(message)
        elif isinstance(message, RateLimitEvent):
            self._handle_rate_limit(message)

    def _notice(self, text: str, style: str = "dim") -> None:
        self.pause()
        self._print(Text(text, style=style))
        self.start()

    def _handle_task(self, message) -> None:
        if isinstance(message, TaskStartedMessage):
            label = self.theme.get_task_label("started")
            self._notice(f"{label} {message.description or message.task_id}")
        else:
            label = self.theme.get_task_label(message.status)
            summary = (message.summary or "").strip().splitlines()
            self._notice(f"{label} {summary[0] if summary else message.task_id}")

    def _handle_compaction(self, message: SystemMessage) -> None:
        # Compaction drops detail from the conversation; never let it happen silently
        meta = message.data.get("compact_metadata") or {}
        before, after = meta.get("pre_tokens"), meta.get("post_tokens")
        sizes = f" ({before:,} → {after:,} tokens)" if before and after else ""
        how = "you asked" if meta.get("trigger") == "manual" else "the context was filling up"
        self._notice(
            f"{self.theme.get_compaction_label()}{sizes}, because {how}. "
            "Earlier details are now a summary; restate anything that matters.",
            style="yellow",
        )

    def _handle_rate_limit(self, message: RateLimitEvent) -> None:
        info = message.rate_limit_info
        if info.get("status") == "rejected":
            self._notice("⏳ Rate limit reached; Claude is waiting for it to reset.", "yellow")
        elif info.get("status") == "allowed_warning":
            used = info.get("utilization")
            share = f" ({used:.0%} used)" if isinstance(used, (int, float)) else ""
            self._notice(f"⏳ Getting close to a rate limit{share}.", "yellow")

    def _handle_stream_event(self, message: StreamEvent) -> None:
        if message.parent_tool_use_id:
            return  # Subagent output stays out of the main transcript
        event = message.event
        kind = event.get("type")
        if kind == "message_start":
            message_id = event.get("message", {}).get("id")
            if message_id:
                self._streamed_ids.add(message_id)
        elif kind == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                self._append_text(delta.get("text", ""))
        elif kind == "content_block_stop" and self._buffer:
            self._flush_text()
            self.start()

    def _handle_assistant(self, message: AssistantMessage) -> None:
        if message.error:
            self.pause()
            self._print(
                Text(API_ERRORS.get(message.error, self.theme.get_error_message()), style="yellow")
            )
            self._api_error_shown = True
            return

        subagent = message.parent_tool_use_id is not None
        for block in message.content:
            if isinstance(block, TextBlock) and not subagent:
                if message.message_id in self._streamed_ids:
                    continue  # Already shown from the stream
                self.pause()
                self._print(Markdown(block.text))
                self.start()
            elif isinstance(block, ToolUseBlock):
                if subagent and self._buffer:
                    # Don't cut Claude's sentence in half with a subagent's step
                    self._after_text.append(self._tool_line(block, subagent))
                    continue
                self.pause()
                self._print(self._tool_line(block, subagent))
                self.start()

    def _tool_line(self, block: ToolUseBlock, subagent: bool) -> Text:
        # Subagent lines are dimmed as a whole; a base style on Text applies to every span
        line = Text(style="dim" if subagent else "")
        if subagent:
            line.append("  ↳ ")
        name = block.name
        if name in ("Write", "Edit") and is_plan_file(block.input.get("file_path", "")):
            name = "PlanFile"
        line.append(self.theme.get_tool_label(name), style="cyan")
        summary = summarize_tool_input(block.name, block.input, self.get_root())
        if summary:
            line.append(" ")
            line.append(summary, style="bold" if not subagent else "dim")
        return line

    def _handle_result(self, message: ResultMessage) -> None:
        self.pause()
        if message.terminal_reason in INTERRUPTED_REASONS:
            self.console.print(Text("✋ Interrupted", style="dim"))
            return
        if message.is_error:
            if self._api_error_shown:
                return  # Already explained; the CLI's own text mentions commands we don't have
            self.console.print(Text(self.theme.get_error_message(), style="red"))
            for error in message.errors or []:
                self.console.print(Text(error, style="red"))
            return

        self._spent_ms += message.duration_ms or 0
        if message.total_cost_usd is not None:
            self._spent_usd = (self._spent_usd or 0) + message.total_cost_usd
        waiting = self.background()
        if waiting:
            first = next(iter(waiting.values())) or "a background task"
            more = f" and {len(waiting) - 1} more" if len(waiting) > 1 else ""
            self.console.print(
                Text(
                    f"{self.theme.get_task_label('waiting')} {first}{more} · Ctrl+C stops it",
                    style="dim",
                )
            )
            self.start()
            return

        stats = [f"{self._spent_ms / 1000:.1f}s"]
        if self._spent_usd is not None:
            stats.append(f"${self._spent_usd:.4f}")
        # The stats are spans of their own, so they are dim gray rather than dim green
        footer = Text()
        footer.append(self.theme.get_success_message(), style="green")
        footer.append("  " + " · ".join(stats), style="dim")
        self.console.print(footer)
        self._show_lights()
        self.console.print()

    def _show_lights(self) -> None:
        """In CheerLights mode, end a finished task with the lights as they are right now."""
        cheer = self.cheerlights
        if cheer is None or cheer.current is None:
            return
        color = cheer.current
        line = Text("  ")
        line.append_text(strand(glow(color.hex)))
        changes = cheer.changes_since(self._started)
        if changes:
            line.append("  While you worked, the lights went ", style="dim")
            for i, change in enumerate(changes[-6:]):
                if i:
                    line.append(" → ", style="dim")
                line.append_text(chip(change.name, change.hex, ink_for(change.hex)))
        else:
            line.append("  Lights around the world are ", style="dim")
            line.append_text(chip(color.name, color.hex, ink_for(color.hex)))
            line.append(" right now.", style="dim")
        self.console.print(line)
