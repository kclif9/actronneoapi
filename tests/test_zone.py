"""Tests for zone async command methods."""

from typing import Any

import pytest

from actron_neo_api.exceptions import ActronAirAPIError
from actron_neo_api.models import ActronAirStatus, ActronAirZone
from actron_neo_api.models.zone import ActronAirZoneSensor


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
                "TemperatureSetpoint_Cool_oC": 24.0,
                "ZoneTemperatureSetpointVariance_oC": 3.0,
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
            "UserAirconSettings": {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "EnabledZones": [True, False, False],
                "TemperatureSetpoint_Cool_oC": 24.0,
                "ZoneTemperatureSetpointVariance_oC": 3.0,
            },
            "RemoteZoneInfo": [
                {
                    "ZoneNumber": 0,
                    "LiveTemp_oC": 22.0,
                    "EnabledZone": True,
                    "CanOperate": True,
                }
            ],
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
    async def test_set_temperature_without_api(self, zone_without_api: ActronAirZone) -> None:
        """Test setting temperature without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await zone_without_api.set_temperature(24.0)

    @pytest.mark.asyncio
    async def test_set_temperature_raises_in_fan_mode(self, zone_with_api: ActronAirZone) -> None:
        """Test setting temperature in FAN mode raises ValueError."""
        zone_with_api._parent_status.user_aircon_settings.mode = "FAN"
        with pytest.raises(ValueError, match="Cannot set temperature in FAN mode"):
            await zone_with_api.set_temperature(22.0)

    @pytest.mark.asyncio
    async def test_set_temperature_raises_in_off_mode(self, zone_with_api: ActronAirZone) -> None:
        """Test setting temperature in OFF mode raises ValueError."""
        zone_with_api._parent_status.user_aircon_settings.mode = "OFF"
        with pytest.raises(ValueError, match="Cannot set temperature in OFF mode"):
            await zone_with_api.set_temperature(22.0)


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
    async def test_enable_without_api(self, zone_without_api: ActronAirZone) -> None:
        """Test enabling without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
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
            zone_id=0,
            zone_number=0,
            live_temp_c=22.0,
            enabled_zone=True,
            can_operate=True,
        )

        with pytest.raises(RuntimeError, match="Zone must be attached to a parent status"):
            zone.set_enable_command(True)

    def test_set_enable_command_empty_enabled_zones(self) -> None:
        """Test set_enable_command when enabled_zones is empty (no real data parsed)."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "RemoteZoneInfo": [
                    {"LiveTemp_oC": 22.0, "CanOperate": True},
                ],
            },
        )
        zone = status.remote_zone_info[0]

        with pytest.raises(ValueError, match="No enabled zones available"):
            zone.set_enable_command(True)

    def test_set_temperature_command_empty_mode(self) -> None:
        """Test set_temperature_command when mode is empty (no real data parsed)."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "RemoteZoneInfo": [
                    {"LiveTemp_oC": 22.0, "CanOperate": True},
                ],
            },
        )
        zone = status.remote_zone_info[0]

        with pytest.raises(ValueError, match="No AC mode available"):
            zone.set_temperature_command(22.0)


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
                    "ZoneTemperatureSetpointVariance_oC": 3.0,
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


class TestZoneTempLimitsHeatMode:
    """Test max_temp/min_temp use heat setpoint/limits when mode is HEAT."""

    @staticmethod
    def _make_zone_with_state(last_known_state: dict[str, Any]) -> ActronAirZone:
        """Create a zone with the given last_known_state."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState=last_known_state,
        )
        return status.remote_zone_info[0]

    def test_max_temp_heat_mode_uses_heat_limits(self) -> None:
        """max_temp uses setHeat_Max and heat setpoint in HEAT mode."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Min": 18.0,
                        "setCool_Max": 30.0,
                        "setHeat_Min": 14.0,
                        "setHeat_Max": 26.0,
                    }
                },
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "HEAT",
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Heat_oC": 20.0,
                    "TemperatureSetpoint_Cool_oC": 26.0,
                    "ZoneTemperatureSetpointVariance_oC": 2.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 20.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Heat mode: target=20, variance=2 → 22.0; max_setpoint=26 → min(26, 22)=22
        assert zone.max_temp == 22.0

    def test_min_temp_heat_mode_uses_heat_limits(self) -> None:
        """min_temp uses setHeat_Min and heat setpoint in HEAT mode."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Min": 18.0,
                        "setCool_Max": 30.0,
                        "setHeat_Min": 14.0,
                        "setHeat_Max": 26.0,
                    }
                },
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "HEAT",
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Heat_oC": 20.0,
                    "TemperatureSetpoint_Cool_oC": 26.0,
                    "ZoneTemperatureSetpointVariance_oC": 2.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 20.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Heat mode: target=20, variance=2 → 18.0; min_setpoint=14 → max(14, 18)=18
        assert zone.min_temp == 18.0

    def test_min_temp_heat_mode_clamped_by_limit(self) -> None:
        """min_temp clamps to setHeat_Min when variance goes below it."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setHeat_Min": 19.0,
                        "setHeat_Max": 26.0,
                    }
                },
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "HEAT",
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Heat_oC": 20.0,
                    "ZoneTemperatureSetpointVariance_oC": 2.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 20.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Heat mode: target=20, variance=2 → 18.0; but min_setpoint=19 → clamps to 19
        assert zone.min_temp == 19.0

    def test_max_temp_heat_mode_clamped_by_limit(self) -> None:
        """max_temp clamps to setHeat_Max when variance exceeds it."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setHeat_Min": 14.0,
                        "setHeat_Max": 21.0,
                    }
                },
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "HEAT",
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Heat_oC": 20.0,
                    "ZoneTemperatureSetpointVariance_oC": 2.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 20.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Heat mode: target=20, variance=2 → 22; but max_setpoint=21 → clamps to 21
        assert zone.max_temp == 21.0

    def test_cool_mode_ignores_heat_limits(self) -> None:
        """In COOL mode, heat limits do not affect min/max_temp."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Min": 18.0,
                        "setCool_Max": 30.0,
                        "setHeat_Min": 14.0,
                        "setHeat_Max": 26.0,
                    }
                },
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "TemperatureSetpoint_Heat_oC": 20.0,
                    "ZoneTemperatureSetpointVariance_oC": 2.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Cool mode: target=24, variance=2 → max=26, min=22; limited by 30/18
        assert zone.max_temp == 26.0
        assert zone.min_temp == 22.0

    def test_heat_mode_defaults_when_limits_missing(self) -> None:
        """Heat mode uses Pydantic defaults when NV_Limits missing."""
        zone = self._make_zone_with_state(
            {
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "HEAT",
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Heat_oC": 22.0,
                    "ZoneTemperatureSetpointVariance_oC": 3.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 20.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        # Heat mode: target=22, variance=3 → max=25, min=19
        # max_setpoint default=30, min_setpoint default=16
        assert zone.max_temp == 25.0
        assert zone.min_temp == 19.0

    def test_auto_mode_uses_cool_limits(self) -> None:
        """AUTO mode uses cool limits, same as COOL."""
        zone = self._make_zone_with_state(
            {
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Min": 18.0,
                        "setCool_Max": 30.0,
                        "setHeat_Min": 14.0,
                        "setHeat_Max": 26.0,
                    }
                },
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "AUTO",
                    "EnabledZones": [True],
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "ZoneTemperatureSetpointVariance_oC": 2.0,
                },
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True}
                ],
            }
        )
        assert zone.max_temp == 26.0
        assert zone.min_temp == 22.0


class TestZoneSensorAliasParsing:
    """Test that ZoneSensor fields parse from API aliases correctly."""

    def test_signal_strength_parses_from_alias(self) -> None:
        """signal_strength correctly parses from Signal_of3 alias."""
        sensor = ActronAirZoneSensor.model_validate(
            {"Signal_of3": "3", "Connected": True, "NV_Kind": "Wireless"}
        )
        assert sensor.signal_strength == "3"

    def test_signal_strength_default_when_missing(self) -> None:
        """signal_strength defaults to 'NA' when not in data."""
        sensor = ActronAirZoneSensor.model_validate({})
        assert sensor.signal_strength == "NA"


class TestZoneCapabilityFields:
    """Test zone capability fields parse from API aliases correctly."""

    @staticmethod
    def _make_zone(zone_data: dict[str, Any]) -> ActronAirZone:
        """Create a zone with the given RemoteZoneInfo data."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "EnabledZones": [True],
                },
                "RemoteZoneInfo": [zone_data],
            },
        )
        return status.remote_zone_info[0]

    def test_capabilities_parse_from_aliases(self) -> None:
        """Zone capability fields parse from their NV_ aliases."""
        zone = self._make_zone(
            {
                "LiveTemp_oC": 22.0,
                "CanOperate": True,
                "NV_VAV": True,
                "NV_ITC": True,
                "NV_ITD": True,
                "NV_IHD": True,
                "NV_IAC": True,
            }
        )
        assert zone.variable_air_volume is True
        assert zone.individual_temperature_control is True
        assert zone.individual_temperature_deadband is True
        assert zone.integrated_humidity_tracking is True
        assert zone.indoor_air_compensation is True

    def test_capabilities_default_to_false(self) -> None:
        """Zone capability fields default to False when not present."""
        zone = self._make_zone({"LiveTemp_oC": 22.0, "CanOperate": True})
        assert zone.variable_air_volume is False
        assert zone.individual_temperature_control is False
        assert zone.individual_temperature_deadband is False
        assert zone.integrated_humidity_tracking is False
        assert zone.indoor_air_compensation is False

    def test_mixed_capabilities(self) -> None:
        """Capabilities can be independently set."""
        zone = self._make_zone(
            {
                "LiveTemp_oC": 22.0,
                "CanOperate": True,
                "NV_IHD": True,
                "NV_VAV": False,
            }
        )
        assert zone.variable_air_volume is False
        assert zone.individual_temperature_control is False
        assert zone.integrated_humidity_tracking is True
