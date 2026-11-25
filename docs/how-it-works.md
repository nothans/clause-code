# How it works

Clause Code is a terminal front end for the [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk), which runs Claude Code as a library.
The SDK supplies the agent loop, the built-in tools, sessions, and context management.
Clause Code supplies the prompt, the approvals, the safety rules, the rendering, and the festive parts.
Version 3.0 uses `claude-agent-sdk` 0.2.188, which bundles Claude Code 2.1.331.

## A turn

1. You type a message, and `ClauseAgent.send` passes it to `ClaudeSDKClient.query`.
2. The runtime streams events back; `TurnRenderer` shows text as it arrives, then renders it as Markdown, and announces each tool call on one line.
3. When Claude wants to change something, the runtime calls `ToolApprover` (the SDK's `can_use_tool` callback), which shows a diff or a command preview and asks you.
4. The turn ends with a `ResultMessage`, which carries the duration and the cost shown in the footer.

## Safety

- File edits and shell commands that change things ask first.
  The Claude Code runtime runs commands it classifies as read-only, such as `git status`, without asking.
- A `PreToolUse` hook denies any file write outside the project folder, even with `/autoaccept` on.
  It is registered with `on_failure="block"`, so if the hook itself fails, the write is blocked instead of allowed.
  The one exception is the plan file the runtime writes under `~/.claude/plans/` while plan mode is on.
- Shell commands, plan approvals, and CheerLights posts can never be allowed for a whole session.
- `AskUserQuestion` is turned off; Claude asks in plain text.

## Undo

The SDK option `enable_file_checkpointing` backs up each file before Claude's edit tools change it.
The runtime replays each prompt with its ID (`replay-user-messages`), and Clause Code keeps those IDs.
`/undo` calls `rewind_files` with the latest one, which restores every file changed since that prompt, and tells Claude on your next message.
Shell commands are not checkpointed.

## Plan mode

`/plan` sets the permission mode to `plan`.
Claude reads and writes its plan, then calls `ExitPlanMode`, which reaches the approval prompt as the plan itself.
Approving it answers with a `setMode` permission update, to `default` or to `acceptEdits`, and the same turn goes on to build.

## The checker

`/check` asks Claude to use a subagent defined with `AgentDefinition`: its own instructions, read and search tools, a shell that still asks, no write tools, and Claude Sonnet 5.5.
It reviews the changes with a fresh context, so the reviewer is not the one who wrote the code.
Its first line is a verdict, NICE, NAUGHTY, or UNSURE.

## Background work

Claude can start a shell command or a subagent in the background.
When it finishes, the runtime starts a short follow-up turn on its own to report it.
Clause Code keeps the turn open while background work runs (the spinner says what it is waiting for), shows the follow-up in the same turn, and adds up the cost in one footer.
Without this, the follow-up would sit unread and appear under your next message.
Ctrl+C stops the turn and the background tasks, through `stop_task`.

## Ctrl+C

A terminal sends Ctrl+C to every process attached to it.
The Claude Code runtime exits when it gets one, which used to end the conversation.
Clause Code keeps the terminal's Ctrl+C away from the runtime, catches Ctrl+C itself, and stops the turn through the SDK's `interrupt`.

- Windows: the runtime starts with the console's "ignore Ctrl+C" flag, which child processes inherit, and Clause Code clears the flag for itself afterwards.
- macOS and Linux: the runtime installs its own `SIGINT` handler, so an inherited ignored signal does not hold.
  Instead Clause Code writes `~/.clause-code/runtime-launcher.sh`, passes it to the SDK as `cli_path`, and the launcher starts the bundled runtime in a session of its own, outside the terminal's foreground process group.

Both were checked against the real runtime on 2026-11-24: on Windows 11 with a console Ctrl+C event, and on Ubuntu (WSL) by typing Ctrl+C into a pseudo-terminal under `uv run`.
Without them, the runtime exited and the next message failed.

## Context

The models have a 1M-token context window.
`/context` shows how full it is, by category, from `get_context_usage`.
When the runtime compacts the conversation, on its own or after `/compact`, Clause Code says so and how many tokens were packed down, because compaction replaces earlier detail with a summary.

## Sessions

Conversations are the runtime's own sessions, stored under `~/.claude/projects/`.
`--continue` and `--resume` open one at startup; `/resume` lists them with `list_sessions` and reconnects with the SDK's `resume` option.
Clause Code tags its own sessions with `tag_session` so `/resume` can mark them.

## CheerLights

`cheerlights.py` reads the color without the SDK: ThingSpeak over HTTPS, the CheerLights MQTT broker through `paho-mqtt`, and Bluesky search for who set it.
`cheerlights_tools.py` turns it into tools for Claude with `create_sdk_mcp_server`, an MCP server that runs inside Clause Code.
The read tools are listed in `allowed_tools` and run without asking; `set_color` goes through the approval prompt.
See [CheerLights mode](cheerlights.md).

## Files

```text
src/clause_code/
├── cli.py                # prompt, status line, slash commands, Ctrl+C
├── agent.py              # SDK options, sessions, undo, plan mode, the checker
├── permissions.py        # approval prompts and the project-folder write guard
├── render.py             # streaming output, tool lines, background waits
├── console.py            # keeps the terminal's Ctrl+C away from the runtime (and its launcher)
├── cheerlights.py        # the live color, its history, who set it, Bluesky posts
├── cheerlights_tools.py  # CheerLights tools for Claude
├── theme.py              # festive and minimal messages, snow, the countdown
├── commands/             # slash command handlers
└── utils/config.py       # ~/.clause-code settings
```
