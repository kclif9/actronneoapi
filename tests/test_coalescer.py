"""Tests for CommandCoalescer and command coalescing integration."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from actron_neo_api.actron import ActronAirAPI, CommandCoalescer
from actron_neo_api.exceptions import ActronAirAPIError
from actron_neo_api.models.status import ActronAirStatus
from actron_neo_api.models.system import ActronAirSystemInfo
from actron_neo_api.state import StateManager


def _make_zone_command(enabled_zones: list[bool]) -> dict[str, Any]:
    """Build a set-settings command with EnabledZones."""
    return {
        "command": {
            "type": "set-settings",
            "UserAirconSettings.EnabledZones": enabled_zones,
        }
    }


def _make_mode_command(mode: str) -> dict[str, Any]:
    """Build a set-settings command for system mode."""
    return {
        "command": {
            "type": "set-settings",
            "UserAirconSettings.Mode": mode,
        }
    }


def _make_non_settings_command() -> dict[str, Any]:
    """Build a non-set-settings command."""
    return {"command": {"type": "restart-system"}}


def _state_manager_with_zones(
    serial: str, zones: list[bool]
) -> StateManager:
    """Create a StateManager with a stubbed status containing *zones*."""
    sm = StateManager()
    status = MagicMock(spec=ActronAirStatus)
    settings = MagicMock()
    settings.enabled_zones = list(zones)
    status.user_aircon_settings = settings
    sm.status[serial] = status
    return sm


class TestCommandCoalescer:
    """Unit tests for the CommandCoalescer class."""

    @pytest.mark.asyncio
    async def test_single_command_sent_after_debounce(self) -> None:
        """A single enqueued command is sent after the debounce window."""
        send_fn = AsyncMock()
        sm = _state_manager_with_zones("abc", [True, True, True, True])
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.05)

        cmd = _make_zone_command([False, True, True, True])
        await coalescer.enqueue("abc", cmd)

        send_fn.assert_called_once()
        sent_command = send_fn.call_args[0][1]
        assert sent_command["command"]["UserAirconSettings.EnabledZones"] == [
            False,
            True,
            True,
            True,
        ]

    @pytest.mark.asyncio
    async def test_concurrent_zone_toggles_merged(self) -> None:
        """Concurrent zone toggles are merged into a single API call."""
        send_fn = AsyncMock()
        sm = _state_manager_with_zones("abc", [True, True, True, True])
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.05)

        # Simulate 3 concurrent zone disable commands (stale-read scenario)
        cmd0 = _make_zone_command([False, True, True, True])  # zone 0 off
        cmd1 = _make_zone_command([True, False, True, True])  # zone 1 off
        cmd2 = _make_zone_command([True, True, False, True])  # zone 2 off

        await asyncio.gather(
            coalescer.enqueue("abc", cmd0),
            coalescer.enqueue("abc", cmd1),
            coalescer.enqueue("abc", cmd2),
        )

        # Only ONE API call should have been made
        send_fn.assert_called_once()
        sent_command = send_fn.call_args[0][1]
        assert sent_command["command"]["UserAirconSettings.EnabledZones"] == [
            False,
            False,
            False,
            True,
        ]

    @pytest.mark.asyncio
    async def test_scalar_keys_last_write_wins(self) -> None:
        """Non-list keys use last-write-wins merging."""
        send_fn = AsyncMock()
        sm = StateManager()
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.05)

        cmd_cool = _make_mode_command("COOL")
        cmd_heat = _make_mode_command("HEAT")

        await asyncio.gather(
            coalescer.enqueue("abc", cmd_cool),
            coalescer.enqueue("abc", cmd_heat),
        )

        send_fn.assert_called_once()
        sent_command = send_fn.call_args[0][1]
        assert sent_command["command"]["UserAirconSettings.Mode"] == "HEAT"

    @pytest.mark.asyncio
    async def test_mixed_keys_merged(self) -> None:
        """Zone changes and scalar keys are merged into one command."""
        send_fn = AsyncMock()
        sm = _state_manager_with_zones("abc", [True, True, True, True])
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.05)

        cmd_zone = _make_zone_command([False, True, True, True])
        cmd_mode = _make_mode_command("HEAT")

        await asyncio.gather(
            coalescer.enqueue("abc", cmd_zone),
            coalescer.enqueue("abc", cmd_mode),
        )

        send_fn.assert_called_once()
        sent = sent_command = send_fn.call_args[0][1]["command"]
        assert sent["UserAirconSettings.EnabledZones"] == [False, True, True, True]
        assert sent["UserAirconSettings.Mode"] == "HEAT"
        assert sent["type"] == "set-settings"

    @pytest.mark.asyncio
    async def test_error_propagated_to_all_futures(self) -> None:
        """An API error is propagated to every waiting caller."""
        send_fn = AsyncMock(side_effect=ActronAirAPIError("boom"))
        sm = _state_manager_with_zones("abc", [True, True, True, True])
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.05)

        cmd0 = _make_zone_command([False, True, True, True])
        cmd1 = _make_zone_command([True, False, True, True])

        with pytest.raises(ActronAirAPIError, match="boom"):
            await asyncio.gather(
                coalescer.enqueue("abc", cmd0),
                coalescer.enqueue("abc", cmd1),
            )

    @pytest.mark.asyncio
    async def test_separate_serials_not_merged(self) -> None:
        """Commands for different serial numbers are sent separately."""
        send_fn = AsyncMock()
        sm = _state_manager_with_zones("abc", [True, True])
        sm.status["xyz"] = sm.status["abc"]  # reuse for convenience
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.05)

        cmd_abc = _make_zone_command([False, True])
        cmd_xyz = _make_zone_command([True, False])

        await asyncio.gather(
            coalescer.enqueue("abc", cmd_abc),
            coalescer.enqueue("xyz", cmd_xyz),
        )

        assert send_fn.call_count == 2

    @pytest.mark.asyncio
    async def test_flush_all_sends_pending(self) -> None:
        """flush_all sends pending batches immediately."""
        send_fn = AsyncMock()
        sm = _state_manager_with_zones("abc", [True, True, True, True])
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=10.0)

        # Enqueue but don't await (it would block waiting for debounce)
        task = asyncio.create_task(
            coalescer.enqueue("abc", _make_zone_command([False, True, True, True]))
        )
        await asyncio.sleep(0)  # let the task start

        await coalescer.flush_all()
        await task  # should now complete

        send_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_baseline_zones_fallback(self) -> None:
        """Without baseline zones, EnabledZones uses last-write-wins."""
        send_fn = AsyncMock()
        sm = StateManager()  # empty — no status
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.05)

        cmd0 = _make_zone_command([False, True, True, True])
        cmd1 = _make_zone_command([True, False, True, True])

        await asyncio.gather(
            coalescer.enqueue("abc", cmd0),
            coalescer.enqueue("abc", cmd1),
        )

        send_fn.assert_called_once()
        sent = send_fn.call_args[0][1]["command"]
        # Last-write-wins since no baseline
        assert sent["UserAirconSettings.EnabledZones"] == [True, False, True, True]

    @pytest.mark.asyncio
    async def test_debounce_resets_on_new_command(self) -> None:
        """The debounce timer resets when a new command is added."""
        send_fn = AsyncMock()
        sm = _state_manager_with_zones("abc", [True, True, True, True])
        coalescer = CommandCoalescer(send_fn, sm, debounce_seconds=0.08)

        # Enqueue first command
        task1 = asyncio.create_task(
            coalescer.enqueue("abc", _make_zone_command([False, True, True, True]))
        )
        await asyncio.sleep(0)

        # After 50ms, add another — should reset the timer
        await asyncio.sleep(0.05)
        task2 = asyncio.create_task(
            coalescer.enqueue("abc", _make_zone_command([True, False, True, True]))
        )
        await asyncio.sleep(0)

        # At 50ms after first command, nothing sent yet (timer was reset)
        send_fn.assert_not_called()

        # Wait for debounce after second command
        await asyncio.gather(task1, task2)

        send_fn.assert_called_once()
        sent = send_fn.call_args[0][1]["command"]
        assert sent["UserAirconSettings.EnabledZones"] == [False, False, True, True]


class TestActronAirAPISendCommandCoalescing:
    """Integration tests for command coalescing through ActronAirAPI.send_command."""

    @pytest.mark.asyncio
    async def test_set_settings_routed_through_coalescer(
        self,
        mock_oauth: MagicMock,
        mock_aiohttp_response: Any,
        sample_system_neo: dict[str, Any],
    ) -> None:
        """set-settings commands are routed through the coalescer."""
        api = ActronAirAPI()
        api.oauth2_auth = mock_oauth
        api._initialized = True
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        with patch.object(api._coalescer, "enqueue", new_callable=AsyncMock) as mock_enqueue:
            cmd = _make_mode_command("COOL")
            await api.send_command("abc123", cmd)
            mock_enqueue.assert_called_once_with("abc123", cmd)

    @pytest.mark.asyncio
    async def test_non_settings_bypasses_coalescer(
        self,
        mock_oauth: MagicMock,
        mock_aiohttp_response: Any,
        sample_system_neo: dict[str, Any],
    ) -> None:
        """Non-set-settings commands bypass the coalescer."""
        api = ActronAirAPI()
        api.oauth2_auth = mock_oauth
        api._initialized = True
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_resp = mock_aiohttp_response(status=200, json_data={"success": True})
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.request = MagicMock(return_value=mock_ctx)

        api._session = mock_session

        with patch.object(api._coalescer, "enqueue", new_callable=AsyncMock) as mock_enqueue:
            await api.send_command("abc123", _make_non_settings_command())
            mock_enqueue.assert_not_called()
            mock_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_flushes_coalescer(self) -> None:
        """API close() flushes the coalescer before closing the session."""
        api = ActronAirAPI()

        with patch.object(
            api._coalescer, "flush_all", new_callable=AsyncMock
        ) as mock_flush:
            await api.close()
            mock_flush.assert_called_once()

    def test_custom_debounce_seconds(self) -> None:
        """Custom debounce_seconds is passed to the coalescer."""
        api = ActronAirAPI(debounce_seconds=0.5)
        assert api._coalescer._debounce == 0.5

    def test_zero_debounce_disables_coalescing(self) -> None:
        """Setting debounce_seconds=0 effectively disables coalescing."""
        api = ActronAirAPI(debounce_seconds=0)
        assert api._coalescer._debounce == 0

    @pytest.mark.asyncio
    async def test_concurrent_zone_toggles_end_to_end(
        self,
        mock_oauth: MagicMock,
        mock_aiohttp_response: Any,
        sample_system_neo: dict[str, Any],
        sample_status_full: dict[str, Any],
    ) -> None:
        """End-to-end test: concurrent zone toggles produce single API call."""
        api = ActronAirAPI(debounce_seconds=0.05)
        api.oauth2_auth = mock_oauth
        api._initialized = True
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        # Load status into state manager so coalescer has a baseline
        api.state_manager.process_status_update("abc123", sample_status_full)

        mock_resp = mock_aiohttp_response(status=200, json_data={"success": True})
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.request = MagicMock(return_value=mock_ctx)
        api._session = mock_session

        # The fixture has EnabledZones = [T, F, T, F, F, F, F, F]
        # Toggle zone 0 off and zone 1 on concurrently (stale-read problem)
        cmd0 = _make_zone_command([False, False, True, False, False, False, False, False])
        cmd1 = _make_zone_command([True, True, True, False, False, False, False, False])

        await asyncio.gather(
            api.send_command("abc123", cmd0),
            api.send_command("abc123", cmd1),
        )

        # Only ONE API call
        assert mock_session.request.call_count == 1

        # Verify merged EnabledZones: zone 0→False, zone 1→True, rest unchanged
        call_kwargs = mock_session.request.call_args
        sent_json = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert sent_json["command"]["UserAirconSettings.EnabledZones"] == [
            False,
            True,
            True,
            False,
            False,
            False,
            False,
            False,
        ]
