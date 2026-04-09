"""Tests targeting remaining uncovered lines for 100% coverage."""

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from actron_neo_api import ActronAirAPI
from actron_neo_api.actron import CommandCoalescer
from actron_neo_api.exceptions import ActronAirAPIError, ActronAirAuthError
from actron_neo_api.models import ActronAirStatus
from actron_neo_api.models.system import ActronAirACSystem
from actron_neo_api.models.zone import ActronAirPeripheral, ActronAirZone
from actron_neo_api.oauth import ActronAirOAuth2DeviceCodeAuth
from actron_neo_api.state import StateManager

# ---------------------------------------------------------------------------
# actron.py – _CommandCoalescer._flush edge cases (lines 171, 194)
# ---------------------------------------------------------------------------


class TestCoalescerFlushEdgeCases:
    """Test _CommandCoalescer._flush with missing batch and BaseException."""

    @pytest.mark.asyncio
    async def test_flush_no_batch_returns_early(self) -> None:
        """Line 171: _flush returns immediately when batch is None."""
        from actron_neo_api.actron import CommandCoalescer

        send_fn = AsyncMock()
        state_mgr = MagicMock()
        coalescer = CommandCoalescer(
            send_fn=send_fn, state_manager=state_mgr, debounce_seconds=0.01
        )
        # Flush a serial that was never enqueued
        await coalescer._flush("nonexistent_serial")
        send_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_base_exception_propagates(self) -> None:
        """BaseException (e.g. KeyboardInterrupt) resolves futures then re-raises."""
        from actron_neo_api.actron import CommandCoalescer, _PendingBatch

        send_fn = AsyncMock(side_effect=KeyboardInterrupt("interrupted"))
        state_mgr = MagicMock()
        coalescer = CommandCoalescer(
            send_fn=send_fn, state_manager=state_mgr, debounce_seconds=10.0
        )

        # Manually create a batch with a future
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        batch = _PendingBatch(baseline_zones=None)
        batch.merged_command = {"type": "set-settings", "key": "value"}
        batch.futures.append(future)
        coalescer._batches["serial1"] = batch

        with pytest.raises(KeyboardInterrupt):
            await coalescer._flush("serial1")

        # BaseException sets the exception on futures before re-raising
        assert future.done()
        with pytest.raises(KeyboardInterrupt):
            future.result()


# ---------------------------------------------------------------------------
# actron.py – _make_request 401 retry paths (lines 551, 562)
# ---------------------------------------------------------------------------


class TestMakeRequest401RetryPaths:
    """Test 401 retry where refresh raises different exception types."""

    def _make_api_with_valid_token(self) -> ActronAirAPI:
        """Create an API instance with valid token to bypass ensure_token_valid."""
        api = ActronAirAPI(refresh_token="test_refresh")
        api._initialized = True
        api.oauth2_auth.access_token = "valid_token"
        api.oauth2_auth.token_expiry = time.monotonic() + 3600
        return api

    def _make_401_session(self) -> MagicMock:
        """Create a mock session that returns a 401 response."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        session = MagicMock()
        session.closed = False
        session.request = MagicMock(return_value=mock_ctx)
        return session

    @pytest.mark.asyncio
    async def test_401_refresh_raises_auth_error_reraises(self) -> None:
        """Line 551: ActronAirAuthError from refresh is re-raised directly."""
        api = self._make_api_with_valid_token()
        api._session = self._make_401_session()
        api.oauth2_auth.refresh_access_token = AsyncMock(
            side_effect=ActronAirAuthError("Token revoked")
        )

        with pytest.raises(ActronAirAuthError, match="Token revoked"):
            await api._make_request("get", "test/endpoint")

    @pytest.mark.asyncio
    async def test_401_refresh_raises_client_error_wraps(self) -> None:
        """Line 562: Non-auth error from refresh is wrapped in ActronAirAuthError."""
        api = self._make_api_with_valid_token()
        api._session = self._make_401_session()
        api.oauth2_auth.refresh_access_token = AsyncMock(
            side_effect=aiohttp.ClientError("Connection reset")
        )

        with pytest.raises(
            ActronAirAuthError, match="Authentication failed and token refresh failed"
        ):
            await api._make_request("get", "test/endpoint")

    @pytest.mark.asyncio
    async def test_401_refresh_raises_value_error_wraps(self) -> None:
        """Line 562: ValueError from refresh is wrapped in ActronAirAuthError."""
        api = self._make_api_with_valid_token()
        api._session = self._make_401_session()
        api.oauth2_auth.refresh_access_token = AsyncMock(side_effect=ValueError("Bad token format"))

        with pytest.raises(
            ActronAirAuthError, match="Authentication failed and token refresh failed"
        ):
            await api._make_request("get", "test/endpoint")

    @pytest.mark.asyncio
    async def test_401_no_refresh_token_raises_directly(self) -> None:
        """Line 562: 401 with no refresh_token raises ActronAirAuthError directly."""
        api = self._make_api_with_valid_token()
        api.oauth2_auth.refresh_token = None  # No refresh token
        api._session = self._make_401_session()

        with pytest.raises(ActronAirAuthError, match="Authentication failed"):
            await api._make_request("get", "test/endpoint")


# ---------------------------------------------------------------------------
# actron.py – get_ac_systems response validation (lines 593, 597, 601)
# ---------------------------------------------------------------------------


class TestGetACSystemsValidation:
    """Test get_ac_systems with invalid response structures."""

    def _make_api_with_mock_request(self, response_data: dict[str, Any]) -> ActronAirAPI:
        """Create an API that returns a specific response from _make_request."""
        api = ActronAirAPI(refresh_token="test")
        api._initialized = True

        async def fake_make_request(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return response_data

        api._make_request = fake_make_request  # type: ignore[assignment]
        return api

    @pytest.mark.asyncio
    async def test_missing_embedded_key(self) -> None:
        """Line 593: Response missing '_embedded' key."""
        api = self._make_api_with_mock_request({"data": "wrong"})

        with pytest.raises(ActronAirAPIError, match="missing '_embedded' key"):
            await api.get_ac_systems()

    @pytest.mark.asyncio
    async def test_missing_ac_system_in_embedded(self) -> None:
        """Line 597: '_embedded' missing 'ac-system'."""
        api = self._make_api_with_mock_request({"_embedded": {"other": []}})

        with pytest.raises(ActronAirAPIError, match="missing 'ac-system'"):
            await api.get_ac_systems()

    @pytest.mark.asyncio
    async def test_ac_system_not_a_list(self) -> None:
        """Line 601: 'ac-system' is not a list."""
        api = self._make_api_with_mock_request({"_embedded": {"ac-system": "not_a_list"}})

        with pytest.raises(ActronAirAPIError, match="is not a list"):
            await api.get_ac_systems()


# ---------------------------------------------------------------------------
# settings.py – set_temperature validation (lines 354, 356)
# ---------------------------------------------------------------------------


class TestSettingsSetTemperatureValidation:
    """Test async set_temperature validation in settings."""

    @pytest.mark.asyncio
    async def test_set_temperature_non_numeric(self) -> None:
        """Line 354: set_temperature with non-numeric value."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "UserAirconSettings": {"isOn": True, "Mode": "COOL"},
            },
        )
        status.parse_nested_components()

        with pytest.raises(ValueError, match="Temperature must be a number"):
            await status.user_aircon_settings.set_temperature("hot")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_set_temperature_out_of_range(self) -> None:
        """Line 356: set_temperature with value outside physical limits."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "UserAirconSettings": {"isOn": True, "Mode": "COOL"},
            },
        )
        status.parse_nested_components()

        with pytest.raises(ValueError, match="outside reasonable range"):
            await status.user_aircon_settings.set_temperature(200.0)


# ---------------------------------------------------------------------------
# status.py – get_peripheral_for_zone no match (line 272)
# ---------------------------------------------------------------------------


class TestGetPeripheralForZoneNoMatch:
    """Test get_peripheral_for_zone edge cases."""

    def test_no_matching_peripheral(self) -> None:
        """Returns None when no peripheral has the zone assigned."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "AirconSystem": {
                    "MasterSerial": "TEST",
                    "Peripherals": [
                        {
                            "ZoneAssignment": [2, 3],
                            "SerialNumber": "P1",
                        }
                    ],
                },
                "RemoteZoneInfo": [
                    {"CanOperate": True, "LiveTemp_oC": 22.0, "NV_Exists": True},
                ],
            },
        )
        status.parse_nested_components()

        # Zone 0 is not in any peripheral's assignments
        result = status.get_peripheral_for_zone(0)
        assert result is None

    def test_negative_zone_index(self) -> None:
        """Line 272: Negative zone_index raises ValueError."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "AirconSystem": {"MasterSerial": "TEST"},
            },
        )
        status.parse_nested_components()

        with pytest.raises(ValueError, match="zone_index must be non-negative"):
            status.get_peripheral_for_zone(-1)


# ---------------------------------------------------------------------------
# system.py – set_system_mode validation (lines 134, 139)
# ---------------------------------------------------------------------------


class TestACSystemSetModeValidation:
    """Test set_system_mode with invalid inputs."""

    @pytest.mark.asyncio
    async def test_set_mode_empty_string(self) -> None:
        """Line 134: Empty string is rejected as a mode."""
        ac_system = ActronAirACSystem(master_serial="TEST")
        parent = MagicMock()
        parent.api = MagicMock()
        ac_system._parent_status = parent

        with pytest.raises(ValueError, match="Mode must be a non-empty string"):
            await ac_system.set_system_mode("")

    @pytest.mark.asyncio
    async def test_set_mode_invalid_value(self) -> None:
        """Line 139: Invalid mode value."""
        ac_system = ActronAirACSystem(master_serial="TEST")
        parent = MagicMock()
        parent.api = MagicMock()
        ac_system._parent_status = parent

        with pytest.raises(ValueError, match="Invalid mode"):
            await ac_system.set_system_mode("TURBO")


# ---------------------------------------------------------------------------
# zone.py – from_peripheral_data exception handlers (lines 82, 95-97)
# ---------------------------------------------------------------------------


class TestPeripheralDataExceptionHandlers:
    """Test from_peripheral_data exception branches for temperature/humidity."""

    def test_empty_peripheral_data(self) -> None:
        """Line 82: Empty peripheral_data raises ValueError."""
        with pytest.raises(ValueError, match="peripheral_data cannot be None or empty"):
            ActronAirPeripheral.from_peripheral_data({})

    def test_none_peripheral_data(self) -> None:
        """Line 82: None peripheral_data raises ValueError."""
        with pytest.raises(ValueError, match="peripheral_data cannot be None or empty"):
            ActronAirPeripheral.from_peripheral_data(None)  # type: ignore[arg-type]

    def test_temperature_value_type_exception(self) -> None:
        """Temperature value that's not int/float is skipped."""
        data = {
            "LogicalAddress": 1,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "S1",
            "SensorInputs": {
                "SHTC1": {
                    "Temperature_oC": [22.5],  # List, not int/float
                }
            },
        }
        peripheral = ActronAirPeripheral.from_peripheral_data(data)
        # Non-numeric type is skipped (isinstance check fails), temperature stays None
        assert peripheral.temperature is None

    def test_humidity_value_type_exception(self) -> None:
        """Humidity value that's not int/float is skipped."""
        data = {
            "LogicalAddress": 1,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "S1",
            "SensorInputs": {
                "SHTC1": {
                    "RelativeHumidity_pc": {"value": 55},  # Dict, not int/float
                }
            },
        }
        peripheral = ActronAirPeripheral.from_peripheral_data(data)
        assert peripheral.humidity is None

    def test_temperature_except_handler(self) -> None:
        """Lines 95-97: Force the temperature except handler via mock."""
        data = {
            "LogicalAddress": 1,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "S1",
            "SensorInputs": {
                "SHTC1": {
                    "Temperature_oC": 22.5,
                }
            },
        }

        original_float = float

        def patched_float(val: Any = 0.0) -> float:
            """Raise ValueError for the specific temperature value."""
            if val == 22.5:
                raise ValueError("mock conversion error")
            return original_float(val)

        with patch("actron_neo_api.models.zone.float", patched_float, create=True):
            peripheral = ActronAirPeripheral.from_peripheral_data(data)

        assert peripheral.temperature is None

    def test_humidity_except_handler(self) -> None:
        """Lines 103-105: Force the humidity except handler via mock."""
        data = {
            "LogicalAddress": 1,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "S1",
            "SensorInputs": {
                "SHTC1": {
                    "RelativeHumidity_pc": 55.0,
                }
            },
        }

        original_float = float

        def patched_float(val: Any = 0.0) -> float:
            """Raise ValueError for the specific humidity value."""
            if val == 55.0:
                raise ValueError("mock conversion error")
            return original_float(val)

        with patch("actron_neo_api.models.zone.float", patched_float, create=True):
            peripheral = ActronAirPeripheral.from_peripheral_data(data)

        assert peripheral.humidity is None


# ---------------------------------------------------------------------------
# zone.py – ActronAirPeripheral.set_parent_status (lines 103-105)
# ---------------------------------------------------------------------------


class TestPeripheralSetParentStatus:
    """Test ActronAirPeripheral.set_parent_status."""

    def test_set_parent_status(self) -> None:
        """Lines 103-105: set_parent_status stores the parent reference."""
        peripheral = ActronAirPeripheral(ZoneAssignment=[1])
        parent = MagicMock()
        peripheral.set_parent_status(parent)
        assert peripheral._parent_status is parent


# ---------------------------------------------------------------------------
# zone.py – is_active zone_id >= len(enabled_zones) (line 156)
# ---------------------------------------------------------------------------


class TestZoneIsActiveOutOfRange:
    """Test is_active when zone_id exceeds enabled_zones length."""

    def test_zone_id_exceeds_enabled_zones(self) -> None:
        """Line 156: zone_id >= len(enabled_zones) returns False."""
        zone = ActronAirZone(CanOperate=True)
        parent = MagicMock()
        parent.user_aircon_settings.enabled_zones = [True]  # Only 1 zone
        zone._parent_status = parent
        zone.zone_id = 5  # Out of range
        zone.can_operate = True

        assert zone.is_active is False


# ---------------------------------------------------------------------------
# zone.py – set_parent_status negative index (line 379)
# ---------------------------------------------------------------------------


class TestZoneSetParentStatusNegative:
    """Test zone set_parent_status with negative zone_index."""

    def test_negative_zone_index(self) -> None:
        """Line 379: Negative zone_index raises ValueError."""
        zone = ActronAirZone()
        parent = MagicMock()

        with pytest.raises(ValueError, match="zone_index must be non-negative"):
            zone.set_parent_status(parent, zone_index=-1)


# ---------------------------------------------------------------------------
# zone.py – async set_temperature validation (lines 402, 404)
# ---------------------------------------------------------------------------


class TestZoneAsyncSetTemperatureValidation:
    """Test async set_temperature validation in zone."""

    @pytest.mark.asyncio
    async def test_set_temperature_non_numeric(self) -> None:
        """Line 402: Non-numeric temperature raises ValueError."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.mode = "COOL"
        parent.api = MagicMock()
        zone.set_parent_status(parent, 0)

        with pytest.raises(ValueError, match="Temperature must be a number"):
            await zone.set_temperature("warm")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_set_temperature_out_of_range(self) -> None:
        """Line 404: Temperature outside physical limits raises ValueError."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.mode = "COOL"
        parent.api = MagicMock()
        zone.set_parent_status(parent, 0)

        with pytest.raises(ValueError, match="outside reasonable range"):
            await zone.set_temperature(150.0)


# ---------------------------------------------------------------------------
# oauth.py – constructor validation (lines 45, 47)
# ---------------------------------------------------------------------------


class TestOAuth2ConstructorValidation:
    """Test ActronAirOAuth2DeviceCodeAuth constructor validation."""

    def test_empty_base_url(self) -> None:
        """Line 45: Empty base_url raises ValueError."""
        with pytest.raises(ValueError, match="base_url cannot be empty"):
            ActronAirOAuth2DeviceCodeAuth("", "client_id")

    def test_whitespace_base_url(self) -> None:
        """Line 45: Whitespace-only base_url raises ValueError."""
        with pytest.raises(ValueError, match="base_url cannot be empty"):
            ActronAirOAuth2DeviceCodeAuth("   ", "client_id")

    def test_empty_client_id(self) -> None:
        """Line 47: Empty client_id raises ValueError."""
        with pytest.raises(ValueError, match="client_id cannot be empty"):
            ActronAirOAuth2DeviceCodeAuth("https://example.com", "")

    def test_whitespace_client_id(self) -> None:
        """Line 47: Whitespace-only client_id raises ValueError."""
        with pytest.raises(ValueError, match="client_id cannot be empty"):
            ActronAirOAuth2DeviceCodeAuth("https://example.com", "   ")


# ---------------------------------------------------------------------------
# oauth.py – poll_for_token validation (lines 189, 191, 193)
# ---------------------------------------------------------------------------


class TestPollForTokenValidation:
    """Test poll_for_token input validation."""

    @pytest.mark.asyncio
    async def test_empty_device_code(self) -> None:
        """Line 189: Empty device_code raises ValueError."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        with pytest.raises(ValueError, match="device_code cannot be empty"):
            await auth.poll_for_token("")

    @pytest.mark.asyncio
    async def test_interval_too_low(self) -> None:
        """Line 191: interval < 1 raises ValueError."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        with pytest.raises(ValueError, match="interval must be at least 1"):
            await auth.poll_for_token("code", interval=0)

    @pytest.mark.asyncio
    async def test_timeout_too_low(self) -> None:
        """Line 193: timeout < 10 raises ValueError."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        with pytest.raises(ValueError, match="timeout must be at least 10"):
            await auth.poll_for_token("code", timeout=5)


# ---------------------------------------------------------------------------
# oauth.py – refresh_access_token non-string token_type (lines 310-311)
# ---------------------------------------------------------------------------


class TestRefreshTokenEdgeCases:
    """Test refresh_access_token response parsing edge cases."""

    @pytest.mark.asyncio
    async def test_non_string_token_type_defaults_to_bearer(
        self, mock_aiohttp_session: Any
    ) -> None:
        """Lines 310-311: Non-string token_type defaults to 'Bearer'."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        auth.refresh_token = "refresh_tok"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "access_token": "new_token",
                "token_type": 12345,  # Non-string
                "expires_in": 3600,
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session(mock_resp)):
            token, expiry = await auth.refresh_access_token()

        assert token == "new_token"
        assert auth.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_unparseable_expires_in_defaults_to_3600(self, mock_aiohttp_session: Any) -> None:
        """Line 320: Non-parseable expires_in defaults to 3600."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        auth.refresh_token = "refresh_tok"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "access_token": "new_token",
                "token_type": "Bearer",
                "expires_in": "not_a_number",  # Unparseable
            }
        )

        before = time.monotonic()
        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session(mock_resp)):
            token, expiry = await auth.refresh_access_token()

        assert token == "new_token"
        # Expiry should be ~3600 seconds from now (the fallback)
        assert expiry >= before + 3500

    @pytest.mark.asyncio
    async def test_refresh_sets_tokens_atomically(self, mock_aiohttp_session: Any) -> None:
        """Refresh atomically sets access_token, token_expiry, and authenticated_platform."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        auth.refresh_token = "refresh_tok"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "access_token": "new_token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session(mock_resp)):
            token, expiry = await auth.refresh_access_token()

        assert token == "new_token"
        assert auth.access_token == "new_token"
        assert auth.token_expiry is not None
        assert auth.authenticated_platform == "https://example.com"


# ---------------------------------------------------------------------------
# oauth.py – ensure_token_valid proactive refresh warning (line 393)
# ---------------------------------------------------------------------------


class TestEnsureTokenValidProactiveRefresh:
    """Test ensure_token_valid when proactive refresh fails but token is still valid."""

    @pytest.mark.asyncio
    async def test_proactive_refresh_fails_uses_existing_token(self) -> None:
        """Line 393: Warning logged, existing valid token returned."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        auth.access_token = "still_valid"
        # Token valid but expiring soon (within 15 min)
        auth.token_expiry = time.monotonic() + 600

        auth._refresh_access_token_unlocked = AsyncMock(
            side_effect=ActronAirAuthError("Refresh server down")
        )

        # Should succeed because token is still valid (not expired)
        result = await auth.ensure_token_valid()
        assert result == "still_valid"

    @pytest.mark.asyncio
    async def test_access_token_none_after_lock(self) -> None:
        """Line 393: Access token is None after lock block raises ActronAirAuthError."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        auth.access_token = None
        auth.token_expiry = None
        auth.refresh_token = "some_refresh"

        # Refresh sets access_token then we clear it
        async def bad_refresh() -> tuple[str, float]:
            auth.access_token = None
            auth.token_expiry = time.monotonic() + 3600
            return "", 0.0

        auth._refresh_access_token_unlocked = bad_refresh  # type: ignore[assignment]

        with pytest.raises(ActronAirAuthError, match="Access token is not available"):
            await auth.ensure_token_valid()


# ---------------------------------------------------------------------------
# oauth.py – set_tokens validation (lines 416, 418)
# ---------------------------------------------------------------------------


class TestSetTokensValidation:
    """Test set_tokens input validation."""

    def test_empty_access_token(self) -> None:
        """Line 416: Empty access_token raises ValueError."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        with pytest.raises(ValueError, match="access_token cannot be empty"):
            auth.set_tokens("")

    def test_whitespace_access_token(self) -> None:
        """Line 416: Whitespace-only access_token raises ValueError."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        with pytest.raises(ValueError, match="access_token cannot be empty"):
            auth.set_tokens("   ")

    def test_negative_expires_in(self) -> None:
        """Line 418: Negative expires_in raises ValueError."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "client")
        with pytest.raises(ValueError, match="expires_in cannot be negative"):
            auth.set_tokens("valid_token", expires_in=-1)


# ---------------------------------------------------------------------------
# state.py – _extract_peripheral_humidity edge cases (lines 169, 173, 177-180)
# ---------------------------------------------------------------------------


class TestExtractPeripheralHumidity:
    """Test StateManager._extract_peripheral_humidity edge cases."""

    def test_invalid_sensor_inputs_type(self) -> None:
        """Line 169: Non-dict sensor_inputs returns None."""
        sm = StateManager()
        result = sm._extract_peripheral_humidity({"SensorInputs": "invalid"})
        assert result is None

    def test_invalid_shtc1_type(self) -> None:
        """Non-dict SHTC1 returns None."""
        sm = StateManager()
        result = sm._extract_peripheral_humidity({"SensorInputs": {"SHTC1": "not_a_dict"}})
        assert result is None

    def test_shtc1_missing_humidity_key(self) -> None:
        """Line 173: SHTC1 dict exists but has no RelativeHumidity_pc key."""
        sm = StateManager()
        result = sm._extract_peripheral_humidity(
            {"SensorInputs": {"SHTC1": {"Temperature_oC": 22.5}}}
        )
        assert result is None

    def test_non_numeric_humidity(self) -> None:
        """Lines 177-178: Non-numeric humidity returns None."""
        sm = StateManager()
        result = sm._extract_peripheral_humidity(
            {"SensorInputs": {"SHTC1": {"RelativeHumidity_pc": "fifty"}}}
        )
        assert result is None

    def test_humidity_out_of_range_high(self) -> None:
        """Lines 179-180: Humidity > 100 returns None."""
        sm = StateManager()
        result = sm._extract_peripheral_humidity(
            {"SensorInputs": {"SHTC1": {"RelativeHumidity_pc": 150.0}}}
        )
        assert result is None

    def test_humidity_out_of_range_negative(self) -> None:
        """Lines 179-180: Negative humidity returns None."""
        sm = StateManager()
        result = sm._extract_peripheral_humidity(
            {"SensorInputs": {"SHTC1": {"RelativeHumidity_pc": -5.0}}}
        )
        assert result is None


# ---------------------------------------------------------------------------
# actron.py – _flush_task_done callback (lines 99, 102)
# ---------------------------------------------------------------------------


class TestFlushTaskDoneCallback:
    """Test CommandCoalescer._flush_task_done static method."""

    @pytest.mark.asyncio
    async def test_flush_task_done_logs_exception(self) -> None:
        """Task that raised an exception is logged via _LOGGER.error."""

        async def _raise() -> None:
            raise RuntimeError("boom")

        task: asyncio.Task[None] = asyncio.get_running_loop().create_task(_raise())
        await asyncio.sleep(0)  # let task complete

        with patch("actron_neo_api.actron._LOGGER") as mock_logger:
            CommandCoalescer._flush_task_done(task)
            mock_logger.error.assert_called_once()
            assert "Command flush failed" in mock_logger.error.call_args.args[0]

    @pytest.mark.asyncio
    async def test_flush_task_done_cancelled_noop(self) -> None:
        """Cancelled task returns without logging."""
        task: asyncio.Task[None] = asyncio.get_running_loop().create_task(asyncio.sleep(10))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        with patch("actron_neo_api.actron._LOGGER") as mock_logger:
            CommandCoalescer._flush_task_done(task)
            mock_logger.error.assert_not_called()


# ---------------------------------------------------------------------------
# actron.py – _make_request 204 response (line 597)
# ---------------------------------------------------------------------------


class TestMakeRequest204Response:
    """Test _make_request returns empty dict for 204 No Content."""

    @pytest.mark.asyncio
    async def test_204_returns_empty_dict(self) -> None:
        """204 response returns {} without calling response.json()."""
        api = ActronAirAPI(refresh_token="test_refresh")
        api._initialized = True
        api.oauth2_auth.access_token = "valid_token"
        api.oauth2_auth.token_expiry = time.monotonic() + 3600

        mock_response = AsyncMock()
        mock_response.status = 204
        mock_response.json = AsyncMock()

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)

        session = MagicMock()
        session.closed = False
        session.request = MagicMock(return_value=mock_ctx)
        api._session = session

        result = await api._make_request("delete", "some/endpoint")

        assert result == {}
        mock_response.json.assert_not_called()
