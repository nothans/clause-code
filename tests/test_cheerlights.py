"""Tests for the CheerLights core: parsing, attribution, posting, and the live service.

These use recorded shapes of the real feeds. Live checks against the real services are in
test_live.py and run with CLAUSE_LIVE=1.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from clause_code.cheerlights import (
    HOW_TO_SET,
    PALETTE,
    BlueskyPoster,
    CheerLights,
    CheerLightsUnavailable,
    Color,
    ago,
    build_post,
    colors_in,
    ink_for,
    light_string,
    match_setter,
    parse_entry,
    post_url,
)

NOW = datetime(2026, 11, 24, 21, 15, tzinfo=timezone.utc)

# Shapes recorded from ThingSpeak channel 1417 and Bluesky search on 2026-11-24
LAST = {
    "created_at": "2026-11-24T21:10:02Z",
    "entry_id": 1067960,
    "field1": "magenta",
    "field2": "#ff00ff",
}


def bsky_post(handle, text, created, rkey="3n33kl42hha2b"):
    return {
        "uri": f"at://did:plc:abc/app.bsky.feed.post/{rkey}",
        "author": {"did": "did:plc:abc", "handle": handle},
        "record": {"$type": "app.bsky.feed.post", "text": text, "createdAt": created},
    }


class TestParsing:
    def test_entry(self):
        color = parse_entry(LAST)

        assert color == Color(
            "magenta", "#ff00ff", datetime(2026, 11, 24, 21, 10, 2, tzinfo=timezone.utc), 1067960
        )

    def test_entry_without_hex_uses_palette(self):
        assert parse_entry({"field1": "Orange"}).hex == "#ffa500"

    def test_entry_without_color_is_unavailable(self):
        with pytest.raises(CheerLightsUnavailable):
            parse_entry({"field1": None})

    def test_palette_matches_the_feed(self):
        # Every name/hex pair seen in 8,000 ThingSpeak entries (2026-04-27 to 2026-11-24)
        seen = {
            "blue": "#0000ff",
            "cyan": "#00ffff",
            "green": "#008000",
            "magenta": "#ff00ff",
            "oldlace": "#fdf5e6",
            "orange": "#ffa500",
            "pink": "#ffc0cb",
            "purple": "#800080",
            "red": "#ff0000",
            "white": "#ffffff",
            "yellow": "#ffff00",
        }
        assert PALETTE == seen


class TestWords:
    @pytest.mark.parametrize(
        "seconds, expected",
        [
            (5, "just now"),
            (60, "1 min ago"),
            (600, "10 min ago"),
            (7200, "2 h ago"),
            (3 * 86400, "3 d ago"),
        ],
    )
    def test_ago(self, seconds, expected):
        assert ago(NOW - timedelta(seconds=seconds), NOW) == expected

    def test_ago_unknown(self):
        assert ago(None, NOW) == "at an unknown time"

    def test_ago_never_negative(self):
        assert ago(NOW + timedelta(seconds=30), NOW) == "just now"

    @pytest.mark.parametrize("name", ["yellow", "white", "oldlace", "cyan", "pink", "orange"])
    def test_light_colors_get_dark_ink(self, name):
        from clause_code.cheerlights import DARK_INK

        assert ink_for(PALETTE[name]) == DARK_INK

    @pytest.mark.parametrize("name", ["blue", "purple", "red", "green"])
    def test_dark_colors_get_light_ink(self, name):
        assert ink_for(PALETTE[name]) == "#ffffff"

    def test_ink_for_garbage(self):
        assert ink_for("nope") == "#ffffff"

    def test_light_string(self):
        assert light_string(3) == "●─●─●"


class TestColorsIn:
    def test_in_order(self):
        assert colors_in("#cheerlights red then blue") == ["red", "blue"]

    def test_case_and_punctuation(self):
        assert colors_in("#cheerlights change to MagentA.") == ["magenta"]

    def test_old_lace_spellings(self):
        assert colors_in("old lace") == ["oldlace"]
        assert colors_in("Old-Lace please") == ["oldlace"]

    def test_whole_words_only(self):
        assert colors_in("bluetooth reddit") == []

    def test_no_repeats(self):
        assert colors_in("red red red") == ["red"]


class TestMatchSetter:
    color = Color("magenta", "#ff00ff", datetime(2026, 11, 24, 21, 10, 2, tzinfo=timezone.utc))

    def test_real_match(self):
        """The 2026-11-24 21:10 change: cymplecybot's post at 21:10:00, applied at 21:10:02."""
        posts = [
            bsky_post(
                "cymplecybot.bsky.social",
                "#cheerlights Quiet been for 60 minutes - change to MagentA",
                "2026-11-24T21:10:00.011Z",
            )
        ]

        setter = match_setter(posts, self.color)

        assert setter.handle == "cymplecybot.bsky.social"
        assert setter.url == "https://bsky.app/profile/cymplecybot.bsky.social/post/3n33kl42hha2b"

    def test_wrong_color_is_not_a_match(self):
        posts = [bsky_post("a.bsky.social", "#cheerlights green", "2026-11-24T21:10:00Z")]
        assert match_setter(posts, self.color) is None

    def test_too_early_is_not_a_match(self):
        posts = [bsky_post("a.bsky.social", "#cheerlights magenta", "2026-11-24T21:00:00Z")]
        assert match_setter(posts, self.color) is None

    def test_long_after_is_not_a_match(self):
        posts = [bsky_post("a.bsky.social", "#cheerlights magenta", "2026-11-24T21:11:00Z")]
        assert match_setter(posts, self.color) is None

    def test_closest_post_wins(self):
        posts = [
            bsky_post("early.bsky.social", "#cheerlights magenta", "2026-11-24T21:08:30Z", "a"),
            bsky_post("close.bsky.social", "#cheerlights magenta", "2026-11-24T21:09:58Z", "b"),
        ]
        assert match_setter(posts, self.color).handle == "close.bsky.social"

    def test_cheerlights_account_never_counts(self):
        posts = [
            bsky_post("cheerlights.bsky.social", "CheerLights is magenta", "2026-11-24T21:10:00Z")
        ]
        assert match_setter(posts, self.color) is None

    def test_post_must_be_about_cheerlights(self):
        posts = [bsky_post("a.bsky.social", "my magenta scarf", "2026-11-24T21:10:00Z")]
        assert match_setter(posts, self.color) is None

    def test_color_without_time(self):
        posts = [bsky_post("a.bsky.social", "#cheerlights magenta", "2026-11-24T21:10:00Z")]
        assert match_setter(posts, Color("magenta", "#ff00ff")) is None


class TestBuildPost:
    def test_text_and_hashtag_facet(self):
        record = build_post("red", NOW)

        assert record["text"] == "#cheerlights red"
        assert record["createdAt"] == "2026-11-24T21:15:00Z"
        facet = record["facets"][0]
        start, end = facet["index"]["byteStart"], facet["index"]["byteEnd"]
        assert record["text"].encode()[start:end] == b"#cheerlights"
        assert facet["features"] == [{"$type": "app.bsky.richtext.facet#tag", "tag": "cheerlights"}]

    def test_the_service_reads_the_color_back(self):
        assert colors_in(build_post("oldlace", NOW)["text"]) == ["oldlace"]

    def test_post_url(self):
        assert post_url("at://did:plc:x/app.bsky.feed.post/abc", "me.bsky.social") == (
            "https://bsky.app/profile/me.bsky.social/post/abc"
        )


class FakeBluesky:
    """Records the XRPC calls a poster makes and answers like Bluesky does."""

    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    async def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        if self.fail:
            raise CheerLightsUnavailable(self.fail)
        if url.endswith("createSession"):
            return {"accessJwt": "jwt", "did": "did:plc:me", "handle": "me.bsky.social"}
        return {"uri": "at://did:plc:me/app.bsky.feed.post/3kxyz", "cid": "c"}


class TestBlueskyPoster:
    def make(self, fake, clock=None):
        times = iter(clock or [0.0, 0.0, 100.0, 100.0])
        return BlueskyPoster("@me.bsky.social", "app-pass", post=fake, clock=lambda: next(times))

    async def test_posts_and_returns_link(self):
        fake = FakeBluesky()
        poster = self.make(fake)

        url = await poster.post_color("Red", NOW)

        assert url == "https://bsky.app/profile/me.bsky.social/post/3kxyz"
        session, create = fake.calls
        assert session[0] == "https://bsky.social/xrpc/com.atproto.server.createSession"
        assert session[1] == {"identifier": "me.bsky.social", "password": "app-pass"}
        assert create[0].endswith("com.atproto.repo.createRecord")
        assert create[1]["repo"] == "did:plc:me"
        assert create[1]["record"]["text"] == "#cheerlights red"
        assert create[2] == {"Authorization": "Bearer jwt"}

    async def test_rejects_colors_outside_the_palette(self):
        fake = FakeBluesky()
        with pytest.raises(ValueError, match="not a CheerLights color"):
            await self.make(fake).post_color("chartreuse", NOW)
        assert fake.calls == []

    async def test_cooldown_between_posts(self):
        fake = FakeBluesky()
        poster = self.make(fake, clock=[0.0, 10.0])
        await poster.post_color("red", NOW)

        with pytest.raises(ValueError, match="one color per person"):
            await poster.post_color("blue", NOW)
        assert len(fake.calls) == 2

    async def test_bluesky_failure_is_reported(self):
        poster = self.make(FakeBluesky(fail="HTTP 401 from bsky.social: Invalid password"))
        with pytest.raises(CheerLightsUnavailable, match="Invalid password"):
            await poster.post_color("red", NOW)
        # A failed post does not start the cooldown
        assert poster.seconds_until_ready() == 0

    def test_from_env(self):
        poster = BlueskyPoster.from_env(
            {
                "BLUESKY_HANDLE": "me.bsky.social",
                "BLUESKY_APP_PASSWORD": "pw",
                "BLUESKY_SERVICE": "https://pds.example/",
            }
        )
        assert poster.handle == "me.bsky.social"
        assert poster.service == "https://pds.example"

    def test_from_env_needs_both(self):
        assert BlueskyPoster.from_env({"BLUESKY_HANDLE": "me"}) is None
        assert BlueskyPoster.from_env({}) is None

    def test_repr_hides_the_password(self):
        assert "secret" not in repr(BlueskyPoster("me", "secret"))


class FakeFeed:
    """Stands in for the MQTT broker: the test pushes colors through it."""

    instances = []

    def __init__(self, on_color, on_status):
        self.on_color, self.on_status = on_color, on_status
        self.started = self.stopped = False
        FakeFeed.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class FakeThingSpeak:
    def __init__(self, entries, search=None):
        self.entries = list(entries)
        self.search = search or {"posts": []}
        self.urls = []
        self.down = False

    async def __call__(self, url):
        self.urls.append(url)
        if self.down:
            raise CheerLightsUnavailable("api.thingspeak.com is unreachable (offline)")
        if "searchPosts" in url:
            return self.search
        if url.endswith("feeds/last.json"):
            return self.entries[-1]
        return {"feeds": self.entries}


class GatedThingSpeak(FakeThingSpeak):
    """ThingSpeak whose answers to last.json wait until the test releases them, in any order."""

    def __init__(self, entries):
        super().__init__(entries)
        self.waiting = []

    async def __call__(self, url):
        if url.endswith("feeds/last.json"):
            gate = asyncio.get_running_loop().create_future()
            self.waiting.append(gate)
            await gate
        return await super().__call__(url)

    async def answer(self, index):
        self.waiting[index].set_result(None)
        await settle()

    async def answer_all(self):
        for gate in self.waiting:
            if not gate.done():
                gate.set_result(None)
        self.waiting.clear()
        await settle()


async def settle():
    for _ in range(20):
        await asyncio.sleep(0)


@pytest.fixture
def ts():
    return FakeThingSpeak([LAST])


@pytest.fixture
def service(ts):
    FakeFeed.instances.clear()
    return CheerLights(get=ts, feed_factory=FakeFeed, now=lambda: NOW)


class TestService:
    async def test_snapshot_reads_thingspeak_when_not_following(self, service):
        color, setter = await service.snapshot()

        assert color.name == "magenta"
        assert setter is None

    async def test_snapshot_offline(self, service, ts):
        ts.down = True
        with pytest.raises(CheerLightsUnavailable, match="unreachable"):
            await service.snapshot()

    async def test_history_is_clamped(self, service, ts):
        await service.fetch_history(500)
        assert ts.urls[-1].endswith("feed.json?results=100")

    async def test_find_setter_survives_search_outage(self, service, ts):
        ts.down = True
        assert await service.find_setter(parse_entry(LAST)) is None

    async def test_start_live_reads_and_follows(self, service):
        seen = []
        service.add_listener(seen.append)

        await service.start_live()
        await settle()

        assert service.current.name == "magenta"
        assert service.status == "polling"  # the broker has not answered yet
        assert FakeFeed.instances[0].started
        feed = FakeFeed.instances[0]
        service._on_status(True)  # what the feed's thread hands over
        assert service.status == "live"
        assert seen[0].name == "magenta"
        await service.stop_live()
        assert feed.stopped and service.status == "off"

    async def test_push_records_a_change_and_tells_listeners(self, service, ts):
        await service.start_live()
        await settle()
        seen = []
        service.add_listener(seen.append)

        ts.entries.append(
            {
                "created_at": "2026-11-24T21:14:59Z",
                "entry_id": 1067961,
                "field1": "green",
                "field2": "#008000",
            }
        )
        await service._on_pushed("green")

        assert service.current.name == "green"
        assert service.current.entry_id == 1067961  # ThingSpeak's record of the change
        assert [c.name for c in service.changes_since(NOW - timedelta(minutes=1))] == ["green"]
        assert seen[-1].name == "green"
        await service.stop_live()

    async def test_repeated_retained_color_is_not_a_change(self, service):
        await service.start_live()
        await settle()

        await service._on_pushed("magenta")

        assert list(service.changes) == []
        await service.stop_live()

    async def test_push_before_thingspeak_catches_up(self, service):
        await service.start_live()
        await settle()

        await service._on_pushed("blue")  # ThingSpeak still says magenta

        assert service.current == Color("blue", "#0000ff", NOW)
        await service.stop_live()

    async def test_overlapping_pushes_keep_the_newest(self):
        """Two pushes close together each check ThingSpeak; the older one's answer can
        come back last, and must not replace the newer color."""
        gated = GatedThingSpeak([LAST])
        service = CheerLights(get=gated, feed_factory=FakeFeed, now=lambda: NOW)
        await service.start_live()
        await settle()
        await gated.answer_all()  # the first read
        assert service.current.name == "magenta"

        service._spawn(service._on_pushed("green"))
        await settle()
        service._spawn(service._on_pushed("blue"))
        await settle()
        await gated.answer(1)  # blue's check returns first
        await gated.answer(0)  # then green's

        assert service.current.name == "blue"
        assert [c.name for c in service.changes_since(NOW - timedelta(minutes=1))] == ["blue"]
        await service.stop_live()

    async def test_poll_keeps_a_pushed_color_over_an_older_entry(self, service, monkeypatch):
        """The broker drops right after a push, before ThingSpeak has the new entry."""
        monkeypatch.setattr("clause_code.cheerlights.POLL_INTERVAL_S", 0)
        await service.start_live()
        await settle()
        await service._on_pushed("blue")  # ThingSpeak still says magenta

        await settle()  # the poller reads magenta again and again

        assert service.current.name == "blue"
        assert [c.name for c in service.changes_since(NOW - timedelta(minutes=1))] == ["blue"]
        await service.stop_live()

    async def test_poll_adopts_thingspeak_record_of_a_pushed_color(self, service, ts, monkeypatch):
        monkeypatch.setattr("clause_code.cheerlights.POLL_INTERVAL_S", 0)
        await service.start_live()
        await settle()
        await service._on_pushed("blue")
        ts.entries.append(
            {"created_at": "2026-11-24T21:15:01Z", "entry_id": 1067961, "field1": "blue"}
        )

        await settle()

        assert service.current.entry_id == 1067961
        assert len(service.changes) == 1  # the same change, now with ThingSpeak's time
        await service.stop_live()

    async def test_poll_takes_a_newer_color(self, service, ts, monkeypatch):
        monkeypatch.setattr("clause_code.cheerlights.POLL_INTERVAL_S", 0)
        await service.start_live()
        await settle()
        ts.entries.append(
            {"created_at": "2026-11-24T21:14:00Z", "entry_id": 1067961, "field1": "red"}
        )

        await settle()

        assert service.current.name == "red"
        assert [c.name for c in service.changes_since(NOW - timedelta(minutes=1))] == ["red"]
        await service.stop_live()

    async def test_poll_never_goes_back_to_an_older_entry(self, service, ts, monkeypatch):
        """A ThingSpeak read served from a lagging copy must not undo a newer entry."""
        monkeypatch.setattr("clause_code.cheerlights.POLL_INTERVAL_S", 0)
        newer = {"created_at": "2026-11-24T21:14:00Z", "entry_id": 1067961, "field1": "red"}
        ts.entries.append(newer)
        await service.start_live()
        await settle()
        assert service.current.name == "red"

        ts.entries.append(LAST)  # an older entry served last
        await settle()

        assert service.current.name == "red"
        await service.stop_live()

    async def test_attribution_after_a_change(self, ts):
        ts.search = {
            "posts": [
                bsky_post("cymplecybot.bsky.social", "#cheerlights MagentA", "2026-11-24T21:10:00Z")
            ]
        }
        service = CheerLights(get=ts, feed_factory=FakeFeed, now=lambda: NOW)
        await service.start_live()
        await settle()

        assert service.setter.handle == "cymplecybot.bsky.social"
        assert service.describe(service.current, service.setter) == (
            "magenta · set 5 min ago · by @cymplecybot.bsky.social on Bluesky"
        )
        await service.stop_live()

    async def test_offline_start(self, ts):
        ts.down = True
        service = CheerLights(get=ts, feed_factory=None, now=lambda: NOW)

        await service.start_live()
        await settle()

        assert service.status == "offline"
        assert "unreachable" in service.error
        assert service.current is None
        await service.stop_live()

    async def test_broken_broker_falls_back_to_polling(self, ts):
        def broken(on_color, on_status):
            raise OSError("no route to mqtt.cheerlights.com")

        service = CheerLights(get=ts, feed_factory=broken, now=lambda: NOW)
        await service.start_live()
        await settle()

        assert service.status == "polling"
        assert service.current.name == "magenta"
        await service.stop_live()

    async def test_listener_errors_do_not_stop_the_feed(self, service):
        service.add_listener(lambda color: 1 / 0)
        await service.start_live()
        await settle()

        assert service.current.name == "magenta"
        await service.stop_live()

    async def test_set_color_without_bluesky_explains_how(self, service):
        with pytest.raises(ValueError) as info:
            await service.set_color("red")
        assert str(info.value) == HOW_TO_SET
        assert "/cheerlights" in HOW_TO_SET and "BLUESKY_APP_PASSWORD" in HOW_TO_SET

    async def test_set_color_posts(self, ts):
        fake = FakeBluesky()
        poster = BlueskyPoster("me.bsky.social", "pw", post=fake, clock=lambda: 0.0)
        service = CheerLights(get=ts, poster=poster, now=lambda: NOW)

        url = await service.set_color("cyan")

        assert url.endswith("/post/3kxyz")
        assert fake.calls[-1][1]["record"]["text"] == "#cheerlights cyan"

    def test_describe_unknown_setter(self, service):
        assert service.describe(parse_entry(LAST), None) == (
            "magenta · set 5 min ago · by someone, somewhere"
        )


class TestReadable:
    """Text in a CheerLights color has to read on dark and light terminals alike."""

    def test_every_palette_color_reads_on_dark_and_light_terminals(self):
        from clause_code.cheerlights import (
            DARK_BACKGROUND,
            LIGHT_BACKGROUND,
            TEXT_CONTRAST,
            contrast,
            readable,
        )

        for hex_value in PALETTE.values():
            text = readable(hex_value)
            assert contrast(text, DARK_BACKGROUND) >= TEXT_CONTRAST, hex_value
            assert contrast(text, LIGHT_BACKGROUND) >= TEXT_CONTRAST, hex_value

    def test_colors_that_already_read_are_left_alone(self):
        from clause_code.cheerlights import readable

        assert readable("#ff0000") == "#ff0000"
        assert readable("#008000") == "#008000"

    def test_dark_colors_are_lightened_and_light_ones_darkened(self):
        from clause_code.cheerlights import readable

        assert readable("#0000ff") == "#4c4cff"
        assert readable("#ffff00") == "#8a8a00"
        assert readable("#ffffff") == "#858585"

    def test_garbage_passes_through(self):
        from clause_code.cheerlights import readable

        assert readable("nope") == "nope"


class TestGlow:
    """Bulbs hang on a dark strip, so they only need to show against dark."""

    def test_every_palette_color_glows_on_the_night_strip(self):
        from clause_code.cheerlights import DARK_BACKGROUND, contrast, glow

        for hex_value in PALETTE.values():
            assert contrast(glow(hex_value), DARK_BACKGROUND) >= 4.5

    def test_bright_colors_are_left_alone(self):
        from clause_code.cheerlights import glow

        assert glow("#ffff00") == "#ffff00"
        assert glow("#ffffff") == "#ffffff"

    def test_dark_colors_keep_their_hue(self):
        from clause_code.cheerlights import glow

        assert glow("#0000ff") == "#6666ff"
        assert glow("#800080") == "#b366b3"
