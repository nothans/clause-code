"""Tests for keeping the terminal's Ctrl+C away from the runtime.

The behavior itself was checked against the real runtime on 2026-11-24: on Windows with a
console Ctrl+C event, and on Linux by typing Ctrl+C into a pty under `uv run`. Without
these measures the runtime exited and the next message failed.
"""

import asyncio
import os
import subprocess
import sys
import types
from pathlib import Path, PurePosixPath

import pytest

from clause_code import console
from clause_code.agent import ClauseAgent

from .test_agent import FakeClientFactory


def fake_kernel32(monkeypatch):
    calls = []
    kernel32 = types.SimpleNamespace(
        SetConsoleCtrlHandler=lambda handler, ignore: calls.append((handler, ignore)) or 1
    )
    monkeypatch.setitem(
        sys.modules,
        "ctypes",
        types.SimpleNamespace(windll=types.SimpleNamespace(kernel32=kernel32)),
    )
    return calls


class TestWindows:
    def test_children_inherit_ignore_then_clause_code_takes_ctrl_c_back(self, monkeypatch):
        calls = fake_kernel32(monkeypatch)
        monkeypatch.setattr(console, "on_windows", lambda: True)

        with console.children_ignore_ctrl_c():
            assert calls == [(None, True)]

        assert calls == [(None, True), (None, False)]

    def test_no_launcher_on_windows(self, monkeypatch, temp_dir):
        monkeypatch.setattr(console, "on_windows", lambda: True)
        assert console.runtime_launcher(temp_dir, runtime=temp_dir / "claude.exe") is None

    def test_restored_even_when_start_fails(self, monkeypatch, project_folder):
        calls = fake_kernel32(monkeypatch)
        monkeypatch.setattr(console, "on_windows", lambda: True)
        factory = FakeClientFactory()
        original = factory.__call__

        def failing(options):
            client = original(options)
            client.connect.side_effect = OSError("runtime missing")
            return client

        agent = ClauseAgent(project_folder, client_factory=failing)

        with pytest.raises(OSError):
            asyncio.run(agent.connect())
        assert calls == [(None, True), (None, False)]
        assert not agent.connected


class TestPosix:
    def test_no_console_flag_off_windows(self, monkeypatch):
        calls = fake_kernel32(monkeypatch)
        monkeypatch.setattr(console, "on_windows", lambda: False)

        with console.children_ignore_ctrl_c():
            pass

        assert calls == []

    def test_launcher_is_written_once_and_executable(self, monkeypatch, temp_dir):
        monkeypatch.setattr(console, "on_windows", lambda: False)
        runtime = temp_dir / "sdk" / "claude"

        path = Path(console.runtime_launcher(temp_dir / "cfg", runtime=runtime))
        first = path.stat().st_mtime_ns
        again = Path(console.runtime_launcher(temp_dir / "cfg", runtime=runtime))

        assert path == again == temp_dir / "cfg" / console.LAUNCHER_NAME
        assert path.read_text(encoding="utf-8") == console.launcher_script(runtime)
        assert path.stat().st_mtime_ns == first
        if os.name != "nt":
            assert os.access(path, os.X_OK)

    def test_launcher_follows_a_new_runtime(self, monkeypatch, temp_dir):
        monkeypatch.setattr(console, "on_windows", lambda: False)
        console.runtime_launcher(temp_dir, runtime=temp_dir / "old" / "claude")

        path = Path(console.runtime_launcher(temp_dir, runtime=temp_dir / "new" / "claude"))

        assert "new" in path.read_text(encoding="utf-8")

    def test_script_quotes_paths(self):
        text = console.launcher_script(
            PurePosixPath("/opt/it's here/claude"), python="/usr/bin/python3"
        )

        assert text.startswith("#!/bin/sh\n")
        assert "'/opt/it'\"'\"'s here/claude' \"$@\"" in text
        assert "os.setsid()" in text

    @pytest.mark.skipif(os.name == "nt", reason="needs /bin/sh and setsid")
    def test_launcher_runs_the_runtime_in_its_own_session(self, temp_dir):
        fake_runtime = temp_dir / "claude"
        fake_runtime.write_text('#!/bin/sh\nps -o sid= -p $$; echo args: "$@"\n')
        fake_runtime.chmod(0o700)

        launcher = console.runtime_launcher(temp_dir / "cfg", runtime=fake_runtime)
        out = subprocess.run(
            [launcher, "--output-format", "stream-json"], capture_output=True, text=True, check=True
        ).stdout

        session = int(out.split()[0])
        assert session != os.getsid(0)
        assert "args: --output-format stream-json" in out

    def test_no_launcher_without_a_bundled_runtime(self, monkeypatch, temp_dir):
        monkeypatch.setattr(console, "on_windows", lambda: False)
        monkeypatch.setattr(console, "bundled_runtime", lambda: None)
        assert console.runtime_launcher(temp_dir) is None


class TestAgentWiring:
    async def test_runtime_starts_inside_the_block(self, project_folder, monkeypatch):
        inside = []

        @console.contextlib.contextmanager
        def recording():
            inside.append(True)
            yield
            inside.append(False)

        monkeypatch.setattr("clause_code.agent.children_ignore_ctrl_c", recording)
        factory = FakeClientFactory()
        original = factory.__call__

        def spying(options):
            client = original(options)

            async def check_inside():
                assert inside == [True]

            client.connect.side_effect = check_inside
            return client

        agent = ClauseAgent(project_folder, client_factory=spying)
        await agent.connect()

        assert inside == [True, False]

    def test_cli_path_is_the_launcher(self, project_folder, temp_dir, monkeypatch):
        monkeypatch.setattr(
            "clause_code.agent.runtime_launcher", lambda folder: str(folder / "launch.sh")
        )
        agent = ClauseAgent(
            project_folder, launcher_dir=temp_dir, client_factory=FakeClientFactory()
        )

        assert agent.build_options().cli_path == str(temp_dir / "launch.sh")

    def test_no_launcher_dir_leaves_the_sdk_default(self, project_folder):
        agent = ClauseAgent(project_folder, client_factory=FakeClientFactory())
        assert agent.build_options().cli_path is None
