"""Shared realtime transport primitives.

The realtime clients for Neo and Que will live in separate modules, but they
share a small set of common event types and a protocol for the consumer-facing
surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class RealtimeTransportType(str, Enum):
    """Supported realtime transport families."""

    MQTT = "mqtt"
    SIGNALR = "signalr"


class RealtimeConnectionState(str, Enum):
    """Connection state shared by all realtime transports."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class RealtimeEventKind(str, Enum):
    """Kinds of realtime events emitted by a transport."""

    CONNECTION = "connection"
    MESSAGE = "message"


@dataclass(frozen=True, slots=True)
class RealtimeEvent:
    """Base realtime event payload.

    Attributes:
        transport: Transport family that emitted the event.
        kind: Event category.
    """

    transport: RealtimeTransportType
    kind: RealtimeEventKind


@dataclass(frozen=True, slots=True)
class RealtimeConnectionEvent(RealtimeEvent):
    """Connection state transition emitted by a realtime transport."""

    state: RealtimeConnectionState
    previous_state: RealtimeConnectionState | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RealtimeMessage(RealtimeEvent):
    """Message received from a realtime transport."""

    topic: str
    payload: dict[str, Any]
    raw_payload: bytes | None = None
    domain_model: Any | None = None


@dataclass(frozen=True, slots=True)
class RealtimeConnectionDetails:
    """Connection details required to open a realtime transport."""

    endpoint: str
    port: int
    protocol: str
    user_id: str

    def __post_init__(self) -> None:
        """Validate the connection settings."""
        if not self.endpoint.strip():
            raise ValueError("endpoint cannot be empty")
        if self.port <= 0:
            raise ValueError("port must be greater than zero")
        if not self.protocol.strip():
            raise ValueError("protocol cannot be empty")
        if not self.user_id.strip():
            raise ValueError("user_id cannot be empty")

    @property
    def uses_tls(self) -> bool:
        """Return whether the transport should use TLS."""
        return self.protocol.strip().lower() in {"ssl", "tls", "mqtts"}

    @property
    def scheme(self) -> str:
        """Return the transport URI scheme."""
        return "ssl" if self.uses_tls else "tcp"


@runtime_checkable
class RealtimeClient(Protocol):
    """Protocol shared by platform-specific realtime clients."""

    transport_type: RealtimeTransportType

    async def connect(self) -> None:
        """Connect the realtime transport."""

    async def disconnect(self) -> None:
        """Disconnect the realtime transport."""

    async def subscribe(self, topic: str) -> None:
        """Subscribe to a transport-specific topic."""

    async def unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a transport-specific topic."""

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        """Publish a transport-specific payload."""
