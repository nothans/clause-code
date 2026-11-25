# What's new in Clause Code 3.0

Clause Code 3.0 adds CheerLights mode, moves to the Claude Agent SDK 0.2.188, and uses the SDK's newer features for planning, undo, review, and sessions.
It also fixes four bugs from 2.0, two of which ended conversations or showed replies under the wrong message.

## CheerLights mode

`/cheerlights` makes Clause Code follow [CheerLights](https://cheerlights.com), the network of lights around the world that all show one color that anyone can set.

- The prompt bulb and the spinner take the live color, and change when the color changes.
- The status line shows the color, how long ago it was set, and who set it when that is public (colors set from Bluesky).
- A finished task ends with a string of lights in the current color, and lists the changes when the color moved while Claude worked.
- `/cheerlights history` shows recent colors as a row of colored bulbs.
- `/cheerlights red` sets the color for everyone by posting `#cheerlights red` from your Bluesky account, when you give Clause Code an app password.
- Claude gets CheerLights tools: it reads the color and the history without asking, and posts a color only after you approve the exact post.

The color comes from ThingSpeak channel 1417 and the CheerLights MQTT broker, with ThingSpeak polling when the broker is out of reach.
Details: [CheerLights mode](cheerlights.md).

## Working with Claude

- `/plan` puts Claude in plan mode: it reads and proposes a plan, and nothing changes until you approve it, with or without auto-accepted edits.
- `/undo` restores the files Claude edited in its last turn, using the SDK's file checkpoints, and tells Claude what happened.
- `/check` sends a reviewer subagent that did not write the code and cannot edit files; it answers NICE, NAUGHTY, or UNSURE, then its findings.
- `--continue`, `--resume`, and `/resume` pick up earlier conversations in the same folder.
- A status line under the prompt shows the model and the permission mode.
- `/context` shows how full the context window is, and `/compact` summarizes the conversation on request.
  When the conversation is compacted, Clause Code says so.
- Background work is shown while it runs, and its follow-up arrives in the same turn.

## Festive extras

- `/snow` shows three seconds of falling snow, in the CheerLights color when CheerLights mode is on.
- In festive mode, the welcome screen counts the sleeps until Christmas.

## In the terminal

- The welcome screen fits in 11 lines: the tree beside the model, the folder, and the mode, with long folder paths shortened.
- Text keeps its own colors on dark and light terminal themes; color names sit on swatches of the real color, and bulbs hang on a dark strip so white and yellow stay visible.
- `/help` lists commands and keys in aligned columns, and `/context` shows a plain bar.
- Output sent to a pipe or a file is UTF-8, and a terminal keeps its own encoding.
  A character the terminal cannot show becomes an ASCII stand-in (a bulb becomes `o`, an arrow `->`), so borders and columns stay aligned.
  `CLAUSE_CODE_ASCII=1` forces ASCII everywhere.
  Details: [Unicode output](configuration.md#unicode-output).

## Safety

- The project-folder write guard fails closed: if the hook itself breaks, the write is blocked.
- PowerShell commands, like Bash commands, can no longer be allowed for a whole session.
- Plan approvals and CheerLights posts ask every time.

## Fixes

- Ctrl+C during a turn ended the conversation, because the terminal also sent it to the Claude Code runtime, which exited.
  The runtime no longer gets the terminal's Ctrl+C, and Clause Code stops the turn through the SDK.
  On Windows, Ctrl+C during a turn used to quit Clause Code; it now stops the turn there too.
  Checked with the real runtime on Windows 11 and on Ubuntu; not run on macOS.
- When a background task finished after a turn, its follow-up showed up under the next message, and every reply after that was one turn late.
- Typing `/c` and pressing Tab completed nothing, and every space in an ordinary message popped up the list of commands.
- A one-line file preview said "(1 lines)".
- On Windows, output sent to a pipe or a file crashed on the first emoji (`UnicodeEncodeError`).
- Every start printed a long SDK warning about `can_use_tool`.

## Under the hood

- `claude-agent-sdk` 0.2.174 to 0.2.188 (bundled Claude Code 2.1.310 to 2.1.331), pinned exactly, with the other dependencies pinned to the versions in `uv.lock`.
- New SDK features in use: `create_sdk_mcp_server` and `@tool` for the CheerLights tools, `AgentDefinition` for the checker, `enable_file_checkpointing` and `rewind_files` for undo, `set_permission_mode("plan")` with a `setMode` update for plan approval, `list_sessions`, `tag_session`, and `resume` for sessions, `get_context_usage`, `stop_task`, `HookMatcher(on_failure="block")`, and `client_app`.
- New dependency: `paho-mqtt` 2.1.0, for the CheerLights broker.
- On macOS and Linux the runtime starts through `~/.clause-code/runtime-launcher.sh`, passed as `cli_path`, so it runs in a session of its own.
- 426 tests pass on Windows 11 and 433 on Ubuntu (WSL), both with Python 3.12; the Ubuntu run includes the 4 live CheerLights checks (`CLAUSE_LIVE=1`) and the tests that need a POSIX shell.
  Every feature was also run end to end in a real Windows console, driving the app as a user would.

## Not in 3.0

- Background work that reports while you type.
  The follow-up turn is shown inside the turn that started it, because an approval prompt cannot open while you are typing a message.
- Running inside an editor through the Agent Client Protocol.
  Claude Code already has an ACP adapter, so Clause Code would add little there beyond its theme.
- Other model providers.
  Clause Code is built on the Claude Agent SDK and stays on it.
