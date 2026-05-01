"""Tests for the Neo MQTT realtime client."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from actron_neo_api.models import ActronAirStatus
from actron_neo_api.rt import MQTTRTClient, RealtimeConnectionDetails, RealtimeMessage


class TestRealtimeConnectionDetails:
    """Test the shared realtime connection details model."""

    def test_tls_detection(self) -> None:
        """TLS should be detected from the protocol field."""
        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.com",
            port=8883,
            protocol="ssl",
            user_id="user-1",
        )

        assert details.uses_tls is True
        assert details.scheme == "ssl"


class TestMQTTRTClient:
    """Test the Neo MQTT client helpers and payload parsing."""

    def test_build_topic_set(self) -> None:
        """The client should build the expected Neo topic structure."""
        topics = MQTTRTClient.build_topic_set("user-1", "ABC123", "machine-9")

        assert topics.heart_beat == "actron-cloud/user-1/neo/abc123/mwc/heart-beat"
        assert topics.full_status == "actron-cloud/user-1/neo/abc123/mwc/full-status"
        assert topics.cmd_response == "actron-cloud/user-1/neo/abc123/mwc/cmd-response/machine-9/+"
        assert topics.status_change == "actron-cloud/user-1/neo/abc123/mwc/status-change"

    @pytest.mark.asyncio
    async def test_handle_message_parses_full_status(self, sample_status_full: dict[str, object]) -> None:
        """Full status payloads should be converted into ActronAirStatus models."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        await client._handle_message(  # noqa: SLF001 - exercising the parse path directly
            "actron-cloud/user-1/neo/abc123/mwc/full-status",
            json.dumps(sample_status_full).encode("utf-8"),
        )

        event = client._event_queue.get_nowait()  # noqa: SLF001 - testing emitted events
        assert isinstance(event, RealtimeMessage)
        assert isinstance(event.domain_model, ActronAirStatus)
        assert event.domain_model.serial_number == "ABC123"
        assert event.domain_model.system_on is True

    @pytest.mark.asyncio
    async def test_publish_uses_compact_json(self) -> None:
        """Publishing should serialize payloads as compact JSON."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        client._client = MagicMock()  # noqa: SLF001 - inject a fake broker client
        client._client.publish = AsyncMock(return_value=None)

        payload = {"b": 2, "a": 1}
        await client.publish("actron/topic", payload)

        client._client.publish.assert_awaited_once_with("actron/topic", b'{"b":2,"a":1}')

    @pytest.mark.asyncio
    async def test_update_access_token_disconnects_running_client(self) -> None:
        """Updating credentials should force the live client to disconnect."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        client._running = True  # noqa: SLF001 - simulate an active connection
        client._client = MagicMock()  # noqa: SLF001 - inject a fake broker client
        client._client.disconnect = AsyncMock(return_value=None)

        await client.update_access_token("token-456")

        assert client.access_token == "token-456"
        client._client.disconnect.assert_awaited_once()
