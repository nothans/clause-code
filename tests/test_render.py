"""Tests for rendering SDK messages."""

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, StreamEvent, TextBlock, ToolUseBlock

from clause_code.render import TurnRenderer, summarize_tool_input
from clause_code.theme import FestiveTheme, GrinchTheme


def stream(event, parent=None):
    return StreamEvent(uuid="u", session_id="s", event=event, parent_tool_use_id=parent)


def streamed_text(message_id, *chunks):
    events = [stream({"type": "message_start", "message": {"id": message_id}})]
    events += [
        stream(
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": c}}
        )
        for c in chunks
    ]
    events.append(stream({"type": "content_block_stop", "index": 0}))
    return events


def assistant(*blocks, message_id="msg_1", error=None, parent=None):
    return AssistantMessage(
        content=list(blocks),
        model="claude-opus-5-5",
        message_id=message_id,
        error=error,
        parent_tool_use_id=parent,
    )


def result(**overrides):
    fields = dict(
        subtype="success",
        duration_ms=2500,
        duration_api_ms=2000,
        is_error=False,
        num_turns=1,
        session_id="s",
        total_cost_usd=0.0123,
    )
    fields.update(overrides)
    return ResultMessage(**fields)


@pytest.fixture
def renderer(recording_console, project_folder):
    return TurnRenderer(recording_console, GrinchTheme, lambda: project_folder)


def run(renderer, messages):
    renderer.start()
    for message in messages:
        renderer.handle(message)
    renderer.finish()
    return renderer.console.export_text()


class TestTurnRenderer:
    def test_brackets_in_code_are_not_markup(self, renderer):
        """Regression: 1.x printed `arr[i]` as `arr` and crashed on `[/]`."""
        text = run(renderer, [assistant(TextBlock("value = arr[i] + d[b] and m[/]"))])

        assert "arr[i]" in text
        assert "d[b]" in text
        assert "m[/]" in text

    def test_streamed_text_printed_once(self, renderer):
        messages = streamed_text("msg_1", "Hello ", "there") + [
            assistant(TextBlock("Hello there"), message_id="msg_1"),
            result(),
        ]

        text = run(renderer, messages)

        assert text.count("Hello there") == 1

    def test_unstreamed_text_printed(self, renderer):
        text = run(renderer, [assistant(TextBlock("No stream for me"), message_id="msg_9")])

        assert "No stream for me" in text

    def test_markdown_rendered(self, renderer):
        text = run(renderer, [assistant(TextBlock("# Heading\n\n- item"))])

        assert "Heading" in text
        assert "#" not in text

    def test_tool_line(self, renderer, project_folder):
        block = ToolUseBlock(
            id="t", name="Edit", input={"file_path": str(project_folder / "src/app.py")}
        )

        text = run(renderer, [assistant(block)])

        assert "→ Edit src/app.py" in text

    def test_festive_tool_label(self, recording_console, project_folder):
        renderer = TurnRenderer(recording_console, FestiveTheme, lambda: project_folder)
        block = ToolUseBlock(id="t", name="Bash", input={"command": "pytest -q"})

        text = run(renderer, [assistant(block)])

        assert "🔔 Running pytest -q" in text

    def test_subagent_text_hidden(self, renderer):
        messages = streamed_text("msg_2", "elf chatter")
        messages = [stream(m.event, parent="toolu_1") for m in messages]
        messages.append(assistant(TextBlock("elf chatter"), message_id="msg_2", parent="toolu_1"))

        text = run(renderer, messages)

        assert "elf chatter" not in text

    def test_api_error_explained(self, renderer):
        messages = [
            assistant(
                TextBlock("Invalid API key · Please run /login"), error="authentication_failed"
            ),
            result(is_error=True, errors=["Invalid API key · Please run /login"]),
        ]

        text = run(renderer, messages)

        assert "/setkey" in text
        assert "/login" not in text

    def test_result_footer(self, renderer):
        text = run(renderer, [result()])

        assert "✓ Done" in text
        assert "2.5s" in text
        assert "$0.0123" in text

    def test_result_error(self, renderer):
        text = run(
            renderer, [result(is_error=True, subtype="error_max_turns", errors=["Too many turns"])]
        )

        assert "Too many turns" in text

    def test_interrupted(self, renderer):
        text = run(renderer, [result(terminal_reason="aborted_streaming")])

        assert "Interrupted" in text
        assert "Done" not in text


class TestSummarizeToolInput:
    def test_path_relative_to_project(self, project_folder):
        assert (
            summarize_tool_input(
                "Read", {"file_path": str(project_folder / "a.py")}, project_folder
            )
            == "a.py"
        )

    def test_path_outside_project_kept(self, project_folder):
        assert (
            summarize_tool_input("Read", {"file_path": "/etc/hosts"}, project_folder)
            == "/etc/hosts"
        )

    def test_long_command_truncated(self, project_folder):
        summary = summarize_tool_input("Bash", {"command": "x" * 200}, project_folder)

        assert len(summary) == 80
        assert summary.endswith("…")

    def test_multiline_command_first_line(self, project_folder):
        assert summarize_tool_input("Bash", {"command": "cd src\nmake"}, project_folder) == "cd src"

    def test_unknown_input(self, project_folder):
        assert summarize_tool_input("TodoWrite", {"todos": []}, project_folder) == ""
