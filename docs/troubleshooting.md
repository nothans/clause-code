# Troubleshooting

## "Authentication failed"

Set a new key with `/setkey`, or export it for one shell session:

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

A key in the environment takes precedence over the saved one.

## "The Claude Code runtime ... is missing"

The runtime ships inside the `claude-agent-sdk` wheel.
Reinstall it:

```bash
uv sync --reinstall-package claude-agent-sdk
```

## "Command not found: clause-code"

`clause-code` is on the PATH only inside the project's environment.
Run it through uv from the repository folder:

```bash
uv run clause-code
```

To run it from any folder, install it as a uv tool from the repository folder:

```bash
uv tool install .
```

## Boxes, gaps, or characters like `Γ¥î` in the output

Clause Code writes piped and redirected output as UTF-8.
A program that reads it in a legacy code page shows each emoji as two or three wrong characters, as `more` does in a console on code page 437.
Switch the console to UTF-8, or ask for ASCII:

```bash
chcp 65001                                         # Windows: the console reads UTF-8
CLAUSE_CODE_ASCII=1 uv run clause-code             # macOS, Linux: ASCII only
```

In PowerShell, set `$env:CLAUSE_CODE_ASCII = "1"` before starting.
ASCII mode also helps a terminal whose font has no emoji, where they show as boxes.
See [Unicode output](configuration.md#unicode-output) for how the encoding is chosen.

## The status line says the lights are out of reach

Clause Code could not reach ThingSpeak or the CheerLights MQTT broker.
It keeps trying every 30 seconds, and the status line shows the color again when one answers.
Networks that block port 1883 still work through ThingSpeak, with up to 30 seconds' delay.

## `/cheerlights red` explains how to set the color instead of setting it

Setting the color needs `BLUESKY_HANDLE` and `BLUESKY_APP_PASSWORD` in the environment when Clause Code starts.
See [CheerLights mode](cheerlights.md#setting-the-color).

## A turn keeps going after Claude's answer

Claude started something in the background, and the turn waits for it; the spinner line names it.
Press Ctrl+C to stop waiting; the background task stops too.

## A shell command ran without asking

The Claude Code runtime runs commands it classifies as read-only, such as `git status` or `Get-ChildItem`, without a prompt.
Other commands ask first.
