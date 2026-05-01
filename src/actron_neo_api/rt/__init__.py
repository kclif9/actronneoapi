"""Realtime transport abstractions for Actron Air push updates.

This package keeps platform-specific realtime transports isolated from the
shared API models and auth code.
"""

from .base import (
    RealtimeClient,
    RealtimeConnectionEvent,
    RealtimeConnectionState,
    RealtimeEvent,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
)

__all__ = [
    "RealtimeClient",
    "RealtimeConnectionEvent",
    "RealtimeConnectionState",
    "RealtimeEvent",
    "RealtimeEventKind",
    "RealtimeMessage",
    "RealtimeTransportType",
]