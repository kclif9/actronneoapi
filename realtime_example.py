"""Realtime push smoke test for ActronAirAPI.

This script is intended for manual validation of realtime subscriptions. It
starts the library's push transport, registers a callback, and optionally
streams a small number of realtime status updates.

Usage:
    export ACTRON_REFRESH_TOKEN="your_refresh_token"
    python realtime_example.py

Optional environment variables:
    ACTRON_SERIAL                 Specific system serial to subscribe to.
    ACTRON_PLATFORM               Explicit platform override: neo or que.
    ACTRON_PUSH_EVENT_LIMIT       Number of updates to wait for. Default: 1.
    ACTRON_PUSH_IDLE_TIMEOUT      Seconds to wait for the next update. Default: 30.
    ACTRON_PUSH_WARMUP_SECONDS    Seconds to keep the subscription open after
                                  start_push() succeeds, even if no update is
                                  received. Default: 5.
    ACTRON_PUSH_DEBUG_RAW         Print raw realtime event keys and tracked
                                  quiet/turbo fields. Default: false.
    ACTRON_LOG_LEVEL              Logging level. Default: INFO.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import ssl
from collections.abc import Awaitable, Callable
from pprint import pformat
from typing import Any
from urllib.parse import urlparse

from actron_neo_api import (
    ActronAirAPI,
    ActronAirAPIError,
    ActronAirAuthError,
    ActronAirStatus,
)
from actron_neo_api.rt import (
    MQTTRTClient,
    RealtimeConnectionDetails,
    RealtimeEvent,
    RealtimeMessage,
)

LOGGER = logging.getLogger(__name__)


def _require_env(name: str) -> str:
    """Return a required environment variable or raise a clear error."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Environment variable {name} is required")
    return value


def _read_int_env(name: str, default: int) -> int:
    """Read an integer environment variable with a fallback."""
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    return int(raw_value)


def _read_float_env(name: str, default: float) -> float:
    """Read a float environment variable with a fallback."""
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return default
    return float(raw_value)


def _read_bool_env(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable with a fallback."""
    raw_value = os.environ.get(name, "").strip().lower()
    if not raw_value:
        return default
    return raw_value in {"1", "true", "yes", "on"}


def _configure_logging() -> None:
    """Configure process logging from the environment."""
    log_level_name = os.environ.get("ACTRON_LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logging.getLogger("actron_neo_api").setLevel(log_level)


def _format_status_summary(status: ActronAirStatus) -> str:
    """Build a concise one-line status summary for manual verification."""
    settings = status.user_aircon_settings
    if settings is None:
        return f"serial={status.serial_number} settings=unavailable"

    return (
        f"serial={status.serial_number} "
        f"power={'on' if settings.is_on else 'off'} "
        f"mode={settings.mode} "
        f"fan={settings.fan_mode} "
        f"cool={settings.temperature_setpoint_cool_c} "
        f"heat={settings.temperature_setpoint_heat_c} "
        f"quiet={'on' if settings.quiet_mode_enabled else 'off'} "
        f"turbo={'on' if settings.turbo_enabled else 'off'}"
    )


async def _print_callback(status: ActronAirStatus) -> None:
    """Print callback-delivered realtime updates."""
    print(f"callback update: {_format_status_summary(status)}")


def _lookup_nested_value(payload: dict[str, Any], path: str) -> Any:
    """Return a nested dictionary value or None when the path is absent."""
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _tracked_payload_values(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract the raw realtime fields relevant to quiet/turbo debugging."""
    tracked_paths = (
        "UserAirconSettings.QuietModeEnabled",
        "UserAirconSettings.TurboMode",
        "lastKnownState.UserAirconSettings.QuietModeEnabled",
        "lastKnownState.UserAirconSettings.TurboMode",
        "QuietModeEnabled",
        "TurboMode",
    )
    tracked: dict[str, Any] = {}
    for path in tracked_paths:
        value = _lookup_nested_value(payload, path)
        if value is not None:
            tracked[path] = value
    return tracked


def _summarize_payload(payload: dict[str, Any]) -> str:
    """Build a concise raw payload summary for debugging."""
    top_level_keys = sorted(payload.keys())
    tracked = _tracked_payload_values(payload)
    tracked_summary = pformat(tracked, compact=True) if tracked else "<absent>"
    return f"top_level_keys={top_level_keys} tracked={tracked_summary}"


async def _print_raw_event(event: RealtimeEvent) -> None:
    """Print raw realtime events for debugging payload shape issues."""
    if not isinstance(event, RealtimeMessage):
        return
    print(f"raw event: topic={event.topic} {_summarize_payload(event.payload)}")


def _resolve_probe_target(details: RealtimeConnectionDetails) -> tuple[str, int, str | None]:
    """Resolve a realtime endpoint to host, port, and TLS server name for probing."""
    if "://" not in details.endpoint:
        return details.endpoint, details.port, details.endpoint if details.uses_tls else None

    parsed = urlparse(details.endpoint)
    host = parsed.hostname
    if host is None:
        raise RuntimeError(f"Could not determine host from endpoint: {details.endpoint}")

    port = parsed.port or details.port
    server_name = host if details.uses_tls else None
    return host, port, server_name


def _is_ip_literal(value: str) -> bool:
    """Return whether a string is an IP literal."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


async def _probe_connection_details(details: RealtimeConnectionDetails, timeout: float) -> None:
    """Attempt a raw socket/TLS connection to the discovered realtime endpoint."""
    host, port, server_name = _resolve_probe_target(details)
    ssl_context = await asyncio.to_thread(ssl.create_default_context) if details.uses_tls else None
    if ssl_context is not None and _is_ip_literal(host):
        ssl_context.check_hostname = False
        server_name = None

    print(f"Probe target: host={host} port={port} tls={'yes' if details.uses_tls else 'no'}")

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                host=host,
                port=port,
                ssl=ssl_context,
                server_hostname=server_name,
            ),
            timeout=timeout,
        )
    except TimeoutError:
        print(f"Network probe timed out after {timeout:.1f}s")
        return
    except Exception as exc:
        print(f"Network probe failed: {type(exc).__name__}: {exc}")
        return

    if ssl_context is not None and _is_ip_literal(host):
        print(
            "Network probe succeeded: TCP/TLS connection established "
            "with hostname check disabled for IP endpoint"
        )
    else:
        print("Network probe succeeded: TCP/TLS connection established")
    writer.close()
    await writer.wait_closed()
    del reader


async def main() -> None:
    """Run a manual realtime push smoke test."""
    _configure_logging()

    refresh_token = _require_env("ACTRON_REFRESH_TOKEN")
    serial_override = os.environ.get("ACTRON_SERIAL", "").strip().lower() or None
    platform_override = os.environ.get("ACTRON_PLATFORM", "").strip().lower() or None
    event_limit = _read_int_env("ACTRON_PUSH_EVENT_LIMIT", 1)
    idle_timeout = _read_float_env("ACTRON_PUSH_IDLE_TIMEOUT", 30.0)
    warmup_seconds = _read_float_env("ACTRON_PUSH_WARMUP_SECONDS", 5.0)
    debug_raw = _read_bool_env("ACTRON_PUSH_DEBUG_RAW")

    if event_limit <= 0:
        raise RuntimeError("ACTRON_PUSH_EVENT_LIMIT must be greater than zero")
    if idle_timeout <= 0:
        raise RuntimeError("ACTRON_PUSH_IDLE_TIMEOUT must be greater than zero")
    if warmup_seconds < 0:
        raise RuntimeError("ACTRON_PUSH_WARMUP_SECONDS must be greater than or equal to zero")

    api_kwargs: dict[str, Any] = {"refresh_token": refresh_token}
    if platform_override:
        api_kwargs["platform"] = platform_override

    print("Starting realtime smoke test...")
    async with ActronAirAPI(**api_kwargs) as api:
        systems = await api.get_ac_systems()
        if not systems:
            raise RuntimeError("No AC systems found for this account")

        if serial_override is not None:
            serial = serial_override
        else:
            first_system = next((system for system in systems if system.serial), None)
            if first_system is None or first_system.serial is None:
                raise RuntimeError("No AC system with a serial number was found")
            serial = first_system.serial.lower()

        print(f"Using system serial: {serial}")
        print(f"Detected platform: {api.platform}")
        print(f"Initial system count: {len(systems)}")

        details = await api._discover_realtime_connection_details(serial)  # noqa: SLF001
        if details is None:
            print("Realtime connection details could not be discovered.")
        else:
            print(
                "Realtime details: "
                f"endpoint={details.endpoint} port={details.port} "
                f"protocol={details.protocol} user_id={details.user_id}"
            )
            await _probe_connection_details(details, idle_timeout)

        started = await api.start_push([serial])
        if not started:
            print("Realtime push could not be started. Falling back to one polling update.")
            await api.update_status(serial)
            status = api.state_manager.get_status(serial)
            if status is None:
                print("Polling fallback returned no status for the selected system.")
            else:
                print(f"polled status: {_format_status_summary(status)}")
            return

        callback: Callable[[ActronAirStatus], Awaitable[None] | None] = _print_callback
        api.subscribe_system_updates(serial, callback)
        if debug_raw and isinstance(api._rt_client, MQTTRTClient):  # noqa: SLF001 - targeted smoke-test debug hook
            api._rt_client.register_callback(_print_raw_event)
            print("Raw realtime event debugging is enabled.")

        print("Realtime push started successfully.")
        print(f"Waiting for up to {event_limit} update(s) with {idle_timeout:.1f}s idle timeout...")
        received = 0

        try:
            stream = api.stream_system_updates(serial)
            while received < event_limit:
                try:
                    status = await asyncio.wait_for(anext(stream), timeout=idle_timeout)
                except TimeoutError:
                    print("Timed out waiting for the next realtime update.")
                    break

                received += 1
                print(f"stream update {received}: {_format_status_summary(status)}")

            if received == 0 and warmup_seconds > 0:
                print(
                    "No update received yet; keeping the subscription open for "
                    f"{warmup_seconds:.1f}s to observe broker connectivity."
                )
                await asyncio.sleep(warmup_seconds)
        finally:
            await api.stop_push()

        print(f"Realtime smoke test finished. Updates received: {received}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ActronAirAuthError, ActronAirAPIError, RuntimeError, ValueError) as exc:
        LOGGER.error("Realtime smoke test failed: %s", exc, exc_info=True)
        raise SystemExit(1) from exc
