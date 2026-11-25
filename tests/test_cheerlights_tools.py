"""Tests for the CheerLights tools Claude calls through the Agent SDK."""

from datetime import datetime, timezone

from clause_code.cheerlights import BlueskyPoster, CheerLights
from clause_code.cheerlights_tools import (
    GET_COLOR,
    GET_HISTORY,
    READ_TOOLS,
    SET_COLOR,
    build_server,
    make_tools,
)

from .test_cheerlights import LAST, FakeBluesky, FakeThingSpeak, bsky_post

NOW = datetime(2026, 11, 24, 21, 15, tzinfo=timezone.utc)


def tools_by_name(service):
    return {t.name: t for t in make_tools(service)}


def text_of(result):
    return result["content"][0]["text"]


class TestToolset:
    def test_read_tools_only_without_bluesky(self):
        tools = tools_by_name(CheerLights())

        assert set(tools) == {"get_color", "get_history"}
        assert tools["get_color"].annotations.read_only_hint is True

    def test_set_tool_with_bluesky(self):
        service = CheerLights(poster=BlueskyPoster("me.bsky.social", "pw"))
        tools = tools_by_name(service)

        assert "set_color" in tools
        assert "@me.bsky.social" in tools["set_color"].description
        schema = tools["set_color"].input_schema
        assert schema["properties"]["color"]["enum"][0] == "red"
        assert tools["set_color"].annotations.read_only_hint is False

    def test_names_match_what_the_runtime_calls(self):
        assert GET_COLOR == "mcp__cheerlights__get_color"
        assert GET_HISTORY == "mcp__cheerlights__get_history"
        assert SET_COLOR == "mcp__cheerlights__set_color"
        # set_color is never auto-approved
        assert SET_COLOR not in READ_TOOLS

    def test_server_config(self):
        config = build_server(CheerLights())
        assert config["type"] == "sdk" and config["name"] == "cheerlights"


class TestHandlers:
    async def test_get_color(self):
        ts = FakeThingSpeak(
            [LAST],
            search={
                "posts": [
                    bsky_post(
                        "cymplecybot.bsky.social", "#cheerlights MagentA", "2026-11-24T21:10:00Z"
                    )
                ]
            },
        )
        tools = tools_by_name(CheerLights(get=ts, now=lambda: NOW))

        result = await tools["get_color"].handler({})

        text = text_of(result)
        assert "color: magenta" in text and "hex: #ff00ff" in text
        assert "2026-11-24T21:10:02+00:00 (5 min ago)" in text
        assert "set_by: @cymplecybot.bsky.social on Bluesky" in text
        assert "is_error" not in result

    async def test_get_color_unknown_setter(self):
        tools = tools_by_name(CheerLights(get=FakeThingSpeak([LAST]), now=lambda: NOW))

        text = text_of(await tools["get_color"].handler({}))

        assert "set_by: not public" in text

    async def test_get_color_offline(self):
        ts = FakeThingSpeak([LAST])
        ts.down = True
        tools = tools_by_name(CheerLights(get=ts))

        result = await tools["get_color"].handler({})

        assert result["is_error"] is True
        assert "unreachable" in text_of(result)

    async def test_get_history(self):
        entries = [
            {
                "created_at": "2026-11-24T21:00:00Z",
                "entry_id": 1,
                "field1": "red",
                "field2": "#ff0000",
            },
            LAST,
        ]
        ts = FakeThingSpeak(entries)
        tools = tools_by_name(CheerLights(get=ts))

        text = text_of(await tools["get_history"].handler({"count": 2}))

        assert text.splitlines()[0].endswith("red      #ff0000")
        assert "magenta" in text.splitlines()[1]
        assert ts.urls[-1].endswith("results=2")

    async def test_set_color(self):
        fake = FakeBluesky()
        poster = BlueskyPoster("me.bsky.social", "pw", post=fake, clock=lambda: 0.0)
        tools = tools_by_name(CheerLights(poster=poster, now=lambda: NOW))

        result = await tools["set_color"].handler({"color": "green"})

        assert "Posted '#cheerlights green'" in text_of(result)
        assert fake.calls[-1][1]["record"]["text"] == "#cheerlights green"

    async def test_set_color_failure_is_an_error_result(self):
        poster = BlueskyPoster(
            "me.bsky.social", "pw", post=FakeBluesky(fail="HTTP 401"), clock=lambda: 0.0
        )
        tools = tools_by_name(CheerLights(poster=poster))

        result = await tools["set_color"].handler({"color": "green"})

        assert result["is_error"] is True
        assert "not set" in text_of(result)
