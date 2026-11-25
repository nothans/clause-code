"""Keep the terminal's Ctrl+C for Clause Code, away from the runtime it starts.

A terminal delivers Ctrl+C to every process attached to it, not just the one in front.
The Claude Code runtime that the Agent SDK starts exits when it receives one, which ends
the conversation. Clause Code catches Ctrl+C itself and asks the runtime to stop the turn
through the SDK, so the runtime must never see the keypress.

- Windows: the console's "ignore Ctrl+C" flag is inherited by child processes, so it is
  set while the runtime starts and cleared again for Clause Code.
- macOS and Linux: the runtime installs its own SIGINT handler, so an inherited ignored
  signal does not hold. Instead the runtime starts in its own session, outside the
  terminal's foreground process group, through a small launcher passed as ``cli_path``.
"""

import contextlib
import os
import shlex
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

LAUNCHER_NAME = "runtime-launcher.sh"

_LAUNCHER = """#!/bin/sh
# Written by Clause Code. Starts the Claude Code runtime in a session of its own, so the
# terminal's Ctrl+C reaches only Clause Code, which stops the turn through the SDK.
exec {python} -c {code} {runtime} "$@"
"""

_SETSID_EXEC = (
    "import os, sys\n"
    "try:\n"
    "    os.setsid()\n"
    "except OSError:\n"
    "    pass\n"
    "os.execv(sys.argv[1], sys.argv[1:])\n"
)


def on_windows() -> bool:
    """Whether Clause Code runs on Windows."""
    return os.name == "nt"


@contextlib.contextmanager
def children_ignore_ctrl_c() -> Iterator[None]:
    """On Windows, processes started inside this block ignore the console's Ctrl+C.

    Elsewhere this does nothing; see ``runtime_launcher``.
    """
    if not on_windows():
        yield
        return

    import ctypes

    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleCtrlHandler(None, True)
    try:
        yield
    finally:
        # Clause Code itself always handles Ctrl+C
        kernel32.SetConsoleCtrlHandler(None, False)


def bundled_runtime() -> Optional[Path]:
    """The Claude Code runtime that ships in the claude-agent-sdk wheel, if present."""
    import claude_agent_sdk

    name = "claude.exe" if os.name == "nt" else "claude"
    path = Path(claude_agent_sdk.__file__).parent / "_bundled" / name
    return path if path.is_file() else None


def launcher_script(runtime: Path, python: str = sys.executable) -> str:
    """The launcher's text: start ``runtime`` in a new session with this Python."""
    return _LAUNCHER.format(
        python=shlex.quote(python),
        code=shlex.quote(_SETSID_EXEC),
        runtime=shlex.quote(str(runtime)),
    )


def runtime_launcher(folder: Path, runtime: Optional[Path] = None) -> Optional[str]:
    """Write the launcher into ``folder`` and return its path, for ``cli_path``.

    Returns None on Windows, and when there is no bundled runtime to launch (the SDK
    then finds the runtime the usual way).
    """
    if on_windows():
        return None
    runtime = runtime or bundled_runtime()
    if runtime is None:
        return None
    launcher = Path(folder) / LAUNCHER_NAME
    text = launcher_script(runtime)
    if not launcher.is_file() or launcher.read_text(encoding="utf-8") != text:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        staging = launcher.with_suffix(".tmp")
        staging.write_text(text, encoding="utf-8")
        staging.chmod(0o700)
        staging.replace(launcher)
    return str(launcher)
