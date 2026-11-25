"""Tests for the 3.0 commands: plan, undo, resume, check, context, compact, cheerlights, snow."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, create_autospec

import pytest
from claude_agent_sdk import SDKSessionInfo

from clause_code.agent import ClauseAgent
from clause_code.cheerlights import BlueskyPoster, CheerLights
from clause_code.commands import (
    CheckCommand,
    CheerLightsCommand,
    CompactCommand,
    ContextCommand,
    PlanCommand,
    ResumeCommand,
    SnowCommand,
    UndoCommand,
)

from .test_cheerlights import LAST, FakeBluesky, FakeThingSpeak

NOW = datetime(2026, 11, 24, 21, 15, tzinfo=timezone.utc)


@pytest.fixture
def agent(project_folder):
    agent = create_autospec(ClauseAgent, instance=True)
    agent.project_folder = project_folder
    agent.plan_mode = False
    agent.session_id = "current"
    return agent


class TestPlan:
    async def test_toggle(self, agent, recording_console):
        await PlanCommand(agent, recording_console).execute("")
        agent.set_plan_mode.assert_awaited_once_with(True)
        assert "Plan mode on" in recording_console.export_text()

    async def test_off(self, agent, recording_console):
        agent.plan_mode = True
        await PlanCommand(agent, recording_console).execute("off")
        agent.set_plan_mode.assert_awaited_once_with(False)

    async def test_bad_argument(self, agent, recording_console):
        await PlanCommand(agent, recording_console).execute("maybe")
        agent.set_plan_mode.assert_not_awaited()
        assert "Usage" in recording_console.export_text()


class TestUndo:
    async def test_undo(self, agent, recording_console):
        agent.undo.return_value = True
        await UndoCommand(agent, recording_console).execute()
        assert "back to how they were" in recording_console.export_text()

    async def test_nothing_to_undo(self, agent, recording_console):
        agent.undo.return_value = False
        await UndoCommand(agent, recording_console).execute()
        assert "Nothing to undo" in recording_console.export_text()


def session(sid, summary, minutes_ago, tag=None):
    modified = int((datetime.now(timezone.utc).timestamp() - minutes_ago * 60) * 1000)
    return SDKSessionInfo(session_id=sid, summary=summary, last_modified=modified, tag=tag)


class TestResume:
    async def test_lists_and_resumes_by_number(self, agent, recording_console, monkeypatch):
        agent.recent_sessions.return_value = [
            session("current", "this one", 0),
            session("abc123", "Add a --verbose flag", 4, tag="clause-code"),
            session("def456", "Fix the build", 90),
        ]
        monkeypatch.setattr("clause_code.commands.session.Prompt.ask", lambda *a, **k: "2")

        await ResumeCommand(agent, recording_console).execute()

        text = recording_console.export_text()
        assert "this one" not in text  # the open conversation is not offered
        assert "🎄" in text and "4 min ago" in text and "Fix the build" in text
        agent.resume.assert_awaited_once_with("def456")
        assert "Resumed: Fix the build" in text

    async def test_resume_by_id_prefix(self, agent, recording_console):
        agent.recent_sessions.return_value = [session("abc123", "Sleigh", 4)]
        await ResumeCommand(agent, recording_console).execute("abc")
        agent.resume.assert_awaited_once_with("abc123")

    async def test_cancel(self, agent, recording_console, monkeypatch):
        agent.recent_sessions.return_value = [session("abc123", "Sleigh", 4)]
        monkeypatch.setattr("clause_code.commands.session.Prompt.ask", lambda *a, **k: "")
        await ResumeCommand(agent, recording_console).execute()
        agent.resume.assert_not_awaited()

    async def test_no_sessions(self, agent, recording_console):
        agent.recent_sessions.return_value = []
        await ResumeCommand(agent, recording_console).execute()
        assert "No earlier conversations" in recording_console.export_text()

    async def test_unknown_choice(self, agent, recording_console):
        agent.recent_sessions.return_value = [session("abc123", "Sleigh", 4)]
        await ResumeCommand(agent, recording_console).execute("zzz")
        agent.resume.assert_not_awaited()
        assert "No conversation matches" in recording_console.export_text()


class TestCheckAndCompact:
    async def test_check_asks_for_the_checker(self, recording_console):
        run_turn = AsyncMock()
        await CheckCommand(run_turn, recording_console).execute("the parser")
        prompt = run_turn.await_args.args[0]
        assert "checker agent" in prompt and "Focus on: the parser" in prompt

    async def test_compact_passes_through(self, recording_console):
        run_turn = AsyncMock()
        await CompactCommand(run_turn, recording_console).execute("keep the API notes")
        run_turn.assert_awaited_once_with("/compact keep the API notes")


class TestContext:
    async def test_shows_fullness(self, agent, recording_console):
        agent.context_usage.return_value = {
            "totalTokens": 250_000,
            "maxTokens": 1_000_000,
            "percentage": 25.0,
            "isAutoCompactEnabled": True,
            "categories": [
                {"name": "Messages", "tokens": 200_000, "color": "x"},
                {"name": "System prompt", "tokens": 50_000, "color": "y"},
                {"name": "Free space", "tokens": 750_000, "color": "z"},
                {"name": "Autocompact buffer", "tokens": 33_000, "color": "z"},
            ],
        }

        await ContextCommand(agent, recording_console).execute()

        text = recording_console.export_text()
        assert "25% · 250,000 of 1,000,000 tokens" in text
        assert "Messages" in text and "200,000" in text
        assert "Free space" not in text
        assert "Autocompact buffer" not in text
        assert "/compact" in text


@pytest.fixture
def ts():
    return FakeThingSpeak([LAST])


@pytest.fixture
def cheer(ts):
    return CheerLights(get=ts, feed_factory=None, now=lambda: NOW)


class TestCheerLightsCommand:
    async def test_turning_on(self, cheer, config_manager, recording_console):
        toggled = AsyncMock()
        command = CheerLightsCommand(cheer, config_manager, recording_console, toggled)

        await command.execute("")

        assert config_manager.is_cheerlights_mode() is True
        assert cheer.following
        toggled.assert_awaited_once_with(True)
        text = recording_console.export_text()
        assert "CheerLights mode on" in text
        assert "magenta #ff00ff" in text and "by someone, somewhere" in text
        await cheer.stop_live()

    async def test_bare_command_when_on_just_shows_the_color(
        self, cheer, config_manager, recording_console
    ):
        command = CheerLightsCommand(cheer, config_manager, recording_console)
        await command.execute("on")
        recording_console.export_text()

        await command.execute("")

        text = recording_console.export_text()
        assert "magenta" in text and "CheerLights mode on" not in text
        await cheer.stop_live()

    async def test_off(self, cheer, config_manager, recording_console):
        command = CheerLightsCommand(cheer, config_manager, recording_console)
        await command.execute("on")
        await command.execute("off")

        assert config_manager.is_cheerlights_mode() is False
        assert not cheer.following
        assert "stay on for everyone else" in recording_console.export_text()

    async def test_on_while_offline(self, cheer, ts, config_manager, recording_console):
        ts.down = True
        await CheerLightsCommand(cheer, config_manager, recording_console).execute("on")

        text = recording_console.export_text()
        assert "out of reach" in text and "keeps trying" in text
        await cheer.stop_live()

    async def test_history(self, cheer, ts, config_manager, recording_console):
        ts.entries.insert(
            0, {"created_at": "2026-11-24T21:00:00Z", "field1": "red", "field2": "#ff0000"}
        )

        await CheerLightsCommand(cheer, config_manager, recording_console).execute("history 2")

        text = recording_console.export_text()
        assert "The last 2 colors" in text
        assert text.index("red") < text.index("magenta")
        assert ts.urls[-1].endswith("results=2")

    async def test_set_without_bluesky_explains_how(self, cheer, config_manager, recording_console):
        await CheerLightsCommand(cheer, config_manager, recording_console).execute("red")
        text = recording_console.export_text()
        assert "Discord" in text and "BLUESKY_HANDLE" in text

    async def test_set_with_bluesky(self, ts, config_manager, recording_console):
        fake = FakeBluesky()
        poster = BlueskyPoster("me.bsky.social", "pw", post=fake, clock=lambda: 0.0)
        cheer = CheerLights(get=ts, poster=poster, now=lambda: NOW)

        await CheerLightsCommand(cheer, config_manager, recording_console).execute("Old Lace")

        assert fake.calls[-1][1]["record"]["text"] == "#cheerlights oldlace"
        text = recording_console.export_text()
        assert "as @me.bsky.social" in text and "bsky.app/profile" in text

    async def test_unknown_word(self, cheer, config_manager, recording_console):
        await CheerLightsCommand(cheer, config_manager, recording_console).execute("plaid")
        assert "not a CheerLights color" in recording_console.export_text()


class TestSnow:
    async def test_snows_in_festive_mode(self, recording_console, monkeypatch):
        monkeypatch.setattr(SnowCommand, "SECONDS", 0.25)
        await SnowCommand(recording_console).execute()
        assert "❄️" in recording_console.export_text()

    async def test_grinch(self, recording_console):
        await SnowCommand(recording_console, festive=lambda: False).execute()
        assert "Bah, humbug." in recording_console.export_text()
