"""CheerLights: the one color that lights around the world are showing right now.

CheerLights (https://cheerlights.com) is a global network of lights that all show the
same color, and anyone can change it. This module reads the color live and, when the
user has Bluesky credentials, sets it the same way people do: with a #cheerlights post.

Read paths, all public and unauthenticated:

- ThingSpeak channel 1417 over HTTPS: the current color and its history.
- The CheerLights MQTT broker: a push the moment the color changes.
- Bluesky's public post search: who set the color, when it was set from Bluesky.

Write path: a post on the user's own Bluesky account. The CheerLights Bluesky service
reads every public post and applies the colors in posts that tag #cheerlights.
"""

import asyncio
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ._version import __version__

log = logging.getLogger(__name__)

THINGSPEAK = "https://api.thingspeak.com/channels/1417"
MQTT_HOST = "mqtt.cheerlights.com"
MQTT_PORT = 1883
MQTT_TOPIC = "cheerlights"
BLUESKY_SEARCH = "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts"
BLUESKY_SERVICE = "https://bsky.social"
CHEERLIGHTS_HANDLE = "cheerlights.bsky.social"
USER_AGENT = f"clause-code/{__version__} (+https://github.com/nothans/clause-code)"

# The colors CheerLights accepts, with the hex every feed publishes for them.
PALETTE = {
    "red": "#ff0000",
    "green": "#008000",
    "blue": "#0000ff",
    "cyan": "#00ffff",
    "white": "#ffffff",
    "oldlace": "#fdf5e6",
    "purple": "#800080",
    "magenta": "#ff00ff",
    "yellow": "#ffff00",
    "orange": "#ffa500",
    "pink": "#ffc0cb",
}

HTTP_TIMEOUT_S = 6
POLL_INTERVAL_S = 30
# The CheerLights Bluesky service applies one color per author every 30 seconds.
POST_COOLDOWN_S = 30
# A Bluesky post counts as the one that set a color when it was written this close to the change.
MATCH_BEFORE_S = 180
MATCH_AFTER_S = 30
# How long after a change to look for the Bluesky post behind it (search indexing lags a little).
ATTRIBUTION_DELAY_S = 4
# A pushed color carries this computer's clock; ThingSpeak records the same change about a
# second later on its own clock. Within this margin a ThingSpeak entry is not older than a push.
CLOCK_MARGIN_S = 10

HttpGet = Callable[[str], Awaitable[Any]]
HttpPost = Callable[[str, dict, Optional[dict]], Awaitable[Any]]


class CheerLightsUnavailable(Exception):
    """CheerLights could not be reached or answered with something unusable."""


@dataclass(frozen=True)
class Color:
    """One CheerLights color, as the lights showed it."""

    name: str
    hex: str
    set_at: Optional[datetime] = None
    entry_id: Optional[int] = None


@dataclass(frozen=True)
class Setter:
    """Who set a color, when it can be known.

    Only colors set from Bluesky can be traced to a person, because those posts are
    public. Discord, Telegram, and the other channels do not publish who asked.
    """

    handle: str
    url: str
    source: str = "Bluesky"


# Pure helpers


def parse_time(value: str) -> Optional[datetime]:
    """Parse an ISO 8601 time from ThingSpeak or Bluesky into an aware datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_entry(entry: dict) -> Color:
    """Turn a ThingSpeak feed entry into a Color.

    Raises:
        CheerLightsUnavailable: when the entry has no color name
    """
    name = str(entry.get("field1") or "").strip().lower()
    if not name:
        raise CheerLightsUnavailable("ThingSpeak returned an entry with no color")
    hex_value = str(entry.get("field2") or "").strip().lower() or PALETTE.get(name, "")
    return Color(
        name=name,
        hex=hex_value,
        set_at=parse_time(str(entry.get("created_at") or "")),
        entry_id=entry.get("entry_id"),
    )


def ago(when: Optional[datetime], now: datetime) -> str:
    """Say how long ago something happened, briefly: "just now", "4 min ago", "2 h ago"."""
    if when is None:
        return "at an unknown time"
    seconds = max((now - when).total_seconds(), 0)
    if seconds < 45:
        return "just now"
    if seconds < 3600:
        return f"{max(round(seconds / 60), 1)} min ago"
    if seconds < 86400:
        return f"{round(seconds / 3600)} h ago"
    return f"{round(seconds / 86400)} d ago"


def _luminance(rgb: tuple[float, float, float]) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# Typical dark and light terminal backgrounds (Windows Terminal's Campbell and One Half Light)
DARK_BACKGROUND = "#0c0c0c"
LIGHT_BACKGROUND = "#fafafa"
# WCAG AA for text, used where only a dark background matters (bulbs on the night strip)
MIN_CONTRAST = 4.5
# No color reads at 4.5:1 on both a dark and a light background; this much it can
TEXT_CONTRAST = 3.5
# Dark ink on a light swatch: charcoal rather than pure black
DARK_INK = "#252525"


def contrast(hex_a: str, hex_b: str) -> float:
    """WCAG contrast ratio between two colors."""
    la, lb = (_luminance(_rgb(h)) for h in (hex_a, hex_b))
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _rgb(hex_value: str) -> tuple[float, float, float]:
    h = hex_value.lstrip("#")
    if len(h) != 6:
        raise ValueError(hex_value)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _hex(rgb: tuple[float, ...]) -> str:
    return "#" + "".join(f"{round(c * 255):02x}" for c in rgb)


def glow(hex_value: str) -> str:
    """The same hue, lightened until it shows against the dark night strip.

    Bulbs are drawn in this, so a blue or purple bulb still glows.
    """
    try:
        r, g, b = _rgb(hex_value)
    except (ValueError, IndexError):
        return hex_value
    for step in range(21):
        mix = step / 20
        candidate = _hex(tuple(c + (1 - c) * mix for c in (r, g, b)))
        if contrast(candidate, DARK_BACKGROUND) >= MIN_CONTRAST:
            return candidate
    return "#ffffff"


def readable(hex_value: str) -> str:
    """The same hue as text that reads on dark and light terminals alike.

    Dark colors are lightened and light ones darkened, just enough for TEXT_CONTRAST
    against both backgrounds; red, green, and orange stay as they are.
    """
    try:
        rgb = _rgb(hex_value)
    except (ValueError, IndexError):
        return hex_value

    def reads(candidate: str) -> bool:
        return (
            contrast(candidate, DARK_BACKGROUND) >= TEXT_CONTRAST
            and contrast(candidate, LIGHT_BACKGROUND) >= TEXT_CONTRAST
        )

    if reads(hex_value):
        return hex_value.lower()
    too_dark = contrast(hex_value, DARK_BACKGROUND) < TEXT_CONTRAST
    for step in range(1, 101):
        mix = step / 100
        if too_dark:
            candidate = _hex(tuple(c + (1 - c) * mix for c in rgb))
        else:
            candidate = _hex(tuple(c * (1 - mix) for c in rgb))
        if reads(candidate):
            return candidate
    return "#808080"


def ink_for(hex_value: str) -> str:
    """Dark or white ink, whichever reads better on a background of this color."""
    try:
        luminance = _luminance(_rgb(hex_value))
    except (ValueError, IndexError):
        return "#ffffff"
    return DARK_INK if luminance > 0.25 else "#ffffff"


# Oldlace is also written "old lace" or "old-lace", as the CheerLights Bluesky service reads it.
_COLOR_WORD = re.compile(
    r"\b(" + "|".join(c if c != "oldlace" else r"old[\s-]*lace" for c in PALETTE) + r")\b",
    re.IGNORECASE,
)


def colors_in(text: str) -> list[str]:
    """Palette color words in a post, in the order they first appear."""
    seen: list[str] = []
    for match in _COLOR_WORD.finditer(text or ""):
        name = re.sub(r"[\s-]", "", match.group(1).lower())
        if name not in seen:
            seen.append(name)
    return seen


def post_url(uri: str, handle: str) -> str:
    """Turn an at:// post URI into its bsky.app link."""
    rkey = uri.rsplit("/", 1)[-1]
    return f"https://bsky.app/profile/{handle}/post/{rkey}"


def match_setter(posts: list[dict], color: Color) -> Optional[Setter]:
    """Find the Bluesky post that set a color, from a page of search results.

    A post matches when it names the color and was written shortly before the change
    (the CheerLights service applies posts within seconds). The closest one wins.

    Args:
        posts: ``posts`` from app.bsky.feed.searchPosts
        color: The color to explain; needs ``set_at``

    Returns:
        The matching post's author, or None when no post fits
    """
    if color.set_at is None:
        return None
    best: Optional[tuple[float, Setter]] = None
    for post in posts:
        record = post.get("record") or {}
        author = post.get("author") or {}
        handle = author.get("handle", "")
        if not handle or handle == CHEERLIGHTS_HANDLE:
            continue
        if "cheerlight" not in (record.get("text") or "").lower():
            continue
        if color.name not in colors_in(record.get("text", "")):
            continue
        written = parse_time(record.get("createdAt") or post.get("indexedAt") or "")
        if written is None:
            continue
        lead = (color.set_at - written).total_seconds()
        if not -MATCH_AFTER_S <= lead <= MATCH_BEFORE_S:
            continue
        candidate = Setter(handle=handle, url=post_url(post.get("uri", ""), handle))
        if best is None or abs(lead) < best[0]:
            best = (abs(lead), candidate)
    return best[1] if best else None


def build_post(color: str, now: datetime) -> dict:
    """Build the Bluesky post record that sets a color: ``#cheerlights <color>``.

    The hashtag carries a tag facet, so Bluesky shows it as a real hashtag. Facet
    offsets count UTF-8 bytes.
    """
    text = f"#cheerlights {color}"
    tag = "#cheerlights"
    start = text.encode().index(tag.encode())
    return {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "facets": [
            {
                "index": {"byteStart": start, "byteEnd": start + len(tag.encode())},
                "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "cheerlights"}],
            }
        ],
    }


# HTTP, on a worker thread so the event loop stays free


def _request(url: str, body: Optional[dict] = None, headers: Optional[dict] = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET")
    request.add_header("User-Agent", USER_AGENT)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("message", "")
        except (ValueError, AttributeError, OSError):
            pass
        raise CheerLightsUnavailable(
            f"HTTP {e.code} from {urllib.parse.urlsplit(url).netloc}"
            + (f": {detail}" if detail else "")
        ) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        raise CheerLightsUnavailable(
            f"{urllib.parse.urlsplit(url).netloc} is unreachable ({reason})"
        ) from e
    except ValueError as e:
        raise CheerLightsUnavailable(
            f"{urllib.parse.urlsplit(url).netloc} sent something that is not JSON"
        ) from e


async def http_get(url: str) -> Any:
    """GET a JSON document."""
    return await asyncio.to_thread(_request, url)


async def http_post(url: str, body: dict, headers: Optional[dict] = None) -> Any:
    """POST JSON and read a JSON answer."""
    return await asyncio.to_thread(_request, url, body, headers)


# Bluesky


class BlueskyPoster:
    """Posts ``#cheerlights <color>`` from the user's own Bluesky account.

    Credentials come from the environment and are never written to disk:
    ``BLUESKY_HANDLE`` and ``BLUESKY_APP_PASSWORD`` (an app password from
    Bluesky's settings, not the account password), plus ``BLUESKY_SERVICE``
    for an account on its own PDS.
    """

    def __init__(
        self,
        handle: str,
        app_password: str,
        service: str = BLUESKY_SERVICE,
        *,
        post: HttpPost = http_post,
        clock: Optional[Callable[[], float]] = None,
    ):
        self.handle = handle.lstrip("@")
        self._password = app_password
        self.service = service.rstrip("/")
        self._post = post
        self._clock = clock or (lambda: asyncio.get_running_loop().time())
        self._last_post: Optional[float] = None

    def __repr__(self) -> str:
        return f"BlueskyPoster(handle={self.handle!r}, service={self.service!r})"

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> Optional["BlueskyPoster"]:
        """Build a poster from the environment, or None when it is not configured."""
        env = os.environ if env is None else env
        handle = env.get("BLUESKY_HANDLE", "").strip()
        password = env.get("BLUESKY_APP_PASSWORD", "").strip()
        if not handle or not password:
            return None
        return cls(handle, password, env.get("BLUESKY_SERVICE", "").strip() or BLUESKY_SERVICE)

    def seconds_until_ready(self) -> float:
        """Seconds left in the cooldown between posts (0 when a post can go now)."""
        if self._last_post is None:
            return 0.0
        return max(POST_COOLDOWN_S - (self._clock() - self._last_post), 0.0)

    async def post_color(self, color: str, now: Optional[datetime] = None) -> str:
        """Post ``#cheerlights <color>`` and return the post's bsky.app link.

        Raises:
            ValueError: the color is not one CheerLights accepts, or the cooldown is running
            CheerLightsUnavailable: Bluesky refused or could not be reached
        """
        color = color.strip().lower().replace(" ", "").replace("-", "")
        if color not in PALETTE:
            raise ValueError(f"{color!r} is not a CheerLights color. Try: {', '.join(PALETTE)}")
        wait = self.seconds_until_ready()
        if wait > 0:
            raise ValueError(
                f"CheerLights takes one color per person every {POST_COOLDOWN_S} s. "
                f"Try again in {wait:.0f} s."
            )
        session = await self._post(
            f"{self.service}/xrpc/com.atproto.server.createSession",
            {"identifier": self.handle, "password": self._password},
            None,
        )
        token, did = session.get("accessJwt"), session.get("did")
        if not token or not did:
            raise CheerLightsUnavailable("Bluesky did not return a session")
        created = await self._post(
            f"{self.service}/xrpc/com.atproto.repo.createRecord",
            {
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": build_post(color, now or datetime.now(timezone.utc)),
            },
            {"Authorization": f"Bearer {token}"},
        )
        self._last_post = self._clock()
        return post_url(created.get("uri", ""), session.get("handle") or self.handle)


# MQTT


class MqttFeed:
    """Pushes each new color from the CheerLights broker, on paho-mqtt's own thread.

    Anonymous clients may read the broker but not publish to it.
    """

    def __init__(self, on_color: Callable[[str], None], on_status: Callable[[bool], None]):
        self._on_color = on_color
        self._on_status = on_status
        self._client = None

    def start(self) -> None:
        import paho.mqtt.client as mqtt

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="", clean_session=True)
        client.reconnect_delay_set(min_delay=2, max_delay=60)

        def on_connect(client, userdata, flags, reason_code, properties=None):
            if reason_code.is_failure:
                self._on_status(False)
                return
            client.subscribe(MQTT_TOPIC, qos=0)
            self._on_status(True)

        def on_disconnect(client, userdata, flags, reason_code, properties=None):
            self._on_status(False)

        def on_message(client, userdata, message):
            name = message.payload.decode("utf-8", "replace").strip().lower()
            if name:
                self._on_color(name)

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            client.disconnect()
            client.loop_stop()


# The live service


@dataclass
class Change:
    """A color change seen while Clause Code was running."""

    color: Color
    seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CheerLights:
    """The live CheerLights color, its history, who set it, and the way to set it.

    ``start_live()`` follows the color: a push from the MQTT broker, or a ThingSpeak
    poll every 30 seconds when the broker cannot be reached. Everything degrades to
    "offline" without raising, so the rest of Clause Code never waits on it.
    """

    def __init__(
        self,
        *,
        poster: Optional[BlueskyPoster] = None,
        get: HttpGet = http_get,
        feed_factory: Optional[Callable[..., Any]] = MqttFeed,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ):
        self.poster = poster
        self._get = get
        self._feed_factory = feed_factory
        self._now = now
        self.current: Optional[Color] = None
        self.setter: Optional[Setter] = None
        self.status = "off"  # off, connecting, live, polling, offline
        self.error: Optional[str] = None
        self.changes: deque[Change] = deque(maxlen=50)
        self._listeners: list[Callable[[Color], None]] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._feed = None
        self._mqtt_up = False
        self._tasks: set[asyncio.Task] = set()
        self._poller: Optional[asyncio.Task] = None
        self._pushes = 0  # numbers each push, so a slow check cannot undo a newer one
        self._lock = threading.Lock()

    def now(self) -> datetime:
        """The current time, as this service sees it."""
        return self._now()

    # Reading

    async def fetch_current(self) -> Color:
        """Read the current color from ThingSpeak."""
        return parse_entry(await self._get(f"{THINGSPEAK}/feeds/last.json"))

    async def fetch_history(self, count: int = 10) -> list[Color]:
        """Read the most recent colors from ThingSpeak, oldest first (1 to 100)."""
        count = min(max(int(count), 1), 100)
        data = await self._get(f"{THINGSPEAK}/feed.json?results={count}")
        feeds = (data or {}).get("feeds") or []
        return [parse_entry(entry) for entry in feeds if entry.get("field1")]

    async def find_setter(self, color: Color) -> Optional[Setter]:
        """Look for the public Bluesky post that set a color. None when there is none."""
        query = urllib.parse.urlencode({"q": "cheerlights", "sort": "latest", "limit": 50})
        try:
            data = await self._get(f"{BLUESKY_SEARCH}?{query}")
        except CheerLightsUnavailable as e:
            log.debug("bluesky search failed: %s", e)
            return None
        return match_setter((data or {}).get("posts") or [], color)

    async def snapshot(self) -> tuple[Color, Optional[Setter]]:
        """The color right now and who set it, from the live feed or a fresh read.

        Raises:
            CheerLightsUnavailable: when there is no live color and ThingSpeak is unreachable
        """
        if self.current is not None and self.status in ("live", "polling"):
            return self.current, self.setter
        color = await self.fetch_current()
        setter = await self.find_setter(color)
        return color, setter

    # Following live

    def add_listener(self, callback: Callable[[Color], None]) -> None:
        """Call ``callback(color)`` on the event loop after every change."""
        self._listeners.append(callback)

    @property
    def following(self) -> bool:
        return self.status not in ("off",)

    async def start_live(self) -> None:
        """Start following the color. Returns at once; the first read runs in the background."""
        if self.following:
            return
        self._loop = asyncio.get_running_loop()
        self.status = "connecting"
        self._spawn(self._first_read())
        if self._feed_factory is not None:
            try:
                self._feed = self._feed_factory(self._from_thread_color, self._from_thread_status)
                self._feed.start()
            except Exception as e:  # noqa: BLE001 - any broker failure means "poll instead"
                log.debug("mqtt unavailable: %s", e)
                self._feed = None
        self._poller = self._spawn(self._poll())

    async def stop_live(self) -> None:
        """Stop following the color."""
        feed, self._feed = self._feed, None
        if feed is not None:
            await asyncio.to_thread(feed.stop)
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()
        self._mqtt_up = False
        self.status = "off"

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _first_read(self) -> None:
        try:
            color = await self.fetch_current()
        except CheerLightsUnavailable as e:
            self.error = str(e)
            if not self._mqtt_up:
                self.status = "offline"
            return
        self.error = None
        if self.current is None:
            self._set(color, record=False)
        if self.status in ("connecting", "offline"):
            self.status = "live" if self._mqtt_up else "polling"
        self._spawn(self._attribute(color, delay=0))

    async def _poll(self) -> None:
        # ThingSpeak stands in while the broker is down, and catches up after a reconnect.
        while True:
            await asyncio.sleep(POLL_INTERVAL_S)
            if self._mqtt_up:
                continue
            try:
                color = await self.fetch_current()
            except CheerLightsUnavailable as e:
                self.error = str(e)
                self.status = "offline"
                continue
            self.error = None
            self.status = "polling"
            if self._is_newer(color):
                changed = self.current is not None and color.name != self.current.name
                self._set(color, record=changed)
                self._spawn(self._attribute(color, delay=0))

    def _is_newer(self, color: Color) -> bool:
        """Whether a color read from ThingSpeak is a later change than the one showing.

        Entry numbers decide when both colors have one. A color from a push has none
        until ThingSpeak records it, so its time decides, with a margin for the two clocks.
        """
        current = self.current
        if current is None:
            return True
        if current.entry_id is not None and color.entry_id is not None:
            return color.entry_id > current.entry_id
        if current.entry_id is None and color.entry_id is None:
            return False  # nothing to say this read is any later
        if current.set_at is not None and color.set_at is not None:
            return color.set_at >= current.set_at - timedelta(seconds=CLOCK_MARGIN_S)
        return color.entry_id is not None

    def _from_thread_color(self, name: str) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(lambda: self._spawn(self._on_pushed(name)))

    def _from_thread_status(self, up: bool) -> None:
        loop = self._loop
        if loop is not None and not loop.is_closed():
            loop.call_soon_threadsafe(self._on_status, up)

    def _on_status(self, up: bool) -> None:
        self._mqtt_up = up
        if not self.following:
            return
        if up:
            self.status = "live"
        elif self.current is not None and self.status == "live":
            self.status = "polling"

    async def _on_pushed(self, name: str) -> None:
        self._pushes += 1
        push = self._pushes
        if self.current is not None and name == self.current.name:
            return  # The broker repeats the retained color on every (re)connect
        # ThingSpeak has the time the color was set; use it when it agrees with the push.
        color = Color(name=name, hex=PALETTE.get(name, ""), set_at=self._now())
        try:
            fetched = await self.fetch_current()
            if fetched.name == name and self._is_newer(fetched):
                color = fetched
        except CheerLightsUnavailable:
            pass
        if push != self._pushes:
            return  # A later push arrived while ThingSpeak answered; it is the color now
        if not color.hex:
            return  # A name outside the palette with no hex to show
        first = self.current is None
        self._set(color, record=not first)
        self.status = "live"
        self._spawn(self._attribute(color, delay=ATTRIBUTION_DELAY_S))

    def _set(self, color: Color, *, record: bool) -> None:
        with self._lock:
            self.current = color
            self.setter = None
            if record:
                self.changes.append(Change(color, self._now()))
        for callback in list(self._listeners):
            try:
                callback(color)
            except Exception:  # noqa: BLE001 - a display callback must not stop the feed
                log.exception("cheerlights listener failed")

    async def _attribute(self, color: Color, delay: float) -> None:
        if delay:
            await asyncio.sleep(delay)
        setter = await self.find_setter(color)
        if (
            setter
            and self.current is not None
            and self.current.entry_id == color.entry_id
            and self.current.name == color.name
        ):
            self.setter = setter
            for callback in list(self._listeners):
                try:
                    callback(color)
                except Exception:  # noqa: BLE001
                    log.exception("cheerlights listener failed")

    def changes_since(self, when: datetime) -> list[Color]:
        """Colors the lights changed to after ``when``, oldest first."""
        return [change.color for change in self.changes if change.seen_at >= when]

    # Writing

    async def set_color(self, color: str) -> str:
        """Set the color by posting to the user's Bluesky account.

        Returns:
            The post's link

        Raises:
            ValueError: no Bluesky account configured, bad color, or cooldown
            CheerLightsUnavailable: Bluesky refused or could not be reached
        """
        if self.poster is None:
            raise ValueError(HOW_TO_SET)
        return await self.poster.post_color(color, self._now())

    # Words

    def describe(self, color: Color, setter: Optional[Setter]) -> str:
        """One line: "yellow · set 4 min ago · by @someone on Bluesky"."""
        who = f"by @{setter.handle} on {setter.source}" if setter else "by someone, somewhere"
        return f"{color.name} · set {ago(color.set_at, self._now())} · {who}"


HOW_TO_SET = (
    "Anyone can set the CheerLights color:\n"
    "  • on Discord, with the /cheerlights command (https://cheerlights.com/discord)\n"
    '  • on Bluesky, with a post like "#cheerlights red"\n'
    "To set it from Clause Code, set BLUESKY_HANDLE and BLUESKY_APP_PASSWORD (an app\n"
    "password from Bluesky's settings) and restart. Clause Code then posts\n"
    '"#cheerlights <color>" from your account.'
)


def light_string(count: int = 9) -> str:
    """A string of holiday lights, to be drawn in the current color."""
    return "─".join(["●"] * count)


__all__ = [
    "BlueskyPoster",
    "Change",
    "CheerLights",
    "CheerLightsUnavailable",
    "Color",
    "HOW_TO_SET",
    "MqttFeed",
    "PALETTE",
    "Setter",
    "ago",
    "build_post",
    "colors_in",
    "glow",
    "ink_for",
    "readable",
    "light_string",
    "match_setter",
    "parse_entry",
]
