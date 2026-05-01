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
from typing import AsyncIterator, Callable, Optional

import aiohttp

from .base import (
    RealtimeClient,
    RealtimeConnectionDetails,
    RealtimeEvent,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
)

_LOGGER = logging.getLogger(__name__)


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
    ) -> None:
        """Initialize the SignalRRTClient.

        Args:
            connection_details: Connection info for the SignalR endpoint.
            access_token: OAuth2 access token.
            session: Optional aiohttp session (for testing/mocking).
            reconnect_initial_delay: Initial reconnect backoff (seconds).
            reconnect_max_delay: Max reconnect backoff (seconds).
        """
        self._connection_details = connection_details
        self._access_token = access_token
        self._session = session
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay

        self._subscriptions: set[str] = set()
        self._callbacks: list[Callable[[RealtimeEvent], None]] = []
        self._events: asyncio.Queue[RealtimeEvent] = asyncio.Queue()

        self._supervisor_task: Optional[asyncio.Task[None]] = None
        self._running = False

    def register_callback(self, callback: Callable[[RealtimeEvent], None]) -> None:
        """Register a callback to receive realtime events."""
        self._callbacks.append(callback)

    async def connect(self) -> None:
        """Connect to the SignalR endpoint and start listening."""
        if self._supervisor_task is not None:
            return
        if self._session is None:
            self._session = aiohttp.ClientSession()
        self._running = True
        self._supervisor_task = asyncio.create_task(self._run_supervisor())

    async def disconnect(self) -> None:
        """Disconnect from the SignalR endpoint and stop listening."""
        self._running = False
        task = self._supervisor_task
        self._supervisor_task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def subscribe(self, device_serial: str) -> None:
        """Subscribe to updates for a device serial."""
        self._subscriptions.add(device_serial)
        await self._send_subscribe(device_serial)

    async def unsubscribe(self, device_serial: str) -> None:
        """Unsubscribe from updates for a device serial."""
        self._subscriptions.discard(device_serial)
        await self._send_unsubscribe(device_serial)

    async def update_access_token(self, access_token: str) -> None:
        """Update the OAuth2 access token used for authentication."""
        self._access_token = access_token

    async def iter_events(self) -> AsyncIterator[RealtimeEvent]:
        """Yield realtime events as they arrive."""
        while True:
            ev = await self._events.get()
            yield ev

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
            session = self._session
            if session is None:
                return
            url = f"{self._connection_details.endpoint.rstrip('/')}/subscribe"
            headers = {"Authorization": f"Bearer {self._access_token}"}
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.post(
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
            session = self._session
            if session is None:
                return
            url = f"{self._connection_details.endpoint.rstrip('/')}/unsubscribe"
            headers = {"Authorization": f"Bearer {self._access_token}"}
            try:
                timeout = aiohttp.ClientTimeout(total=10)
                async with session.post(
                    url, json={"serial": device_serial}, headers=headers, timeout=timeout
                ):
                    pass
            except Exception:  # pragma: no cover - network defensive behavior
                _LOGGER.debug("unsubscribe POST failed", exc_info=True)

    async def _run_supervisor(self) -> None:
        backoff = self._reconnect_initial_delay
        while self._running:
            try:
                await self._connect_and_listen()
                backoff = self._reconnect_initial_delay
            except asyncio.CancelledError:
                break
            except Exception:  # pragma: no cover - reconnect/backoff loop
                _LOGGER.exception("SignalR supervisor error; reconnecting in %s", backoff)
                await asyncio.sleep(backoff)
                backoff = min(self._reconnect_max_delay, backoff * 2)

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
        async with self._session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"sse connect failed: {resp.status}")
            # restore subscriptions immediately after a successful connection
            await self._restore_subscriptions()
            # SSE: read stream and accumulate data: lines
            buffer = ""
            async for raw in resp.content:
                if not self._running:
                    break
                try:
                    line = raw.decode()
                except Exception:
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

    async def _negotiate(self) -> str:
        """Call the SignalR negotiate endpoint and return an SSE connect URL.

        The negotiate response varies; prefer an explicit `url` when present,
        otherwise build a serverSentEvents URL using a connectionId/token.
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

        # If server returned a connect URL, use it directly.
        if isinstance(data, dict) and "url" in data:
            return str(data["url"])

        # Otherwise try to construct a serverSentEvents URL.
        connection_id = data.get("connectionId") if isinstance(data, dict) else None
        token = data.get("connectionToken") if isinstance(data, dict) else None
        base = self._connection_details.endpoint.rstrip("/")
        if connection_id:
            # SignalR-compatible query for serverSentEvents transport
            return f"{base}/?id={connection_id}&transport=serverSentEvents"
        if token:
            return f"{base}/?transport=serverSentEvents&connectionToken={token}"
        # Fallback to the base endpoint
        return str(self._connection_details.endpoint)

    async def _restore_subscriptions(self) -> None:
        """Resend subscribe commands for current subscriptions after reconnect."""
        for serial in list(self._subscriptions):
            try:
                await self._send_subscribe(serial)
            except Exception:
                _LOGGER.debug("failed to resubscribe %s", serial, exc_info=True)

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
        for cb in list(self._callbacks):
            try:
                cb(ev)
            except Exception:
                _LOGGER.exception("event callback failed")
        await self._events.put(ev)
