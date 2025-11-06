"""Tests for Claude agent integration."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from clause_code.agent import ClaudeAgent
from clause_code.theme import FestiveTheme, GrinchTheme


class TestClaudeAgent:
    """Test cases for ClaudeAgent class."""

    def test_init_default_params(self, api_key, mock_console):
        """Test agent initialization with default parameters."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        assert agent.model == "sonnet"
        assert agent.festive_mode is True
        assert agent.theme == FestiveTheme
        assert agent.conversation_history == []

    def test_init_custom_model(self, api_key, mock_console):
        """Test agent initialization with custom model."""
        agent = ClaudeAgent(
            api_key=api_key,
            model="haiku",
            festive_mode=False,
            console=mock_console
        )

        assert agent.model == "haiku"
        assert agent.festive_mode is False
        assert agent.theme == GrinchTheme

    def test_get_model_id(self, api_key, mock_console):
        """Test getting model ID for different models."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        # Test default sonnet
        assert agent.get_model_id() == "claude-sonnet-4-5-20250929"

        # Test haiku
        agent.set_model("haiku")
        assert agent.get_model_id() == "claude-haiku-4-5-20251001"

        # Test opus
        agent.set_model("opus")
        assert agent.get_model_id() == "claude-opus-4-1-20250805"

    def test_get_model_info(self, api_key, mock_console):
        """Test getting model information."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        info = agent.get_model_info()
        assert "id" in info
        assert "name" in info
        assert "emoji" in info
        assert "description" in info
        assert "max_tokens" in info
        assert info["id"] == "claude-sonnet-4-5-20250929"
        assert info["max_tokens"] == 64000

    def test_set_model_valid(self, api_key, mock_console):
        """Test setting a valid model."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        agent.set_model("haiku")
        assert agent.model == "haiku"

        agent.set_model("opus")
        assert agent.model == "opus"

    def test_set_model_invalid(self, api_key, mock_console):
        """Test setting an invalid model raises error."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        with pytest.raises(ValueError, match="Unknown model"):
            agent.set_model("invalid_model")

    def test_set_festive_mode(self, api_key, mock_console):
        """Test toggling festive mode."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        # Start in festive mode
        assert agent.festive_mode is True
        assert agent.theme == FestiveTheme

        # Disable festive mode
        agent.set_festive_mode(False)
        assert agent.festive_mode is False
        assert agent.theme == GrinchTheme

        # Re-enable festive mode
        agent.set_festive_mode(True)
        assert agent.festive_mode is True
        assert agent.theme == FestiveTheme

    def test_clear_history(self, api_key, mock_console):
        """Test clearing conversation history."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        # Add some fake history
        agent.conversation_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]

        assert len(agent.conversation_history) == 2

        # Clear history
        agent.clear_history()
        assert len(agent.conversation_history) == 0

    @pytest.mark.asyncio
    async def test_chat_adds_to_history(self, api_key, mock_console):
        """Test that chat messages are added to conversation history."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        # Mock the Anthropic client
        mock_stream = AsyncMock()
        mock_stream.text_stream = self._async_generator(["Hello", " there", "!"])
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        with patch.object(agent.client.messages, 'stream', return_value=mock_stream):
            response = []
            async for chunk in agent.chat("Test message"):
                response.append(chunk)

        # Check history
        assert len(agent.conversation_history) == 2
        assert agent.conversation_history[0]["role"] == "user"
        assert agent.conversation_history[0]["content"] == "Test message"
        assert agent.conversation_history[1]["role"] == "assistant"
        assert agent.conversation_history[1]["content"] == "Hello there!"

    @pytest.mark.asyncio
    async def test_chat_with_project_folder(self, api_key, mock_console, project_folder):
        """Test chat with project folder context."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        mock_stream = AsyncMock()
        mock_stream.text_stream = self._async_generator(["Response"])
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        with patch.object(agent.client.messages, 'stream', return_value=mock_stream) as mock:
            async for _ in agent.chat("Test", project_folder=str(project_folder)):
                pass

            # Check that stream was called with project folder in system prompt
            call_kwargs = mock.call_args[1]
            assert str(project_folder) in call_kwargs["system"]

    @pytest.mark.asyncio
    async def test_chat_error_handling(self, api_key, mock_console):
        """Test that chat handles errors gracefully."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        # Mock an error
        with patch.object(agent.client.messages, 'stream', side_effect=Exception("API Error")):
            response = []
            async for chunk in agent.chat("Test message"):
                response.append(chunk)

            # Should return empty string on error
            assert response == [""]
            # Should print error message
            assert mock_console.print.called

    @pytest.mark.asyncio
    async def test_generate_code(self, api_key, mock_console):
        """Test code generation."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        # Mock response
        mock_content = Mock()
        mock_content.text = "def hello():\n    return 'Hello'"
        mock_response = Mock()
        mock_response.content = [mock_content]

        # Use AsyncMock for the create method since it's async
        with patch.object(agent.client.messages, 'create', new=AsyncMock(return_value=mock_response)):
            code, explanation = await agent.generate_code("Create a hello function")

            assert "def hello()" in code
            assert code != ""

    @pytest.mark.asyncio
    async def test_generate_code_error(self, api_key, mock_console):
        """Test code generation error handling."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        with patch.object(agent.client.messages, 'create', side_effect=Exception("API Error")):
            code, explanation = await agent.generate_code("Create a function")

            assert code == ""
            assert explanation == ""

    def test_render_code(self, api_key, mock_console):
        """Test code rendering with syntax highlighting."""
        agent = ClaudeAgent(api_key=api_key, console=mock_console)

        code = "def hello():\n    return 'Hello'"
        agent.render_code(code, language="python", title="Test Code")

        # Should have called console.print
        assert mock_console.print.called

    def test_render_code_festive_title(self, api_key, mock_console):
        """Test code rendering uses festive title in festive mode."""
        agent = ClaudeAgent(api_key=api_key, festive_mode=True, console=mock_console)

        code = "console.log('Hello')"
        agent.render_code(code, language="javascript")

        # Should have called console.print
        assert mock_console.print.called

    @staticmethod
    async def _async_generator(items):
        """Helper to create an async generator for testing."""
        for item in items:
            yield item
