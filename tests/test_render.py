"""Tests for rendering SDK messages."""

from pathlib import Path

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

        assert f"→ Edit {Path('src/app.py')}" in text

    def test_hold_queues_output_and_keeps_spinner_off(self, renderer, project_folder):
        renderer.start()
        renderer.hold()
        renderer.handle(
            assistant(
                ToolUseBlock(
                    id="t", name="Write", input={"file_path": str(project_folder / "b.py")}
                )
            )
        )
        for event in streamed_text("msg_2", "second ", "reply"):
            renderer.handle(event)

        assert renderer._status is None and renderer._live is None
        assert "b.py" not in renderer.console.export_text(clear=False)

        renderer.release()
        renderer.finish()
        text = renderer.console.export_text()

        assert text.index("b.py") < text.index("second reply")

    def test_finish_prints_output_queued_by_an_unanswered_prompt(self, renderer, project_folder):
        renderer.hold()
        renderer.handle(
            assistant(
                ToolUseBlock(id="t", name="Read", input={"file_path": str(project_folder / "a.py")})
            )
        )

        renderer.finish()

        assert "a.py" in renderer.console.export_text()

    def test_tool_line_not_dimmed(self, renderer, project_folder):
        """Regression: a dim base style made every top-level tool line dim."""
        block = ToolUseBlock(id="t", name="Read", input={"file_path": str(project_folder / "a.py")})

        line = renderer._tool_line(block, subagent=False)

        assert line.style == ""
        assert [span.style for span in line.spans] == ["cyan", "bold"]

    def test_subagent_tool_line_dimmed(self, renderer, project_folder):
        block = ToolUseBlock(id="t", name="Read", input={"file_path": str(project_folder / "a.py")})

        line = renderer._tool_line(block, subagent=True)

        assert line.style == "dim"
        assert line.plain.startswith("  ↳ ")

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


class TestV3Messages:
    def test_compaction_is_never_silent(self, renderer, recording_console):
        from claude_agent_sdk import SystemMessage

        renderer.handle(
            SystemMessage(
                subtype="compact_boundary",
                data={
                    "compact_metadata": {
                        "trigger": "auto",
                        "pre_tokens": 812000,
                        "post_tokens": 41000,
                    }
                },
            )
        )
        renderer.finish()

        text = recording_console.export_text()
        assert "812,000 → 41,000 tokens" in text
        assert "the context was filling up" in text

    def test_manual_compaction(self, renderer, recording_console):
        from claude_agent_sdk import SystemMessage

        renderer.handle(
            SystemMessage(
                subtype="compact_boundary", data={"compact_metadata": {"trigger": "manual"}}
            )
        )
        renderer.finish()

        assert "because you asked" in recording_console.export_text()

    def test_background_task_start_and_finish(self, renderer, recording_console):
        from claude_agent_sdk import TaskNotificationMessage, TaskStartedMessage

        renderer.handle(
            TaskStartedMessage(
                subtype="task_started",
                data={},
                task_id="t1",
                description="run the test suite",
                uuid="u",
                session_id="s",
            )
        )
        renderer.handle(
            TaskNotificationMessage(
                subtype="task_notification",
                data={},
                task_id="t1",
                status="completed",
                output_file="",
                summary="42 passed\nmore",
                uuid="u",
                session_id="s",
            )
        )
        renderer.finish()

        text = recording_console.export_text()
        assert "started: run the test suite" in text
        assert "completed: 42 passed" in text
        assert "more" not in text

    def test_festive_task_labels(self):
        assert FestiveTheme.get_task_label("started").endswith("An elf started on")
        assert FestiveTheme.get_task_label("failed").endswith("An elf hit a snag:")

    @pytest.mark.parametrize(
        "status, words",
        [
            ("rejected", "Rate limit reached"),
            ("allowed_warning", "close to a rate limit (91% used)"),
        ],
    )
    def test_rate_limits(self, renderer, recording_console, status, words):
        from claude_agent_sdk import RateLimitEvent

        renderer.handle(
            RateLimitEvent(
                rate_limit_info={"status": status, "utilization": 0.91}, uuid="u", session_id="s"
            )
        )
        renderer.finish()

        assert words in recording_console.export_text()

    def test_allowed_rate_limit_is_quiet(self, renderer, recording_console):
        from claude_agent_sdk import RateLimitEvent

        renderer.handle(
            RateLimitEvent(rate_limit_info={"status": "allowed"}, uuid="u", session_id="s")
        )
        renderer.finish()

        assert recording_console.export_text().strip() == ""

    def test_cheerlights_color_is_summarized(self, project_folder):
        assert (
            summarize_tool_input("mcp__cheerlights__set_color", {"color": "red"}, project_folder)
            == "red"
        )


class TestCheerLightsMode:
    @pytest.fixture
    def cheer(self):
        from datetime import datetime, timezone

        from clause_code.cheerlights import CheerLights, Color

        service = CheerLights(feed_factory=None)
        service.current = Color("cyan", "#00ffff", datetime.now(timezone.utc))
        return service

    @pytest.fixture
    def color_console(self):
        from rich.console import Console

        return Console(record=True, width=120, force_terminal=True, color_system="truecolor")

    def lit(self, console, theme, project_folder, cheer):
        return TurnRenderer(console, theme, lambda: project_folder, cheerlights=cheer)

    def test_finished_turn_shows_the_lights(self, color_console, project_folder, cheer):
        renderer = self.lit(color_console, GrinchTheme, project_folder, cheer)

        renderer.handle(result())

        styled = color_console.export_text(styles=True, clear=False)
        text = color_console.export_text()
        assert "●─●─●" in text
        assert "Lights around the world are  cyan  right now." in text
        # The bulbs glow in the live color on the dark strip; the name sits on a swatch
        assert "1;38;2;0;255;255;48;2;37;37;37m" in styled
        assert "48;2;0;255;255m cyan " in styled

    def test_changes_during_the_turn(self, color_console, project_folder, cheer):
        from clause_code.cheerlights import PALETTE, Change, Color

        renderer = self.lit(color_console, GrinchTheme, project_folder, cheer)
        for name in ("red", "green", "blue"):
            cheer.changes.append(Change(Color(name, PALETTE[name])))
        cheer.current = Color("blue", PALETTE["blue"])

        renderer.handle(result())

        assert "While you worked, the lights went  red  →  green  →  blue " in (
            color_console.export_text()
        )

    def test_changes_before_the_turn_are_not_counted(self, color_console, project_folder, cheer):
        from datetime import datetime, timedelta, timezone

        from clause_code.cheerlights import Change, Color

        cheer.changes.append(
            Change(Color("red", "#ff0000"), datetime.now(timezone.utc) - timedelta(hours=1))
        )
        renderer = self.lit(color_console, GrinchTheme, project_folder, cheer)

        renderer.handle(result())

        assert "While you worked" not in color_console.export_text()

    def test_no_lights_outside_cheerlights_mode(self, renderer, recording_console):
        renderer.handle(result())
        assert "●" not in recording_console.export_text()

    def test_no_lights_after_an_error(self, color_console, project_folder, cheer):
        renderer = self.lit(color_console, GrinchTheme, project_folder, cheer)
        renderer.handle(result(is_error=True, subtype="error_during_execution"))
        assert "●" not in color_console.export_text()

    def test_spinner_takes_the_color_but_labels_do_not(self, color_console, project_folder, cheer):
        """A red light must not make a tool line or a finished turn look like an error."""
        renderer = self.lit(color_console, FestiveTheme, project_folder, cheer)

        renderer.handle(
            assistant(ToolUseBlock(id="t", name="mcp__cheerlights__get_color", input={}))
        )
        renderer.finish()

        styled = color_console.export_text(styles=True, clear=False)
        assert "Checking the lights" in color_console.export_text()
        assert "\x1b[36m🎄 Checking the lights" in styled  # the label stays cyan
        assert "38;2;0;148;148m" in styled  # the spinner, in cyan that reads on any theme


class TestQuietPlumbing:
    def test_tool_search_reads_as_tool_names(self, project_folder):
        summary = summarize_tool_input(
            "ToolSearch",
            {"query": "select:mcp__cheerlights__get_color,mcp__cheerlights__get_history"},
            project_folder,
        )
        assert summary == "get_color, get_history"

    def test_tool_search_label(self):
        assert FestiveTheme.get_tool_label("ToolSearch") == "🧰 Unpacking"

    def test_plan_file_is_named_not_pathed(
        self, recording_console, project_folder, monkeypatch, temp_dir
    ):
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(temp_dir / "runtime"))
        plan = temp_dir / "runtime" / "plans" / "create-hello-txt.md"
        renderer = TurnRenderer(recording_console, FestiveTheme, lambda: project_folder)

        renderer.handle(
            assistant(
                ToolUseBlock(id="t", name="Write", input={"file_path": str(plan), "content": "x"})
            )
        )
        renderer.finish()

        text = recording_console.export_text()
        assert "Sketching the plan create-hello-txt.md" in text
        assert "runtime" not in text


class TestBackgroundWaits:
    def test_waits_then_one_footer_with_summed_cost(self, recording_console, project_folder):
        waiting = {"b1": "npm run dev"}
        renderer = TurnRenderer(
            recording_console, GrinchTheme, lambda: project_folder, background=lambda: waiting
        )

        renderer.handle(result(duration_ms=1000, total_cost_usd=0.01))
        waiting.clear()
        renderer.handle(result(duration_ms=2000, total_cost_usd=0.02))
        renderer.finish()

        text = recording_console.export_text()
        assert "waiting: npm run dev · Ctrl+C stops it" in text
        assert text.count("Done") == 1
        assert "3.0s · $0.0300" in text

    def test_subagent_step_waits_for_the_sentence_to_end(self, recording_console, project_folder):
        renderer = TurnRenderer(recording_console, GrinchTheme, lambda: project_folder)
        events = streamed_text("m1", "I told the checker ", "not to fix anything.")

        for event in events[:2]:
            renderer.handle(event)
        renderer.handle(
            assistant(
                ToolUseBlock(id="t", name="Read", input={"file_path": "elf.py"}),
                message_id="sub",
                parent="toolu_agent",
            )
        )
        for event in events[2:]:
            renderer.handle(event)
        renderer.finish()

        text = recording_console.export_text()
        assert "I told the checker not to fix anything." in text
        assert text.index("not to fix anything.") < text.index("↳")


class TestReadableAccent:
    def test_blue_bulbs_glow_and_the_swatch_stays_blue(self, project_folder):
        from datetime import datetime, timezone

        from rich.console import Console

        from clause_code.cheerlights import CheerLights, Color

        console = Console(record=True, width=120, force_terminal=True, color_system="truecolor")
        cheer = CheerLights(feed_factory=None)
        cheer.current = Color("blue", "#0000ff", datetime.now(timezone.utc))
        renderer = TurnRenderer(console, GrinchTheme, lambda: project_folder, cheerlights=cheer)

        renderer.handle(result())

        styled = console.export_text(styles=True)
        assert "38;2;102;102;255" in styled  # the bulbs, lightened to glow on the strip
        assert "48;2;0;0;255m blue " in styled  # the name, on a swatch of true blue


class TestFooterStyle:
    def test_stats_are_not_tinted_by_the_success_color(self, project_folder):
        """Regression: the time and cost inherited the green line and read at about 2.5:1."""
        from rich.console import Console

        console = Console(record=True, width=120, force_terminal=True, color_system="truecolor")
        renderer = TurnRenderer(console, GrinchTheme, lambda: project_folder)

        renderer.handle(result())

        styled = console.export_text(styles=True)
        assert "\x1b[32m✓ Done\x1b[0m" in styled
        assert "\x1b[2m  2.5s · $0.0123\x1b[0m" in styled
