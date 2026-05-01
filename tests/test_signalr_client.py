"""Unit tests for the SignalR realtime client."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import pytest

from actron_neo_api.rt import RealtimeConnectionDetails, SignalRRTClient
from actron_neo_api.rt.base import (
    RealtimeEvent,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
)


class _BadRaw:
    """Bytes-like object that fails decode for SSE parsing tests."""

    def decode(self) -> str:
        raise UnicodeDecodeError("utf-8", b"x", 0, 1, "bad")


class _AsyncContent:
    """Async iterator used as aiohttp response content."""

    def __init__(self, items: list[Any]) -> None:
        self._items = items
        self._idx = 0

    def __aiter__(self) -> _AsyncContent:
        return self

    async def __anext__(self) -> Any:
        if self._idx >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._idx]
        self._idx += 1
        return item


class _Response:
    """Minimal async-context HTTP response fake."""

    def __init__(
        self,
        *,
        status: int = 200,
        json_data: Any = None,
        content_items: list[Any] | None = None,
    ) -> None:
        self.status = status
        self._json_data = json_data
        self.content = _AsyncContent(content_items or [])

    async def __aenter__(self) -> _Response:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False

    async def json(self) -> Any:
        return self._json_data


class _Session:
    """Minimal aiohttp ClientSession fake."""

    def __init__(
        self,
        *,
        post_responses: list[_Response] | None = None,
        get_responses: list[_Response] | None = None,
    ) -> None:
        self.post_responses = post_responses or []
        self.get_responses = get_responses or []
        self.post_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.closed = False

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.post_calls.append({"url": url, **kwargs})
        if self.post_responses:
            return self.post_responses.pop(0)
        return _Response(status=200, json_data={})

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.get_calls.append({"url": url, **kwargs})
        if self.get_responses:
            return self.get_responses.pop(0)
        return _Response(status=200, content_items=[])

    async def close(self) -> None:
        self.closed = True


def _details() -> RealtimeConnectionDetails:
    return RealtimeConnectionDetails(
        endpoint="https://example.test/signalr",
        port=443,
        protocol="https",
        user_id="u",
    )


def _message(payload: dict[str, Any] | None = None) -> RealtimeMessage:
    body = payload or {"foo": "bar"}
    return RealtimeMessage(
        transport=RealtimeTransportType.SIGNALR,
        kind=RealtimeEventKind.MESSAGE,
        topic="signalr",
        payload=body,
        raw_payload=None,
        domain_model=body,
    )


@pytest.mark.asyncio
async def test_register_callback_and_emit() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    seen: list[RealtimeEvent] = []

    def cb(ev: RealtimeEvent) -> None:
        seen.append(ev)

    client.register_callback(cb)
    msg = _message()

    await client._emit_event(msg)

    assert len(seen) == 1
    assert seen[0] == msg


@pytest.mark.asyncio
async def test_emit_event_handles_callback_exception() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    seen: list[RealtimeEvent] = []

    def bad(_: RealtimeEvent) -> None:
        raise ValueError("boom")

    def good(ev: RealtimeEvent) -> None:
        seen.append(ev)

    client.register_callback(bad)
    client.register_callback(good)
    msg = _message()

    await client._emit_event(msg)

    assert seen == [msg]


@pytest.mark.asyncio
async def test_iter_events_and_update_token() -> None:
    client = SignalRRTClient(_details(), access_token="oldtoken")
    msg = _message({"k": "v"})

    await client._emit_event(msg)
    await client.update_access_token("newtoken")

    event_iter = client.iter_events()
    got = await asyncio.wait_for(event_iter.__anext__(), timeout=1.0)

    assert got is msg
    assert client._access_token == "newtoken"


@pytest.mark.asyncio
async def test_connect_creates_session_and_task(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session()

    def _factory() -> _Session:
        return session

    monkeypatch.setattr(aiohttp, "ClientSession", _factory)

    client = SignalRRTClient(_details(), access_token="secret")

    async def _run_once() -> None:
        client._running = False

    client._run_supervisor = _run_once  # type: ignore[method-assign]

    await client.connect()

    assert client._session is session
    assert client._supervisor_task is not None

    await client._supervisor_task


@pytest.mark.asyncio
async def test_connect_is_noop_when_already_connected() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    task = asyncio.create_task(asyncio.sleep(0.01))
    client._supervisor_task = task

    await client.connect()

    assert client._supervisor_task is task
    await task


@pytest.mark.asyncio
async def test_connect_restarts_when_previous_task_done(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _Session()

    def _factory() -> _Session:
        return session

    monkeypatch.setattr(aiohttp, "ClientSession", _factory)

    client = SignalRRTClient(_details(), access_token="secret")
    client._supervisor_task = asyncio.create_task(asyncio.sleep(0))
    await client._supervisor_task

    async def _run_once() -> None:
        client._running = False

    client._run_supervisor = _run_once  # type: ignore[method-assign]

    await client.connect()

    assert client._supervisor_task is not None
    await client._supervisor_task


@pytest.mark.asyncio
async def test_disconnect_cancels_task_and_closes_session() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    client._session = _Session()
    client._external_session = False
    client._running = True
    client._supervisor_task = asyncio.create_task(asyncio.sleep(10))

    await client.disconnect()

    assert client._running is False
    assert client._supervisor_task is None
    assert client._session is None


@pytest.mark.asyncio
async def test_disconnect_does_not_close_external_session() -> None:
    session = _Session()
    client = SignalRRTClient(_details(), access_token="secret", session=session)

    await client.disconnect()

    assert session.closed is False
    assert client._session is session


@pytest.mark.asyncio
async def test_disconnect_without_task_or_session() -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    await client.disconnect()

    assert client._supervisor_task is None
    assert client._session is None


@pytest.mark.asyncio
async def test_disconnect_cancels_resubscribe_task() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    client._running = True
    client._resubscribe_task = asyncio.create_task(asyncio.sleep(10))

    await client.disconnect()

    assert client._resubscribe_task is None


@pytest.mark.asyncio
async def test_subscribe_and_unsubscribe_send_posts() -> None:
    session = _Session(post_responses=[_Response(), _Response()])
    client = SignalRRTClient(_details(), access_token="secret", session=session)

    await client.subscribe("SERIAL1")
    await client.unsubscribe("SERIAL1")

    assert "SERIAL1" not in client._subscriptions
    assert len(session.post_calls) == 2
    assert session.post_calls[0]["url"].endswith("/subscribe")
    assert session.post_calls[0]["json"] == {"serial": "SERIAL1"}
    assert session.post_calls[1]["url"].endswith("/unsubscribe")


@pytest.mark.asyncio
async def test_send_subscribe_and_unsubscribe_no_session_noop() -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    await client._send_subscribe("SERIAL1")
    await client._send_unsubscribe("SERIAL1")

    assert client._session is None


@pytest.mark.asyncio
async def test_subscribe_unsubscribe_empty_serial_rejected() -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    with pytest.raises(ValueError, match="device_serial cannot be empty"):
        await client.subscribe("  ")

    with pytest.raises(ValueError, match="device_serial cannot be empty"):
        await client.unsubscribe("")


@pytest.mark.asyncio
async def test_run_supervisor_retries_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SignalRRTClient(
        _details(),
        access_token="secret",
        reconnect_initial_delay=0.25,
        reconnect_max_delay=1.0,
    )
    client._running = True
    calls = {"connect": 0}
    slept: list[float] = []

    async def _connect_and_listen() -> None:
        calls["connect"] += 1
        if calls["connect"] == 1:
            raise RuntimeError("fail once")
        client._running = False

    async def _sleep(delay: float) -> None:
        slept.append(delay)

    client._connect_and_listen = _connect_and_listen  # type: ignore[method-assign]
    monkeypatch.setattr(asyncio, "sleep", _sleep)

    await client._run_supervisor()

    assert calls["connect"] == 2
    assert slept == [0.25]


@pytest.mark.asyncio
async def test_run_supervisor_uses_backoff_when_stream_ends(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SignalRRTClient(
        _details(),
        access_token="secret",
        reconnect_initial_delay=0.25,
        reconnect_max_delay=1.0,
    )
    client._running = True
    slept: list[float] = []

    async def _connect_and_listen() -> None:
        return None

    async def _sleep(delay: float) -> None:
        slept.append(delay)
        client._running = False

    client._connect_and_listen = _connect_and_listen  # type: ignore[method-assign]
    monkeypatch.setattr(asyncio, "sleep", _sleep)

    await client._run_supervisor()

    assert slept == [0.25]


@pytest.mark.asyncio
async def test_run_supervisor_stops_on_cancelled_error() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    client._running = True

    async def _connect_and_listen() -> None:
        raise asyncio.CancelledError

    client._connect_and_listen = _connect_and_listen  # type: ignore[method-assign]

    await client._run_supervisor()

    assert client._running is True


@pytest.mark.asyncio
async def test_connect_and_listen_requires_session() -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    with pytest.raises(RuntimeError, match="no aiohttp session available"):
        await client._connect_and_listen()


@pytest.mark.asyncio
async def test_connect_and_listen_raises_when_sse_status_not_200() -> None:
    session = _Session(get_responses=[_Response(status=500)])
    client = SignalRRTClient(_details(), access_token="secret", session=session)
    client._running = True

    async def _negotiate() -> str:
        return "https://example.test/signalr/connect"

    client._negotiate = _negotiate  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="sse connect failed"):
        await client._connect_and_listen()


@pytest.mark.asyncio
async def test_connect_and_listen_fallback_when_negotiate_fails() -> None:
    data = [b'data: {"x": 1}\n', b"\n"]
    session = _Session(get_responses=[_Response(status=200, content_items=data)])
    client = SignalRRTClient(_details(), access_token="secret", session=session)
    client._running = True

    async def _negotiate() -> str:
        raise RuntimeError("negotiate failed")

    seen: list[dict[str, object]] = []

    def _handle_payload(payload: dict[str, object]) -> None:
        seen.append(payload)
        client._running = False

    client._negotiate = _negotiate  # type: ignore[method-assign]
    client._handle_payload = _handle_payload  # type: ignore[method-assign]

    await client._connect_and_listen()

    assert session.get_calls[0]["url"] == "https://example.test/signalr"
    assert seen == [{"x": 1}]


@pytest.mark.asyncio
async def test_connect_and_listen_handles_bad_decode_and_invalid_json() -> None:
    data = [_BadRaw(), b"data: not-json\n", b"\n"]
    session = _Session(get_responses=[_Response(status=200, content_items=data)])
    client = SignalRRTClient(_details(), access_token="secret", session=session)
    client._running = True

    async def _negotiate() -> str:
        return "https://example.test/signalr/connect"

    client._negotiate = _negotiate  # type: ignore[method-assign]

    await client._connect_and_listen()

    assert session.get_calls[0]["url"] == "https://example.test/signalr/connect"


@pytest.mark.asyncio
async def test_connect_and_listen_breaks_when_not_running() -> None:
    data = [b'data: {"x": 1}\n', b"\n"]
    session = _Session(get_responses=[_Response(status=200, content_items=data)])
    client = SignalRRTClient(_details(), access_token="secret", session=session)
    client._running = False

    async def _negotiate() -> str:
        return "https://example.test/signalr/connect"

    seen: list[dict[str, object]] = []

    def _handle_payload(payload: dict[str, object]) -> None:
        seen.append(payload)

    client._negotiate = _negotiate  # type: ignore[method-assign]
    client._handle_payload = _handle_payload  # type: ignore[method-assign]

    await client._connect_and_listen()

    assert seen == []


@pytest.mark.asyncio
async def test_negotiate_requires_session() -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    with pytest.raises(RuntimeError, match="no aiohttp session available"):
        await client._negotiate()


@pytest.mark.asyncio
async def test_negotiate_raises_on_non_200() -> None:
    session = _Session(post_responses=[_Response(status=401, json_data={})])
    client = SignalRRTClient(_details(), access_token="secret", session=session)

    with pytest.raises(RuntimeError, match="negotiate failed: 401"):
        await client._negotiate()


@pytest.mark.asyncio
async def test_update_access_token_validates_and_normalizes() -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    with pytest.raises(ValueError, match="access_token cannot be empty"):
        await client.update_access_token("  ")

    await client.update_access_token(" next-token ")
    assert client._access_token == "next-token"


@pytest.mark.asyncio
async def test_iter_events_returns_when_not_running_and_empty() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    items = [item async for item in client.iter_events()]
    assert items == []


@pytest.mark.asyncio
async def test_publish_not_supported() -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    with pytest.raises(NotImplementedError, match="does not support publish"):
        await client.publish("topic", {"x": 1})


@pytest.mark.parametrize(
    ("access_token", "initial_delay", "max_delay", "error_match"),
    [
        ("", 1.0, 30.0, "access_token cannot be empty"),
        ("secret", 0.0, 30.0, "reconnect_initial_delay must be greater than zero"),
        (
            "secret",
            2.0,
            1.0,
            "reconnect_max_delay must be greater than or equal to initial delay",
        ),
    ],
)
def test_constructor_validation(
    access_token: str,
    initial_delay: float,
    max_delay: float,
    error_match: str,
) -> None:
    with pytest.raises(ValueError, match=error_match):
        SignalRRTClient(
            _details(),
            access_token=access_token,
            reconnect_initial_delay=initial_delay,
            reconnect_max_delay=max_delay,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"url": "https://example.test/signalr/sse"}, "https://example.test/signalr/sse"),
        (
            {"connectionId": "cid-1"},
            "https://example.test/signalr/?id=cid-1&transport=serverSentEvents",
        ),
        (
            {"connectionToken": "tok-1"},
            "https://example.test/signalr/?transport=serverSentEvents&connectionToken=tok-1",
        ),
        ({"other": "value"}, "https://example.test/signalr"),
    ],
)
async def test_negotiate_url_variants(payload: dict[str, str], expected: str) -> None:
    session = _Session(post_responses=[_Response(status=200, json_data=payload)])
    client = SignalRRTClient(_details(), access_token="secret", session=session)

    got = await client._negotiate()

    assert got == expected


@pytest.mark.asyncio
async def test_restore_subscriptions_invokes_send_subscribe() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    client._subscriptions = {"A", "B"}
    sent: list[str] = []

    async def _send(serial: str) -> None:
        sent.append(serial)

    client._send_subscribe = _send  # type: ignore[method-assign]

    await client._restore_subscriptions()

    assert sorted(sent) == ["A", "B"]


@pytest.mark.asyncio
async def test_restore_subscriptions_ignores_send_errors() -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    client._subscriptions = {"A"}

    async def _send(_: str) -> None:
        raise RuntimeError("boom")

    client._send_subscribe = _send  # type: ignore[method-assign]

    await client._restore_subscriptions()


@pytest.mark.asyncio
async def test_run_subscription_refresh_breaks_after_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    client._running = True
    restored = {"count": 0}

    async def _sleep(_: float) -> None:
        client._running = False

    async def _restore() -> None:
        restored["count"] += 1

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    client._restore_subscriptions = _restore  # type: ignore[method-assign]

    await client._run_subscription_refresh()

    assert restored["count"] == 0


@pytest.mark.asyncio
async def test_run_subscription_refresh_calls_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    client._running = True
    restored = {"count": 0}

    async def _sleep(_: float) -> None:
        return None

    async def _restore() -> None:
        restored["count"] += 1
        client._running = False

    monkeypatch.setattr(asyncio, "sleep", _sleep)
    client._restore_subscriptions = _restore  # type: ignore[method-assign]

    await client._run_subscription_refresh()

    assert restored["count"] == 1


@pytest.mark.asyncio
async def test_handle_payload_status_parse_success(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    payload = {
        "Status": {
            "isOn": True,
            "lastKnownState": {
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "FanMode": "LOW",
                    "TemperatureSetpoint_Cool_oC": 22,
                    "TemperatureSetpoint_Heat_oC": 20,
                }
            },
            "MasterInfo": {},
            "Alerts": {},
            "RemoteZoneInfo": [],
            "SystemStatus_Local": {},
            "LiveAircon": {},
            "AirconSystem": {},
        }
    }

    seen: list[RealtimeEvent] = []

    async def _emit(ev: RealtimeEvent) -> None:
        seen.append(ev)

    client._emit_event = _emit  # type: ignore[method-assign]

    created: list[asyncio.Task[Any]] = []
    real_create_task = asyncio.create_task

    def _capture(coro: Any) -> asyncio.Task[Any]:
        task = real_create_task(coro)
        created.append(task)
        return task

    monkeypatch.setattr(asyncio, "create_task", _capture)

    client._handle_payload(payload)
    await asyncio.gather(*created)

    assert len(seen) == 1
    msg = seen[0]
    assert isinstance(msg, RealtimeMessage)
    assert msg.payload == payload
    assert msg.domain_model is not None


@pytest.mark.asyncio
async def test_handle_payload_status_parse_failure_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    payload = {"Status": {"bad": object()}}
    seen: list[RealtimeEvent] = []

    async def _emit(ev: RealtimeEvent) -> None:
        seen.append(ev)

    client._emit_event = _emit  # type: ignore[method-assign]

    created: list[asyncio.Task[Any]] = []
    real_create_task = asyncio.create_task

    def _capture(coro: Any) -> asyncio.Task[Any]:
        task = real_create_task(coro)
        created.append(task)
        return task

    def _raise_validate(_: Any) -> Any:
        raise ValueError("invalid status payload")

    monkeypatch.setattr(
        "actron_neo_api.models.status.ActronAirStatus.model_validate",
        _raise_validate,
    )
    monkeypatch.setattr(asyncio, "create_task", _capture)

    client._handle_payload(payload)
    await asyncio.gather(*created)

    assert len(seen) == 1
    msg = seen[0]
    assert isinstance(msg, RealtimeMessage)
    assert msg.domain_model == payload


@pytest.mark.asyncio
async def test_handle_payload_without_status_uses_raw_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SignalRRTClient(_details(), access_token="secret")
    payload = {"a": 1}
    seen: list[RealtimeEvent] = []

    async def _emit(ev: RealtimeEvent) -> None:
        seen.append(ev)

    client._emit_event = _emit  # type: ignore[method-assign]

    created: list[asyncio.Task[Any]] = []
    real_create_task = asyncio.create_task

    def _capture(coro: Any) -> asyncio.Task[Any]:
        task = real_create_task(coro)
        created.append(task)
        return task

    monkeypatch.setattr(asyncio, "create_task", _capture)

    client._handle_payload(payload)
    await asyncio.gather(*created)

    assert len(seen) == 1
    msg = seen[0]
    assert isinstance(msg, RealtimeMessage)
    assert msg.domain_model == payload


@pytest.mark.asyncio
async def test_handle_payload_outer_exception_path(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SignalRRTClient(_details(), access_token="secret")

    def _raise(coro: Any) -> None:
        coro.close()
        raise RuntimeError("create task failed")

    monkeypatch.setattr(asyncio, "create_task", _raise)

    # The method should swallow/log the failure and not raise.
    client._handle_payload({"a": 1})
