"""Tests for zone async command methods."""

from typing import Any

import pytest

from actron_neo_api.exceptions import ActronAirAPIError
from actron_neo_api.models import ActronAirStatus, ActronAirZone


@pytest.fixture
def zone_with_api(mock_api: Any) -> ActronAirZone:
    """Create zone object with API reference."""
    status = ActronAirStatus(
        isOnline=True,
        lastKnownState={
            "UserAirconSettings": {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "SetPoint": 22.0,
                "EnabledZones": [True, True, False],
            },
            "RemoteZoneInfo": [
                {
                    "ZoneNumber": 0,
                    "LiveTemp_oC": 22.0,
                    "EnabledZone": True,
                    "CanOperate": True,
                },
                {
                    "ZoneNumber": 1,
                    "LiveTemp_oC": 23.0,
                    "EnabledZone": True,
                    "CanOperate": True,
                },
                {
                    "ZoneNumber": 2,
                    "LiveTemp_oC": 24.0,
                    "EnabledZone": False,
                    "CanOperate": True,
                },
            ],
            "NV_Limits": {
                "UserSetpoint_oC": {
                    "setCool_Min": 18.0,
                    "setCool_Max": 30.0,
                }
            },
        },
        serial_number="TEST123",
    )
    status.parse_nested_components()
    status.set_api(mock_api)
    return status.remote_zone_info[0]


@pytest.fixture
def zone_without_api() -> ActronAirZone:
    """Create zone object without API reference."""
    status = ActronAirStatus(
        isOnline=True,
        lastKnownState={
            "RemoteZoneInfo": [
                {
                    "ZoneNumber": 0,
                    "LiveTemp_oC": 22.0,
                    "EnabledZone": True,
                    "CanOperate": True,
                }
            ]
        },
    )
    status.parse_nested_components()
    return status.remote_zone_info[0]


class TestZoneAsyncSetTemperature:
    """Test async set_temperature method."""

    @pytest.mark.asyncio
    async def test_set_temperature_with_api(
        self, zone_with_api: ActronAirZone, mock_api: Any
    ) -> None:
        """Test setting zone temperature with API reference."""
        result = await zone_with_api.set_temperature(24.0)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["type"] == "set-settings"

        # Optimistic local state update (mode is COOL)
        assert zone_with_api.temperature_setpoint_cool_c == 24.0

    @pytest.mark.asyncio
    async def test_set_temperature_clamps_to_limits(
        self, zone_with_api: ActronAirZone, mock_api: Any
    ) -> None:
        """Test temperature clamping to zone limits."""
        # Try to set below minimum
        result = await zone_with_api.set_temperature(10.0)
        assert result is None  # Commands return None on success
        # Command should be sent successfully
        assert mock_api.last_command is not None

        # Try to set above maximum
        result = await zone_with_api.set_temperature(35.0)
        assert result is None  # Commands return None on success
        assert mock_api.last_command is not None

    @pytest.mark.asyncio
    async def test_set_temperature_without_zone_id(self) -> None:
        """Test setting temperature without zone_id raises."""
        zone = ActronAirZone(
            zone_number=0,
            live_temp_c=22.0,
            enabled_zone=True,
            can_operate=True,
        )

        with pytest.raises(ValueError, match="Zone index not set"):
            await zone.set_temperature(24.0)

    @pytest.mark.asyncio
    async def test_set_temperature_without_api(self, zone_without_api: ActronAirZone) -> None:
        """Test setting temperature without API reference raises."""
        with pytest.raises(ValueError, match="No parent AC status available"):
            await zone_without_api.set_temperature(24.0)


class TestZoneAsyncEnable:
    """Test async enable method."""

    @pytest.mark.asyncio
    async def test_enable_zone_with_api(self, zone_with_api: ActronAirZone, mock_api: Any) -> None:
        """Test enabling zone with API reference."""
        result = await zone_with_api.enable(True)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["type"] == "set-settings"
        # Zone 0 should be enabled (True)
        assert mock_api.last_command["command"]["UserAirconSettings.EnabledZones"][0] is True

        # Optimistic local state update
        assert zone_with_api._parent_status.user_aircon_settings.enabled_zones[0] is True

    @pytest.mark.asyncio
    async def test_disable_zone_with_api(self, zone_with_api: ActronAirZone, mock_api: Any) -> None:
        """Test disabling zone with API reference."""
        result = await zone_with_api.enable(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        # Zone 0 should be disabled (False)
        assert mock_api.last_command["command"]["UserAirconSettings.EnabledZones"][0] is False

        # Optimistic local state update
        assert zone_with_api._parent_status.user_aircon_settings.enabled_zones[0] is False

    @pytest.mark.asyncio
    async def test_enable_without_zone_id(self) -> None:
        """Test enabling without zone_id raises."""
        zone = ActronAirZone(
            zone_number=0,
            live_temp_c=22.0,
            enabled_zone=True,
            can_operate=True,
        )

        with pytest.raises(ValueError, match="Zone index not set"):
            await zone.enable(True)

    @pytest.mark.asyncio
    async def test_enable_without_api(self, zone_without_api: ActronAirZone) -> None:
        """Test enabling without API reference raises."""
        with pytest.raises(ValueError, match="No parent AC status available"):
            await zone_without_api.enable(True)


class TestZoneSetEnableCommand:
    """Test set_enable_command method edge cases."""

    def test_set_enable_command_out_of_range(self, zone_with_api: ActronAirZone) -> None:
        """Test set_enable_command with zone_id out of range."""
        # Manually set zone_id to invalid value
        zone_with_api.zone_id = 10  # Out of range (only 3 zones)

        with pytest.raises(ValueError, match="Zone index .* out of range"):
            zone_with_api.set_enable_command(True)

    def test_set_enable_command_without_parent(self) -> None:
        """Test set_enable_command without parent status."""
        zone = ActronAirZone(
            zone_number=0,
            live_temp_c=22.0,
            enabled_zone=True,
            can_operate=True,
        )
        zone.zone_id = 0  # Set zone_id but no parent

        with pytest.raises(ValueError, match="No parent AC status available"):
            zone.set_enable_command(True)


class TestZoneOptimisticStateNotUpdatedOnError:
    """Verify zone optimistic state is NOT updated when send_command raises."""

    @pytest.fixture
    def zone_with_failing_api(self) -> ActronAirZone:
        """Create zone with an API that raises on send_command."""

        class FailingAPI:
            async def send_command(self, serial_number: str, command: dict[str, Any]) -> None:
                raise ActronAirAPIError("API error")

        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "FanMode": "AUTO",
                    "EnabledZones": [True, True, False],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "TemperatureSetpoint_Heat_oC": 20.0,
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                        "TemperatureSetpoint_Cool_oC": 24.0,
                        "TemperatureSetpoint_Heat_oC": 20.0,
                    },
                ],
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Min": 18.0,
                        "setCool_Max": 30.0,
                    }
                },
            },
            serial_number="TEST123",
        )
        status.parse_nested_components()
        status.set_api(FailingAPI())
        return status.remote_zone_info[0]

    @pytest.mark.asyncio
    async def test_enable_not_updated_on_error(self, zone_with_failing_api: ActronAirZone) -> None:
        """Enabled zones unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await zone_with_failing_api.enable(False)
        assert zone_with_failing_api._parent_status.user_aircon_settings.enabled_zones[0] is True

    @pytest.mark.asyncio
    async def test_temperature_not_updated_on_error(
        self, zone_with_failing_api: ActronAirZone
    ) -> None:
        """Temperature unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await zone_with_failing_api.set_temperature(28.0)
        assert zone_with_failing_api.temperature_setpoint_cool_c == 24.0


class TestZoneOptimisticAutoMode:
    """Test zone optimistic state for AUTO mode temperature."""

    @pytest.fixture
    def zone_auto_mode(self) -> ActronAirZone:
        """Create zone with AUTO mode settings."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "AUTO",
                    "FanMode": "AUTO",
                    "EnabledZones": [True, True, False],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "TemperatureSetpoint_Heat_oC": 20.0,
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                        "TemperatureSetpoint_Cool_oC": 24.0,
                        "TemperatureSetpoint_Heat_oC": 20.0,
                    },
                ],
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Min": 18.0,
                        "setCool_Max": 30.0,
                    }
                },
            },
            serial_number="TEST123",
        )
        status.parse_nested_components()

        class MockAPI:
            async def send_command(
                self, serial_number: str, command: dict[str, Any]
            ) -> dict[str, Any]:
                return {"success": True}

        status.set_api(MockAPI())
        return status.remote_zone_info[0]

    @pytest.mark.asyncio
    async def test_set_temperature_auto_mode(self, zone_auto_mode: ActronAirZone) -> None:
        """Setting temperature in AUTO mode updates both cool and heat setpoints."""
        await zone_auto_mode.set_temperature(26.0)

        assert zone_auto_mode.temperature_setpoint_cool_c == 26.0
        assert zone_auto_mode.temperature_setpoint_heat_c == 22.0

    @pytest.mark.asyncio
    async def test_set_temperature_heat_mode(self, zone_auto_mode: ActronAirZone) -> None:
        """Setting temperature in HEAT mode updates heat setpoint only."""
        zone_auto_mode._parent_status.user_aircon_settings.mode = "HEAT"
        await zone_auto_mode.set_temperature(22.0)

        assert zone_auto_mode.temperature_setpoint_heat_c == 22.0


class TestZoneTempLimitsFallback:
    """Test max_temp/min_temp fallback when API returns non-numeric values."""

    @staticmethod
    def _make_zone_with_state(last_known_state: dict[str, Any]) -> ActronAirZone:
        """Create a zone with the given last_known_state."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState=last_known_state,
        )
        status.parse_nested_components()
        return status.remote_zone_info[0]

    def test_max_temp_non_numeric_setpoint(self) -> None:
        """max_temp uses default setpoint (30.0) when setCool_Max is non-numeric."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {"UserSetpoint_oC": {"setCool_Max": "not_a_number"}},
                "UserAirconSettings": {"EnabledZones": [True]},
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # max_setpoint defaults to 30.0, target defaults to 24.0, variance to 3.0
        # target + variance = 27 < max_setpoint (30), so returns 27
        assert zone.max_temp == 27.0

    def test_min_temp_non_numeric_setpoint(self) -> None:
        """min_temp uses default setpoint (16.0) when setCool_Min is non-numeric."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {"UserSetpoint_oC": {"setCool_Min": "bad"}},
                "UserAirconSettings": {"EnabledZones": [True]},
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # min_setpoint defaults to 16.0, target defaults to 24.0, variance to 3.0
        # min_setpoint (16) < target - variance (21), so returns 21
        assert zone.min_temp == 21.0

    def test_max_temp_none_variance(self) -> None:
        """max_temp uses default variance (3.0) when variance is None."""
        zone = self._make_zone_with_state(
            {
                "UserAirconSettings": {
                    "EnabledZones": [True],
                    "ZoneTemperatureSetpointVariance_oC": None,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # max_setpoint defaults to 30.0, target defaults to 24.0, variance defaults to 3.0
        # target + variance = 27 < max_setpoint (30), so returns 27
        assert zone.max_temp == 27.0

    def test_min_temp_none_variance(self) -> None:
        """min_temp uses default variance (3.0) when variance is None."""
        zone = self._make_zone_with_state(
            {
                "UserAirconSettings": {
                    "EnabledZones": [True],
                    "ZoneTemperatureSetpointVariance_oC": None,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # min_setpoint defaults to 16.0, target defaults to 24.0, variance defaults to 3.0
        # min_setpoint (16) < target - variance (21), so returns 21
        assert zone.min_temp == 21.0

    def test_max_temp_bad_variance_preserves_valid_limit(self) -> None:
        """max_temp honors NV_Limits even when variance is non-numeric."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {"UserSetpoint_oC": {"setCool_Max": 25.0}},
                "UserAirconSettings": {
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "ZoneTemperatureSetpointVariance_oC": "bad",
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # target (24) + default variance (3) = 27 > max_setpoint (25), so clamps to 25
        assert zone.max_temp == 25.0

    def test_min_temp_bad_variance_preserves_valid_limit(self) -> None:
        """min_temp honors NV_Limits even when variance is non-numeric."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {"UserSetpoint_oC": {"setCool_Min": 22.0}},
                "UserAirconSettings": {
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "ZoneTemperatureSetpointVariance_oC": "bad",
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # target (24) - default variance (3) = 21 < min_setpoint (22), so clamps to 22
        assert zone.min_temp == 22.0

    def test_max_temp_bad_target_preserves_valid_limit(self) -> None:
        """max_temp honors NV_Limits even when target setpoint is non-numeric."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {"UserSetpoint_oC": {"setCool_Max": 25.0}},
                "UserAirconSettings": {
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "ZoneTemperatureSetpointVariance_oC": 3.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Inject bad value into last_known_state after Pydantic validation
        zone._parent_status.last_known_state["UserAirconSettings"][
            "TemperatureSetpoint_Cool_oC"
        ] = "bad"
        # default target (24) + variance (3) = 27 > max_setpoint (25), clamps to 25
        assert zone.max_temp == 25.0

    def test_min_temp_bad_target_preserves_valid_limit(self) -> None:
        """min_temp honors NV_Limits even when target setpoint is non-numeric."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {"UserSetpoint_oC": {"setCool_Min": 22.0}},
                "UserAirconSettings": {
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "ZoneTemperatureSetpointVariance_oC": 3.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Inject bad value into last_known_state after Pydantic validation
        zone._parent_status.last_known_state["UserAirconSettings"][
            "TemperatureSetpoint_Cool_oC"
        ] = "bad"
        # default target (24) - variance (3) = 21 < min_setpoint (22), clamps to 22
        assert zone.min_temp == 22.0
