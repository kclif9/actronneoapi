"""Unit tests for the SignalR realtime client skeleton."""

from __future__ import annotations

import asyncio

import pytest

from actron_neo_api.rt import RealtimeConnectionDetails, SignalRRTClient


def test_register_callback_and_emit(tmp_path) -> None:
    details = RealtimeConnectionDetails(endpoint="https://example.test/signalr", port=443, protocol="https", user_id="u")
    client = SignalRRTClient(details, access_token="secret")

    seen: list = []

    def cb(ev):
        seen.append(ev)

    client.register_callback(cb)

    ev = type("E", (), {"message": type("M", (), {"domain_model": {"foo": "bar"}})})()

    # schedule emit and consume from queue
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client._emit_event(ev))

    # callback should have been called and queue populated
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_iter_events_and_update_token() -> None:
    details = RealtimeConnectionDetails(endpoint="https://example.test/signalr", port=443, protocol="https", user_id="u")
    client = SignalRRTClient(details, access_token="oldtoken")

    # put a fake event onto the queue
    ev = type("E", (), {"message": type("M", (), {"domain_model": {"k": "v"}})})()
    await client._emit_event(ev)

    # update token should not raise
    await client.update_access_token("newtoken")

    it = client.iter_events()
    got = await asyncio.wait_for(it.__anext__(), timeout=1.0)
    assert got is ev
