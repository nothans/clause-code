"""Tests for festive theming system."""

import pytest

from clause_code.theme import FestiveTheme, GrinchTheme


class TestFestiveTheme:
    """Test cases for FestiveTheme class."""

    def test_thinking_states_exist(self):
        """Test that thinking states are defined."""
        assert len(FestiveTheme.THINKING_STATES) > 0

        # Check structure of thinking states
        for emoji, message in FestiveTheme.THINKING_STATES:
            assert isinstance(emoji, str)
            assert isinstance(message, str)
            assert len(emoji) > 0
            assert len(message) > 0

    def test_success_messages_exist(self):
        """Test that success messages are defined."""
        assert len(FestiveTheme.SUCCESS_MESSAGES) > 0

        for message in FestiveTheme.SUCCESS_MESSAGES:
            assert isinstance(message, str)
            assert len(message) > 0

    def test_error_messages_exist(self):
        """Test that error messages are defined."""
        assert len(FestiveTheme.ERROR_MESSAGES) > 0

        for message in FestiveTheme.ERROR_MESSAGES:
            assert isinstance(message, str)
            assert len(message) > 0

    def test_analysis_messages_exist(self):
        """Test that analysis messages are defined."""
        assert len(FestiveTheme.ANALYSIS_MESSAGES) > 0

        for message in FestiveTheme.ANALYSIS_MESSAGES:
            assert isinstance(message, str)
            assert len(message) > 0

    def test_prompt_and_ready_line(self):
        assert FestiveTheme.prompt == "🎅 > "
        assert FestiveTheme.ready.startswith("🎄 Ready!")
        assert GrinchTheme.prompt == "> "
        assert GrinchTheme.ready.isascii()

    def test_get_thinking_state(self):
        """Test getting a random thinking state."""
        state = FestiveTheme.get_thinking_state()

        assert isinstance(state, str)
        assert len(state) > 0

        # Should contain an emoji and text
        parts = state.split()
        assert len(parts) >= 2

    def test_get_thinking_state_randomness(self):
        """Test that thinking states are random (probabilistic test)."""
        states = [FestiveTheme.get_thinking_state() for _ in range(20)]

        # With 15+ different states, we should get at least a few unique ones
        unique_states = set(states)
        assert len(unique_states) > 1

    def test_get_success_message(self):
        """Test getting a success message."""
        message = FestiveTheme.get_success_message()

        assert isinstance(message, str)
        assert len(message) > 0
        assert message in FestiveTheme.SUCCESS_MESSAGES

    def test_get_error_message(self):
        """Test getting an error message."""
        message = FestiveTheme.get_error_message()

        assert isinstance(message, str)
        assert len(message) > 0
        assert message in FestiveTheme.ERROR_MESSAGES

    def test_get_analysis_message(self):
        """Test getting an analysis message."""
        message = FestiveTheme.get_analysis_message()

        assert isinstance(message, str)
        assert len(message) > 0
        assert message in FestiveTheme.ANALYSIS_MESSAGES


class TestGrinchTheme:
    """Test cases for GrinchTheme class."""

    def test_get_thinking_state(self):
        """Test Grinch theme thinking state."""
        state = GrinchTheme.get_thinking_state()

        assert isinstance(state, str)
        assert state == "Working..."

    def test_get_success_message(self):
        """Test Grinch theme success message."""
        message = GrinchTheme.get_success_message()

        assert isinstance(message, str)
        assert "Done" in message

    def test_get_error_message(self):
        """Test Grinch theme error message."""
        message = GrinchTheme.get_error_message()

        assert isinstance(message, str)
        assert "Error" in message

    def test_get_analysis_message(self):
        """Test Grinch theme analysis message."""
        message = GrinchTheme.get_analysis_message()

        assert isinstance(message, str)
        assert "Analyzing" in message

    def test_grinch_theme_consistency(self):
        """Test that Grinch theme always returns the same messages."""
        # Unlike festive theme, Grinch should be consistent
        states = [GrinchTheme.get_thinking_state() for _ in range(10)]
        assert len(set(states)) == 1  # All the same

        messages = [GrinchTheme.get_success_message() for _ in range(10)]
        assert len(set(messages)) == 1  # All the same


class TestThemeComparison:
    """Test comparing FestiveTheme and GrinchTheme behaviors."""

    def test_festive_more_variety(self):
        """Test that festive theme has more variety than Grinch."""
        festive_states = [FestiveTheme.get_thinking_state() for _ in range(20)]
        grinch_states = [GrinchTheme.get_thinking_state() for _ in range(20)]

        assert len(set(festive_states)) > len(set(grinch_states))

    def test_different_messages(self):
        """Test that festive and Grinch themes have different messages."""
        festive_thinking = FestiveTheme.get_thinking_state()
        grinch_thinking = GrinchTheme.get_thinking_state()

        # They should be formatted differently
        assert festive_thinking != grinch_thinking

        festive_success = FestiveTheme.get_success_message()
        grinch_success = GrinchTheme.get_success_message()

        assert festive_success != grinch_success


class TestChristmas:
    @pytest.mark.parametrize(
        "day, sleeps",
        [
            ((2026, 11, 24), 31),
            ((2026, 12, 24), 1),
            ((2026, 12, 25), 0),
            ((2026, 12, 26), 364),
            ((2027, 12, 26), 365),  # 2028 is a leap year
        ],
    )
    def test_sleeps(self, day, sleeps):
        from datetime import date

        from clause_code.theme import sleeps_until_christmas

        assert sleeps_until_christmas(date(*day)) == sleeps

    def test_countdown_lines(self):
        from datetime import date

        from clause_code.theme import christmas_countdown

        assert christmas_countdown(date(2026, 11, 24)) == "31 sleeps until Christmas"
        assert "one more sleep" in christmas_countdown(date(2026, 12, 24))
        assert "Merry Christmas" in christmas_countdown(date(2026, 12, 25))


class TestSnowfall:
    def test_frame_shape(self):
        from clause_code.theme import snowfall

        frames = snowfall(30, 6, 20, seed=1)

        assert len(frames) == 20
        assert all(len(frame) == 6 and all(len(row) == 30 for row in frame) for frame in frames)

    def test_snow_settles(self):
        from clause_code.theme import snowfall

        frames = snowfall(30, 6, 40, seed=1)

        assert frames[0][-1].strip() == ""
        assert frames[-1][-1].count("█") > frames[5][-1].count("█")

    def test_new_tool_labels(self):
        assert (
            FestiveTheme.get_tool_label("mcp__cheerlights__get_color") == "🎄 Checking the lights"
        )
        assert FestiveTheme.get_tool_label("PowerShell") == "🔔 Running"
        assert GrinchTheme.get_compaction_label() == "Conversation compacted"


class TestDrawing:
    """The tree, the string of lights, and the color chip."""

    def test_tree_is_symmetric_and_single_width(self):
        from rich.cells import cell_len

        from clause_code.theme import christmas_tree

        rows = christmas_tree(5).plain.split("\n")
        assert rows[0].strip() == "★"
        assert rows[1].strip() == "/●\\"
        assert rows[5].strip() == "/● ● ● ● ●\\"
        for row in rows:
            # Every character is one cell, so the tree lines up in any terminal
            assert cell_len(row) == len(row)
            # Centered on the same column as the star
            assert len(row) - len(row.lstrip()) + len(row.strip()) // 2 == 5

    def test_tree_bulbs_take_turns(self):
        from clause_code.theme import ORNAMENTS, christmas_tree

        tree = christmas_tree(3)
        bulbs = [span.style for span in tree.spans if tree.plain[span.start] == "●"]
        assert bulbs == [ORNAMENTS[i % len(ORNAMENTS)] for i in range(6)]

    def test_strand_hangs_on_the_night_strip(self):
        from clause_code.theme import NIGHT, strand

        line = strand("#ffffff", 3)
        assert line.plain == " ●─●─● "
        assert all(f"on {NIGHT}" in str(span.style) for span in line.spans)

    def test_chip(self):
        from clause_code.theme import chip

        swatch = chip("red", "#ff0000", "#ffffff")
        assert swatch.plain == " red "
        assert swatch.style == "bold #ffffff on #ff0000"


class TestGlyphWidths:
    """Regression: emoji such as the map and the scissors need a variation selector to
    look like emoji. Rich counted them one cell wide while Windows Terminal drew them two
    wide, so the label ran into them ("🗺️Mapping"). Every emoji the app prints must be
    wide by default, and no string may lean on a variation selector."""

    # Narrow symbols that every terminal tested draws one cell wide
    NARROW = set("●○★─━═│█▀▌▐░•·…→←↳✓✗")

    def strings(self):
        import ast
        import pathlib

        import clause_code

        root = pathlib.Path(clause_code.__file__).parent
        for path in root.rglob("*.py"):
            if path.name == "terminal.py":
                continue  # the fallback table names glyphs it does not print
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    yield path.name, node.value

    def test_no_variation_selectors(self):
        offenders = [(name, s) for name, s in self.strings() if "\ufe0f" in s or "\ufe0e" in s]
        assert offenders == []

    def test_every_symbol_is_wide_or_known_narrow(self):
        import unicodedata

        offenders = set()
        for name, text in self.strings():
            for char in text:
                if char.isascii() or char in self.NARROW:
                    continue
                if unicodedata.category(char).startswith("S"):
                    if unicodedata.east_asian_width(char) != "W":
                        offenders.add((name, char, unicodedata.name(char, "?")))
        assert offenders == set()


class TestLightThemes:
    """Regression: terminals draw bold ANSI colors in their bright variant, and bright green
    on a light background reads at about 2:1 ("Ready!" and "Plan mode on." all but vanished).
    Bold goes with the default text color only; colored text stays regular weight."""

    def test_no_bold_named_colors(self):
        import ast
        import pathlib
        import re

        import clause_code

        pattern = re.compile(r"bold (green|red|yellow|blue|magenta|cyan|white)\b")
        root = pathlib.Path(clause_code.__file__).parent
        offenders = []
        for path in root.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if pattern.search(node.value):
                        offenders.append((path.name, node.value[:60]))
        assert offenders == []
