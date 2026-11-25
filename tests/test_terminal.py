"""Tests for Unicode output: the encoding choice, the ASCII stand-ins, and the console."""

import ast
import io
import os
import pathlib
import subprocess
import sys

import pytest
from rich.panel import Panel
from rich.text import Text

import clause_code
from clause_code.terminal import (
    ASCII_ENV,
    ERRORS,
    FALLBACKS,
    TerminalConsole,
    ascii_requested,
    encodes,
    fallback,
    fit,
    fit_text,
    output_encoding,
    prepare_stream,
)


class FakeStream(io.TextIOWrapper):
    """A text stream over bytes that says whether it is a terminal."""

    def __init__(self, encoding: str, tty: bool, errors: str = "strict"):
        super().__init__(io.BytesIO(), encoding=encoding, errors=errors, newline="\n")
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty

    def written(self) -> bytes:
        self.flush()
        return self.buffer.getvalue()


def app_strings():
    """Every string constant in the app, except the fallback table itself."""
    root = pathlib.Path(clause_code.__file__).parent
    for path in root.rglob("*.py"):
        if path.name == "terminal.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                yield node.value


class TestFallbackTable:
    def test_every_stand_in_is_ascii(self):
        for char, stand_in in FALLBACKS.items():
            assert stand_in.isascii(), char

    def test_every_glyph_the_app_prints_has_a_real_stand_in(self):
        """No "?" soup: each non-ASCII character in the app maps to something chosen."""
        for text in app_strings():
            for char in text:
                if char.isascii():
                    continue
                chosen = char in FALLBACKS or fallback(char) != "?"
                assert chosen, f"{char!r} (U+{ord(char):04X}) in {text!r}"

    @pytest.mark.parametrize(
        ("char", "expected"),
        [
            ("●", "o"),
            ("─", "-"),
            ("═", "="),
            ("╭", "+"),  # a corner, by the box-drawing rule
            ("┃", "|"),
            ("▓", "#"),
            ("⠋", "."),  # a braille spinner frame
            ("é", "e"),  # accents fold away
            ("️", ""),  # variation selector
            ("‍", ""),  # zero-width joiner
            ("→", "->"),
            ("…", "..."),
            ("\u2014", "--"),
            ("✓", "+"),
            ("❌", "x"),
            ("🎄", ""),
            ("中", "?"),  # a letter with no ASCII form is the last resort
        ],
    )
    def test_stand_ins(self, char, expected):
        assert fallback(char) == expected


class TestFit:
    def test_utf8_keeps_everything(self):
        assert fit("🎄 Ready! ●─●", "utf-8") == "🎄 Ready! ●─●"

    def test_decorative_emoji_take_their_space_with_them(self):
        assert fit("🎄 Ready! What would you like to build today?", "ascii") == (
            "Ready! What would you like to build today?"
        )
        assert fit("  🧭 Mapping", "ascii") == "  Mapping"

    def test_meaningful_marks_stay(self):
        assert fit("❌ Not a folder", "ascii") == "x Not a folder"
        assert fit("a → b", "ascii") == "a -> b"

    def test_a_variation_selector_goes_with_its_emoji(self):
        assert fit("🗺️ Mapping", "ascii") == "Mapping"
        assert fit("❄️ cold", "ascii") == "* cold"

    def test_cp1252_keeps_what_it_can(self):
        # cp1252 has the middle dot and the bullet, but no bulb or box drawing
        assert fit("a · b • c ●─●", "cp1252") == "a · b • c o-o"

    def test_cp437_keeps_box_drawing(self):
        assert fit("═══ ● ═══", "cp437") == "═══ o ═══"

    def test_fit_text_keeps_styles_on_their_characters(self):
        text = Text("🎄 Ready ", style="green")
        text.append("●", style="red")
        text.append(" now", style="bold")
        fitted = fit_text(text, "ascii")
        assert fitted.plain == "Ready o now"
        styles = {fitted.plain[span.start : span.end]: str(span.style) for span in fitted.spans}
        assert styles == {"o": "red", " now": "bold"}
        assert fitted.style == "green"

    def test_fit_text_returns_the_same_object_when_nothing_changes(self):
        text = Text("plain")
        assert fit_text(text, "ascii") is text


class TestErrorHandler:
    """The safety net on stdout and stderr: no character ever stops the app."""

    def test_cp1252_pipe_writes_stand_ins(self):
        stream = FakeStream("cp1252", tty=False, errors=ERRORS)
        stream.write("🎄 Ready ●─● · done ✓")
        assert stream.written() == "Ready o-o · done +".encode("cp1252")

    def test_ascii_stream_never_raises(self):
        stream = FakeStream("ascii", tty=True, errors=ERRORS)
        stream.write("中文 ⠋ 🎅 > ️")
        assert stream.written() == b"?? . > "

    def test_without_the_handler_it_crashes(self):
        """The bug this module fixes, reproduced on a cp1252 stream."""
        stream = FakeStream("cp1252", tty=False)
        with pytest.raises(UnicodeEncodeError):
            stream.write("🌟")
            stream.flush()


class TestEncodingChoice:
    def test_a_cp1252_pipe_becomes_utf8(self):
        assert output_encoding(FakeStream("cp1252", tty=False), {}) == "utf-8"

    def test_a_terminal_keeps_its_encoding(self):
        assert output_encoding(FakeStream("cp437", tty=True), {}) is None

    def test_utf8_is_left_alone(self):
        assert output_encoding(FakeStream("utf-8", tty=False), {}) is None

    def test_pythonioencoding_is_respected(self):
        stream = FakeStream("cp1252", tty=False)
        assert output_encoding(stream, {"PYTHONIOENCODING": "cp1252"}) is None

    def test_ascii_mode(self):
        assert output_encoding(FakeStream("utf-8", tty=True), {ASCII_ENV: "1"}) == "ascii"
        assert output_encoding(FakeStream("ascii", tty=True), {ASCII_ENV: "1"}) is None

    def test_a_legacy_windows_console_gets_its_own_code_page(self):
        """Regression: with PYTHONLEGACYWINDOWSSTDIO, Python wrote cp1252 to a code page 437
        console, so a middle dot showed as a box corner and an ellipsis as an accented a."""
        stream = FakeStream("cp1252", tty=True)
        assert output_encoding(stream, {}, console_cp=437) == "cp437"
        assert output_encoding(stream, {}, console_cp=65001) == "utf-8"
        assert output_encoding(stream, {}, console_cp=1252) is None
        assert output_encoding(stream, {}, console_cp=99999) is None  # no codec for it

    def test_the_console_code_page_only_matters_for_a_terminal(self):
        assert output_encoding(FakeStream("cp1252", tty=False), {}, console_cp=437) == "utf-8"

    def test_pythonioencoding_wins_over_the_console(self):
        stream = FakeStream("cp1252", tty=True)
        assert output_encoding(stream, {"PYTHONIOENCODING": "cp1252"}, console_cp=437) is None

    def test_only_byte_streams_on_a_console_report_a_code_page(self):
        from clause_code.terminal import console_code_page

        # Not a console: an in-memory stream has no raw console handle behind it
        assert console_code_page(FakeStream("cp1252", tty=True)) is None
        assert console_code_page(io.StringIO()) is None

        class _WindowsConsoleIO(io.RawIOBase):
            """Stands in for Python's Unicode console writer, which needs no code page."""

            def writable(self) -> bool:
                return True

        unicode_console = io.TextIOWrapper(io.BufferedWriter(_WindowsConsoleIO()))
        assert console_code_page(unicode_console) is None

    def test_legacy_console_stream_encodes_for_code_page_437(self):
        stream = FakeStream("cp1252", tty=True)
        stream.reconfigure(encoding=output_encoding(stream, {}, console_cp=437), errors=ERRORS)
        stream.write("a · b … c ═ ●")
        assert stream.written() == "a · b ... c ═ o".encode("cp437")

    def test_the_console_follows_a_code_page_change(self, monkeypatch):
        """The runtime switches a shared console to 65001 while it runs and back to 437
        after; output written in between must follow, or 437 bytes show as U+FFFD."""
        import clause_code.terminal as terminal

        code_page = {"now": 437}
        monkeypatch.setattr(terminal, "console_code_page", lambda stream: code_page["now"])
        stream = FakeStream("cp1252", tty=True, errors=ERRORS)
        console = TerminalConsole(file=stream, width=40, color_system=None)

        console.print("a · b")
        code_page["now"] = 65001
        console.print("a · b 🎄")
        code_page["now"] = 437
        console.print("a · b 🎄")

        assert stream.written() == (
            "a · b\n".encode("cp437") + "a · b 🎄\n".encode("utf-8") + "a · b \n".encode("cp437")
        )

    def test_linux_console_is_ascii_unless_told_otherwise(self):
        assert ascii_requested({"TERM": "linux"})
        assert not ascii_requested({"TERM": "linux", ASCII_ENV: "0"})
        assert not ascii_requested({"TERM": "xterm-256color"})


class TestPrepareStream:
    def test_pipe_switches_to_utf8(self):
        stream = FakeStream("cp1252", tty=False)
        prepare_stream(stream, {})
        stream.write("🎄 ●")
        assert stream.encoding == "utf-8"
        assert stream.written() == "🎄 ●".encode("utf-8")

    def test_legacy_terminal_keeps_its_code_page_and_gets_stand_ins(self):
        stream = FakeStream("cp437", tty=True)
        prepare_stream(stream, {})
        stream.write("🎄 Ready ═ ●")
        assert stream.encoding == "cp437"
        assert stream.written() == "Ready ═ o".encode("cp437")

    def test_ascii_mode_on_a_utf8_terminal(self):
        stream = FakeStream("utf-8", tty=True)
        prepare_stream(stream, {ASCII_ENV: "1"})
        stream.write("🎅 > ●")
        assert stream.written() == b"> o"

    def test_a_stream_without_reconfigure_is_left_alone(self):
        stream = io.StringIO()
        prepare_stream(stream, {})
        prepare_stream(None, {})


class TestTerminalConsole:
    def console(self, encoding: str) -> TerminalConsole:
        return TerminalConsole(
            file=FakeStream(encoding, tty=False, errors=ERRORS), width=40, color_system=None
        )

    def test_panel_borders_stay_aligned_in_ascii(self):
        console = self.console("ascii")
        console.print(Panel(Text("🎄 Ready → go ●─●"), title="📜 Plan"))
        lines = console.file.written().decode("ascii").splitlines()
        assert len({len(line) for line in lines}) == 1, lines
        assert "Ready -> go o-o" in lines[1]

    def test_markup_strings_are_fitted(self):
        console = self.console("ascii")
        console.print("[bold]🎄 Ready![/bold] ✨ done")
        assert console.file.written() == b"Ready! * done\n"

    def test_utf8_prints_as_written(self):
        console = self.console("utf-8")
        console.print("🎄 Ready ●")
        assert console.file.written().decode("utf-8") == "🎄 Ready ●\n"

    def test_no_auto_highlighting(self):
        """Regression: Rich colored "3.0" in the version and the tree's slashes."""
        console = TerminalConsole(
            file=io.StringIO(), width=40, force_terminal=True, color_system="truecolor"
        )
        console.print("Clause Code v3.0.0 /help")
        assert "\x1b" not in console.file.getvalue()

    def test_spinner_choice(self):
        assert self.console("ascii").status("x").renderable.name == "line"
        assert self.console("utf-8").status("x").renderable.name == "dots"

    def test_shows(self):
        assert self.console("cp1252").shows("a · b")
        assert not self.console("cp1252").shows("●")
        assert encodes("●", "utf-8")


class TestEndToEnd:
    """Run the real entry point with its output on a pipe, as `clause-code > out.txt` does."""

    def run(self, tmp_path, **env):
        environ = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PYTHONIOENCODING", "PYTHONUTF8", ASCII_ENV)
        }
        environ.update(
            HOME=str(tmp_path),
            USERPROFILE=str(tmp_path),
            ANTHROPIC_API_KEY="sk-ant-test",
            **env,
        )
        missing = tmp_path / "no-such-folder"
        return subprocess.run(
            [sys.executable, "-m", "clause_code", "--project", str(missing)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=environ,
            timeout=60,
        )

    def test_emoji_reach_a_pipe_as_utf8(self, tmp_path):
        done = self.run(tmp_path)
        assert done.returncode == 1, done.stderr.decode("utf-8", "replace")
        assert b"Traceback" not in done.stderr
        assert "❌ Not a folder" in done.stdout.decode("utf-8")

    def test_ascii_mode_writes_ascii(self, tmp_path):
        done = self.run(tmp_path, **{ASCII_ENV: "1"})
        assert done.returncode == 1
        assert done.stdout.isascii()
        assert b"x Not a folder" in done.stdout
