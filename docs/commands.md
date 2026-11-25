# Commands

Every slash command, command-line flag, and keyboard shortcut in Clause Code 3.0.
Type `/help` in the app for the same list.

## Command-line flags

| Flag | What it does |
|---|---|
| `--project PATH` | Work in `PATH` for this session instead of the current folder. |
| `--model opus\|sonnet\|haiku` | Use this model for the session. The default comes from `config.json` (Opus 5.5 unless you changed it). |
| `-c`, `--continue` | Continue the most recent conversation in the project folder. |
| `-r`, `--resume [SESSION_ID]` | Resume a conversation by ID, or choose one from a list when no ID is given. |
| `--version` | Print the version and exit. |

`--continue` and `--resume` cannot be used together.

## Working with Claude

| Command | What it does |
|---|---|
| `/plan [on\|off]` | Plan mode. Claude reads and proposes a plan and changes nothing until you approve it. At the plan, answer `y` to build with the usual approvals, `a` to build with file edits auto-accepted, or `n` to keep planning. Without an argument, `/plan` toggles. |
| `/autoaccept [on\|off]` | Apply file edits inside the project without asking. Shell commands that change things still ask, and writes outside the project stay blocked. |
| `/undo` | Restore the files Claude edited in its last turn to how they were before it. Run it again to go back another turn. Claude is told about the undo with your next message. |
| `/check [focus]` | Ask the checker subagent to review the changes made in this conversation. It starts with a verdict: NICE, NAUGHTY, or UNSURE. Text after `/check` tells it what to focus on. |
| `/resume [number\|id]` | List earlier conversations in this folder and switch to one. Conversations started in Clause Code are marked with 🎄; the others are Claude Code sessions in the same folder. |
| `/context` | Show how full the context window is, by category. |
| `/compact [what to keep]` | Summarize the conversation now to free context. Text after `/compact` says what the summary must keep. |

## Configuration

| Command | What it does |
|---|---|
| `/setkey` | Set or replace your Anthropic API key and start a new session with it. |
| `/project [path]` | Switch to another project folder, remember it for next time, and start a new session. |
| `/model [opus\|sonnet\|haiku]` | Switch models and keep the conversation. The model you pick also becomes the default for the next start. |
| `/santa` | Festive mode: holiday status messages, tool labels, and tone. |
| `/grinch` | Minimal mode: plain labels and a professional tone. |

The status messages change at once; Claude's tone follows from the next `/clear`.

## Fun

| Command | What it does |
|---|---|
| `/cheerlights` | Turn on CheerLights mode, or show the current color when it is already on. See [CheerLights mode](cheerlights.md). |
| `/cheerlights off` | Turn CheerLights mode off. |
| `/cheerlights history [n]` | Show the last `n` colors (12 by default, at most 100). |
| `/cheerlights <color>` | Set the color for everyone by posting `#cheerlights <color>` to your Bluesky account. |
| `/cheerlights how` | Explain the ways to set the color. |
| `/snow` | Three seconds of snow, in the CheerLights color when CheerLights mode is on. Festive mode only. |
| `/advent [day]` | In December, the day's coding challenge, or the challenge for any day from 1 to 25. Outside December it asks you to come back then. |

## Utility

| Command | What it does |
|---|---|
| `/clear` | Clear the screen and start a new conversation. |
| `/help` | List the commands. |
| `/exit`, `/quit` | Quit. |

## Keyboard shortcuts

| Key | What it does |
|---|---|
| Tab | Complete a slash command once you have typed `/`. |
| Up, Down | Move through your earlier messages. |
| Ctrl+C during a turn | Stop Claude's turn, and any background task it is waiting for. The conversation stays open. |
| Ctrl+C at an approval prompt | Decline and stop the turn. |
| Ctrl+D | Quit. |

## Answers at an approval prompt

| Answer | What it does |
|---|---|
| `y` | Allow this one action. |
| `a` | Allow this tool for the rest of the session. Not offered for shell commands, plan approvals, or CheerLights posts. |
| `n`, or anything else | Decline. Claude is told to ask you how to proceed. |
