"""Neo MQTT realtime client.

This module encapsulates the Neo cloud push transport used by the Android app.
It keeps MQTT-specific behavior isolated from the shared API models so the rest
of the library can treat realtime updates as generic events.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import ssl
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiomqtt import Client, MqttError

from ..models import ActronAirStatus
from .base import (
    RealtimeConnectionDetails,
    RealtimeConnectionEvent,
    RealtimeConnectionState,
    RealtimeEvent,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
)

_LOGGER = logging.getLogger(__name__)

_MQTT_TOPIC_PREFIX = "actron-cloud"
_MQTT_PLATFORM_SEGMENT = "neo"
_MQTT_TOPIC_HEART_BEAT = "mwc/heart-beat"
_MQTT_TOPIC_FULL_STATUS = "mwc/full-status"
_MQTT_TOPIC_CMD_RESPONSE = "mwc/cmd-response"
_MQTT_TOPIC_STATUS_CHANGE = "mwc/status-change"
_MQTT_DEFAULT_KEEPALIVE = 60
_MQTT_DEFAULT_RECONNECT_DELAY = 0.5
_MQTT_MAX_RECONNECT_DELAY = 60.0


@dataclass(frozen=True, slots=True)
class NeoMQTTTopicSet:
    """The MQTT topics associated with a single Neo device subscription."""

    heart_beat: str
    full_status: str
    cmd_response: str
    status_change: str


class MQTTRTClient:
    """Neo MQTT realtime client.

    The client keeps a background connection loop alive, automatically
    reconnects after transient failures, and resubscribes to all known topics.
    It also converts full-status payloads into :class:`ActronAirStatus` models.

    Args:
        connection_details: Realtime connection information from the backend.
        access_token: OAuth access token used as the MQTT password.
        client_id: Optional MQTT client identifier.
        ssl_context: Optional custom TLS context.
        keepalive: MQTT keepalive interval in seconds.
        connect_timeout: Time to wait for the first successful connection.
        reconnect_initial_delay: Initial reconnect delay in seconds.
        reconnect_max_delay: Maximum reconnect delay in seconds.

    """

    transport_type = RealtimeTransportType.MQTT

    def __init__(
        self,
        connection_details: RealtimeConnectionDetails,
        access_token: str,
        client_id: str | None = None,
        ssl_context: ssl.SSLContext | None = None,
        keepalive: int = _MQTT_DEFAULT_KEEPALIVE,
        connect_timeout: float = 15.0,
        reconnect_initial_delay: float = _MQTT_DEFAULT_RECONNECT_DELAY,
        reconnect_max_delay: float = _MQTT_MAX_RECONNECT_DELAY,
    ) -> None:
        """Initialize the MQTT realtime client."""
        if not access_token.strip():
            raise ValueError("access_token cannot be empty")
        if keepalive <= 0:
            raise ValueError("keepalive must be greater than zero")
        if connect_timeout <= 0:
            raise ValueError("connect_timeout must be greater than zero")
        if reconnect_initial_delay <= 0:
            raise ValueError("reconnect_initial_delay must be greater than zero")
        if reconnect_max_delay < reconnect_initial_delay:
            raise ValueError("reconnect_max_delay must be greater than or equal to initial delay")

        self._details = connection_details
        self._access_token = access_token
        self._client_id = client_id or uuid.uuid4().hex
        self._ssl_context = ssl_context
        self._keepalive = keepalive
        self._connect_timeout = connect_timeout
        self._reconnect_initial_delay = reconnect_initial_delay
        self._reconnect_max_delay = reconnect_max_delay

        self._client: Client | None = None
        self._supervisor_task: asyncio.Task[None] | None = None
        self._running = False
        self._connected_event = asyncio.Event()
        self._connection_state = RealtimeConnectionState.DISCONNECTED
        self._subscriptions: set[str] = set()
        self._callbacks: list[Callable[[RealtimeEvent], Awaitable[None] | None]] = []
        self._event_queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue()
        self._last_error: Exception | None = None

    @property
    def connection_details(self) -> RealtimeConnectionDetails:
        """Return the connection details used by the client."""
        return self._details

    @property
    def access_token(self) -> str:
        """Return the current OAuth access token."""
        return self._access_token

    @property
    def connection_state(self) -> RealtimeConnectionState:
        """Return the current connection state."""
        return self._connection_state

    @property
    def last_error(self) -> Exception | None:
        """Return the last connection error, if any."""
        return self._last_error

    @staticmethod
    def build_topic_set(
        user_id: str,
        device_serial: str,
        machine_id: str | None = None,
    ) -> NeoMQTTTopicSet:
        """Build the standard MQTT topic set for a Neo device."""
        if not user_id.strip():
            raise ValueError("user_id cannot be empty")
        if not device_serial.strip():
            raise ValueError("device_serial cannot be empty")

        serial = device_serial.lower()
        machine_segment = machine_id or "+"
        base = f"{_MQTT_TOPIC_PREFIX}/{user_id}/{_MQTT_PLATFORM_SEGMENT}/{serial}"
        return NeoMQTTTopicSet(
            heart_beat=f"{base}/{_MQTT_TOPIC_HEART_BEAT}",
            full_status=f"{base}/{_MQTT_TOPIC_FULL_STATUS}",
            cmd_response=f"{base}/{_MQTT_TOPIC_CMD_RESPONSE}/{machine_segment}/+",
            status_change=f"{base}/{_MQTT_TOPIC_STATUS_CHANGE}",
        )

    def register_callback(
        self,
        callback: Callable[[RealtimeEvent], Awaitable[None] | None],
    ) -> None:
        """Register a callback that is invoked for every emitted realtime event."""
        self._callbacks.append(callback)

    async def connect(self) -> None:
        """Start the supervisor loop and wait for the first successful connection."""
        if self._supervisor_task is not None and not self._supervisor_task.done():
            return

        self._running = True
        self._connected_event.clear()
        self._supervisor_task = asyncio.create_task(self._run_supervisor())

        try:
            await asyncio.wait_for(self._connected_event.wait(), timeout=self._connect_timeout)
        except Exception:
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Stop the supervisor loop and disconnect from the broker."""
        self._running = False
        self._connected_event.clear()

        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # pragma: no cover - best effort cleanup
                _LOGGER.debug("MQTT disconnect failed", exc_info=True)
            finally:
                self._client = None

        if self._supervisor_task is not None:
            self._supervisor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._supervisor_task
            self._supervisor_task = None

        await self._set_state(RealtimeConnectionState.DISCONNECTED)

    async def subscribe(self, topic: str) -> None:
        """Subscribe to a raw MQTT topic."""
        if not topic.strip():
            raise ValueError("topic cannot be empty")

        self._subscriptions.add(topic)
        if self._client is not None:
            await self._client.subscribe(topic)

    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a raw MQTT topic."""
        if not topic.strip():
            raise ValueError("topic cannot be empty")

        self._subscriptions.discard(topic)
        if self._client is not None:
            await self._client.unsubscribe(topic)

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish a JSON payload to the broker."""
        if not topic.strip():
            raise ValueError("topic cannot be empty")

        if self._client is None:
            raise RuntimeError("MQTT client is not connected")

        encoded_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        await self._client.publish(topic, encoded_payload)

    async def subscribe_system(
        self,
        device_serial: str,
        machine_id: str | None = None,
    ) -> NeoMQTTTopicSet:
        """Subscribe to the standard Neo topic set for a device."""
        topics = self.build_topic_set(self._details.user_id, device_serial, machine_id)
        await self.subscribe(topics.heart_beat)
        await self.subscribe(topics.full_status)
        await self.subscribe(topics.cmd_response)
        await self.subscribe(topics.status_change)
        return topics

    async def unsubscribe_system(
        self,
        device_serial: str,
        machine_id: str | None = None,
    ) -> None:
        """Remove the standard Neo topic subscriptions for a device."""
        topics = self.build_topic_set(self._details.user_id, device_serial, machine_id)
        await self.unsubscribe(topics.heart_beat)
        await self.unsubscribe(topics.full_status)
        await self.unsubscribe(topics.cmd_response)
        await self.unsubscribe(topics.status_change)

    async def update_access_token(self, access_token: str) -> None:
        """Update the MQTT password and trigger a reconnect."""
        if not access_token.strip():
            raise ValueError("access_token cannot be empty")

        self._access_token = access_token
        if self._running and self._client is not None:
            await self._client.disconnect()

    async def iter_events(self) -> AsyncIterator[RealtimeEvent]:
        """Yield realtime events as they arrive."""
        while self._running or not self._event_queue.empty():
            event = await self._event_queue.get()
            yield event

    async def _run_supervisor(self) -> None:
        retry_delay = self._reconnect_initial_delay

        while self._running:
            client: Client | None = None
            try:
                await self._set_state(RealtimeConnectionState.CONNECTING)
                client = self._build_client()
                self._client = client

                async with client:
                    await self._restore_subscriptions(client)
                    await self._set_state(RealtimeConnectionState.CONNECTED)
                    self._connected_event.set()
                    retry_delay = self._reconnect_initial_delay

                    async with client.unfiltered_messages() as messages:
                        async for message in messages:
                            if not self._running:
                                break
                            await self._handle_message(str(message.topic), bytes(message.payload))

                if self._running:
                    self._connected_event.clear()
                    await self._set_state(
                        RealtimeConnectionState.RECONNECTING,
                        reason="connection closed",
                    )
            except asyncio.CancelledError:
                raise
            except (MqttError, OSError, ssl.SSLError, ConnectionError) as exc:
                self._last_error = exc
                self._connected_event.clear()
                if self._running:
                    _LOGGER.debug("MQTT reconnecting after error: %s", exc, exc_info=True)
                    await self._set_state(RealtimeConnectionState.RECONNECTING, reason=str(exc))
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, self._reconnect_max_delay)
            finally:
                self._client = None

        self._connected_event.clear()
        await self._set_state(RealtimeConnectionState.DISCONNECTED)

    def _build_client(self) -> Client:
        """Create a configured aiomqtt client instance."""
        tls_context = self._ssl_context
        if tls_context is None and self._details.uses_tls:
            tls_context = ssl.create_default_context()

        client_kwargs: dict[str, Any] = {
            "hostname": self._details.endpoint,
            "port": self._details.port,
            "username": "",
            "password": self._access_token,
            "client_id": self._client_id,
            "keepalive": self._keepalive,
            "clean_session": False,
        }
        if tls_context is not None:
            client_kwargs["tls_context"] = tls_context

        return Client(**client_kwargs)

    async def _restore_subscriptions(self, client: Client) -> None:
        """Resubscribe to all known topics after a reconnect."""
        for topic in sorted(self._subscriptions):
            await client.subscribe(topic)

    async def _handle_message(self, topic: str, raw_payload: bytes) -> None:
        """Decode a raw MQTT message and forward it to the event queue."""
        payload = self._decode_payload(raw_payload)
        domain_model: Any | None = None

        if topic.endswith(_MQTT_TOPIC_FULL_STATUS):
            try:
                domain_model = ActronAirStatus.model_validate(payload)
            except Exception as exc:  # pragma: no cover - defensive parsing
                _LOGGER.warning("Failed to parse MQTT full-status payload: %s", exc)
        elif topic.endswith(_MQTT_TOPIC_STATUS_CHANGE):
            try:
                domain_model = ActronAirStatus.model_validate(payload)
            except Exception:
                domain_model = None

        event = RealtimeMessage(
            transport=self.transport_type,
            kind=RealtimeEventKind.MESSAGE,
            topic=topic,
            payload=payload,
            raw_payload=raw_payload,
            domain_model=domain_model,
        )
        await self._emit_event(event)

    @staticmethod
    def _decode_payload(raw_payload: bytes) -> dict[str, Any]:
        """Decode an MQTT payload into a JSON object."""
        decoded = raw_payload.decode("utf-8")
        payload = json.loads(decoded)
        if not isinstance(payload, dict):
            raise ValueError("MQTT payload must decode to a JSON object")
        return payload

    async def _emit_event(self, event: RealtimeEvent) -> None:
        """Queue an event and notify registered callbacks."""
        await self._event_queue.put(event)
        for callback in list(self._callbacks):
            try:
                result = callback(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # pragma: no cover - callback failures should not break transport
                _LOGGER.warning("Realtime event callback failed", exc_info=True)

    async def _set_state(
        self,
        state: RealtimeConnectionState,
        *,
        reason: str | None = None,
    ) -> None:
        """Update the connection state and emit a connection event if needed."""
        previous_state = self._connection_state
        self._connection_state = state

        event = RealtimeConnectionEvent(
            transport=self.transport_type,
            kind=RealtimeEventKind.CONNECTION,
            state=state,
            previous_state=previous_state,
            reason=reason,
        )
        await self._event_queue.put(event)


__all__ = ["MQTTRTClient", "NeoMQTTTopicSet"]
