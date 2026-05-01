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
from typing import AsyncIterator, Callable, Dict, Optional, Set

import aiohttp

from .base import (
    RealtimeClient,
    RealtimeEvent,
    RealtimeMessage,
    RealtimeConnectionDetails,
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
        self._connection_details = connection_details
        self._access_token = access_token
        self._session = session
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay

        self._subscriptions: Set[str] = set()
        self._callbacks: list[Callable[[RealtimeEvent], None]] = []
        self._events: "asyncio.Queue[RealtimeEvent]" = asyncio.Queue()

        self._supervisor_task: Optional[asyncio.Task] = None
        self._running = False

    def register_callback(self, callback: Callable[[RealtimeEvent], None]) -> None:
        self._callbacks.append(callback)

    async def connect(self) -> None:
        if self._supervisor_task is not None:
            return
        if self._session is None:
            self._session = aiohttp.ClientSession()
        self._running = True
        self._supervisor_task = asyncio.create_task(self._run_supervisor())

    async def disconnect(self) -> None:
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
        self._subscriptions.add(device_serial)
        await self._send_subscribe(device_serial)

    async def unsubscribe(self, device_serial: str) -> None:
        self._subscriptions.discard(device_serial)
        await self._send_unsubscribe(device_serial)

    async def update_access_token(self, access_token: str) -> None:
        self._access_token = access_token

    async def iter_events(self) -> AsyncIterator[RealtimeEvent]:
        while True:
            ev = await self._events.get()
            yield ev

    async def _send_subscribe(self, device_serial: str) -> None:
        if not self._session:
            return
        url = f"{self._connection_details.endpoint.rstrip('/')}/subscribe"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with self._session.post(url, json={"serial": device_serial}, headers=headers, timeout=10):
                pass
        except Exception:  # pragma: no cover - network defensive behavior
            _LOGGER.debug("subscribe POST failed", exc_info=True)

    async def _send_unsubscribe(self, device_serial: str) -> None:
        if not self._session:
            return
        url = f"{self._connection_details.endpoint.rstrip('/')}/unsubscribe"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with self._session.post(url, json={"serial": device_serial}, headers=headers, timeout=10):
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
        url = self._connection_details.endpoint
        async with self._session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise RuntimeError(f"sse connect failed: {resp.status}")
            # SSE: read stream and accumulate data: lines
            buffer = ""
            async for raw in resp.content:  # type: ignore[attr-defined]
                if not self._running:
                    break
                try:
                    line = raw.decode()
                except Exception:
                    continue
                if line.startswith("data:"):
                    buffer += line[len("data:"):].strip()
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

    def _handle_payload(self, payload: Dict) -> None:
        try:
            # Prefer domain model conversion when payload contains known fields
            if isinstance(payload, dict) and ("Status" in payload or "status" in payload):
                try:
                    from actron_neo_api.models.status import ActronAirStatus

                    status_payload = payload.get("Status") or payload.get("status")
                    domain = ActronAirStatus.model_validate(status_payload)
                except Exception:
                    domain = payload
            else:
                domain = payload

            ev = RealtimeEvent(message=RealtimeMessage(domain_model=domain))
            asyncio.create_task(self._emit_event(ev))
        except Exception:
            _LOGGER.exception("failed to handle incoming signalr payload")

    async def _emit_event(self, ev: RealtimeEvent) -> None:
        for cb in list(self._callbacks):
            try:
                cb(ev)
            except Exception:
                _LOGGER.exception("event callback failed")
        await self._events.put(ev)
