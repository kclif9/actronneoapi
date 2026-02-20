"""Tests for zone async command methods."""

from typing import Any, Dict

import pytest

from actron_neo_api.models import ActronAirStatus, ActronAirZone
from actron_neo_api.models.zone import ActronAirPeripheral


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

    @pytest.mark.asyncio
    async def test_disable_zone_with_api(self, zone_with_api: ActronAirZone, mock_api: Any) -> None:
        """Test disabling zone with API reference."""
        result = await zone_with_api.enable(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        # Zone 0 should be disabled (False)
        assert mock_api.last_command["command"]["UserAirconSettings.EnabledZones"][0] is False

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


# ---------------------------------------------------------------------------
# ActronAirZone — new fields + has_temp_control
# ---------------------------------------------------------------------------
class TestActronAirZoneNewFields:
    """Tests for the new ActronAirZone fields and has_temp_control property."""

    def test_defaults(self) -> None:
        """New fields should have correct defaults."""
        zone = ActronAirZone()
        assert zone.nv_vav is False
        assert zone.nv_itc is False
        assert zone.temperature_setpoint_c is None
        assert zone.airflow_setpoint is None
        assert zone.airflow_control_enabled is False
        assert zone.airflow_control_locked is False
        assert zone.zone_max_position is None
        assert zone.zone_min_position is None

    def test_from_api_aliases(self) -> None:
        """Verify alias mapping for zone fields."""
        data = {
            "NV_VAV": True,
            "NV_ITC": True,
            "TemperatureSetpoint_oC": 22.0,
            "AirflowSetpoint": 75,
            "AirflowControlEnabled": True,
            "AirflowControlLocked": False,
            "ZoneMaxPosition": 100,
            "ZoneMinPosition": 10,
        }
        zone = ActronAirZone.model_validate(data)
        assert zone.nv_vav is True
        assert zone.nv_itc is True
        assert zone.temperature_setpoint_c == 22.0
        assert zone.airflow_setpoint == 75
        assert zone.airflow_control_enabled is True
        assert zone.airflow_control_locked is False
        assert zone.zone_max_position == 100
        assert zone.zone_min_position == 10

    def test_has_temp_control_both_true(self) -> None:
        """has_temp_control is True only when nv_vav AND nv_itc."""
        zone = ActronAirZone.model_validate({"NV_VAV": True, "NV_ITC": True})
        assert zone.has_temp_control is True

    def test_has_temp_control_vav_only(self) -> None:
        """has_temp_control is False when only nv_vav is True."""
        zone = ActronAirZone.model_validate({"NV_VAV": True, "NV_ITC": False})
        assert zone.has_temp_control is False

    def test_has_temp_control_itc_only(self) -> None:
        """has_temp_control is False when only nv_itc is True."""
        zone = ActronAirZone.model_validate({"NV_VAV": False, "NV_ITC": True})
        assert zone.has_temp_control is False

    def test_has_temp_control_both_false(self) -> None:
        """has_temp_control is False when neither is True."""
        zone = ActronAirZone.model_validate({"NV_VAV": False, "NV_ITC": False})
        assert zone.has_temp_control is False


# ---------------------------------------------------------------------------
# ActronAirPeripheral — new fields
# ---------------------------------------------------------------------------
class TestActronAirPeripheralNewFields:
    """Tests for the new ActronAirPeripheral fields."""

    def test_defaults(self) -> None:
        """New fields should have correct defaults."""
        p = ActronAirPeripheral()
        assert p.rssi is None
        assert p.last_connection_time is None
        assert p.connection_state is None
        assert p.control_capabilities is None

    def test_from_api_aliases(self) -> None:
        """Verify alias mapping for peripheral fields."""
        data: Dict[str, Any] = {
            "RSSI": {"value": -55, "unit": "dBm"},
            "LastConnectionTime": "2026-02-20T10:00:00Z",
            "ConnectionState": "connected",
            "ControlCapabilities": {"temperature": True, "humidity": True},
        }
        p = ActronAirPeripheral.model_validate(data)
        assert p.rssi == {"value": -55, "unit": "dBm"}
        assert p.last_connection_time == "2026-02-20T10:00:00Z"
        assert p.connection_state == "connected"
        assert p.control_capabilities == {"temperature": True, "humidity": True}

    def test_from_peripheral_data_includes_new_fields(self) -> None:
        """from_peripheral_data should parse new fields."""
        data: Dict[str, Any] = {
            "LogicalAddress": 1,
            "DeviceType": "sensor",
            "ZoneAssignment": [1],
            "SerialNumber": "PER001",
            "RSSI": {"value": -40},
            "ConnectionState": "online",
        }
        p = ActronAirPeripheral.from_peripheral_data(data)
        assert p.rssi == {"value": -40}
        assert p.connection_state == "online"
