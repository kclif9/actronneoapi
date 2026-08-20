"""Minimal SignalR / SSE realtime client for Que systems.

This module provides a lightweight, asyncio-based SignalR-over-SSE client
implementation tailored to the needs of the library. It intentionally keeps
behavior conservative and testable: negotiate/connect is implemented using
`aiohttp` and incoming SSE "data:" blocks are parsed as JSON and emitted
as `RealtimeEvent` objects.

The implementation focuses on acceptance-criteria-level behavior described
in issue #76: connect, subscribe payload send, reconnect + resubscribe,
and mapping incoming payloads to shared domain models.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Optional
from urllib.parse import quote

import aiohttp

from .base import (
    DEFAULT_EVENT_QUEUE_MAXSIZE,
    RealtimeClient,
    RealtimeConnectionDetails,
    RealtimeConnectionEvent,
    RealtimeConnectionState,
    RealtimeEvent,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
    new_event_queue,
    put_event_dropping_oldest,
)

_LOGGER = logging.getLogger(__name__)
_SIGNALR_SUBSCRIBE_REFRESH_SECONDS = 300.0
_SSE_CONNECT_TIMEOUT_SECONDS = 15.0
_SSE_DEFAULT_READ_TIMEOUT_SECONDS = 600.0
_HEALTHY_CONNECTION_SECONDS = 60.0


class SignalRRTClient(RealtimeClient):
    """SignalR-over-SSE realtime client (minimal, asyncio/aiohttp based).

    Notes:
    - `connection_details.endpoint` should be the full URL to the SignalR
      endpoint that speaks Server-Sent Events (text/event-stream).
    - Subscribes are performed by POSTing a simple JSON payload to the
      provided endpoint + "/subscribe". The Android client uses a similar
      command pattern; this keeps the client generic and testable.
    """

    transport_type = RealtimeTransportType.SIGNALR

    def __init__(
        self,
        connection_details: RealtimeConnectionDetails,
        access_token: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        reconnect_initial_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
        stream_read_timeout: float | None = _SSE_DEFAULT_READ_TIMEOUT_SECONDS,
        event_queue_maxsize: int = DEFAULT_EVENT_QUEUE_MAXSIZE,
    ) -> None:
        """Initialize the SignalRRTClient.

        Args:
            connection_details: Connection info for the SignalR endpoint.
            access_token: OAuth2 access token.
            session: Optional aiohttp session (for testing/mocking).
            reconnect_initial_delay: Initial reconnect backoff (seconds).
            reconnect_max_delay: Max reconnect backoff (seconds).
            stream_read_timeout: Seconds of complete silence on the event
                stream before it is treated as dead and reconnected. This is a
                socket read timeout, so it resets on every byte received,
                including SSE keepalive comments. Pass None to disable the
                check, at the cost of never noticing a half-open connection.
            event_queue_maxsize: Number of events retained for ``iter_events``
                consumers before the oldest is dropped.

        Raises:
            ValueError: If arguments are invalid.
        """
        if not access_token.strip():
            raise ValueError("access_token cannot be empty")
        if reconnect_initial_delay <= 0:
            raise ValueError("reconnect_initial_delay must be greater than zero")
        if reconnect_max_delay < reconnect_initial_delay:
            raise ValueError("reconnect_max_delay must be greater than or equal to initial delay")
        if stream_read_timeout is not None and stream_read_timeout <= 0:
            raise ValueError("stream_read_timeout must be greater than zero or None")
        if event_queue_maxsize <= 0:
            raise ValueError("event_queue_maxsize must be greater than zero")

        self._connection_details = connection_details
        self._access_token = access_token
        self._session = session
        self._external_session = session is not None
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._stream_read_timeout = stream_read_timeout

        self._subscriptions: set[str] = set()
        self._callbacks: list[Callable[[RealtimeEvent], Awaitable[None] | None]] = []
        self._events: asyncio.Queue[RealtimeEvent] = new_event_queue(event_queue_maxsize)

        self._supervisor_task: Optional[asyncio.Task[None]] = None
        self._resubscribe_task: Optional[asyncio.Task[None]] = None
        self._connection_state = RealtimeConnectionState.DISCONNECTED
        self._running = False

    def register_callback(
        self,
        callback: Callable[[RealtimeEvent], Awaitable[None] | None],
    ) -> None:
        """Register a callback that is invoked for every emitted realtime event."""
        self._callbacks.append(callback)

    async def connect(self) -> None:
        """Connect to the SignalR endpoint and start listening."""
        if self._supervisor_task is not None and not self._supervisor_task.done():
            return
        self._supervisor_task = None
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._external_session = False
        self._running = True
        self._supervisor_task = asyncio.create_task(self._run_supervisor())

    async def disconnect(self) -> None:
        """Disconnect from the SignalR endpoint and stop listening."""
        self._running = False
        if self._resubscribe_task is not None:
            self._resubscribe_task.cancel()
            try:
                await self._resubscribe_task
            except asyncio.CancelledError:
                pass
            self._resubscribe_task = None
        task = self._supervisor_task
        self._supervisor_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._session is not None and not self._session.closed and not self._external_session:
            await self._session.close()
            self._session = None
        await self._set_state(RealtimeConnectionState.DISCONNECTED)

    async def subscribe(self, device_serial: str) -> None:
        """Subscribe to updates for a device serial."""
        serial = device_serial.strip()
        if not serial:
            raise ValueError("device_serial cannot be empty")
        self._subscriptions.add(serial)
        await self._send_subscribe(serial)

    async def unsubscribe(self, device_serial: str) -> None:
        """Unsubscribe from updates for a device serial."""
        serial = device_serial.strip()
        if not serial:
            raise ValueError("device_serial cannot be empty")
        self._subscriptions.discard(serial)
        await self._send_unsubscribe(serial)

    async def update_access_token(self, access_token: str) -> None:
        """Update the OAuth2 access token used for authentication.

        Args:
            access_token: OAuth2 access token.

        Raises:
            ValueError: If the token is empty.
        """
        normalized_access_token = access_token.strip()
        if not normalized_access_token:
            raise ValueError("access_token cannot be empty")
        self._access_token = normalized_access_token

    async def iter_events(self) -> AsyncIterator[RealtimeEvent]:
        """Yield realtime events as they arrive."""
        while self._running or not self._events.empty():
            ev = await self._events.get()
            yield ev

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish is not supported for SignalR transport."""
        raise NotImplementedError("SignalR transport does not support publish")

    async def _send_subscribe(self, device_serial: str) -> None:
        if not self._session:
            return
        url = f"{self._connection_details.endpoint.rstrip('/')}/subscribe"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self._session.post(
                url, json={"serial": device_serial}, headers=headers, timeout=timeout
            ):
                pass
        except Exception:  # pragma: no cover - network defensive behavior
            _LOGGER.debug("subscribe POST failed", exc_info=True)

    async def _send_unsubscribe(self, device_serial: str) -> None:
        if not self._session:
            return
        url = f"{self._connection_details.endpoint.rstrip('/')}/unsubscribe"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self._session.post(
                url, json={"serial": device_serial}, headers=headers, timeout=timeout
            ):
                pass
        except Exception:  # pragma: no cover - network defensive behavior
            _LOGGER.debug("unsubscribe POST failed", exc_info=True)

    async def _run_supervisor(self) -> None:
        loop = asyncio.get_running_loop()
        backoff = self._reconnect_initial_delay
        while self._running:
            started = loop.time()
            reason = "event stream ended"
            try:
                await self._set_state(RealtimeConnectionState.CONNECTING)
                await self._connect_and_listen()
            except asyncio.CancelledError:
                break
            except asyncio.TimeoutError:
                # An idle event stream timing out is routine, so reconnect
                # without logging a traceback for it.
                reason = "stream timeout"
                _LOGGER.debug("SignalR stream timed out; reconnecting in %s", backoff)
            except (aiohttp.ClientError, OSError) as exc:
                # Transport drops are expected; the supervisor reconnects.
                reason = str(exc) or type(exc).__name__
                _LOGGER.debug("SignalR reconnecting after error: %s", exc, exc_info=True)
            except Exception:  # pragma: no cover - reconnect/backoff loop
                reason = "transport error"
                _LOGGER.exception("SignalR supervisor error; reconnecting in %s", backoff)
            if not self._running:
                break
            connected_for = loop.time() - started
            await self._set_state(RealtimeConnectionState.RECONNECTING, reason=reason)
            await asyncio.sleep(backoff)
            if connected_for >= _HEALTHY_CONNECTION_SECONDS:
                # The connection was healthy for a while, so treat this as a
                # fresh failure instead of continuing to grow the backoff.
                backoff = self._reconnect_initial_delay
            else:
                backoff = min(self._reconnect_max_delay, backoff * 2)
        await self._set_state(RealtimeConnectionState.DISCONNECTED)

    async def _connect_and_listen(self) -> None:
        if not self._session:
            raise RuntimeError("no aiohttp session available")
        headers = {"Authorization": f"Bearer {self._access_token}", "Accept": "text/event-stream"}
        # Perform SignalR negotiate to obtain the best SSE URL
        try:
            sse_url = await self._negotiate()
        except Exception:
            _LOGGER.debug("negotiate failed; falling back to endpoint", exc_info=True)
            sse_url = self._connection_details.endpoint

        url = sse_url
        # The event stream is long-lived, so no total timeout may be applied:
        # aiohttp's default (5 minutes) tears down an otherwise healthy
        # connection. `sock_read` still detects a stalled stream and resets on
        # every byte received.
        timeout = aiohttp.ClientTimeout(
            total=None,
            connect=_SSE_CONNECT_TIMEOUT_SECONDS,
            sock_connect=_SSE_CONNECT_TIMEOUT_SECONDS,
            sock_read=self._stream_read_timeout,
        )
        async with self._session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"sse connect failed: {resp.status}")
            # restore subscriptions immediately after a successful connection
            await self._restore_subscriptions()
            await self._set_state(RealtimeConnectionState.CONNECTED)
            self._resubscribe_task = asyncio.create_task(self._run_subscription_refresh())
            # SSE: read stream and accumulate data: lines
            buffer = ""
            try:
                async for raw in resp.content:
                    if not self._running:
                        break
                    try:
                        line = raw.decode()
                    except Exception:
                        continue
                    if line.startswith(":"):
                        # An SSE comment is a keepalive and carries no data.
                        # Logging it makes the server's idle interval
                        # observable, which is what `stream_read_timeout`
                        # has to be chosen against.
                        _LOGGER.debug("sse keepalive: %s", line.strip())
                        continue
                    if line.startswith("data:"):
                        buffer += line[len("data:") :].strip()
                    elif line.strip() == "":
                        if buffer:
                            try:
                                payload = json.loads(buffer)
                            except Exception:
                                _LOGGER.debug("invalid sse json: %s", buffer)
                            else:
                                self._handle_payload(payload)
                            finally:
                                buffer = ""
            finally:
                if self._resubscribe_task is not None:
                    self._resubscribe_task.cancel()
                    try:
                        await self._resubscribe_task
                    except asyncio.CancelledError:
                        pass
                    self._resubscribe_task = None

    async def _negotiate(self) -> str:
        """Call the SignalR negotiate endpoint and return an SSE connect URL.

        The Actron cloud speaks classic ASP.NET SignalR (not SignalR Core):
        negotiate responses use PascalCase fields, and the SSE transport is
        reached via a `/connect` endpoint carrying the URL-encoded connection
        token and client protocol version, not the bare hub URL.
        """
        session = self._session
        if session is None:
            raise RuntimeError("no aiohttp session available")
        url = f"{self._connection_details.endpoint.rstrip('/')}/negotiate"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.post(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"negotiate failed: {resp.status}")
            data = await resp.json()

        if not isinstance(data, dict):
            return str(self._connection_details.endpoint)

        token = data.get("ConnectionToken") or data.get("connectionToken")
        if not token:
            return str(self._connection_details.endpoint)

        protocol = data.get("ProtocolVersion") or data.get("protocolVersion") or "1.2"
        base = self._connection_details.endpoint.rstrip("/")
        return (
            f"{base}/connect?transport=serverSentEvents"
            f"&connectionToken={quote(token, safe='')}"
            f"&clientProtocol={protocol}"
        )

    async def _restore_subscriptions(self) -> None:
        """Resend subscribe commands for current subscriptions after reconnect."""
        for serial in list(self._subscriptions):
            try:
                await self._send_subscribe(serial)
            except Exception:
                _LOGGER.debug("failed to resubscribe %s", serial, exc_info=True)

    async def _run_subscription_refresh(self) -> None:
        """Periodically refresh subscriptions while connected."""
        while self._running:
            await asyncio.sleep(_SIGNALR_SUBSCRIBE_REFRESH_SECONDS)
            if not self._running:
                break
            await self._restore_subscriptions()

    def _handle_payload(self, payload: dict[str, object]) -> None:
        """Parse and emit a domain event from a raw payload."""
        try:
            # Prefer domain model conversion when payload contains known fields
            domain: object | None = None
            topic = "signalr"
            if isinstance(payload, dict) and ("Status" in payload or "status" in payload):
                try:
                    from actron_neo_api.models.status import ActronAirStatus

                    status_payload = payload.get("Status") or payload.get("status")
                    domain = ActronAirStatus.model_validate(status_payload)
                except Exception:
                    domain = payload
            else:
                domain = payload

            msg = RealtimeMessage(
                transport=RealtimeTransportType.SIGNALR,
                kind=RealtimeEventKind.MESSAGE,
                topic=topic,
                payload=payload,
                raw_payload=None,
                domain_model=domain,
            )
            asyncio.create_task(self._emit_event(msg))
        except Exception:
            _LOGGER.exception("failed to handle incoming signalr payload")

    async def _emit_event(self, ev: RealtimeEvent) -> None:
        """Queue an event and notify registered callbacks."""
        put_event_dropping_oldest(self._events, ev)
        for cb in list(self._callbacks):
            try:
                result = cb(ev)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover - callback failures must not break transport
                _LOGGER.warning("Realtime event callback failed", exc_info=True)

    async def _set_state(
        self,
        state: RealtimeConnectionState,
        *,
        reason: str | None = None,
    ) -> None:
        """Update connection state and emit a connection event."""
        previous_state = self._connection_state
        self._connection_state = state
        event = RealtimeConnectionEvent(
            transport=self.transport_type,
            kind=RealtimeEventKind.CONNECTION,
            state=state,
            previous_state=previous_state,
            reason=reason,
        )
        # Connection events take the same path as messages so callback
        # subscribers see state transitions, not just queue consumers.
        await self._emit_event(event)
