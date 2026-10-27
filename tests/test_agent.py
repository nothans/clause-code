"""Tests for the Claude Agent SDK integration."""

from unittest.mock import create_autospec

import pytest
from claude_agent_sdk import ClaudeSDKClient, CLIConnectionError, ResultMessage

from clause_code.agent import DEFAULT_MODEL, MODELS, ClauseAgent, build_persona
from clause_code.permissions import ToolApprover
from clause_code.theme import FestiveTheme, GrinchTheme


def result_message(**overrides):
    fields = dict(
        subtype="success",
        duration_ms=1200,
        duration_api_ms=1000,
        is_error=False,
        num_turns=1,
        session_id="session-1",
        total_cost_usd=0.01,
    )
    fields.update(overrides)
    return ResultMessage(**fields)


class FakeClientFactory:
    """Builds autospecced SDK clients and remembers the options each got."""

    def __init__(self, messages=None):
        self.messages = messages or [result_message()]
        self.clients = []
        self.options = []

    def __call__(self, options):
        client = create_autospec(ClaudeSDKClient, instance=True)

        async def receive_response():
            for message in self.messages:
                yield message

        client.receive_response.side_effect = receive_response
        self.clients.append(client)
        self.options.append(options)
        return client


@pytest.fixture
def factory():
    return FakeClientFactory()


@pytest.fixture
def agent(project_folder, factory):
    return ClauseAgent(project_folder, client_factory=factory)


class TestModels:
    """The model table."""

    def test_default_is_opus(self):
        assert DEFAULT_MODEL == "opus"
        assert MODELS["opus"]["id"] == "claude-opus-5-5"

    def test_current_model_ids(self):
        assert MODELS["sonnet"]["id"] == "claude-sonnet-5-5"
        assert MODELS["haiku"]["id"] == "claude-haiku-5-5"

    def test_unknown_model_rejected(self, project_folder):
        with pytest.raises(ValueError):
            ClauseAgent(project_folder, model="gpt")


class TestOptions:
    """SDK options built for each session."""

    def test_model_and_folder(self, agent, project_folder):
        options = agent.build_options()

        assert options.model == "claude-opus-5-5"
        assert options.cwd == str(project_folder.resolve())
        assert options.effort == "high"

    def test_no_sampling_parameters(self, agent):
        """temperature/top_p/top_k are rejected by current models and API versions."""
        options = agent.build_options()

        assert not hasattr(options, "temperature")
        assert "temperature" not in options.extra_args

    def test_system_prompt_extends_claude_code(self, agent, project_folder):
        prompt = agent.build_options().system_prompt

        assert prompt["type"] == "preset"
        assert prompt["preset"] == "claude_code"
        assert "Clause Code" in prompt["append"]
        assert str(project_folder.resolve()) in prompt["append"]

    def test_persona_follows_festive_mode(self, project_folder):
        assert "holiday cheer" in build_persona(project_folder, festive=True)
        assert "minimal mode" in build_persona(project_folder, festive=False)

    def test_permissions(self, project_folder, factory):
        approver = ToolApprover(None, None, lambda: project_folder)
        agent = ClauseAgent(project_folder, approver=approver, client_factory=factory)

        options = agent.build_options()

        assert options.permission_mode == "default"
        assert options.can_use_tool is approver
        assert options.allowed_tools == []
        assert "AskUserQuestion" in options.disallowed_tools
        matcher = options.hooks["PreToolUse"][0]
        assert "Write" in matcher.matcher and "Edit" in matcher.matcher

    def test_project_settings_only(self, agent):
        assert agent.build_options().setting_sources == ["project"]

    def test_api_key_passed_to_runtime(self, project_folder, factory, api_key):
        agent = ClauseAgent(project_folder, api_key=api_key, client_factory=factory)

        env = agent.build_options().env

        assert env["ANTHROPIC_API_KEY"] == api_key
        assert env["CLAUDE_AGENT_SDK_CLIENT_APP"].startswith("clause-code/")

    def test_no_api_key_uses_environment(self, agent):
        assert "ANTHROPIC_API_KEY" not in agent.build_options().env

    def test_streams_partial_messages(self, agent):
        assert agent.build_options().include_partial_messages is True


class TestSession:
    """Session lifecycle."""

    async def test_context_manager_connects_and_disconnects(self, agent, factory):
        async with agent:
            assert agent.connected
            factory.clients[0].connect.assert_awaited_once()

        factory.clients[0].disconnect.assert_awaited_once()
        assert not agent.connected

    async def test_send_streams_until_result(self, agent, factory):
        async with agent:
            messages = [m async for m in agent.send("Build a sleigh")]

        factory.clients[0].query.assert_awaited_once_with("Build a sleigh")
        assert isinstance(messages[-1], ResultMessage)

    async def test_send_connects_lazily(self, agent, factory):
        [m async for m in agent.send("hi")]

        assert agent.connected
        assert len(factory.clients) == 1

    async def test_new_session_reconnects_and_resets_approvals(self, project_folder, factory):
        approver = ToolApprover(None, None, lambda: project_folder)
        approver.always_allowed.add("Edit")
        agent = ClauseAgent(project_folder, approver=approver, client_factory=factory)

        async with agent:
            await agent.new_session()

        assert len(factory.clients) == 2
        factory.clients[0].disconnect.assert_awaited_once()
        assert approver.always_allowed == set()

    async def test_set_model_keeps_session(self, agent, factory):
        async with agent:
            await agent.set_model("haiku")

        assert agent.model == "haiku"
        assert len(factory.clients) == 1
        factory.clients[0].set_model.assert_awaited_once_with("claude-haiku-5-5")

    async def test_set_model_failure_keeps_current_model(self, agent, factory):
        """If the runtime rejects the switch, the agent still reports the old model."""
        async with agent:
            factory.clients[0].set_model.side_effect = CLIConnectionError("auth failed")
            with pytest.raises(CLIConnectionError):
                await agent.set_model("haiku")

        assert agent.model == "opus"

    async def test_auto_accept_failure_keeps_setting(self, agent, factory):
        async with agent:
            factory.clients[0].set_permission_mode.side_effect = CLIConnectionError("gone")
            with pytest.raises(CLIConnectionError):
                await agent.set_auto_accept(True)

        assert agent.auto_accept_edits is False

    async def test_set_model_invalid(self, agent):
        with pytest.raises(ValueError):
            await agent.set_model("invalid")

    async def test_set_project_starts_new_session(self, agent, factory, temp_dir):
        other = temp_dir / "other"
        other.mkdir()

        async with agent:
            await agent.set_project(other)

        assert agent.project_folder == other.resolve()
        assert factory.options[-1].cwd == str(other.resolve())
        assert len(factory.clients) == 2

    async def test_set_api_key_starts_new_session(self, agent, factory, api_key):
        async with agent:
            await agent.set_api_key(api_key)

        assert factory.options[-1].env["ANTHROPIC_API_KEY"] == api_key

    async def test_auto_accept(self, agent, factory):
        async with agent:
            await agent.set_auto_accept(True)
            factory.clients[0].set_permission_mode.assert_awaited_once_with("acceptEdits")
            await agent.set_auto_accept(False)
            factory.clients[0].set_permission_mode.assert_awaited_with("default")

    async def test_interrupt(self, agent, factory):
        async with agent:
            await agent.interrupt()

        factory.clients[0].interrupt.assert_awaited_once()

    async def test_interrupt_without_session_is_noop(self, agent):
        await agent.interrupt()

    def test_festive_mode_switches_theme(self, agent):
        assert agent.theme is FestiveTheme

        agent.set_festive_mode(False)

        assert agent.theme is GrinchTheme
        assert "minimal mode" in agent.build_options().system_prompt["append"]
