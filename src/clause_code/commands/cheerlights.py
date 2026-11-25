"""CheerLights mode, and a little snow."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..cheerlights import (
    HOW_TO_SET,
    PALETTE,
    CheerLights,
    CheerLightsUnavailable,
    Color,
    Setter,
    glow,
    ink_for,
    readable,
)
from ..theme import NIGHT, chip, snowfall, strand
from ..utils.config import ConfigManager
from .base import Command


def color_chip(name: str, hex_value: str) -> Text:
    """A color's name on a swatch of the color."""
    return chip(name, hex_value, ink_for(hex_value))


def color_line(cheerlights: CheerLights, color: Color, setter: Optional[Setter]) -> Text:
    """The lights in their color, then what color it is, since when, and who set it."""
    line = Text("  ")
    line.append_text(strand(glow(color.hex)))
    line.append("  ")
    line.append_text(color_chip(color.name, color.hex))
    rest = cheerlights.describe(color, setter).split(" · ", 1)[1]
    line.append(f"  {color.hex} · {rest}", style="dim")
    return line


class CheerLightsCommand(Command):
    """Follow the live CheerLights color, read its history, or set it."""

    def __init__(
        self,
        cheerlights: CheerLights,
        config_manager: ConfigManager,
        console: Optional[Console] = None,
        on_toggle: Optional[Callable[[bool], Awaitable[None]]] = None,
    ):
        """Initialize command.

        Args:
            cheerlights: The CheerLights service
            config_manager: Remembers whether CheerLights mode is on
            console: Rich console for output
            on_toggle: Called after the mode turns on or off
        """
        super().__init__(console)
        self.cheerlights = cheerlights
        self.config_manager = config_manager
        self.on_toggle = on_toggle

    @property
    def name(self) -> str:
        return "cheerlights"

    @property
    def description(self) -> str:
        return "Light the UI in the live CheerLights color (on/off/history/<color>/how)"

    async def execute(self, args: str = "", **kwargs) -> None:
        words = args.strip().lower().split()
        action = words[0] if words else ""
        if action in ("", "on"):
            await self._turn_on(announce=not self.cheerlights.following)
        elif action == "off":
            await self._turn_off()
        elif action == "history":
            count = int(words[1]) if len(words) > 1 and words[1].isdigit() else 12
            await self._history(count)
        elif action in ("how", "help"):
            self.console.print(Text(HOW_TO_SET))
        elif action.replace("-", "") in PALETTE or " ".join(words) == "old lace":
            await self._set("oldlace" if " ".join(words) == "old lace" else action)
        else:
            self.console.print(
                Text(f"❓ {args.strip()!r} is not a CheerLights color.", style="yellow")
            )
            self.console.print(Text(f"Colors: {', '.join(PALETTE)}", style="dim"))

    async def _turn_on(self, announce: bool) -> None:
        if announce:
            self.config_manager.set_cheerlights_mode(True)
            await self.cheerlights.start_live()
            if self.on_toggle:
                await self.on_toggle(True)
        try:
            color, setter = await self.cheerlights.snapshot()
        except CheerLightsUnavailable as e:
            self.console.print(
                Text(
                    f"🎄 CheerLights mode is on, but the lights are out of reach: {e}",
                    style="yellow",
                )
            )
            self.console.print(
                "[dim]Clause Code keeps trying, and lights up when they answer.[/dim]"
            )
            return
        if announce:
            self.console.print(
                "\n[bold]🎄 CheerLights mode on.[/bold] [dim]Clause Code now wears the color "
                "that lights around the world are showing, and changes when they do.[/dim]"
            )
        self.console.print(color_line(self.cheerlights, color, setter))
        if announce:
            self.console.print(
                "[dim]  /cheerlights history · /cheerlights <color> to set it · "
                "/cheerlights off[/dim]\n"
            )

    async def _turn_off(self) -> None:
        self.config_manager.set_cheerlights_mode(False)
        await self.cheerlights.stop_live()
        if self.on_toggle:
            await self.on_toggle(False)
        self.console.print(
            "[dim]🎄 CheerLights mode off. The lights stay on for everyone else.[/dim]"
        )

    async def _history(self, count: int) -> None:
        try:
            colors = await self.cheerlights.fetch_history(count)
        except CheerLightsUnavailable as e:
            self.console.print(Text(f"🧊 CheerLights history is out of reach: {e}", style="yellow"))
            return
        if not colors:
            self.console.print("[dim]No history came back.[/dim]")
            return
        strip = Text("  ")
        strip.append(" ", style=f"on {NIGHT}")
        for color in colors:
            strip.append("● ", style=f"bold {glow(color.hex)} on {NIGHT}")
        self.console.print(f"\n[bold]🎄 The last {len(colors)} colors, oldest first[/bold]")
        self.console.print(strip)
        for color in colors[-12:]:
            when = color.set_at.astimezone().strftime("%a %H:%M") if color.set_at else "?"
            line = Text(f"  {when}  ", style="dim")
            line.append_text(color_chip(color.name, color.hex))
            self.console.print(line)
        self.console.print()

    async def _set(self, color: str) -> None:
        if self.cheerlights.poster is None:
            self.console.print(Text(HOW_TO_SET))
            return
        handle = self.cheerlights.poster.handle
        self.console.print(
            Text(f'🎄 Posting "#cheerlights {color}" to Bluesky as @{handle}...', style="dim")
        )
        try:
            url = await self.cheerlights.set_color(color)
        except (ValueError, CheerLightsUnavailable) as e:
            self.console.print(Text(f"🧊 The color was not set: {e}", style="yellow"))
            return
        line = Text("✨ Posted. ", style="green")
        line.append("The lights should turn ", style="green")
        line.append_text(color_chip(color, PALETTE[color]))
        line.append(" in a few seconds.", style="green")
        self.console.print(line)
        self.console.print(Text(f"   {url}", style="dim"))


class SnowCommand(Command):
    """Let it snow, briefly."""

    SECONDS = 3.0
    FPS = 12

    def __init__(
        self,
        console: Optional[Console] = None,
        festive: Callable[[], bool] = lambda: True,
        accent: Callable[[], Optional[str]] = lambda: None,
    ):
        super().__init__(console)
        self.festive = festive
        self.accent = accent

    @property
    def name(self) -> str:
        return "snow"

    @property
    def description(self) -> str:
        return "Let it snow (three seconds of it)"

    async def execute(self, args: str = "", **kwargs) -> None:
        if not self.festive():
            self.console.print("[dim]Bah, humbug.[/dim]")
            return
        width = max(min(self.console.width - 2, 72), 10)
        frames = snowfall(width, 8, int(self.SECONDS * self.FPS))
        accent = self.accent()
        style = readable(accent) if accent else ""
        with Live(console=self.console, transient=True, refresh_per_second=self.FPS) as live:
            for frame in frames:
                text = Text("\n".join(frame[:-1]) + "\n", style=style)
                text.append(frame[-1], style="bold")
                live.update(text)
                await asyncio.sleep(1 / self.FPS)
        # The snow that settled stays behind
        self.console.print(Text(frames[-1][-1].rstrip() or "█", style="bold"))
