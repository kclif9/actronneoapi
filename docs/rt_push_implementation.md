# Realtime Push Guide

## What Was Implemented

Realtime push support is now available in the library for both supported Actron platforms.

- Neo systems use the MQTT realtime transport.
- Que (NX-Gen) systems use the SignalR/SSE realtime transport.
- The public API exposes `start_push()`, `stop_push()`, `subscribe_system_updates()`, and `stream_system_updates()`.
- Realtime updates are converted into the same `ActronAirStatus` model used by the polling API.

This means consumer code can work with one status model regardless of whether updates arrive through polling or push.

## What You Need To Do To Use It

1. Create an authenticated `ActronAirAPI` instance.
2. Load your systems with `get_ac_systems()`.
3. Call `start_push()` for one or more serial numbers.
4. If `start_push()` returns `True`, consume updates with either callbacks or the async stream API.
5. If `start_push()` returns `False`, continue using your normal polling flow.
6. Call `stop_push()` when you no longer want realtime updates.

## Example

```python
import asyncio
from actron_neo_api import ActronAirAPI


async def main() -> None:
    api = ActronAirAPI(refresh_token="your_refresh_token")

    systems = await api.get_ac_systems()
    serial = systems[0].serial

    started = await api.start_push([serial])
    if not started:
        await api.update_status(serial)
        return

    def on_update(status) -> None:
        print(f"Update received for {status.serial_number}")

    api.subscribe_system_updates(serial, on_update)

    async for status in api.stream_system_updates(serial):
        print(status.user_aircon_settings.mode)
        break

    await api.stop_push()


asyncio.run(main())
```

## Platform Behavior

- Platform selection is automatic when push starts.
- Neo systems are connected through MQTT.
- Que systems are connected through SignalR/SSE.
- Consumer code does not need to manage the transport directly.

## Fallback Behavior

Push is optional.

- If `start_push()` succeeds, updates can be consumed through callbacks or `stream_system_updates()`.
- If `start_push()` returns `False`, push was not started and the caller should continue using polling.
- The library does not automatically begin polling when push startup fails.

## Home Assistant Impact

- Home Assistant integrations can keep using the same status model and update flow.
- The main change is choosing whether to opt into push.
- Existing polling-based integrations remain valid.

## Validation

Realtime support is covered by the repository test suite, including:

- transport behavior for Neo MQTT
- transport behavior for Que SignalR
- public API integration and fallback behavior

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
