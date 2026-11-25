"""Claude integration built on the Claude Agent SDK."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    AgentDefinition,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    Message,
    PermissionMode,
    ResultMessage,
    SDKSessionInfo,
    SystemMessage,
    UserMessage,
    list_sessions,
    tag_session,
)

from ._version import __version__
from .cheerlights import CheerLights
from .cheerlights_tools import READ_TOOLS, SERVER, build_server
from .console import children_ignore_ctrl_c, runtime_launcher
from .permissions import (
    WRITE_TOOLS_MATCHER,
    ToolApprover,
    is_plan_file,
    make_containment_hook,
)
from .theme import FestiveTheme, GrinchTheme

MODELS = {
    "opus": {
        "id": "claude-opus-5-5",
        "name": "Claude Opus 5.5",
        "emoji": "🎅",
        "description": "Most capable, best for complex coding and agentic work",
    },
    "sonnet": {
        "id": "claude-sonnet-5-5",
        "name": "Claude Sonnet 5.5",
        "emoji": "⛷️",
        "description": "Fast and capable for everyday coding",
    },
    "haiku": {
        "id": "claude-haiku-5-5",
        "name": "Claude Haiku 5.5",
        "emoji": "🦌",
        "description": "Fastest and cheapest, for quick questions",
    },
}
DEFAULT_MODEL = "opus"
CONTEXT_WINDOW = "1M"

# Claude asks in plain text instead; Clause Code has no UI for this tool.
DISALLOWED_TOOLS = ["AskUserQuestion"]

# Tag on Clause Code's own sessions, so /resume can tell them from other Claude Code sessions
SESSION_TAG = "clause-code"

# The checker reviews work it did not write, with a fresh context and no write tools.
CHECKER = AgentDefinition(
    description=(
        "Independent reviewer that checks the work done in this session. Use it when the "
        "user asks to check, review, or verify changes. It did not write the code, so it "
        "reads it fresh."
    ),
    prompt=(
        "You are the checker: you review changes someone else made, and you never edit files.\n"
        "1. Find what changed: run `git status` and `git diff` when the folder is a git "
        "repository, otherwise read the files the request names.\n"
        "2. Read the changed code and look for bugs, unhandled edge cases, and anything that "
        "does not do what was asked.\n"
        "3. If there are tests, run them, and check that the new tests could actually fail.\n"
        "Your first line is the verdict, exactly one word: NICE (ready), NAUGHTY (problems "
        "found; list each with file and line), or UNSURE (say what you could not check). "
        "Use these words, not PASS or FAIL. "
        "Report what you ran and what it printed. Keep it under 250 words."
    ),
    tools=["Read", "Grep", "Glob", "Bash"],
    disallowedTools=["Write", "Edit", "MultiEdit", "NotebookEdit"],
    model="sonnet",
    effort="high",
)

_PERSONA_BASE = """
You are running inside Clause Code, a holiday-themed coding assistant in the user's
terminal. If asked who you are, you are Clause Code, built on Claude.

Clause Code asks the user to approve file edits and shell commands, and it only allows
file writes inside the project folder ({project}). If the user declines an action, ask
how they would like to proceed instead of retrying it.

You have CheerLights tools. CheerLights is a global network of lights that all show one
color, which anyone can set. Use the tools when the user asks about CheerLights or its
color; do not bring it up otherwise."""

_FESTIVE_TONE = """
Bring light holiday cheer to your conversational replies: a seasonal word or emoji now
and then. Keep code, comments, commands, commit messages and file contents professional
and free of holiday theming unless the user asks for it."""

_MINIMAL_TONE = """
The user has chosen minimal mode: use a plain, professional tone with no holiday theming."""

UNDO_NOTE = (
    "[Clause Code: the user ran /undo, which restored the files you edited in your previous "
    "turn to how they were before it. Those edits are gone. Shell command effects were not "
    "undone.]\n\n"
)


def build_persona(project_folder: Path, festive: bool) -> str:
    """Build the instructions appended to Claude Code's system prompt.

    Args:
        project_folder: Folder Claude works in
        festive: Whether festive mode is on

    Returns:
        Text for the system prompt preset's ``append`` field
    """
    tone = _FESTIVE_TONE if festive else _MINIMAL_TONE
    return _PERSONA_BASE.format(project=project_folder) + "\n" + tone


class ClauseAgent:
    """A Claude Code agent session scoped to one project folder."""

    def __init__(
        self,
        project_folder: Path,
        *,
        model: str = DEFAULT_MODEL,
        festive_mode: bool = True,
        api_key: Optional[str] = None,
        approver: Optional[ToolApprover] = None,
        cheerlights: Optional[CheerLights] = None,
        resume: Optional[str] = None,
        continue_last: bool = False,
        launcher_dir: Optional[Path] = None,
        client_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient] = ClaudeSDKClient,
    ):
        """Initialize the agent.

        Args:
            project_folder: Folder Claude reads and writes in
            model: Model to use (opus, sonnet, or haiku)
            festive_mode: Whether to use festive theming
            api_key: Anthropic API key; falls back to the environment when None
            approver: Asks the user before edits and commands
            cheerlights: CheerLights service behind Claude's CheerLights tools
            resume: Session ID to resume when the first session opens
            continue_last: Continue the most recent session in this folder
            launcher_dir: Where to write the launcher that keeps the terminal's Ctrl+C
                away from the runtime on macOS and Linux (see console.py)
            client_factory: Builds the SDK client (swapped out in tests)
        """
        if model not in MODELS:
            raise ValueError(f"Unknown model: {model}")
        self.project_folder = Path(project_folder).expanduser().resolve()
        self.model = model
        self.festive_mode = festive_mode
        self.api_key = api_key
        self.approver = approver
        self.cheerlights = cheerlights or CheerLights()
        self.auto_accept_edits = False
        self.plan_mode = False
        self.session_id: Optional[str] = None
        self.stderr_tail: deque[str] = deque(maxlen=50)
        self._client_factory = client_factory
        self._client: Optional[ClaudeSDKClient] = None
        self._resume = resume
        self._continue = continue_last
        self._launcher_dir = launcher_dir
        # The UUID of each prompt this session, newest last, for /undo
        self._prompt_ids: list[str] = []
        self._pending_note = ""
        self._tagged: set[str] = set()
        # Background tasks still running (id -> description), as the runtime reports them
        self.background_tasks: dict[str, str] = {}

    @property
    def theme(self):
        """Theme matching the current mode."""
        return FestiveTheme if self.festive_mode else GrinchTheme

    @property
    def model_info(self) -> dict:
        """Information about the current model."""
        return MODELS[self.model]

    @property
    def permission_mode(self) -> PermissionMode:
        """Permission mode matching plan mode and the auto-accept setting."""
        return _mode(self.plan_mode, self.auto_accept_edits)

    @property
    def connected(self) -> bool:
        """Whether a session is open."""
        return self._client is not None

    @property
    def can_undo(self) -> bool:
        """Whether there is a turn whose file edits /undo can roll back."""
        return bool(self._prompt_ids)

    def _writes_plan_file(self, path: Path) -> bool:
        # In plan mode the runtime writes its plan under its own config folder
        return self.plan_mode and is_plan_file(path)

    def build_options(self) -> ClaudeAgentOptions:
        """Build the SDK options for a new session."""
        env = {}
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key

        containment = make_containment_hook(
            lambda: self.project_folder, allow=self._writes_plan_file
        )
        return ClaudeAgentOptions(
            model=MODELS[self.model]["id"],
            effort="high",
            cwd=str(self.project_folder),
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": build_persona(self.project_folder, self.festive_mode),
            },
            # Load the project's CLAUDE.md, skills, and .claude/settings.json, but not the
            # user's personal Claude Code settings.
            setting_sources=["project"],
            permission_mode=self.permission_mode,
            can_use_tool=self.approver,
            hooks={
                "PreToolUse": [
                    # Fail closed: if the guard itself breaks, the write is blocked
                    HookMatcher(
                        matcher=WRITE_TOOLS_MATCHER, hooks=[containment], on_failure="block"
                    )
                ]
            },
            mcp_servers={SERVER: build_server(self.cheerlights)},
            # Read-only CheerLights tools run without asking; set_color always asks
            allowed_tools=list(READ_TOOLS),
            disallowed_tools=DISALLOWED_TOOLS,
            agents={"checker": CHECKER},
            # Back up files before each edit so /undo can restore them, and replay each
            # prompt with its UUID so /undo knows where a turn began
            enable_file_checkpointing=True,
            extra_args={"replay-user-messages": None},
            resume=self._resume,
            continue_conversation=self._continue,
            include_partial_messages=True,
            client_app=f"clause-code/{__version__}",
            # macOS and Linux: start the runtime in its own session (None on Windows)
            cli_path=runtime_launcher(self._launcher_dir) if self._launcher_dir else None,
            env=env,
            stderr=self.stderr_tail.append,
        )

    async def connect(self) -> None:
        """Open a session (resuming one, if asked)."""
        if self._client is not None:
            return
        client = self._client_factory(self.build_options())
        # The runtime must not get the terminal's Ctrl+C: it would exit and end the
        # conversation. Clause Code handles Ctrl+C and interrupts the turn instead.
        with children_ignore_ctrl_c():
            await client.connect()
        self._client = client
        if self._resume:
            self.session_id = self._resume
        # Resume and continue apply to the first session only
        self._resume = None
        self._continue = False

    async def disconnect(self) -> None:
        """Close the session."""
        client, self._client = self._client, None
        if client is not None:
            await client.disconnect()

    async def new_session(self) -> None:
        """Start a fresh conversation."""
        await self.disconnect()
        if self.approver:
            self.approver.reset()
        self.session_id = None
        self._prompt_ids.clear()
        self._pending_note = ""
        await self.connect()

    async def resume(self, session_id: str) -> None:
        """Switch to an earlier conversation in this folder.

        Args:
            session_id: Session to resume
        """
        await self.disconnect()
        if self.approver:
            self.approver.reset()
        self._prompt_ids.clear()
        self._pending_note = ""
        self._resume = session_id
        await self.connect()

    async def recent_sessions(self, limit: int = 10) -> list[SDKSessionInfo]:
        """Earlier conversations in this folder, newest first."""
        sessions = await asyncio.to_thread(list_sessions, str(self.project_folder), limit, 0, False)
        return sorted(sessions, key=lambda s: s.last_modified, reverse=True)

    async def set_project(self, folder: Path) -> None:
        """Move to another project folder. Starts a new session.

        Args:
            folder: New project folder
        """
        self.project_folder = Path(folder).expanduser().resolve()
        if self.connected:
            await self.new_session()

    async def set_api_key(self, api_key: str) -> None:
        """Use a new API key. Starts a new session.

        Args:
            api_key: Anthropic API key
        """
        self.api_key = api_key
        if self.connected:
            await self.new_session()

    async def set_model(self, model: str) -> None:
        """Switch models, keeping the conversation.

        Args:
            model: Model name (opus, sonnet, or haiku)
        """
        if model not in MODELS:
            raise ValueError(f"Unknown model: {model}")
        if self._client is not None:
            await self._client.set_model(MODELS[model]["id"])
        self.model = model

    async def set_auto_accept(self, enabled: bool) -> None:
        """Turn auto-accepting file edits on or off.

        Args:
            enabled: Whether edits inside the project run without asking
        """
        await self._apply_mode(_mode(self.plan_mode, enabled))
        self.auto_accept_edits = enabled

    async def set_plan_mode(self, enabled: bool) -> None:
        """Turn plan mode on or off. In plan mode Claude reads and plans but changes nothing.

        Args:
            enabled: Whether Claude should plan before building
        """
        await self._apply_mode(_mode(enabled, self.auto_accept_edits))
        self.plan_mode = enabled

    def plan_approved(self, auto_accept: bool) -> None:
        """Record that the user approved a plan; the runtime has already left plan mode."""
        self.plan_mode = False
        self.auto_accept_edits = auto_accept

    async def _apply_mode(self, mode: PermissionMode) -> None:
        # The runtime goes first, so a failed switch leaves the setting as it was
        if self._client is not None:
            await self._client.set_permission_mode(mode)

    def set_festive_mode(self, enabled: bool) -> None:
        """Set festive mode. Claude's tone follows from the next session.

        Args:
            enabled: Whether to enable festive mode
        """
        self.festive_mode = enabled

    async def send(self, prompt: str) -> AsyncIterator[Message]:
        """Send a prompt and stream messages until Claude's turn ends.

        A turn that starts background work (a shell command or a subagent run in the
        background) stays open until that work is done. When it finishes, the runtime
        starts a follow-up turn on its own to report it; that follow-up is part of this
        turn too. Otherwise its messages would sit unread and show up under the next
        prompt, one turn out of step.

        Args:
            prompt: User message

        Yields:
            SDK messages, ending with the ResultMessage of the last turn
        """
        await self.connect()
        note, self._pending_note = self._pending_note, ""
        await self._client.query(note + prompt)
        prompt_seen = False
        async for message in self._client.receive_messages():
            if isinstance(message, UserMessage) and not prompt_seen:
                # The runtime replays the prompt first, with the UUID that /undo rewinds to
                if isinstance(message.content, str) and message.uuid:
                    prompt_seen = True
                    self._prompt_ids.append(message.uuid)
            elif (
                isinstance(message, SystemMessage) and message.subtype == "background_tasks_changed"
            ):
                self.background_tasks = {
                    task.get("task_id", ""): task.get("description", "")
                    for task in message.data.get("tasks") or []
                }
            elif isinstance(message, ResultMessage):
                self.session_id = message.session_id or self.session_id
                await self._tag(self.session_id)
            yield message
            if isinstance(message, ResultMessage) and not self.background_tasks:
                return

    async def _tag(self, session_id: Optional[str]) -> None:
        if not session_id or session_id in self._tagged:
            return
        self._tagged.add(session_id)
        try:
            await asyncio.to_thread(tag_session, session_id, SESSION_TAG, str(self.project_folder))
        except Exception:  # noqa: BLE001 - tagging only helps /resume label sessions
            pass

    async def undo(self) -> bool:
        """Restore the files Claude edited in the last turn to how they were before it.

        Each call goes back one more turn. Shell command effects are not undone.

        Returns:
            True if there was a turn to undo
        """
        if self._client is None or not self._prompt_ids:
            return False
        await self._client.rewind_files(self._prompt_ids.pop())
        self._pending_note = UNDO_NOTE
        return True

    async def context_usage(self) -> dict:
        """How full the context window is, from the runtime."""
        await self.connect()
        return await self._client.get_context_usage()

    async def interrupt(self) -> None:
        """Stop Claude's current turn, and any background work it is waiting on."""
        if self._client is None:
            return
        await self._client.interrupt()
        for task_id in list(self.background_tasks):
            try:
                await self._client.stop_task(task_id)
            except Exception:  # noqa: BLE001 - it may have finished on its own
                self.background_tasks.pop(task_id, None)

    async def __aenter__(self) -> "ClauseAgent":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()


def _mode(plan: bool, auto_accept: bool) -> PermissionMode:
    if plan:
        return "plan"
    return "acceptEdits" if auto_accept else "default"
