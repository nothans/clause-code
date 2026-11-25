"""CheerLights as in-process tools for Claude, through the Claude Agent SDK.

The tools run inside Clause Code (an SDK MCP server), so they need no extra
process. Reading is automatic; setting the color posts to the user's Bluesky
account and always asks the user first.
"""

from typing import Any

from claude_agent_sdk import (
    McpSdkServerConfig,
    SdkMcpTool,
    ToolAnnotations,
    create_sdk_mcp_server,
    tool,
)

from ._version import __version__
from .cheerlights import PALETTE, CheerLights, CheerLightsUnavailable, ago

SERVER = "cheerlights"
GET_COLOR = f"mcp__{SERVER}__get_color"
GET_HISTORY = f"mcp__{SERVER}__get_history"
SET_COLOR = f"mcp__{SERVER}__set_color"

# Read-only tools Claude may call without asking
READ_TOOLS = [GET_COLOR, GET_HISTORY]


def _text(text: str, *, error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if error:
        result["is_error"] = True
    return result


def build_server(cheerlights: CheerLights) -> McpSdkServerConfig:
    """Build the CheerLights tool server for one session."""
    return create_sdk_mcp_server(SERVER, version=__version__, tools=make_tools(cheerlights))


def make_tools(cheerlights: CheerLights) -> list[SdkMcpTool]:
    """The CheerLights tools.

    ``set_color`` is only offered when a Bluesky account is configured, so Claude
    never sees a tool that cannot work.
    """

    @tool(
        "get_color",
        "Get the current CheerLights color: the one color that CheerLights lights around "
        "the world show right now, set by anyone. Returns the color name, hex, when it was "
        "set, and who set it when that is public.",
        {"type": "object", "properties": {}},
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def get_color(args: dict[str, Any]) -> dict[str, Any]:
        try:
            color, setter = await cheerlights.snapshot()
        except CheerLightsUnavailable as e:
            return _text(f"CheerLights is unreachable right now: {e}", error=True)
        when = color.set_at.isoformat() if color.set_at else "unknown"
        lines = [
            f"color: {color.name}",
            f"hex: {color.hex}",
            f"set_at: {when} ({ago(color.set_at, cheerlights.now())})",
        ]
        if setter:
            lines.append(f"set_by: @{setter.handle} on {setter.source} ({setter.url})")
        else:
            lines.append("set_by: not public (Discord and other channels do not say who)")
        return _text("\n".join(lines))

    @tool(
        "get_history",
        "Get the most recent CheerLights colors, oldest first, with the time each was set.",
        {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "description": "How many recent colors to return (default 10)",
                }
            },
        },
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
    )
    async def get_history(args: dict[str, Any]) -> dict[str, Any]:
        try:
            colors = await cheerlights.fetch_history(int(args.get("count") or 10))
        except (CheerLightsUnavailable, ValueError) as e:
            return _text(f"CheerLights history is unavailable right now: {e}", error=True)
        rows = [f"{c.set_at.isoformat() if c.set_at else '?'}  {c.name:8} {c.hex}" for c in colors]
        return _text("\n".join(rows) or "No history returned.")

    tools = [get_color, get_history]

    if cheerlights.poster is not None:
        handle = cheerlights.poster.handle

        @tool(
            "set_color",
            f"Set the CheerLights color for lights around the world by posting "
            f"'#cheerlights <color>' publicly from the user's Bluesky account (@{handle}). "
            f"The user approves every post. Only use this when the user asks to set the color.",
            {
                "type": "object",
                "properties": {"color": {"type": "string", "enum": list(PALETTE)}},
                "required": ["color"],
            },
            annotations=ToolAnnotations(
                read_only_hint=False, destructive_hint=False, open_world_hint=True
            ),
        )
        async def set_color(args: dict[str, Any]) -> dict[str, Any]:
            try:
                url = await cheerlights.set_color(str(args.get("color", "")))
            except (ValueError, CheerLightsUnavailable) as e:
                return _text(f"The color was not set: {e}", error=True)
            return _text(
                f"Posted '#cheerlights {args['color']}' to Bluesky: {url}\n"
                "The CheerLights service usually applies it within a few seconds."
            )

        tools.append(set_color)

    return tools
