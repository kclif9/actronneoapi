# Realtime Push Guide

## What Was Implemented

Realtime push support is now available in the library for both supported Actron platforms.

- Neo systems use the MQTT realtime transport.
- Que (NX-Gen) systems use the SignalR/SSE realtime transport.
- The public API exposes `start_push()`, `stop_push()`, `subscribe_system_updates()`, `subscribe_connection_state()`, and `stream_system_updates()`.
- Realtime updates are converted into the same `ActronAirStatus` model used by the polling API.

This means consumer code can work with one status model regardless of whether updates arrive through polling or push.

## What You Need To Do To Use It

1. Create an authenticated `ActronAirAPI` instance.
2. Load your systems with `get_ac_systems()`.
3. Call `start_push()` for one or more serial numbers.
4. If `start_push()` returns `True`, consume updates with either callbacks or the async stream API.
5. If `start_push()` returns `False`, continue using your normal polling flow.
6. If `start_push()` raises `ActronAirAuthError`, re-authenticate; polling would fail the same way.
7. Call `stop_push()` when you no longer want realtime updates.

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

    unsubscribe = api.subscribe_system_updates(serial, on_update)

    async for status in api.stream_system_updates(serial):
        print(status.user_aircon_settings.mode)
        break

    unsubscribe()
    await api.stop_push()


asyncio.run(main())
```

## Subscriptions

`subscribe_system_updates()` and `subscribe_connection_state()` both return a
zero-argument callable that removes the subscription. Calling it more than once
is safe, which matches the remove-listener idiom used by Home Assistant
(`CALLBACK_TYPE`).

`subscribe_connection_state()` reports transport connection transitions as
`RealtimeConnectionEvent` values (`connecting`, `connected`, `reconnecting`,
`disconnected`, `error`). Connection state belongs to the transport rather than
to a single system, so one callback covers every subscribed serial. Callbacks
may be sync or async, and an exception raised inside one is logged without
disrupting the transport.

```python
def on_connection(event) -> None:
    print(event.state.value, event.previous_state, event.reason)


unsubscribe_connection = api.subscribe_connection_state(on_connection)
```

## Platform Behavior

- Platform selection is automatic when push starts.
- Neo systems are connected through MQTT.
- Que systems are connected through SignalR/SSE.
- Consumer code does not need to manage the transport directly.

## MQTT Client Identifier (Neo)

`start_push()` accepts an optional `client_id` used as the MQTT client
identifier. Supplying one that is stable across restarts — a Home Assistant
config entry id, for example — opts the connection into a persistent broker
session, so messages published while the client was away are delivered on
reconnect.

```python
await api.start_push([serial], client_id=entry.entry_id)
```

When `client_id` is omitted, a random `HA_`-prefixed identifier is generated and
a clean session is used instead. A persistent session keyed to an identifier
that changes every restart would strand a session on the broker each time
without ever resuming one, so the two settings are chosen together.

Use an identifier that is unique per installation. Two clients connecting with
the same identifier will repeatedly disconnect each other.

## Event Buffering

Each transport keeps a bounded buffer of recent events for `iter_events()`
consumers; once it is full the oldest event is dropped rather than retained.
Callback subscribers (`subscribe_system_updates()`,
`subscribe_connection_state()`) are delivered to directly and are unaffected by
the buffer.

## Fallback Behavior

Push is optional.

- If `start_push()` succeeds, updates can be consumed through callbacks or `stream_system_updates()`.
- If `start_push()` returns `False`, push was not started and the caller should continue using polling.
- Expected failures (broker unreachable, connection details missing, network errors) are logged at debug level, since falling back to polling is normal operation.
- Authentication failures are not treated as a fallback: `start_push()` re-raises `ActronAirAuthError` so the caller can start a reauth flow.
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
