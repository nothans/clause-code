# Configuration

Clause Code keeps its settings in `~/.clause-code/`.

```text
~/.clause-code/
├── config.json           # settings
├── .api_key              # your API key, not encrypted
├── history               # your earlier messages, for the Up and Down keys
└── runtime-launcher.sh   # macOS and Linux only: starts the Claude Code runtime
```

On macOS and Linux, `.api_key` is readable only by you (mode 600).
On Windows, it has the permissions of your user folder.
`runtime-launcher.sh` keeps the terminal's Ctrl+C away from the runtime; see [How it works](how-it-works.md#ctrlc).

## config.json

Commands change these settings, and you can edit the file by hand:

```json
{
  "default_model": "opus",
  "festive_mode": true,
  "cheerlights_mode": false,
  "project_folder": "/path/to/your/project"
}
```

| Key | Values | Set by |
|---|---|---|
| `default_model` | `opus`, `sonnet`, `haiku` | `/model` |
| `festive_mode` | `true`, `false` | `/santa`, `/grinch` |
| `cheerlights_mode` | `true`, `false` | `/cheerlights`, `/cheerlights off` |
| `project_folder` | a folder path | `/project` |

`project_folder` is used when you start without `--project`; when it is unset or missing, Clause Code uses the current folder.

## Environment variables

| Variable | What it does |
|---|---|
| `ANTHROPIC_API_KEY` | Your API key. It takes precedence over the saved key and is never written to disk. |
| `BLUESKY_HANDLE` | Your Bluesky handle, for setting the CheerLights color. |
| `BLUESKY_APP_PASSWORD` | A Bluesky app password, for setting the CheerLights color. Never written to disk. |
| `BLUESKY_SERVICE` | Your Bluesky server, when your account is not on `bsky.social`. |
| `CLAUDE_CONFIG_DIR` | Where the Claude Code runtime keeps its own files, such as conversations and plans (`~/.claude` by default). |
| `CLAUSE_CODE_ASCII` | `1` prints ASCII only, for a terminal whose font cannot show emoji or box drawing; `0` turns it off. On by default when `TERM` is `linux` (the Linux console). |
| `PYTHONIOENCODING` | The output encoding. When it is set, Clause Code keeps it and prints an ASCII stand-in for each character it cannot hold. |

## Unicode output

Clause Code prints emoji, box drawing, and colored bulbs.
It picks the output encoding at start:

- A Windows console (Windows Terminal or the classic console) gets Unicode whatever its code page.
- Output piped or redirected to a file is written as UTF-8.
- A terminal with a legacy encoding (a Latin-1 locale, or `PYTHONLEGACYWINDOWSSTDIO` with a code page such as 437) keeps that encoding.

A character the encoding cannot hold is replaced by an ASCII stand-in chosen for it: a bulb becomes `o`, an arrow `->`, a box line `-`, and a decorative emoji is left out with the space after it.
The table is `FALLBACKS` in `src/clause_code/terminal.py`.
On Windows, Clause Code also turns on VT processing in the classic console, so it shows 24-bit color there as Windows Terminal does.

## Project settings

Clause Code loads the project's `CLAUDE.md`, `.claude/settings.json`, and project skills, so conventions and permission rules you already use with Claude Code apply.
Your personal `~/.claude` settings are not loaded.

## Conversations

Conversations are saved by the Claude Code runtime under `~/.claude/projects/`, next to any Claude Code sessions for the same folder.
That is why `/resume` can also open a conversation you started in Claude Code.
