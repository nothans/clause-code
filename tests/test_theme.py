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

    def test_welcome_tree_exists(self):
        """Test that welcome tree ASCII art is defined."""
        assert isinstance(FestiveTheme.WELCOME_TREE, str)
        assert len(FestiveTheme.WELCOME_TREE) > 0
        assert "🌟" in FestiveTheme.WELCOME_TREE

    def test_welcome_banner_exists(self):
        """Test that welcome banner is defined."""
        assert isinstance(FestiveTheme.WELCOME_BANNER, str)
        assert len(FestiveTheme.WELCOME_BANNER) > 0
        assert "Clause Code" in FestiveTheme.WELCOME_BANNER

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
        assert "Processing" in state
        assert "⚙️" in state

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

        assert christmas_countdown(date(2026, 11, 24)) == "🎄 31 sleeps until Christmas"
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
