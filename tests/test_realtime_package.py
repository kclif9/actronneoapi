"""Tests for the realtime package scaffold."""

from __future__ import annotations

from actron_neo_api.rt import (
    RealtimeClient,
    RealtimeConnectionEvent,
    RealtimeConnectionState,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
)


def test_realtime_package_exports() -> None:
    """The rt package should expose the shared transport primitives."""
    assert RealtimeTransportType.MQTT.value == "mqtt"
    assert RealtimeTransportType.SIGNALR.value == "signalr"
    assert RealtimeConnectionState.CONNECTED.value == "connected"
    assert RealtimeEventKind.MESSAGE.value == "message"
    assert RealtimeConnectionEvent.__name__ == "RealtimeConnectionEvent"
    assert RealtimeMessage.__name__ == "RealtimeMessage"
    assert RealtimeClient.__name__ == "RealtimeClient"