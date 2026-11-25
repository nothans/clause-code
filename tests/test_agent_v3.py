"""Tests for the 3.0 agent features: undo, resume, plan mode, the checker, and CheerLights."""

from unittest.mock import create_autospec

import pytest
from claude_agent_sdk import ClaudeSDKClient, CLIConnectionError, SDKSessionInfo, UserMessage

import clause_code.agent as agent_module
from clause_code.agent import CHECKER, SESSION_TAG, UNDO_NOTE, ClauseAgent
from clause_code.permissions import claude_config_dir

from .test_agent import FakeClientFactory, result_message


def prompt_echo(uuid, text="hi"):
    """The runtime replays each prompt first, with its UUID."""
    return UserMessage(content=text, uuid=uuid)


def tool_result_echo(uuid):
    return UserMessage(
        content=[{"type": "tool_result", "tool_use_id": "t", "content": "ok"}], uuid=uuid
    )


@pytest.fixture
def factory():
    return FakeClientFactory(
        [prompt_echo("prompt-1"), tool_result_echo("tool-1"), result_message(session_id="s-1")]
    )


@pytest.fixture
def agent(project_folder, factory, monkeypatch):
    monkeypatch.setattr(agent_module, "tag_session", lambda *a, **k: None)
    return ClauseAgent(project_folder, client_factory=factory)


class TestOptions:
    def test_checkpointing_and_prompt_replay(self, agent):
        options = agent.build_options()

        assert options.enable_file_checkpointing is True
        assert "replay-user-messages" in options.extra_args

    def test_cheerlights_server_registered(self, agent):
        assert "cheerlights" in agent.build_options().mcp_servers

    def test_checker_subagent(self, agent):
        assert agent.build_options().agents == {"checker": CHECKER}
        assert "Write" in CHECKER.disallowedTools and "Edit" in CHECKER.disallowedTools
        assert "Write" not in CHECKER.tools
        assert "NICE" in CHECKER.prompt and "NAUGHTY" in CHECKER.prompt

    def test_resume_and_continue_apply_to_first_session_only(self, project_folder, factory):
        agent = ClauseAgent(project_folder, resume="old-session", client_factory=factory)

        first = agent.build_options()
        assert first.resume == "old-session"

    async def test_resume_is_consumed_by_connect(self, project_folder, factory):
        agent = ClauseAgent(project_folder, continue_last=True, client_factory=factory)
        await agent.connect()
        await agent.new_session()

        assert factory.options[0].continue_conversation is True
        assert factory.options[1].continue_conversation is False
        assert factory.options[1].resume is None


class TestPlanMode:
    async def test_plan_mode_switches_permission_mode(self, agent, factory):
        async with agent:
            await agent.set_plan_mode(True)
            factory.clients[0].set_permission_mode.assert_awaited_with("plan")
            assert agent.permission_mode == "plan"
            await agent.set_plan_mode(False)
            factory.clients[0].set_permission_mode.assert_awaited_with("default")

    async def test_plan_mode_survives_new_session(self, agent, factory):
        await agent.set_plan_mode(True)
        await agent.connect()
        assert factory.options[0].permission_mode == "plan"

    async def test_failed_switch_keeps_setting(self, agent, factory):
        async with agent:
            factory.clients[0].set_permission_mode.side_effect = CLIConnectionError("gone")
            with pytest.raises(CLIConnectionError):
                await agent.set_plan_mode(True)
        assert agent.plan_mode is False

    def test_plan_approved_with_auto_accept(self, agent):
        agent.plan_mode = True
        agent.plan_approved(auto_accept=True)
        assert agent.permission_mode == "acceptEdits"

    def test_plan_file_is_writable_only_in_plan_mode(self, agent):
        plan_file = claude_config_dir() / "plans" / "plan-sleigh.md"

        assert agent._writes_plan_file(plan_file) is False
        agent.plan_mode = True
        assert agent._writes_plan_file(plan_file) is True
        assert agent._writes_plan_file(claude_config_dir() / "settings.json") is False

    def test_config_dir_follows_env(self, monkeypatch, temp_dir):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(temp_dir))
        assert claude_config_dir() == temp_dir


class TestUndo:
    async def test_undo_rewinds_to_the_last_prompt(self, agent, factory):
        [m async for m in agent.send("make a sleigh")]

        assert agent.can_undo
        assert await agent.undo() is True
        factory.clients[0].rewind_files.assert_awaited_once_with("prompt-1")
        assert not agent.can_undo

    async def test_tool_results_are_not_undo_points(self, agent, factory):
        [m async for m in agent.send("make a sleigh")]
        assert agent._prompt_ids == ["prompt-1"]

    async def test_claude_is_told_on_the_next_message(self, agent, factory):
        [m async for m in agent.send("make a sleigh")]
        await agent.undo()
        [m async for m in agent.send("try again")]

        factory.clients[0].query.assert_awaited_with(UNDO_NOTE + "try again")

    async def test_note_is_sent_once(self, agent, factory):
        [m async for m in agent.send("a")]
        await agent.undo()
        [m async for m in agent.send("b")]
        [m async for m in agent.send("c")]

        factory.clients[0].query.assert_awaited_with("c")

    async def test_nothing_to_undo(self, agent):
        assert await agent.undo() is False

    async def test_new_session_forgets_undo_points(self, agent):
        [m async for m in agent.send("a")]
        await agent.new_session()
        assert not agent.can_undo


class TestSessions:
    async def test_session_id_and_tag(self, project_folder, factory, monkeypatch):
        tagged = []
        monkeypatch.setattr(
            agent_module,
            "tag_session",
            lambda sid, tag, directory: tagged.append((sid, tag, directory)),
        )
        agent = ClauseAgent(project_folder, client_factory=factory)

        [m async for m in agent.send("a")]
        [m async for m in agent.send("b")]

        assert agent.session_id == "s-1"
        assert tagged == [("s-1", SESSION_TAG, str(project_folder.resolve()))]

    async def test_tag_failure_is_harmless(self, project_folder, factory, monkeypatch):
        def broken(*args):
            raise OSError("locked")

        monkeypatch.setattr(agent_module, "tag_session", broken)
        agent = ClauseAgent(project_folder, client_factory=factory)

        messages = [m async for m in agent.send("a")]
        assert messages

    async def test_recent_sessions_newest_first(self, agent, monkeypatch, project_folder):
        calls = []

        def fake_list(directory, limit, offset, include_worktrees):
            calls.append((directory, limit, include_worktrees))
            return [
                SDKSessionInfo(session_id="old", summary="old", last_modified=1),
                SDKSessionInfo(session_id="new", summary="new", last_modified=9),
            ]

        monkeypatch.setattr(agent_module, "list_sessions", fake_list)

        sessions = await agent.recent_sessions(limit=5)

        assert [s.session_id for s in sessions] == ["new", "old"]
        assert calls == [(str(project_folder.resolve()), 5, False)]

    async def test_resume_reconnects_with_session(self, agent, factory):
        await agent.connect()
        await agent.resume("abc")

        assert factory.options[-1].resume == "abc"
        assert agent.session_id == "abc"
        assert len(factory.clients) == 2


class TestContextUsage:
    async def test_context_usage(self, project_folder):
        client = create_autospec(ClaudeSDKClient, instance=True)
        client.get_context_usage.return_value = {"totalTokens": 10, "maxTokens": 100}
        agent = ClauseAgent(project_folder, client_factory=lambda options: client)

        assert (await agent.context_usage())["totalTokens"] == 10


def tasks_changed(*tasks):
    from claude_agent_sdk import SystemMessage

    return SystemMessage(
        subtype="background_tasks_changed",
        data={"tasks": [{"task_id": t, "description": f"run {t}"} for t in tasks]},
    )


class TestBackgroundWork:
    """A turn that starts background work stays open until the runtime's follow-up turn.

    Regression: the follow-up turn the runtime starts when a background task finishes was
    left unread and showed up under the next prompt, one turn out of step.
    """

    async def test_turn_waits_for_the_follow_up(self, project_folder):
        factory = FakeClientFactory(
            [
                prompt_echo("p1"),
                tasks_changed("b1"),
                result_message(session_id="s", total_cost_usd=0.01),
                tasks_changed(),
                result_message(session_id="s", total_cost_usd=0.02),
                # Anything after belongs to the next turn and must not be read now
                result_message(session_id="s", total_cost_usd=99.0),
            ]
        )
        agent = ClauseAgent(project_folder, client_factory=factory)

        messages = [m async for m in agent.send("start the dev server")]

        costs = [m.total_cost_usd for m in messages if hasattr(m, "total_cost_usd")]
        assert costs == [0.01, 0.02]
        assert agent.background_tasks == {}

    async def test_turn_ends_at_first_result_without_background_work(self, agent):
        messages = [m async for m in agent.send("hi")]
        assert sum(1 for m in messages if hasattr(m, "total_cost_usd")) == 1

    async def test_interrupt_stops_background_tasks(self, agent, factory):
        await agent.connect()
        agent.background_tasks = {"b1": "dev server", "b2": "tests"}

        await agent.interrupt()

        factory.clients[0].interrupt.assert_awaited_once()
        stopped = [c.args[0] for c in factory.clients[0].stop_task.await_args_list]
        assert stopped == ["b1", "b2"]

    async def test_stop_failure_is_harmless(self, agent, factory):
        await agent.connect()
        agent.background_tasks = {"b1": "already done"}
        factory.clients[0].stop_task.side_effect = CLIConnectionError("no such task")

        await agent.interrupt()

        assert agent.background_tasks == {}
