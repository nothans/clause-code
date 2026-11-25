"""Unicode output that works in every terminal.

Clause Code prints emoji, box drawing, bullets, and bulbs. Whether a terminal can show
them depends on how the output is encoded:

- A Windows console (Windows Terminal or the classic console) takes Unicode directly,
  whatever its code page, so everything prints as written.
- Output piped or redirected to a file is written as UTF-8. Python would otherwise use
  the Windows ANSI code page (cp1252), which has no emoji, and stop with an error.
- A terminal whose encoding cannot hold a character gets an ASCII stand-in for it,
  chosen per character from ``FALLBACKS``. That covers a legacy code page console
  (``PYTHONLEGACYWINDOWSSTDIO``), a Latin-1 locale, and ASCII mode.

ASCII mode (``CLAUSE_CODE_ASCII=1``) is for a terminal whose font cannot show emoji
whatever the encoding. It is on by default for the Linux console (``TERM=linux``).

Text is fitted to the encoding before Rich lays it out, so panels and columns keep
their widths. A codec error handler on stdout and stderr is the safety net for
everything else, so a character the terminal cannot take never stops the app.
"""

import codecs
import copy
import getpass
import io
import os
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from functools import lru_cache
from typing import Optional, TextIO

from rich.console import Console, ConsoleOptions, RenderableType
from rich.panel import Panel
from rich.segment import Segment
from rich.text import Span, Text
from rich.theme import Theme

ASCII_ENV = "CLAUSE_CODE_ASCII"
# Name of the codec error handler that writes ASCII stand-ins
ERRORS = "clause-code-ascii"

# ASCII stand-ins for the characters Clause Code prints, and for common ones in Claude's
# replies. Emoji that only decorate a line stand in as "" (and take their space with them);
# emoji that carry meaning get a mark.
FALLBACKS: dict[str, str] = {
    # Lines, bulbs, and bars
    "─": "-",
    "━": "=",
    "═": "=",
    "│": "|",
    "●": "o",
    "○": "o",
    "★": "*",
    "█": "#",
    "▌": "|",
    "▐": "|",
    "░": ".",
    # Punctuation
    "•": "-",
    "·": "|",
    "…": "...",
    "–": "-",  # en dash
    "\u2014": "--",  # em dash
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    " ": " ",
    "→": "->",
    "←": "<-",
    "↳": "`-",
    # Marks with a meaning
    "✓": "+",
    "✔": "+",
    "✅": "+",
    "✗": "x",
    "✘": "x",
    "❌": "x",
    "❓": "?",
    "❗": "!",
    "⚠": "!",
    "⏪": "<<",
    "⏳": "...",
    "✋": "!",
    "🔑": "!",
    "💳": "!",
    # Festive decoration
    "🌟": "*",
    "⭐": "*",
    "✨": "*",
    "❄": "*",
    "⛄": "",
    "🎄": "",
    "🎅": "",
    "🎁": "",
    "🧝": "",
    "🦌": "",
    "🏂": "",
    "🎿": "",
    "🛷": "",
    "🔔": "",
    "🎵": "",
    "🍪": "",
    "🏮": "",
    "🧊": "",
    "🧁": "",
    "🎀": "",
    "📜": "",
    "📝": "",
    "📨": "",
    "📋": "",
    "📁": "",
    "🔍": "",
    "🧭": "",
    "🧰": "",
    "🔧": "",
    "🧦": "",
    "🔐": "",
    "🗺": "",
}

# A spinner for terminals that cannot show Rich's default braille one
ASCII_SPINNER = "line"
DEFAULT_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

STYLES = Theme(
    {
        # Rich's prompt colors fight the rest of the UI; keep choices plain and quiet
        "prompt.choices": "bold",
        "prompt.default": "dim",
    }
)


def fallback(char: str) -> str:
    """The ASCII stand-in for one character."""
    if char.isascii():
        return char
    if char in FALLBACKS:
        return FALLBACKS[char]
    code = ord(char)
    if 0x2500 <= code <= 0x257F:  # box drawing
        name = unicodedata.name(char, "")
        if "HORIZONTAL" in name and "VERTICAL" not in name:
            return "=" if "DOUBLE" in name or "HEAVY" in name else "-"
        if "VERTICAL" in name and "HORIZONTAL" not in name:
            return "|"
        return "+"
    if 0x2580 <= code <= 0x259F:  # block elements
        return "#"
    if 0x2800 <= code <= 0x28FF:  # braille, as in spinners
        return "."
    category = unicodedata.category(char)
    if category in ("Mn", "Me", "Cf") or 0xFE00 <= code <= 0xFE0F:
        return ""  # combining marks, joiners, variation selectors
    if 0x1F3FB <= code <= 0x1F3FF:
        return ""  # skin tone modifiers
    folded = unicodedata.normalize("NFKD", char).encode("ascii", "ignore").decode("ascii")
    if folded:
        return folded
    if category == "Zs":
        return " "
    if category.startswith("S"):
        return ""  # an emoji or symbol with no ASCII meaning
    return "?"


@lru_cache(maxsize=4096)
def _encodes(char: str, encoding: str) -> bool:
    try:
        char.encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def encodes(text: str, encoding: str) -> bool:
    """Whether every character of text can be written in this encoding."""
    if text.isascii() or is_utf8(encoding):
        return True
    return all(_encodes(char, encoding) for char in text)


def _fit(text: str, encoding: str) -> tuple[str, list[int]]:
    """Replace what the encoding cannot hold; also map old offsets to new ones."""
    out: list[str] = []
    offsets: list[int] = []
    length = 0
    skip_space = False
    for i, char in enumerate(text):
        offsets.append(length)
        if skip_space and char == " ":
            skip_space = False
            continue
        piece = char if _encodes(char, encoding) else fallback(char)
        category = unicodedata.category(char)
        if not piece and category in ("Mn", "Cf"):
            continue  # a variation selector or joiner after a dropped emoji keeps the skip
        skip_space = False
        if not piece and category.startswith("S"):
            # "🎄 Ready" becomes "Ready", not " Ready"
            skip_space = i == 0 or text[i - 1].isspace()
        out.append(piece)
        length += len(piece)
    offsets.append(length)
    return "".join(out), offsets


def fit(text: str, encoding: str) -> str:
    """Text with every character the encoding cannot hold replaced by its ASCII stand-in."""
    if encodes(text, encoding):
        return text
    return _fit(text, encoding)[0]


def fit_text(text: Text, encoding: str) -> Text:
    """A Rich Text fitted to the encoding, with its styles kept on the same characters."""
    if encodes(text.plain, encoding):
        return text
    plain, offsets = _fit(text.plain, encoding)
    spans = [
        Span(offsets[span.start], offsets[min(span.end, len(offsets) - 1)], span.style)
        for span in text.spans
    ]
    return Text(
        plain,
        style=text.style,
        justify=text.justify,
        overflow=text.overflow,
        no_wrap=text.no_wrap,
        end=text.end,
        tab_size=text.tab_size,
        spans=[span for span in spans if span.start < span.end],
    )


def _handle_encode_error(error: UnicodeError) -> tuple[str, int]:
    """Codec error handler: write ASCII stand-ins for characters the stream cannot take."""
    if not isinstance(error, UnicodeEncodeError):
        raise error
    text, start, end = error.object, error.start, error.end
    replacement = "".join(fallback(char) for char in text[start:end])
    if (
        not replacement
        and end < len(text)
        and text[end] == " "
        and (start == 0 or text[start - 1].isspace())
    ):
        end += 1
    return replacement, end


codecs.register_error(ERRORS, _handle_encode_error)


def is_utf8(encoding: Optional[str]) -> bool:
    """Whether an encoding name means UTF-8."""
    if not encoding:
        return False
    try:
        return codecs.lookup(encoding).name in ("utf-8", "utf-8-sig")
    except LookupError:
        return False


def ascii_requested(environ: Mapping[str, str]) -> bool:
    """Whether output should be plain ASCII: CLAUSE_CODE_ASCII, or the Linux console."""
    value = environ.get(ASCII_ENV, "").strip().lower()
    if value:
        return value not in ("0", "false", "no", "off")
    return environ.get("TERM") == "linux"


def console_code_page(stream: TextIO) -> Optional[int]:
    """The output code page of the Windows console a stream writes bytes to.

    None off Windows, when there is no console, and for Python's own console writer,
    which takes Unicode whatever the code page. With PYTHONLEGACYWINDOWSSTDIO, Python
    writes the console in the ANSI code page (cp1252) while the console reads its own
    (437 by default), so a middle dot came out as a box-drawing corner.
    """
    if os.name != "nt":
        return None
    raw = getattr(getattr(stream, "buffer", None), "raw", None)
    if raw is None or type(raw).__name__ == "_WindowsConsoleIO":
        return None
    try:
        if not stream.isatty():
            return None
    except (ValueError, OSError):
        return None
    import ctypes

    return ctypes.windll.kernel32.GetConsoleOutputCP() or None


def output_encoding(
    stream: TextIO, environ: Mapping[str, str], console_cp: Optional[int] = None
) -> Optional[str]:
    """The encoding to switch an output stream to, or None to keep its own.

    - ASCII mode: "ascii".
    - PYTHONIOENCODING set: keep what the user chose.
    - A Windows console written as bytes (``console_cp``): the console's code page.
    - Any other terminal: keep its encoding, which says what it can show. On Windows
      this is already Unicode for any console.
    - A pipe or file that is not UTF-8: "utf-8".
    """
    current = getattr(stream, "encoding", None) or ""
    if ascii_requested(environ):
        return None if codecs.lookup(current or "ascii").name == "ascii" else "ascii"
    if environ.get("PYTHONIOENCODING"):
        return None
    try:
        terminal = stream.isatty()
    except (ValueError, OSError):
        terminal = False
    if terminal and console_cp:
        wanted = "utf-8" if console_cp == 65001 else f"cp{console_cp}"
        try:
            same = codecs.lookup(wanted).name == codecs.lookup(current or "ascii").name
        except LookupError:
            return None  # a code page Python has no codec for
        return None if same else wanted
    if terminal or is_utf8(current):
        return None
    return "utf-8"


def prepare_stream(stream: Optional[TextIO], environ: Mapping[str, str]) -> None:
    """Switch an output stream to the right encoding, with ASCII stand-ins as its safety net."""
    if stream is None or not hasattr(stream, "reconfigure"):
        return
    target = output_encoding(stream, environ, console_code_page(stream))
    try:
        stream.flush()
        if target is not None:
            stream.reconfigure(encoding=target, errors=ERRORS)
        elif not is_utf8(stream.encoding):
            stream.reconfigure(errors=ERRORS)
    except (ValueError, OSError, io.UnsupportedOperation, LookupError):
        pass  # a stream that cannot be changed keeps working as it was


def enable_windows_vt() -> Callable[[], None]:
    """Turn on VT processing for a Windows console, and return how to turn it off again.

    The classic console starts with it off, and Rich then falls back to 16 colors. With
    it on, Rich uses 24-bit color there too, as it does in Windows Terminal.
    """
    if os.name != "nt":
        return lambda: None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    enable_vt = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    changed: list[tuple[int, int]] = []
    for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
        handle = kernel32.GetStdHandle(std_handle)
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)) or mode.value & enable_vt:
            continue
        if kernel32.SetConsoleMode(handle, mode.value | enable_vt):
            changed.append((handle, mode.value))

    def restore() -> None:
        for handle, mode in changed:
            kernel32.SetConsoleMode(handle, mode)

    return restore


def prepare_terminal(environ: Mapping[str, str] = os.environ) -> Callable[[], None]:
    """Get stdout and stderr ready for Clause Code; returns how to undo the console change."""
    import sys

    prepare_stream(sys.stdout, environ)
    prepare_stream(sys.stderr, environ)
    return enable_windows_vt()


class TerminalConsole(Console):
    """A Rich console that prints only what its output can show.

    Text the output's encoding cannot hold is fitted with ASCII stand-ins before Rich
    measures it, so borders and columns stay aligned. Rich's own syntax highlighting of
    numbers and paths is off: it colored version numbers and slashes at random.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("highlight", False)
        kwargs.setdefault("theme", STYLES)
        super().__init__(*args, **kwargs)

    def print(self, *objects, **kwargs) -> None:
        self.follow_code_page()
        super().print(*objects, **kwargs)

    def follow_code_page(self) -> None:
        """Keep a legacy Windows console stream in the console's current code page.

        The Claude Code runtime shares the console and switches it to UTF-8 (65001) while
        it runs, and back when it exits, so the code page chosen at start goes stale.
        """
        stream = self.file
        if console_code_page(stream) is not None:
            prepare_stream(stream, os.environ)

    def shows(self, text: str) -> bool:
        """Whether every character of text reaches the terminal as written."""
        return encodes(text, self.encoding)

    def fit(self, text: str) -> str:
        """Text as this console will show it."""
        return fit(text, self.encoding)

    def render(
        self, renderable: RenderableType, options: Optional[ConsoleOptions] = None
    ) -> Iterable[Segment]:
        # Every Text passes through here, nested ones too (Rich renders recursively)
        if isinstance(renderable, Text) and not self.shows(renderable.plain):
            renderable = fit_text(renderable, self.encoding)
        elif isinstance(renderable, Panel):
            renderable = self._fit_panel(renderable)
        return super().render(renderable, options)

    def _fit_panel(self, panel: Panel) -> Panel:
        # A panel sizes its top and bottom borders from its titles before rendering them
        fitted = {}
        for name in ("title", "subtitle"):
            value = getattr(panel, name)
            if isinstance(value, str):
                value = Text.from_markup(value)
            if isinstance(value, Text) and not self.shows(value.plain):
                fitted[name] = fit_text(value, self.encoding)
        if not fitted:
            return panel
        panel = copy.copy(panel)
        for name, value in fitted.items():
            setattr(panel, name, value)
        return panel

    def status(self, status: RenderableType, *, spinner: str = "dots", **kwargs):
        if spinner == "dots" and not self.shows(DEFAULT_SPINNER_FRAMES):
            spinner = ASCII_SPINNER
        return super().status(status, spinner=spinner, **kwargs)


def ask_secret(console: Console, prompt: str) -> str:
    """Ask for a secret without echoing it.

    The prompt goes through the console: on Windows, getpass writes its prompt one UTF-16
    unit at a time, which turns emoji into boxes.
    """
    console.print(Text(prompt), end="")
    return getpass.getpass("")
