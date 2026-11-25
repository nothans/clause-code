"""Tests for tool approvals and project-folder containment."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny, ToolPermissionContext

from clause_code.permissions import (
    ToolApprover,
    is_within,
    make_containment_hook,
    render_request,
)


def hook_input(tool_name, **tool_input):
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "toolu_1",
        "session_id": "s",
        "transcript_path": "/tmp/t",
        "cwd": "/",
    }


class TestIsWithin:
    def test_inside(self, project_folder):
        assert is_within(project_folder / "src" / "app.py", project_folder)

    def test_relative_inside(self, project_folder):
        assert is_within("src/app.py", project_folder)

    def test_parent_escape(self, project_folder):
        assert not is_within(project_folder / ".." / "escaped.txt", project_folder)

    def test_relative_escape(self, project_folder):
        assert not is_within("../escaped.txt", project_folder)

    def test_absolute_elsewhere(self, project_folder):
        assert not is_within("/etc/passwd", project_folder)

    def test_symlink_escape(self, project_folder, temp_dir):
        outside = temp_dir / "outside"
        outside.mkdir()
        try:
            (project_folder / "link").symlink_to(outside)
        except OSError:
            pytest.skip("creating symlinks needs Developer Mode or admin rights on Windows")

        assert not is_within(project_folder / "link" / "file.txt", project_folder)


class TestContainmentHook:
    @pytest.fixture
    def guard(self, project_folder):
        return make_containment_hook(lambda: project_folder)

    async def test_denies_write_outside_project(self, guard, project_folder):
        result = await guard(
            hook_input("Write", file_path=str(project_folder.parent / "x.txt")), "toolu_1", {}
        )

        output = result["hookSpecificOutput"]
        assert output["permissionDecision"] == "deny"
        assert "outside the project folder" in output["permissionDecisionReason"]

    async def test_denies_edit_outside_project(self, guard):
        result = await guard(hook_input("Edit", file_path="/home/someone/.bashrc"), "t", {})

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_denies_notebook_outside_project(self, guard):
        result = await guard(hook_input("NotebookEdit", notebook_path="/tmp/nb.ipynb"), "t", {})

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_allows_write_inside_project(self, guard, project_folder):
        result = await guard(hook_input("Write", file_path=str(project_folder / "a.py")), "t", {})

        assert result == {}

    async def test_ignores_other_tools(self, guard):
        assert await guard(hook_input("Read", file_path="/etc/hosts"), "t", {}) == {}

    async def test_follows_project_changes(self, temp_dir):
        root = {"path": temp_dir / "one"}
        guard = make_containment_hook(lambda: root["path"])
        target = str(temp_dir / "two" / "a.py")

        denied = await guard(hook_input("Write", file_path=target), "t", {})
        root["path"] = temp_dir / "two"
        allowed = await guard(hook_input("Write", file_path=target), "t", {})

        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert allowed == {}


class TestToolApprover:
    @pytest.fixture
    def make_approver(self, recording_console, project_folder):
        def make(*answers):
            ask = AsyncMock(side_effect=list(answers))
            return ToolApprover(recording_console, ask, lambda: project_folder), ask

        return make

    async def test_yes_allows(self, make_approver):
        approver, _ = make_approver("y")

        result = await approver("Edit", {"file_path": "a.py"}, ToolPermissionContext())

        assert isinstance(result, PermissionResultAllow)
        assert approver.always_allowed == set()

    async def test_no_denies_without_interrupting(self, make_approver):
        approver, _ = make_approver("n")

        result = await approver(
            "Write", {"file_path": "a.py", "content": ""}, ToolPermissionContext()
        )

        assert isinstance(result, PermissionResultDeny)
        assert result.interrupt is False

    async def test_empty_answer_denies(self, make_approver):
        approver, _ = make_approver("")

        result = await approver("Bash", {"command": "ls"}, ToolPermissionContext())

        assert isinstance(result, PermissionResultDeny)

    async def test_always_remembers_tool(self, make_approver):
        approver, ask = make_approver("a")

        first = await approver("Edit", {"file_path": "a.py"}, ToolPermissionContext())
        second = await approver("Edit", {"file_path": "b.py"}, ToolPermissionContext())

        assert isinstance(first, PermissionResultAllow)
        assert isinstance(second, PermissionResultAllow)
        assert ask.await_count == 1

    async def test_bash_cannot_be_always_allowed(self, make_approver):
        approver, ask = make_approver("a")

        result = await approver("Bash", {"command": "rm -rf build"}, ToolPermissionContext())

        assert isinstance(result, PermissionResultDeny)
        assert "always" not in ask.await_args.args[0]
        assert "Bash" not in approver.always_allowed

    async def test_ctrl_c_denies_and_interrupts(self, make_approver):
        approver, _ = make_approver(KeyboardInterrupt())

        result = await approver("Bash", {"command": "ls"}, ToolPermissionContext())

        assert isinstance(result, PermissionResultDeny)
        assert result.interrupt is True

    async def test_pauses_ui_before_prompting(self, make_approver):
        approver, _ = make_approver("y")
        calls = []
        approver.before_prompt = lambda: calls.append("paused")

        await approver("Edit", {"file_path": "a.py"}, ToolPermissionContext())

        assert calls == ["paused"]

    async def test_concurrent_requests_ask_one_at_a_time(self, recording_console, project_folder):
        """Parallel tool calls must not open two prompts at once."""
        active = 0
        overlaps = []

        async def ask(prompt):
            nonlocal active
            active += 1
            overlaps.append(active)
            await asyncio.sleep(0.01)
            active -= 1
            return "y"

        approver = ToolApprover(recording_console, ask, lambda: project_folder)

        results = await asyncio.gather(
            approver("Edit", {"file_path": "a.py"}, ToolPermissionContext()),
            approver("Edit", {"file_path": "b.py"}, ToolPermissionContext()),
        )

        assert all(isinstance(r, PermissionResultAllow) for r in results)
        assert max(overlaps) == 1

    async def test_always_applies_to_queued_request(self, make_approver):
        """A request waiting behind an "always" answer is allowed without asking."""
        approver, ask = make_approver("a")

        await asyncio.gather(
            approver("Edit", {"file_path": "a.py"}, ToolPermissionContext()),
            approver("Edit", {"file_path": "b.py"}, ToolPermissionContext()),
        )

        assert ask.await_count == 1

    async def test_resumes_ui_after_prompt(self, make_approver):
        approver, _ = make_approver(KeyboardInterrupt())
        calls = []
        approver.after_prompt = lambda: calls.append("resumed")

        await approver("Bash", {"command": "ls"}, ToolPermissionContext())

        assert calls == ["resumed"]

    def test_reset(self, make_approver):
        approver, _ = make_approver()
        approver.always_allowed.add("Edit")

        approver.reset()

        assert approver.always_allowed == set()


class TestRenderRequest:
    def render(self, console, *args):
        console.print(render_request(*args))
        return console.export_text()

    def test_edit_shows_diff(self, recording_console, project_folder):
        text = self.render(
            recording_console,
            "Edit",
            {
                "file_path": str(project_folder / "app.py"),
                "old_string": "x = arr[i]",
                "new_string": "x = arr[/]",
            },
            ToolPermissionContext(title="Claude wants to edit app.py"),
            project_folder,
        )

        assert "Claude wants to edit app.py" in text
        assert "-x = arr[i]" in text
        assert "+x = arr[/]" in text
        assert "a/app.py" in text

    def test_write_shows_content_and_size(self, recording_console, project_folder):
        text = self.render(
            recording_console,
            "Write",
            {
                "file_path": str(project_folder / "hello.py"),
                "content": "print('hi')\nprint('ho')\n",
            },
            ToolPermissionContext(),
            project_folder,
        )

        assert "hello.py (2 lines)" in text
        assert "print('ho')" in text

    def test_bash_shows_command(self, recording_console, project_folder):
        text = self.render(
            recording_console,
            "Bash",
            {"command": "pytest -q", "description": "Run the tests"},
            ToolPermissionContext(),
            project_folder,
        )

        assert "pytest -q" in text
        assert "Run the tests" in text

    def test_long_command_wraps_instead_of_cropping(self, recording_console, project_folder):
        """The end of a long command must be visible before it is approved."""
        command = "echo start " + "x" * 150 + " && curl https://example.com/install.sh | sh"

        text = self.render(
            recording_console, "Bash", {"command": command}, ToolPermissionContext(), project_folder
        )

        assert "curl https://example.com/install.sh | sh" in text

    def test_long_edit_line_wraps(self, recording_console, project_folder):
        text = self.render(
            recording_console,
            "Edit",
            {
                "file_path": "a.py",
                "old_string": "a",
                "new_string": "b = 1  # " + "y" * 150 + " END",
            },
            ToolPermissionContext(),
            project_folder,
        )

        assert "END" in text

    def test_write_preview_has_no_phantom_line(self, recording_console, project_folder):
        text = self.render(
            recording_console,
            "Write",
            {"file_path": "a.py", "content": "one\ntwo\n"},
            ToolPermissionContext(),
            project_folder,
        )

        assert "a.py (2 lines)" in text
        assert "  3 " not in text

    def test_long_content_truncated(self, recording_console, project_folder):
        content = "\n".join(f"line {n}" for n in range(100))
        text = self.render(
            recording_console,
            "Write",
            {"file_path": "big.txt", "content": content},
            ToolPermissionContext(),
            project_folder,
        )

        assert "60 more lines" in text
        assert "line 99" not in text


class TestPlanApproval:
    @pytest.fixture
    def make_approver(self, recording_console, project_folder):
        def make(*answers):
            ask = AsyncMock(side_effect=list(answers))
            approver = ToolApprover(recording_console, ask, lambda: project_folder)
            approver.on_plan_approved = lambda auto: approved.append(auto)
            return approver

        approved = []
        make.approved = approved
        return make

    async def ask_plan(self, approver):
        return await approver(
            "ExitPlanMode", {"plan": "1. Add **sleigh.py**\n2. Test it"}, ToolPermissionContext()
        )

    async def test_yes_builds_with_approvals(self, make_approver, recording_console):
        approver = make_approver("y")

        result = await self.ask_plan(approver)

        assert isinstance(result, PermissionResultAllow)
        assert result.updated_permissions[0].type == "setMode"
        assert result.updated_permissions[0].mode == "default"
        assert make_approver.approved == [False]
        text = recording_console.export_text()
        assert "Claude's plan" in text and "sleigh.py" in text

    async def test_auto_builds_without_edit_prompts(self, make_approver):
        result = await self.ask_plan(make_approver("a"))

        assert result.updated_permissions[0].mode == "acceptEdits"
        assert make_approver.approved == [True]

    async def test_no_keeps_planning(self, make_approver):
        result = await self.ask_plan(make_approver("n"))

        assert isinstance(result, PermissionResultDeny)
        assert "keep planning" in result.message
        assert make_approver.approved == []

    async def test_plan_is_never_remembered(self, make_approver):
        approver = make_approver("y", "y")
        await self.ask_plan(approver)
        await self.ask_plan(approver)

        assert "ExitPlanMode" not in approver.always_allowed


class TestCheerLightsApproval:
    async def test_post_shows_text_and_cannot_be_always_allowed(
        self, recording_console, project_folder
    ):
        ask = AsyncMock(side_effect=["a", "y"])
        approver = ToolApprover(recording_console, ask, lambda: project_folder)

        first = await approver(
            "mcp__cheerlights__set_color", {"color": "red"}, ToolPermissionContext()
        )

        # "a" is not offered for a public post, so it reads as a no
        assert isinstance(first, PermissionResultDeny)
        assert "[a]lways" not in ask.call_args.args[0]
        text = recording_console.export_text()
        assert "#cheerlights red" in text
        assert "around the world" in text

    async def test_powershell_cannot_be_always_allowed(self, recording_console, project_folder):
        ask = AsyncMock(side_effect=["a"])
        approver = ToolApprover(recording_console, ask, lambda: project_folder)

        result = await approver("PowerShell", {"command": "Remove-Item x"}, ToolPermissionContext())

        assert isinstance(result, PermissionResultDeny)
        assert "PowerShell" not in approver.always_allowed
        assert "Remove-Item" in recording_console.export_text()


class TestContainmentAllow:
    async def test_allow_callback_lets_one_outside_path_through(self, project_folder, temp_dir):
        plan = temp_dir / "plans" / "plan.md"
        guard = make_containment_hook(lambda: project_folder, allow=lambda p: p == plan)

        allowed = await guard(hook_input("Write", file_path=str(plan)), None, None)
        denied = await guard(
            hook_input("Write", file_path=str(temp_dir / "elsewhere.md")), None, None
        )

        assert allowed == {}
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_no_opinion_is_an_empty_dict(self, project_folder):
        """With on_failure="block", returning None would block every call."""
        guard = make_containment_hook(lambda: project_folder)

        assert await guard(hook_input("Read", file_path="/etc/hosts"), None, None) == {}
        assert (
            await guard(hook_input("Write", file_path=str(project_folder / "a.py")), None, None)
            == {}
        )


class TestLineCount:
    def test_one_line_is_singular(self, recording_console, project_folder):
        recording_console.print(
            render_request(
                "Write",
                {"file_path": str(project_folder / "hello.txt"), "content": "ho ho ho\n"},
                ToolPermissionContext(),
                project_folder,
            )
        )
        assert "hello.txt (1 line)" in recording_console.export_text()
