# Configuration

Clause Code keeps its settings in `~/.clause-code/`.

```text
~/.clause-code/
├── config.json   # settings
├── .api_key      # your API key, readable only by you (not encrypted)
└── history       # your earlier messages, for the Up and Down keys
```

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

## Project settings

Clause Code loads the project's `CLAUDE.md`, `.claude/settings.json`, and project skills, so conventions and permission rules you already use with Claude Code apply.
Your personal `~/.claude` settings are not loaded.

## Conversations

Conversations are saved by the Claude Code runtime under `~/.claude/projects/`, next to any Claude Code sessions for the same folder.
That is why `/resume` can also open a conversation you started in Claude Code.
