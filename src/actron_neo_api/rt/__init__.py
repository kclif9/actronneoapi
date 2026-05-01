"""Realtime transport abstractions for Actron Air push updates.

This package keeps platform-specific realtime transports isolated from the
shared API models and auth code.
"""

from .base import (
    RealtimeClient,
    RealtimeConnectionDetails,
    RealtimeConnectionEvent,
    RealtimeConnectionState,
    RealtimeEvent,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
)
from .mqtt_client import MQTTRTClient, NeoMQTTTopicSet
from .signalr_client import SignalRRTClient

__all__ = [
    "RealtimeClient",
    "RealtimeConnectionDetails",
    "RealtimeConnectionEvent",
    "RealtimeConnectionState",
    "RealtimeEvent",
    "RealtimeEventKind",
    "RealtimeMessage",
    "RealtimeTransportType",
    "MQTTRTClient",
    "NeoMQTTTopicSet",
    "SignalRRTClient",
]
