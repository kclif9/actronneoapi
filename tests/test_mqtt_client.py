"""Tests for the Neo MQTT realtime client."""

from __future__ import annotations

import asyncio
import contextlib
import json
import ssl
from unittest.mock import AsyncMock, MagicMock

import pytest

from actron_neo_api.models import ActronAirStatus
from actron_neo_api.rt import (
    MQTTRTClient,
    RealtimeConnectionDetails,
    RealtimeConnectionEvent,
    RealtimeConnectionState,
    RealtimeEventKind,
    RealtimeMessage,
)
from actron_neo_api.rt import mqtt_client as mqtt_module


class _FakeMQTTMessage:
    """Simple MQTT message object for tests."""

    def __init__(self, topic: str, payload: bytes) -> None:
        self.topic = topic
        self.payload = payload


class _FakeMQTTMessageStream:
    """Async iterator yielding fake MQTT messages."""

    def __init__(self, messages: list[_FakeMQTTMessage]) -> None:
        self._messages = list(messages)

    def __aiter__(self) -> _FakeMQTTMessageStream:
        return self

    async def __anext__(self) -> _FakeMQTTMessage:
        if not self._messages:
            raise StopAsyncIteration
        return self._messages.pop(0)


class _FakeMQTTClient:
    """Async context manager that mimics the MQTT client API used by the tests."""

    def __init__(self, messages: list[_FakeMQTTMessage] | None = None) -> None:
        self._messages = messages or []
        self.subscriptions: list[str] = []
        self.unsubscriptions: list[str] = []
        self.published: list[tuple[str, bytes]] = []
        self.disconnected = False

    async def __aenter__(self) -> _FakeMQTTClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    @property
    def messages(self) -> _FakeMQTTMessageStream:
        return _FakeMQTTMessageStream(self._messages)

    async def subscribe(self, topic: str) -> None:
        self.subscriptions.append(topic)

    async def unsubscribe(self, topic: str) -> None:
        self.unsubscriptions.append(topic)

    async def publish(self, topic: str, payload: bytes) -> None:
        self.published.append((topic, payload))

    async def disconnect(self) -> None:
        self.disconnected = True


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

    @pytest.mark.parametrize(
        ("endpoint", "port", "protocol", "user_id", "message"),
        [
            ("", 8883, "ssl", "user-1", "endpoint cannot be empty"),
            ("mqtt.example.com", 0, "ssl", "user-1", "port must be greater than zero"),
            ("mqtt.example.com", 8883, "", "user-1", "protocol cannot be empty"),
            ("mqtt.example.com", 8883, "ssl", "", "user_id cannot be empty"),
        ],
    )
    def test_invalid_connection_details(
        self,
        endpoint: str,
        port: int,
        protocol: str,
        user_id: str,
        message: str,
    ) -> None:
        """Invalid connection settings should fail fast."""
        with pytest.raises(ValueError, match=message):
            RealtimeConnectionDetails(
                endpoint=endpoint,
                port=port,
                protocol=protocol,
                user_id=user_id,
            )

    def test_invalid_connection_details_tls_scheme(self) -> None:
        """Non-TLS protocols should still be accepted and reported correctly."""
        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.com",
            port=1883,
            protocol="tcp",
            user_id="user-1",
        )

        assert details.uses_tls is False
        assert details.scheme == "tcp"


class TestMQTTRTClient:
    """Test the Neo MQTT client helpers and payload parsing."""

    def test_connection_properties(self) -> None:
        """Client properties should expose the configured state."""
        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.com",
            port=8883,
            protocol="ssl",
            user_id="user-1",
        )
        client = MQTTRTClient(details, access_token="token-123")

        assert client.connection_details is details
        assert client.access_token == "token-123"
        assert client.connection_state == RealtimeConnectionState.DISCONNECTED
        assert client.last_error is None

    @pytest.mark.parametrize(
        (
            "access_token",
            "keepalive",
            "connect_timeout",
            "reconnect_initial_delay",
            "reconnect_max_delay",
            "message",
        ),
        [
            ("", 60, 15.0, 0.5, 60.0, "access_token cannot be empty"),
            ("token", 0, 15.0, 0.5, 60.0, "keepalive must be greater than zero"),
            ("token", 60, 0, 0.5, 60.0, "connect_timeout must be greater than zero"),
            ("token", 60, 15.0, 0, 60.0, "reconnect_initial_delay must be greater than zero"),
            (
                "token",
                60,
                15.0,
                0.5,
                0.1,
                "reconnect_max_delay must be greater than or equal to initial delay",
            ),
        ],
    )
    def test_invalid_client_configuration(
        self,
        access_token: str,
        keepalive: int,
        connect_timeout: float,
        reconnect_initial_delay: float,
        reconnect_max_delay: float,
        message: str,
    ) -> None:
        """Invalid client settings should fail fast."""
        with pytest.raises(ValueError, match=message):
            MQTTRTClient(
                RealtimeConnectionDetails(
                    endpoint="mqtt.example.com",
                    port=8883,
                    protocol="ssl",
                    user_id="user-1",
                ),
                access_token=access_token,
                keepalive=keepalive,
                connect_timeout=connect_timeout,
                reconnect_initial_delay=reconnect_initial_delay,
                reconnect_max_delay=reconnect_max_delay,
            )

    def test_build_topic_set(self) -> None:
        """The client should build the expected Neo topic structure."""
        topics = MQTTRTClient.build_topic_set("user-1", "ABC123", "machine-9")

        assert topics.heart_beat == "actron-cloud/user-1/neo/abc123/mwc/heart-beat"
        assert topics.full_status == "actron-cloud/user-1/neo/abc123/mwc/full-status"
        assert topics.cmd_response == "actron-cloud/user-1/neo/abc123/mwc/cmd-response/machine-9/+"
        assert topics.status_change == "actron-cloud/user-1/neo/abc123/mwc/status-change"

    def test_build_topic_set_defaults_and_validation(self) -> None:
        """Topic construction should normalize serials and validate inputs."""
        topics = MQTTRTClient.build_topic_set("user-1", "ABC123")

        assert topics.cmd_response.endswith("/+/+")
        assert topics.full_status.endswith("/mwc/full-status")

        with pytest.raises(ValueError, match="user_id cannot be empty"):
            MQTTRTClient.build_topic_set("", "ABC123")

        with pytest.raises(ValueError, match="device_serial cannot be empty"):
            MQTTRTClient.build_topic_set("user-1", "")

    @pytest.mark.asyncio
    async def test_handle_message_parses_full_status(
        self,
        sample_status_full: dict[str, object],
    ) -> None:
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
    async def test_handle_message_parses_status_change(
        self,
        sample_status_full: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Status change payloads should be converted into domain models too."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        sentinel = object()
        monkeypatch.setattr(
            ActronAirStatus,
            "model_validate",
            classmethod(lambda cls, payload: sentinel),
        )

        await client._handle_message(  # noqa: SLF001 - targeted transport coverage
            "actron-cloud/user-1/neo/abc123/mwc/status-change",
            json.dumps(sample_status_full).encode("utf-8"),
        )

        event = client._event_queue.get_nowait()  # noqa: SLF001 - testing emitted events
        assert isinstance(event, RealtimeMessage)
        assert event.domain_model is sentinel

    def test_decode_payload_validation(self) -> None:
        """Payload decoding should enforce JSON object payloads."""
        assert MQTTRTClient._decode_payload(b'{"enabled":true}') == {"enabled": True}

        with pytest.raises(ValueError, match="MQTT payload must decode to a JSON object"):
            MQTTRTClient._decode_payload(b"[1,2,3]")

        with pytest.raises(json.JSONDecodeError):
            MQTTRTClient._decode_payload(b"not-json")

    @pytest.mark.asyncio
    async def test_emit_event_calls_callbacks_and_swallows_failures(self) -> None:
        """Callbacks should run without breaking event emission."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        seen: list[tuple[str, str]] = []

        def sync_callback(event: RealtimeMessage) -> None:
            seen.append(("sync", event.topic))

        async def async_callback(event: RealtimeMessage) -> None:
            seen.append(("async", event.topic))

        def failing_callback(event: RealtimeMessage) -> None:
            raise RuntimeError("boom")

        client.register_callback(sync_callback)
        client.register_callback(async_callback)
        client.register_callback(failing_callback)

        event = RealtimeMessage(
            transport=client.transport_type,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron/topic",
            payload={"x": 1},
        )

        await client._emit_event(event)  # noqa: SLF001 - verifying transport event dispatch

        assert seen == [("sync", "actron/topic"), ("async", "actron/topic")]
        assert client._event_queue.get_nowait() == event  # noqa: SLF001 - internal queue check

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self) -> None:
        """Connect should start the supervisor task and disconnect should clean up."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        async def fake_supervisor() -> None:
            client._connected_event.set()  # noqa: SLF001 - simulate a successful connection

        client._run_supervisor = fake_supervisor  # type: ignore[method-assign]

        await client.connect()
        assert client._supervisor_task is not None  # noqa: SLF001 - internal lifecycle state

        await client.disconnect()
        assert client.connection_state == RealtimeConnectionState.DISCONNECTED
        assert client._supervisor_task is None  # noqa: SLF001 - internal lifecycle state

    @pytest.mark.asyncio
    async def test_connect_prepares_tls_context_off_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TLS context should be prepared via to_thread inside the supervisor path."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        created_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        to_thread_calls: list[object] = []
        release_supervisor = asyncio.Event()

        async def fake_to_thread(func: object, *args: object, **kwargs: object) -> ssl.SSLContext:
            to_thread_calls.append(func)
            return created_context

        async def fake_supervisor() -> None:
            await client._ensure_tls_context()  # noqa: SLF001 - exercise real TLS prep path
            client._connected_event.set()  # noqa: SLF001 - simulate successful connect
            await release_supervisor.wait()

        monkeypatch.setattr(mqtt_module.asyncio, "to_thread", fake_to_thread)
        client._run_supervisor = fake_supervisor  # type: ignore[method-assign]

        await client.connect()

        assert to_thread_calls == [ssl.create_default_context]
        assert client._ssl_context is created_context  # noqa: SLF001 - verify cached context

        release_supervisor.set()
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_connect_overlapping_calls_start_single_supervisor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Overlapping connect calls should not start more than one supervisor."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        created_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        release_supervisor = asyncio.Event()
        supervisor_runs = 0

        async def fake_to_thread(func: object, *args: object, **kwargs: object) -> ssl.SSLContext:
            return created_context

        async def fake_supervisor() -> None:
            nonlocal supervisor_runs
            supervisor_runs += 1
            await client._ensure_tls_context()  # noqa: SLF001 - keep startup path realistic
            client._connected_event.set()  # noqa: SLF001 - allow connect() to finish
            await release_supervisor.wait()

        monkeypatch.setattr(mqtt_module.asyncio, "to_thread", fake_to_thread)
        client._run_supervisor = fake_supervisor  # type: ignore[method-assign]

        first_connect = asyncio.create_task(client.connect())
        await asyncio.sleep(0)
        await client.connect()
        await first_connect

        assert supervisor_runs == 1

        release_supervisor.set()
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_ensure_tls_context_noop_without_tls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TLS preparation should no-op for non-TLS transports."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=1883,
                protocol="tcp",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        async def fail_to_thread(*args: object, **kwargs: object) -> ssl.SSLContext:
            raise AssertionError("to_thread should not be called for non-TLS connections")

        monkeypatch.setattr(mqtt_module.asyncio, "to_thread", fail_to_thread)

        await client._ensure_tls_context()  # noqa: SLF001 - direct branch coverage target
        assert client._ssl_context is None  # noqa: SLF001 - no context needed for tcp

    @pytest.mark.asyncio
    async def test_connect_returns_when_supervisor_running(self) -> None:
        """A second connect call should no-op while the supervisor is active."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        client._supervisor_task = asyncio.create_task(asyncio.sleep(0.1))  # noqa: SLF001

        await client.connect()

        assert client._supervisor_task is not None  # noqa: SLF001
        client._supervisor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await client._supervisor_task

    @pytest.mark.asyncio
    async def test_connect_failure_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Connection failures should trigger disconnect and re-raise."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        async def fake_supervisor() -> None:
            await asyncio.sleep(0.1)

        client._run_supervisor = fake_supervisor  # type: ignore[method-assign]

        async def fake_wait_for(coro: object, timeout: float) -> None:
            if hasattr(coro, "close"):
                coro.close()
            raise asyncio.TimeoutError

        monkeypatch.setattr(mqtt_module.asyncio, "wait_for", fake_wait_for)

        with pytest.raises(asyncio.TimeoutError):
            await client.connect()

    @pytest.mark.asyncio
    async def test_disconnect_with_live_client(self) -> None:
        """Disconnect should clear local connection state."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        fake_client = _FakeMQTTClient()
        client._client = fake_client  # noqa: SLF001 - simulate a live broker connection
        client._supervisor_task = asyncio.create_task(asyncio.sleep(0))  # noqa: SLF001

        await client.disconnect()

        assert client._client is None  # noqa: SLF001 - internal lifecycle cleanup
        assert client.connection_state == RealtimeConnectionState.DISCONNECTED

    @pytest.mark.asyncio
    async def test_subscribe_and_unsubscribe(self) -> None:
        """Topic subscription helpers should validate inputs and proxy to the broker."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        fake_client = _FakeMQTTClient()
        client._client = fake_client  # noqa: SLF001 - simulate a live broker connection

        with pytest.raises(ValueError, match="topic cannot be empty"):
            await client.subscribe("")

        with pytest.raises(ValueError, match="topic cannot be empty"):
            await client.unsubscribe("")

        await client.subscribe("actron/topic")
        await client.unsubscribe("actron/topic")

        assert fake_client.subscriptions == ["actron/topic"]
        assert fake_client.unsubscriptions == ["actron/topic"]

    @pytest.mark.asyncio
    async def test_publish_validation_and_success(self) -> None:
        """Publishing should fail without a client and work once connected."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        with pytest.raises(ValueError, match="topic cannot be empty"):
            await client.publish("", {})

        with pytest.raises(RuntimeError, match="MQTT client is not connected"):
            await client.publish("actron/topic", {})

        fake_client = _FakeMQTTClient()
        client._client = fake_client  # noqa: SLF001 - simulate a live broker connection
        await client.publish("actron/topic", {"value": 1})

        assert fake_client.published == [("actron/topic", b'{"value":1}')]

    @pytest.mark.asyncio
    async def test_subscribe_and_unsubscribe_system(self) -> None:
        """System helpers should subscribe and unsubscribe the expected topic set."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        fake_client = _FakeMQTTClient()
        client._client = fake_client  # noqa: SLF001 - simulate a live broker connection

        topics = await client.subscribe_system("ABC123", "machine-9")
        await client.unsubscribe_system("ABC123", "machine-9")

        assert topics.heart_beat in fake_client.subscriptions
        assert topics.full_status in fake_client.subscriptions
        assert topics.cmd_response in fake_client.subscriptions
        assert topics.status_change in fake_client.subscriptions
        assert topics.heart_beat in fake_client.unsubscriptions
        assert topics.full_status in fake_client.unsubscriptions
        assert topics.cmd_response in fake_client.unsubscriptions
        assert topics.status_change in fake_client.unsubscriptions

    @pytest.mark.asyncio
    async def test_update_access_token_without_running_client(self) -> None:
        """Token updates should work even when the client is idle."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        await client.update_access_token("token-456")

        assert client.access_token == "token-456"

    @pytest.mark.asyncio
    async def test_update_access_token_validation(self) -> None:
        """Blank access tokens should be rejected."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        with pytest.raises(ValueError, match="access_token cannot be empty"):
            await client.update_access_token("")

    @pytest.mark.asyncio
    async def test_restore_subscriptions_and_build_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reconnection helpers should rebuild the MQTT client and resubscribe topics."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        client._ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # noqa: SLF001
        client._subscriptions = {"topic/b", "topic/a"}  # noqa: SLF001 - internal state setup

        fake_client = _FakeMQTTClient()
        await client._restore_subscriptions(fake_client)  # noqa: SLF001 - direct coverage target

        assert fake_client.subscriptions == ["topic/a", "topic/b"]

        captured: dict[str, object] = {}

        def fake_client_factory(
            hostname: str,
            port: int,
            *,
            username: str,
            password: str,
            identifier: str,
            keepalive: int,
            clean_session: bool,
            tls_context: ssl.SSLContext,
        ) -> object:
            kwargs = {
                "hostname": hostname,
                "port": port,
                "username": username,
                "password": password,
                "identifier": identifier,
                "keepalive": keepalive,
                "clean_session": clean_session,
                "tls_context": tls_context,
            }
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(mqtt_module, "Client", fake_client_factory)
        result = client._build_client()  # noqa: SLF001 - direct coverage target

        assert result is not None
        assert captured["hostname"] == "mqtt.example.com"
        assert captured["port"] == 8883
        assert captured["password"] == "token-123"
        assert captured["identifier"] == client._client_id  # noqa: SLF001 - kwarg regression check
        assert isinstance(captured["tls_context"], ssl.SSLContext)

    def test_get_client_identifier_arg_name_legacy_client_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Older aiomqtt variants using client_id should still be supported."""

        class _LegacyClient:
            def __init__(self, *, client_id: str | None = None) -> None:
                self.client_id = client_id

        monkeypatch.setattr(mqtt_module, "Client", _LegacyClient)

        assert MQTTRTClient._get_client_identifier_arg_name() == "client_id"  # noqa: SLF001

    def test_get_client_identifier_arg_name_signature_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Signature inspection failures should fall back to the modern identifier kwarg."""

        def raise_type_error(_obj: object) -> None:
            raise TypeError("signature unavailable")

        monkeypatch.setattr(mqtt_module.inspect, "signature", raise_type_error)

        assert MQTTRTClient._get_client_identifier_arg_name() == "identifier"  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_iter_events_yields_queued_events(self) -> None:
        """Queued events should be yielded in order."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        event = RealtimeConnectionEvent(
            transport=client.transport_type,
            kind=RealtimeEventKind.CONNECTION,
            state=RealtimeConnectionState.CONNECTED,
            previous_state=RealtimeConnectionState.CONNECTING,
        )
        client._event_queue.put_nowait(event)  # noqa: SLF001 - queue setup for the iterator

        seen = []
        async for item in client.iter_events():
            seen.append(item)
            break

        assert seen == [event]

    @pytest.mark.asyncio
    async def test_run_supervisor_happy_and_error_paths(
        self,
        sample_status_full: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The supervisor loop should handle success and reconnect errors."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        happy_client = _FakeMQTTClient(
            messages=[
                _FakeMQTTMessage(
                    "actron-cloud/user-1/neo/abc123/mwc/full-status",
                    json.dumps(sample_status_full).encode("utf-8"),
                ),
                _FakeMQTTMessage(
                    "actron-cloud/user-1/neo/abc123/mwc/full-status",
                    json.dumps(sample_status_full).encode("utf-8"),
                ),
            ]
        )
        handled: list[str] = []

        async def happy_handle_message(topic: str, raw_payload: bytes) -> None:
            handled.append(topic)
            client._running = False  # noqa: SLF001 - stop the loop after one iteration

        client._running = True  # noqa: SLF001 - exercise the supervisor loop directly
        client._build_client = lambda: happy_client  # type: ignore[assignment]
        client._handle_message = happy_handle_message  # type: ignore[assignment]

        await client._run_supervisor()  # noqa: SLF001 - direct coverage target

        assert handled == ["actron-cloud/user-1/neo/abc123/mwc/full-status"]
        assert client.connection_state == RealtimeConnectionState.DISCONNECTED
        assert client._connected_event.is_set() is False  # noqa: SLF001

    @pytest.mark.asyncio
    async def test_run_supervisor_reconnect_state_on_clean_exit(self) -> None:
        """A clean exit while still running should enter reconnecting state."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        class _CleanClient(_FakeMQTTClient):
            @property
            def messages(self) -> _FakeMQTTMessageStream:
                return _FakeMQTTMessageStream([])

        states: list[RealtimeConnectionState] = []

        async def fake_set_state(
            state: RealtimeConnectionState,
            *,
            reason: str | None = None,
        ) -> None:
            states.append(state)
            if state == RealtimeConnectionState.RECONNECTING:
                client._running = False  # noqa: SLF001 - stop after the reconnect transition

        client._running = True  # noqa: SLF001 - exercise the supervisor loop directly
        client._build_client = lambda: _CleanClient()  # type: ignore[assignment]
        client._set_state = fake_set_state  # type: ignore[assignment]

        await client._run_supervisor()  # noqa: SLF001 - direct coverage target

        assert RealtimeConnectionState.RECONNECTING in states

    @pytest.mark.asyncio
    async def test_run_supervisor_cancelled_error(self) -> None:
        """Cancellation should propagate cleanly from the supervisor loop."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        class _CancelledClient(_FakeMQTTClient):
            async def __aenter__(self) -> _CancelledClient:
                raise asyncio.CancelledError

        client._running = True  # noqa: SLF001 - exercise the supervisor loop directly
        client._build_client = lambda: _CancelledClient()  # type: ignore[assignment]

        with pytest.raises(asyncio.CancelledError):
            await client._run_supervisor()  # noqa: SLF001 - direct coverage target

    @pytest.mark.asyncio
    async def test_handle_message_status_change_failure(
        self,
        sample_status_full: dict[str, object],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Status-change parsing should fall back to None on validation failure."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )
        monkeypatch.setattr(
            ActronAirStatus,
            "model_validate",
            classmethod(lambda cls, payload: (_ for _ in ()).throw(ValueError("boom"))),
        )

        await client._handle_message(  # noqa: SLF001 - targeted transport coverage
            "actron-cloud/user-1/neo/abc123/mwc/status-change",
            json.dumps(sample_status_full).encode("utf-8"),
        )

        event = client._event_queue.get_nowait()  # noqa: SLF001 - testing emitted events
        assert isinstance(event, RealtimeMessage)
        assert event.domain_model is None

        error_client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        class _BrokenClient(_FakeMQTTClient):
            async def __aenter__(self) -> _BrokenClient:
                raise OSError("boom")

        monkeypatch.setattr(
            mqtt_module.asyncio,
            "sleep",
            AsyncMock(side_effect=lambda delay: setattr(error_client, "_running", False)),
        )
        error_client._running = True  # noqa: SLF001 - exercise the reconnect path directly
        error_client._build_client = lambda: _BrokenClient()  # type: ignore[assignment]

        await error_client._run_supervisor()  # noqa: SLF001 - direct coverage target

        assert error_client.last_error is not None
        assert isinstance(error_client.last_error, OSError)
        assert error_client.connection_state == RealtimeConnectionState.DISCONNECTED

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
    async def test_update_access_token_restarts_running_client(self) -> None:
        """Updating credentials should restart the live client."""
        client = MQTTRTClient(
            RealtimeConnectionDetails(
                endpoint="mqtt.example.com",
                port=8883,
                protocol="ssl",
                user_id="user-1",
            ),
            access_token="token-123",
        )

        disconnect_mock = AsyncMock(return_value=None)
        connect_mock = AsyncMock(return_value=None)
        client.disconnect = disconnect_mock  # type: ignore[method-assign]
        client.connect = connect_mock  # type: ignore[method-assign]
        client._running = True  # noqa: SLF001 - simulate an active connection

        await client.update_access_token("token-456")

        assert client.access_token == "token-456"
        disconnect_mock.assert_awaited_once()
        connect_mock.assert_awaited_once()
