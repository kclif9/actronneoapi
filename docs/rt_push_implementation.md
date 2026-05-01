# Real-time Push (Cloud Push) Implementation Guide

Purpose
-------
This document describes a concrete, implementable plan to add cloud push (real-time) support to the `actronneoapi` Python library so an autonomous agent or developer can implement it end-to-end. It focuses on the transport used by the official Android app (MQTT), how to obtain RTC connection details, how to authenticate, expected topic names and message formats, reliability/keepalive requirements, token refresh behavior, integration points with the existing codebase, testing, and acceptance criteria.

Current status (May 2026)
-------------------------
The realtime rollout is now implemented and shipped in the main package:

- Neo systems use `rt/mqtt_client.py`.
- Que (NX-Gen) systems use `rt/signalr_client.py`.
- Public API integration lives in `actron.py` via `start_push()`, `stop_push()`,
  `subscribe_system_updates()`, and `stream_system_updates()`.
- Realtime events are normalized to the same `ActronAirStatus` model used by
  polling consumers.

This file remains the implementation handoff reference and should describe the
current shipped behavior before proposing future enhancements.

High-level recommendation
------------------------
- Keep platform-specific transports split and explicit: MQTT for Neo and
  SignalR/SSE for Que.
- Keep polling as fallback and expose `start_push()` / `stop_push()` /
  `stream_system_updates()` APIs on the main client.

Repository layout
-----------------
The library should keep the transport split explicit in the source tree so the Neo and Que paths stay isolated while sharing only the common domain models and auth code.

Recommended layout:

```text
src/actron_neo_api/
├── actron.py                 # Public facade, platform selection, common API
├── oauth.py                  # Shared OAuth/device-code/token refresh logic
├── state.py                  # Shared status cache and observers
├── models/                   # Shared Pydantic models for REST and RT payloads
├── rt/
│   ├── __init__.py
│   ├── base.py               # Shared realtime abstractions and event types
│   ├── mqtt_client.py        # Neo: MQTT push client
│   └── signalr_client.py     # Que: SignalR/SSE push client
└── const.py                  # Shared constants and platform defaults
```

Package responsibilities:
- `rt/mqtt_client.py`: Neo-only realtime transport and topic parsing.
- `rt/signalr_client.py`: Que-only realtime transport and subscribe/resubscribe handling.
- `actron.py`: transport selection, lifecycle orchestration, and consumer-facing API.
- `models/`: shared parsing logic so consumer code sees the same status model regardless of transport.

Platform split
--------------
- Neo: uses MQTT for live updates plus the existing REST API for discovery and command submission.
- Que: uses SignalR over Server-Sent Events for live updates, plus REST for discovery and command submission. No MQTT implementation was found in the Que APK trees that were added.
- Practical implication: the Python library should support MQTT push for Neo and SignalR push for Que rather than forcing one transport for both.

Consumer impact (Home Assistant)
-------------------------------
The implementation should minimize changes required in Home Assistant by keeping push support behind the same public library surface.

Target behavior for consumers:
- No consumer code should need to know whether a system is Neo or Que beyond selecting or auto-detecting the platform.
- The public API should continue to return the same `ActronAirStatus` and related models.
- Push should be opt-in and should fall back to polling automatically if the transport is unavailable or unsupported.
- HA integrations should only need to subscribe to status events once and should not need to manage MQTT/SignalR details directly.

What the library should absorb internally:
- Platform detection and transport selection.
- Token refresh and reconnection handling.
- Topic/subscribe command formatting for each platform.
- Conversion from push payloads into the existing domain models.
- Backoff, heartbeat, and subscription renewal semantics.

Why the split is required
-------------------------
- Android evidence indicates Neo uses MQTT topics for `full-status`,
  `heart-beat`, `cmd-response`, and `status-change` messages.
- Android evidence indicates Que uses SignalR over Server-Sent Events.
- The library should not force a single transport when backend behavior differs
  by platform.

Design overview
---------------

1) Components to add
   - `src/actron_neo_api/rt/mqtt_client.py` — Async MQTT real-time client encapsulating connect/subscribe/publish/reconnect logic.
   - Integration points in `src/actron_neo_api/actron.py` to start/stop push and to expose subscription/streaming APIs.
   - Tests in `tests/test_rt_push.py` and supporting fixtures.
   - Optional docs updates in project README and CHANGELOG.

2) Dependencies
   - Prefer `asyncio-mqtt` for a small, modern async API. Add to dev/pyproject: `asyncio-mqtt>=0.14.0` (or latest stable).

3) Security
   - Always use TLS when `RTCDetails.protocol` indicates `ssl`/`tls` — verify certificates.
   - Use the API `access_token` as MQTT password (Android uses token as password).
   - Use `clean_session=False` (persistent session) to maintain subscriptions if broker supports it.

4) Reliability and keepalive
   - Set MQTT `keepalive=60` seconds to match Android behavior.
   - Implement a ping/publish heartbeat every 30s if server requires an application-level ping (Android runs a 30s ping runnable).
   - Reconnect policy: attempt immediate reconnect with short interval (500ms) while initializing, then exponential backoff (cap ~60s) if repeated failures.

RTCDetails and building broker URI
----------------------------------
- `RTCDetails` model fields required: `endPoint`, `port`, `protocol`, `userId`.
- Broker URI forms:
  - `ssl://{endPoint}:{port}` or `tcp://{endPoint}:{port}` depending on `protocol`.
  - For `asyncio-mqtt`, pass `host={endPoint}`, `port={port}`, `tls={ssl_context_or_bool}`.

Topics (observed from Android app)
----------------------------------
The Android app subscribes to topics per-user and per-device. Use these exact topic patterns (replace tokens accordingly):

- `actron-cloud/{userId}/neo/{deviceSerial}/mwc/heart-beat` — heartbeat events
- `actron-cloud/{userId}/neo/{deviceSerial}/mwc/full-status` — full device status payloads
- `actron-cloud/{userId}/neo/{deviceSerial}/mwc/cmd-response/{machineId}/+` — command responses (machineId varies)
- `actron-cloud/{userId}/neo/{deviceSerial}/mwc/status-change` — incremental status changes

Que live connection pattern
---------------------------
- Base URL: `https://que.actronair.com.au/api/v0/`
- SignalR endpoint: `messaging/app`
- Subscribe command: JSON payload built from `SignalRCommand.build("subscribe", deviceSerial)`
- Transport: `ServerSentEventsTransport`
- Reconnect/resubscribe: resend the subscribe command after reconnect and periodically re-send it as a keepalive (observed every 5 minutes in `SystemServiceImpl`).
- Initial state load: REST `getSystem(detailUrl())` before or alongside the SignalR stream.

Subscription strategy
---------------------
- Subscribe to the above topics after connecting. Use single-topic subscriptions where possible to ease parsing.
- Support wildcard subscription for `cmd-response` if machineId is not known ahead of time.

Payload handling and mapping
----------------------------
- Messages are JSON-encoded (Android uses Gson). Payloads should be parsed with `json.loads` and validated via the existing Pydantic models in `src/actron_neo_api/models`.
- Provide a message conversion layer similar to Android's `MQTTMsgConvUtil` that maps raw MQTT payloads to domain events (e.g., `FullStatus`, `StatusChange`, `CmdResponse`).

Client API surface (recommended)
--------------------------------

class MQTTRTClient
- `__init__(self, rtc_details: RTCDetails, access_token: str, client_id: Optional[str] = None, ssl_context: Optional[ssl.SSLContext] = None)`
- `async connect()` — connect and start background loop
- `async disconnect()` — graceful disconnect
- `async subscribe_system(device_serial: str)` — subscribe to the device topics
- `async unsubscribe_system(device_serial: str)`
- `register_callback(topic_pattern: str, callback: Callable[[topic: str, payload: dict], Awaitable[None]])` — register event callbacks
- `async_iter_messages(topic_pattern: str)` — async generator yielding (topic, payload)

Integration with `Actron` client (`src/actron_neo_api/actron.py`)
----------------------------------------------------------------
- Add optional methods on the public API:
  - `async start_push()` — convenience wrapper to fetch `RTCDetails`, create `MQTTRTClient`, and connect.
  - `async stop_push()` — disconnect and cleanup.
  - `subscribe_system_updates(device_serial, callback)` — register callback that will deliver domain events.
  - `async for event in stream_system_updates(device_serial):` — user-facing async generator.
- Token refresh handling: when `oauth` refreshes `access_token`, update `MQTTRTClient` password or reconnect before token expiry.

Token refresh and auth lifecycle
-------------------------------
- The MQTT broker expects the `access_token` as password. Tokens expire — proactively refresh 15 minutes before expiry.
- Strategy:
  1. Use existing OAuth flow to get tokens and `RTCDetails` (mirror Android `GetRTCDetailsUseCase`).
  2. When token refresh occurs, call `MQTTRTClient.update_credentials(new_password)` or reconnect immediately with new token.
  3. Ensure reconnection is robust and preserves subscriptions (prefer persistent sessions on broker side).

Reconnect/backoff policy
------------------------
- Immediately retry at short interval (500ms) for initial connect attempts.
- On repeated failure, use exponential backoff: 0.5s -> 1s -> 2s -> 4s -> 8s -> 16s -> 32s -> 60s.
- Log and emit events to the public client so consumers can observe connectivity state.

Testing and CI
--------------
- Unit tests:
  - MQTT transport coverage in `tests/test_mqtt_client.py`.
  - SignalR transport coverage in `tests/test_signalr_client.py`.
  - Public API/realtime integration coverage in `tests/test_actron.py`
    (`TestActronAirAPIRealtimeIntegration`).
  - Coverage includes message parsing, reconnect/resubscribe behavior,
    credential/token update handling, callback isolation, and push-stream
    lifecycle behavior.
- Integration-style behavior is exercised with fakes/mocks in CI; no external
  broker/service dependency is required for standard test runs.

Work breakdown into issues
--------------------------
Create the implementation as a sequence of issues so each layer can be reviewed independently and so the consumer-facing surface stays stable throughout the rollout.

GitHub issues created for this plan:
- #74 - Transport abstraction and package split
- #75 - Neo MQTT realtime client
- #76 - Que SignalR realtime client
- #77 - Public API integration
- #73 - Tests and documentation

Issue status
------------
- #74: Completed
- #75: Completed
- #76: Completed
- #77: Completed
- #73: Final rollout task (tests/documentation alignment)

1. Transport abstraction and package split
  - Goal: create `src/actron_neo_api/rt/base.py` and the `rt/` package structure.
  - Scope: shared realtime event types, connection state, and common helpers.
  - Exit criteria: the public client can select a transport without importing platform-specific internals.

2. Neo MQTT client
  - Goal: implement `src/actron_neo_api/rt/mqtt_client.py`.
  - Scope: connect, subscribe, message parsing, keepalive, reconnect, and token update handling.
  - Exit criteria: Neo systems receive `full-status` and `status-change` updates without polling.

3. Que SignalR client
  - Goal: implement `src/actron_neo_api/rt/signalr_client.py`.
  - Scope: SSE transport, subscribe command, reconnect/resubscribe, periodic keepalive, and message parsing.
  - Exit criteria: Que systems receive live system updates without poll-only behavior.

4. Public API integration
  - Goal: wire transport selection into `src/actron_neo_api/actron.py`.
  - Scope: `start_push()`, `stop_push()`, `stream_system_updates()`, and platform-aware transport startup.
  - Exit criteria: consumer code does not have to change control flow to use Neo versus Que push.

5. Tests and docs
  - Goal: add unit tests, integration coverage, and README usage notes.
  - Scope: payload parsing, reconnect behavior, token refresh, and fallback-to-poll behavior.
  - Exit criteria: the repo documents the platform split, the consumer impact, and the expected HA usage pattern.

Example minimal implementation sketch (concept)
--------------------------------------------
Install dependency:

```bash
pip install asyncio-mqtt
```

Small example using `asyncio-mqtt` (conceptual, not production-ready):

```py
from asyncio_mqtt import Client, MqttError
import asyncio, json

class MQTTRTClient:
    def __init__(self, host, port, username, password, tls=True, client_id=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.tls = tls
        self.client_id = client_id
        self._client = None
        self._running = False

    async def connect(self):
        self._client = Client(self.host, port=self.port, username=self.username,
                              password=self.password, client_id=self.client_id, tls=self.tls, keepalive=60)
        await self._client.connect()
        asyncio.create_task(self._message_loop())

    async def _message_loop(self):
        async with self._client.unfiltered_messages() as messages:
            await self._client.subscribe('#')
            async for msg in messages:
                try:
                    payload = json.loads(msg.payload.decode())
                except Exception:
                    payload = msg.payload.decode()
                # dispatch to handlers
                self._handle_message(msg.topic, payload)

    def _handle_message(self, topic, payload):
        # convert to domain events and forward
        pass

    async def disconnect(self):
        await self._client.disconnect()
```

Agent instructions (for an automated implementer)
-----------------------------------------------
This section shows the exact steps an agent should perform to implement the feature.

1. Add dependency `asyncio-mqtt` to `pyproject.toml` or `requirements.txt`.
2. Create `src/actron_neo_api/rt/mqtt_client.py` implementing `MQTTRTClient` per API surface above.
3. Implement JSON -> Pydantic mapping using existing models in `src/actron_neo_api/models`.
4. Add integration methods to `src/actron_neo_api/actron.py` (`start_push`, `stop_push`, `stream_system_updates`).
5. Add tests in `tests/test_rt_push.py` covering connect/subscribe/message flow, token update handling, reconnect policy.
6. Run `pre-commit` and `pytest` locally. Ensure mypy and ruff pass.
7. Update README and add a short usage example showing `await api.start_push()` and `async for event in api.stream_system_updates(device_serial)`.

Acceptance criteria
-------------------
- `start_push()` connects to the broker and receives real-time `full-status` messages for a subscribed device.
- Token refresh is handled without losing messages (or reconnects gracefully with preserved subscriptions).
- Tests validate the parsing of at least `full-status` and `status-change` messages.
- Code follows project conventions: type hints, Google-style docstrings, and pre-commit checks pass.

Deliverables
------------
- `src/actron_neo_api/rt/mqtt_client.py` (Neo realtime transport)
- `src/actron_neo_api/rt/signalr_client.py` (Que realtime transport)
- `src/actron_neo_api/actron.py` integration (`start_push`/`stop_push`/
  `subscribe_system_updates`/`stream_system_updates`)
- `tests/test_mqtt_client.py` and `tests/test_signalr_client.py`
- `tests/test_actron.py` realtime public API integration coverage
- README realtime usage example and platform-split documentation

Notes and references
--------------------
- Android references (for developer context): `SignalRClient`, `MQTTClient`, `NeoConnectFirebaseMessagingService` in the `private/android-apk` decompilation. They show the topic names, keepalive/ping intervals, and credential usage.
- Broker base URL and SignalR endpoint lives in `BuildConfig` in the Android code (`https://nimbus.actronair.com.au/api/v0/`, `messaging/app`), but the actual RTC broker endpoint comes from `RTCDetails` returned by the backend.

If you want, I can now scaffold `mqtt_client.py` and wire `start_push()` into `actron.py` with tests. Reply with "scaffold MQTT" to create the initial implementation patch.
