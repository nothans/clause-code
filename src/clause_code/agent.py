"""Claude integration built on the Claude Agent SDK."""

from collections import deque
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    Message,
    PermissionMode,
)

from ._version import __version__
from .permissions import WRITE_TOOLS_MATCHER, ToolApprover, make_containment_hook
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

_PERSONA_BASE = """
You are running inside Clause Code, a holiday-themed coding assistant in the user's
terminal. If asked who you are, you are Clause Code, built on Claude.

Clause Code asks the user to approve file edits and shell commands, and it only allows
file writes inside the project folder ({project}). If the user declines an action, ask
how they would like to proceed instead of retrying it."""

_FESTIVE_TONE = """
Bring light holiday cheer to your conversational replies: a seasonal word or emoji now
and then. Keep code, comments, commands, commit messages and file contents professional
and free of holiday theming unless the user asks for it."""

_MINIMAL_TONE = """
The user has chosen minimal mode: use a plain, professional tone with no holiday theming."""


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
        client_factory: Callable[[ClaudeAgentOptions], ClaudeSDKClient] = ClaudeSDKClient,
    ):
        """Initialize the agent.

        Args:
            project_folder: Folder Claude reads and writes in
            model: Model to use (opus, sonnet, or haiku)
            festive_mode: Whether to use festive theming
            api_key: Anthropic API key; falls back to the environment when None
            approver: Asks the user before edits and commands
            client_factory: Builds the SDK client (swapped out in tests)
        """
        if model not in MODELS:
            raise ValueError(f"Unknown model: {model}")
        self.project_folder = Path(project_folder).expanduser().resolve()
        self.model = model
        self.festive_mode = festive_mode
        self.api_key = api_key
        self.approver = approver
        self.auto_accept_edits = False
        self.stderr_tail: deque[str] = deque(maxlen=50)
        self._client_factory = client_factory
        self._client: Optional[ClaudeSDKClient] = None

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
        """Permission mode matching the auto-accept setting."""
        return "acceptEdits" if self.auto_accept_edits else "default"

    @property
    def connected(self) -> bool:
        """Whether a session is open."""
        return self._client is not None

    def build_options(self) -> ClaudeAgentOptions:
        """Build the SDK options for a new session."""
        env = {"CLAUDE_AGENT_SDK_CLIENT_APP": f"clause-code/{__version__}"}
        if self.api_key:
            env["ANTHROPIC_API_KEY"] = self.api_key

        return ClaudeAgentOptions(
            model=MODELS[self.model]["id"],
            effort="high",
            cwd=str(self.project_folder),
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": build_persona(self.project_folder, self.festive_mode),
            },
            # Load the project's CLAUDE.md and .claude/settings.json, but not the
            # user's personal Claude Code settings.
            setting_sources=["project"],
            permission_mode=self.permission_mode,
            can_use_tool=self.approver,
            hooks={
                "PreToolUse": [
                    HookMatcher(
                        matcher=WRITE_TOOLS_MATCHER,
                        hooks=[make_containment_hook(lambda: self.project_folder)],
                    )
                ]
            },
            disallowed_tools=DISALLOWED_TOOLS,
            include_partial_messages=True,
            env=env,
            stderr=self.stderr_tail.append,
        )

    async def connect(self) -> None:
        """Open a new session."""
        if self._client is not None:
            return
        client = self._client_factory(self.build_options())
        await client.connect()
        self._client = client

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
        await self.connect()

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
        if self._client is not None:
            await self._client.set_permission_mode("acceptEdits" if enabled else "default")
        self.auto_accept_edits = enabled

    def set_festive_mode(self, enabled: bool) -> None:
        """Set festive mode. Claude's tone follows from the next session.

        Args:
            enabled: Whether to enable festive mode
        """
        self.festive_mode = enabled

    async def send(self, prompt: str) -> AsyncIterator[Message]:
        """Send a prompt and stream messages until Claude's turn ends.

        Args:
            prompt: User message

        Yields:
            SDK messages, ending with a ResultMessage
        """
        await self.connect()
        await self._client.query(prompt)
        async for message in self._client.receive_response():
            yield message

    async def interrupt(self) -> None:
        """Stop Claude's current turn."""
        if self._client is not None:
            await self._client.interrupt()

    async def __aenter__(self) -> "ClauseAgent":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()
