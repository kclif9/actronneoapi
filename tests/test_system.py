"""Additional tests for system model methods."""

from typing import Any

import pytest

from actron_neo_api.models import ActronAirStatus
from actron_neo_api.models.system import (
    ActronAirACSystem,
    ActronAirIndoorUnit,
    ActronAirLiveAircon,
    ActronAirOutdoorUnit,
)


@pytest.fixture
def ac_system_with_api(mock_api: Any) -> ActronAirACSystem:
    """Create AC system with API reference."""
    status = ActronAirStatus(
        isOnline=True,
        lastKnownState={
            "AirconSystem": {
                "MasterSerial": "TEST123",
                "CanOperate": True,
            }
        },
        serial_number="TEST123",
    )
    status.parse_nested_components()
    status.set_api(mock_api)
    # We know ac_system is not None after parse_nested_components
    assert status.ac_system is not None
    return status.ac_system


class TestACSystemSetMode:
    """Test ACSystem set_mode method."""

    @pytest.mark.asyncio
    async def test_set_mode_to_cool(
        self, ac_system_with_api: ActronAirACSystem, mock_api: Any
    ) -> None:
        """Test setting AC mode to COOL."""
        result = await ac_system_with_api.set_system_mode("COOL")

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.isOn"] is True
        assert mock_api.last_command["command"]["UserAirconSettings.Mode"] == "COOL"

    @pytest.mark.asyncio
    async def test_set_mode_to_off(
        self, ac_system_with_api: ActronAirACSystem, mock_api: Any
    ) -> None:
        """Test setting AC mode to OFF."""
        result = await ac_system_with_api.set_system_mode("OFF")

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.isOn"] is False
        # Mode should not be set when turning off
        assert "UserAirconSettings.Mode" not in mock_api.last_command["command"]

    @pytest.mark.asyncio
    async def test_set_mode_without_api(self) -> None:
        """Test set_mode without API reference raises ValueError."""
        # Create AC system without API
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "AirconSystem": {
                    "MasterSerial": "TEST123",
                    "CanOperate": True,
                }
            },
        )
        status.parse_nested_components()
        # Don't set API

        assert status.ac_system is not None
        with pytest.raises(ValueError, match="No API reference available"):
            await status.ac_system.set_system_mode("COOL")

    @pytest.mark.asyncio
    async def test_set_mode_without_parent(self) -> None:
        """Test set_mode without parent status raises ValueError."""
        ac_system = ActronAirACSystem(master_serial="TEST123")

        with pytest.raises(ValueError, match="No API reference available"):
            await ac_system.set_system_mode("HEAT")


# ---------------------------------------------------------------------------
# ActronAirIndoorUnit
# ---------------------------------------------------------------------------
class TestActronAirIndoorUnit:
    """Tests for the ActronAirIndoorUnit model."""

    def test_default_values(self) -> None:
        """All fields should have sensible defaults."""
        unit = ActronAirIndoorUnit()
        assert unit.nv_auto_fan_enabled is False
        assert unit.nv_supported_fan_modes == 0
        assert unit.nv_model_number is None

    def test_from_alias(self) -> None:
        """Model should parse API JSON keys (aliases)."""
        data = {
            "NV_AutoFanEnabled": True,
            "NV_SupportedFanModes": 15,
            "NV_ModelNumber": "IU-7.1kW",
        }
        unit = ActronAirIndoorUnit.model_validate(data)
        assert unit.nv_auto_fan_enabled is True
        assert unit.nv_supported_fan_modes == 15
        assert unit.nv_model_number == "IU-7.1kW"

    def test_supported_fan_mode_list_all(self) -> None:
        """Bitmap 15 = LOW | MED | HIGH | AUTO."""
        unit = ActronAirIndoorUnit(nv_supported_fan_modes=15)
        assert unit.supported_fan_mode_list == ["LOW", "MED", "HIGH", "AUTO"]

    def test_supported_fan_mode_list_low_high(self) -> None:
        """Bitmap 5 = LOW | HIGH."""
        unit = ActronAirIndoorUnit(nv_supported_fan_modes=5)
        assert unit.supported_fan_mode_list == ["LOW", "HIGH"]

    def test_supported_fan_mode_list_none(self) -> None:
        """Bitmap 0 = no supported modes."""
        unit = ActronAirIndoorUnit(nv_supported_fan_modes=0)
        assert unit.supported_fan_mode_list == []

    def test_supported_fan_mode_list_auto_only(self) -> None:
        """Bitmap 8 = AUTO only."""
        unit = ActronAirIndoorUnit(nv_supported_fan_modes=8)
        assert unit.supported_fan_mode_list == ["AUTO"]


# ---------------------------------------------------------------------------
# ActronAirOutdoorUnit — new fields
# ---------------------------------------------------------------------------
class TestActronAirOutdoorUnitNewFields:
    """Tests for the new ActronAirOutdoorUnit fields."""

    def test_defaults(self) -> None:
        """New fields should have correct defaults."""
        unit = ActronAirOutdoorUnit()
        assert unit.capacity_kw is None
        assert unit.supply_voltage_vac is None
        assert unit.supply_current_rms_a is None
        assert unit.supply_power_rms_w is None
        assert unit.coil_temp is None
        assert unit.reverse_valve_position is None
        assert unit.defrost_mode is None
        assert unit.drm is None
        assert unit.err_code_1 == 0
        assert unit.err_code_2 == 0
        assert unit.err_code_3 == 0
        assert unit.err_code_4 == 0
        assert unit.err_code_5 == 0

    def test_from_api_aliases(self) -> None:
        """Verify API JSON key mapping (including typos in real API)."""
        data = {
            "Capacity_kW": 7.1,
            "SupplyVoltage_Vac": 240.5,
            "SuppyCurrentRMS_A": 12.3,  # API typo
            "SuppyPowerRMS_W": 2950.0,  # API typo
            "CoilTemp": 8.5,
            "ReverseValvePosition": "cooling",
            "DefrostMode": 0,
            "DRM": False,
            "ErrCode_1": 1,
            "ErrCode_2": 2,
            "ErrCode_3": 3,
            "ErrCode_4": 4,
            "ErrCode_5": 5,
        }
        unit = ActronAirOutdoorUnit.model_validate(data)
        assert unit.capacity_kw == 7.1
        assert unit.supply_voltage_vac == 240.5
        assert unit.supply_current_rms_a == 12.3
        assert unit.supply_power_rms_w == 2950.0
        assert unit.coil_temp == 8.5
        assert unit.reverse_valve_position == "cooling"
        assert unit.defrost_mode == 0
        assert unit.drm is False
        assert unit.err_code_1 == 1
        assert unit.err_code_5 == 5


# ---------------------------------------------------------------------------
# ActronAirLiveAircon — new fields
# ---------------------------------------------------------------------------
class TestActronAirLiveAirconNewFields:
    """Tests for the new ActronAirLiveAircon fields."""

    def test_defaults(self) -> None:
        """New fields should have correct defaults."""
        live = ActronAirLiveAircon()
        assert live.am_running_fan is False
        assert live.fan_pwm == 0
        assert live.coil_inlet is None
        assert live.err_code == 0

    def test_from_api_aliases(self) -> None:
        """Verify alias mapping."""
        data = {
            "AmRunningFan": True,
            "FanPWM": 80,
            "CoilInlet": 12.5,
            "ErrCode": 42,
        }
        live = ActronAirLiveAircon.model_validate(data)
        assert live.am_running_fan is True
        assert live.fan_pwm == 80
        assert live.coil_inlet == 12.5
        assert live.err_code == 42


# ---------------------------------------------------------------------------
# ActronAirACSystem — indoor_unit field
# ---------------------------------------------------------------------------
class TestActronAirACSystemIndoorUnit:
    """Tests for the indoor_unit field on ActronAirACSystem."""

    def test_default_is_none(self) -> None:
        """indoor_unit defaults to None."""
        system = ActronAirACSystem()
        assert system.indoor_unit is None

    def test_parsed_from_dict(self) -> None:
        """indoor_unit should be parsed from nested dict."""
        data = {
            "MasterSerial": "ABC123",
            "IndoorUnit": {
                "NV_AutoFanEnabled": True,
                "NV_SupportedFanModes": 7,
                "NV_ModelNumber": "ESP-7.1kW",
            },
        }
        system = ActronAirACSystem.model_validate(data)
        assert system.indoor_unit is not None
        assert system.indoor_unit.nv_auto_fan_enabled is True
        assert system.indoor_unit.nv_supported_fan_modes == 7
        assert system.indoor_unit.nv_model_number == "ESP-7.1kW"
        assert system.indoor_unit.supported_fan_mode_list == ["LOW", "MED", "HIGH"]
