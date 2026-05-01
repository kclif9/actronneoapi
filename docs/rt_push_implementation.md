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
