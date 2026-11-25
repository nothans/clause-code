# CheerLights mode

[CheerLights](https://cheerlights.com) is a network of lights around the world that all show the same color.
Anyone can change the color, and every connected light follows within seconds.
CheerLights mode makes Clause Code follow it too.

## Turn it on

```text
● 🎅 > /cheerlights
🎄 CheerLights mode on. Clause Code now wears the color that lights around the world are showing,
and changes when they do.
   ●─●─●─●─●─●─●─●─●    orange   #ffa500 · set 15 min ago · by someone, somewhere
  /cheerlights history · /cheerlights <color> to set it · /cheerlights off
```

The setting is saved, so CheerLights mode is still on the next time you start Clause Code.
`/cheerlights off` turns it off.

## What changes

- The bulb in front of the prompt and the thinking spinner take the current color.
- The status line under the prompt shows the color as a swatch, when it was set, and who set it when that is known.
- A finished task ends with a string of lights in the current color.
  When the color changed while Claude worked, the line lists the changes as swatches: `While you worked, the lights went red → green → blue`.
- `/snow` falls in the current color.

Tool labels and the success line keep their own colors, so a red light never makes a finished turn look like an error.

The colors are chosen to read on dark and light terminals:

- A color's name is set on a swatch of the real color, in dark or white ink, whichever reads better.
- Bulbs hang on a dark strip (`#252525`), so white, yellow, and pink bulbs show on a light terminal; dark colors are lightened to glow on it (blue becomes `#6666ff`).
- The spinner is a shade of the color with at least 3.5:1 contrast on both a dark (`#0c0c0c`) and a light (`#fafafa`) background (blue becomes `#4c4cff`, yellow `#8a8a00`).
  No color reaches the usual 4.5:1 on both at once.

## Where the color comes from

| Source | Used for |
|---|---|
| ThingSpeak channel 1417 over HTTPS (`api.thingspeak.com/channels/1417`) | The current color, the time it was set, and the history. |
| The CheerLights MQTT broker (`mqtt.cheerlights.com:1883`, topic `cheerlights`) | A push the moment the color changes. Clients read it anonymously and cannot publish. |
| Bluesky's public post search (`api.bsky.app`) | Who set the color, for colors set from Bluesky. |

When the broker cannot be reached, Clause Code reads ThingSpeak every 30 seconds instead.
When ThingSpeak cannot be reached either, the status line says the lights are out of reach and the rest of Clause Code carries on.
No request blocks the prompt; each one gives up after 6 seconds.

## Who set it

A color set from Bluesky comes from a public post, so Clause Code looks for it.
A post counts when it mentions CheerLights, names the color, and was written in the three minutes before the change (or up to 30 seconds after, for clock differences); the closest one wins.
Colors set on Discord or Telegram are not published with a name, and the status line says "by someone, somewhere".

## Setting the color

Anyone can set the color:

- on the [CheerLights Discord](https://cheerlights.com/discord), with the `/cheerlights` command;
- on Bluesky, with a post such as `#cheerlights red`.

To set it from Clause Code, create an app password in Bluesky's settings (not your account password), put it in the environment, and start Clause Code:

```bash
export BLUESKY_HANDLE=you.bsky.social
export BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
uv run clause-code
```

`/cheerlights red` then posts `#cheerlights red` from your account, and the CheerLights service applies it within a few seconds.
The credentials are read from the environment only and are never written to disk.
For an account on its own server, set `BLUESKY_SERVICE` to that server's URL.

The colors are red, green, blue, cyan, white, oldlace, purple, magenta, yellow, orange, and pink.
The CheerLights service takes one color per person every 30 seconds, and Clause Code waits the same.

## Claude's CheerLights tools

Claude has three tools for CheerLights, whether or not CheerLights mode is on:

| Tool | Approval | What it does |
|---|---|---|
| `get_color` | none | The current color, its hex, when it was set, and who set it when that is public. |
| `get_history` | none | The most recent colors, up to 100, with their times. |
| `set_color` | every time | Posts `#cheerlights <color>` from your Bluesky account. Offered to Claude only when Bluesky credentials are set. |

A `set_color` approval shows the exact post and cannot be allowed for the whole session, because it is a public post that changes lights for everyone.
