"""Tool permissions: approval prompts and project-folder containment."""

import asyncio
import difflib
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Optional

from claude_agent_sdk import (
    HookContext,
    HookInput,
    HookJSONOutput,
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

# Built-in tools that write files, and the input key that holds the target path.
WRITE_TOOLS = {
    "Write": "file_path",
    "Edit": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}
WRITE_TOOLS_MATCHER = "|".join(WRITE_TOOLS)

# Tools that can never be approved for a whole session at once.
NEVER_ALWAYS = {"Bash"}

PREVIEW_LINES = 40
# Wrap rather than crop, so nothing the user approves is hidden off the edge
PREVIEW_STYLE = {"theme": "ansi_dark", "word_wrap": True}

AskFn = Callable[[str], Awaitable[str]]


def is_within(path: str | Path, root: Path) -> bool:
    """Check whether a path resolves to a location inside root.

    Args:
        path: Absolute path, or a path relative to root
        root: Directory the path must stay inside

    Returns:
        True if the resolved path is root or below it
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def display_path(path: str, root: Path) -> str:
    """Show a path relative to root when it is inside it."""
    try:
        return str(Path(path).resolve().relative_to(root.resolve()))
    except ValueError:
        return path


def make_containment_hook(get_root: Callable[[], Path]):
    """Build a PreToolUse hook that denies file writes outside the project folder.

    Hooks run on every tool call, so this holds even when edits are
    auto-accepted.

    Args:
        get_root: Returns the current project folder

    Returns:
        Hook callback for ClaudeAgentOptions.hooks
    """

    async def guard_writes(
        input_data: HookInput, tool_use_id: Optional[str], context: HookContext
    ) -> HookJSONOutput:
        key = WRITE_TOOLS.get(input_data.get("tool_name", ""))
        if key is None:
            return {}
        target = input_data.get("tool_input", {}).get(key)
        root = get_root()
        if target and not is_within(target, root):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        f"{target} is outside the project folder {root}. "
                        "Clause Code only writes files inside the project folder."
                    ),
                }
            }
        return {}

    return guard_writes


def _truncate(text: str, limit: int = PREVIEW_LINES) -> str:
    lines = text.splitlines()
    if len(lines) <= limit:
        return text
    return "\n".join(lines[:limit] + [f"... ({len(lines) - limit} more lines)"])


def _diff(path: str, old: str, new: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), f"a/{path}", f"b/{path}", lineterm=""
        )
    )


def render_request(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
    root: Path,
) -> RenderableType:
    """Render a permission request so the user can see exactly what will happen.

    Args:
        tool_name: Tool Claude wants to use
        tool_input: Tool input
        context: Permission context from the SDK
        root: Project folder, used to shorten paths

    Returns:
        Rich renderable describing the request
    """
    title = context.title or f"Claude wants to use {tool_name}"
    path = display_path(tool_input.get("file_path", ""), root)
    parts: list[RenderableType] = []

    if tool_name == "Edit":
        diff = _diff(path, tool_input.get("old_string", ""), tool_input.get("new_string", ""))
        parts.append(Syntax(_truncate(diff), "diff", **PREVIEW_STYLE))
    elif tool_name == "MultiEdit":
        diffs = [
            _diff(path, edit.get("old_string", ""), edit.get("new_string", ""))
            for edit in tool_input.get("edits", [])
        ]
        parts.append(Syntax(_truncate("\n".join(diffs)), "diff", **PREVIEW_STYLE))
    elif tool_name == "Write":
        content = tool_input.get("content", "")
        parts.append(Text(f"{path} ({len(content.splitlines())} lines)", style="bold"))
        lexer = Syntax.guess_lexer(path, code=content)
        parts.append(
            Syntax(_truncate(content.rstrip("\n")), lexer, line_numbers=True, **PREVIEW_STYLE)
        )
    elif tool_name == "Bash":
        if tool_input.get("description"):
            parts.append(Text(tool_input["description"], style="dim"))
        parts.append(Syntax(tool_input.get("command", ""), "bash", **PREVIEW_STYLE))
    else:
        parts.append(Text(_truncate(json.dumps(tool_input, indent=2))))

    if context.blocked_path:
        parts.append(Text(f"Outside the allowed folders: {context.blocked_path}", style="yellow"))
    if context.decision_reason:
        parts.append(Text(context.decision_reason, style="dim"))

    return Panel(Group(*parts), title=Text(title), title_align="left", border_style="yellow")


class ToolApprover:
    """Asks the user before Claude edits files or runs commands.

    Used as the SDK's ``can_use_tool`` callback, which runs whenever Claude
    Code's permission rules would otherwise prompt.
    """

    def __init__(
        self,
        console: Console,
        ask: AskFn,
        get_root: Callable[[], Path],
    ):
        """Initialize approver.

        Args:
            console: Rich console for output
            ask: Async function that shows a prompt and returns the user's answer
            get_root: Returns the current project folder
        """
        self.console = console
        self.ask = ask
        self.get_root = get_root
        self.always_allowed: set[str] = set()
        # Set by the CLI so spinners pause while the user is asked something
        self.before_prompt: Optional[Callable[[], None]] = None
        self.after_prompt: Optional[Callable[[], None]] = None
        # Parallel tool calls can request permission at the same time; ask one at a time
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        """Forget session-wide approvals."""
        self.always_allowed.clear()

    async def __call__(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ) -> PermissionResult:
        """Decide whether a tool call may run."""
        async with self._lock:
            # Checked under the lock: an earlier prompt may have just said "always"
            if tool_name in self.always_allowed:
                return PermissionResultAllow()

            if self.before_prompt:
                self.before_prompt()
            try:
                return await self._ask_user(tool_name, tool_input, context)
            finally:
                if self.after_prompt:
                    self.after_prompt()

    async def _ask_user(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ) -> PermissionResult:
        self.console.print(render_request(tool_name, tool_input, context, self.get_root()))

        can_always = tool_name not in NEVER_ALWAYS
        prompt = (
            "Allow? [y]es / [a]lways for this session / [n]o: "
            if can_always
            else "Allow? [y]es / [n]o: "
        )
        try:
            answer = (await self.ask(prompt)).strip().lower()
        except (KeyboardInterrupt, EOFError):
            return PermissionResultDeny(message="The user interrupted.", interrupt=True)

        if answer in ("y", "yes"):
            return PermissionResultAllow()
        if can_always and answer in ("a", "always"):
            self.always_allowed.add(tool_name)
            return PermissionResultAllow()
        return PermissionResultDeny(
            message="The user declined this action. Ask them how they would like to proceed."
        )
