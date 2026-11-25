"""Checks against the real CheerLights services. They need the internet, so they only run
with CLAUSE_LIVE=1:

    CLAUSE_LIVE=1 uv run pytest tests/test_live.py

Nothing here writes anywhere: the MQTT broker is read anonymously and nothing is posted.
"""

import asyncio
import os

import pytest

from clause_code.cheerlights import PALETTE, CheerLights

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("CLAUSE_LIVE") != "1", reason="set CLAUSE_LIVE=1"),
]


async def test_thingspeak_current_color():
    color = await CheerLights().fetch_current()

    assert color.name in PALETTE
    assert color.hex == PALETTE[color.name]
    assert color.set_at is not None and color.entry_id


async def test_thingspeak_history():
    colors = await CheerLights().fetch_history(20)

    assert len(colors) == 20
    assert all(c.hex == PALETTE[c.name] for c in colors)
    assert [c.set_at for c in colors] == sorted(c.set_at for c in colors)


async def test_bluesky_search_answers():
    service = CheerLights()
    color = await service.fetch_current()

    # None is a fine answer (most colors come from Discord); an exception is not
    await service.find_setter(color)


async def test_mqtt_broker_pushes_the_current_color():
    service = CheerLights()
    await service.start_live()
    try:
        for _ in range(100):
            if service.status == "live" and service.current is not None:
                break
            await asyncio.sleep(0.1)
        assert service.status == "live"
        assert service.current.name in PALETTE
    finally:
        await service.stop_live()
