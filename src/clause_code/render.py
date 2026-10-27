"""Render Claude Agent SDK messages in the terminal."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Optional

from claude_agent_sdk import (
    AssistantMessage,
    Message,
    ResultMessage,
    StreamEvent,
    TextBlock,
    ToolUseBlock,
)
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.status import Status
from rich.text import Text

from .permissions import display_path

API_ERRORS = {
    "authentication_failed": "🔑 Authentication failed. Check your API key with /setkey.",
    "billing_error": "💳 There is a billing problem with your Anthropic account.",
    "rate_limit": "⏱️ Rate limit reached. Please wait a moment and try again.",
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
    for key in ("file_path", "notebook_path"):
        if tool_input.get(key):
            return display_path(tool_input[key], root)
    for key in ("command", "pattern", "url", "query", "description"):
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

    def __init__(self, console: Console, theme, get_root: Callable[[], Path]):
        """Initialize renderer.

        Args:
            console: Rich console for output
            theme: FestiveTheme or GrinchTheme
            get_root: Returns the current project folder
        """
        self.console = console
        self.theme = theme
        self.get_root = get_root
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
                Text(self.theme.get_thinking_state(), style="italic green")
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

    # Messages

    def handle(self, message: Message) -> None:
        """Render one SDK message."""
        if isinstance(message, StreamEvent):
            self._handle_stream_event(message)
        elif isinstance(message, AssistantMessage):
            self._handle_assistant(message)
        elif isinstance(message, ResultMessage):
            self._handle_result(message)

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
                self.pause()
                self._print(self._tool_line(block, subagent))
                self.start()

    def _tool_line(self, block: ToolUseBlock, subagent: bool) -> Text:
        # Subagent lines are dimmed as a whole; a base style on Text applies to every span
        line = Text(style="dim" if subagent else "")
        if subagent:
            line.append("  ↳ ")
        line.append(self.theme.get_tool_label(block.name), style="cyan")
        summary = summarize_tool_input(block.name, block.input, self.get_root())
        if summary:
            line.append(" ")
            line.append(summary, style="bold" if not subagent else "dim")
        return line

    def _handle_result(self, message: ResultMessage) -> None:
        self.pause()
        if message.terminal_reason in INTERRUPTED_REASONS:
            self.console.print(Text("⚠️  Interrupted", style="dim"))
            return
        if message.is_error:
            if self._api_error_shown:
                return  # Already explained; the CLI's own text mentions commands we don't have
            self.console.print(Text(self.theme.get_error_message(), style="bold red"))
            for error in message.errors or []:
                self.console.print(Text(error, style="red"))
            return

        stats = [f"{message.duration_ms / 1000:.1f}s"]
        if message.total_cost_usd is not None:
            stats.append(f"${message.total_cost_usd:.4f}")
        footer = Text(self.theme.get_success_message(), style="green")
        footer.append("  " + " · ".join(stats), style="dim")
        self.console.print(footer)
        self.console.print()
