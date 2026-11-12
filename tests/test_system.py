"""Additional tests for system model methods."""

from typing import Any

import pytest
from pydantic import ValidationError

from actron_neo_api.models import ActronAirStatus
from actron_neo_api.models.system import ActronAirACSystem, ActronAirEEV, ActronAirOutdoorUnit


@pytest.fixture
def ac_system_with_api(mock_api: Any) -> ActronAirACSystem:
    """Create AC system with API reference."""
    status = ActronAirStatus(
        isOnline=True,
        lastKnownState={
            "AirconSystem": {
                "MasterSerial": "TEST123",
                "CanOperate": True,
            },
            "UserAirconSettings": {
                "isOn": False,
                "Mode": "FAN",
                "FanMode": "AUTO",
                "EnabledZones": [True, False, False, False, False, False, False, False],
                "TemperatureSetpoint_Cool_oC": 24.0,
                "TemperatureSetpoint_Heat_oC": 20.0,
            },
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

        # Optimistic state update
        settings = ac_system_with_api._parent_status.user_aircon_settings
        assert settings is not None
        assert settings.is_on is True
        assert settings.mode == "COOL"

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

        # Optimistic state update
        settings = ac_system_with_api._parent_status.user_aircon_settings
        assert settings is not None
        assert settings.is_on is False

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

    @pytest.mark.asyncio
    async def test_set_mode_empty_serial_number(self, mock_api: Any) -> None:
        """Test set_mode with empty master_serial and no fallback raises ValueError."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "AirconSystem": {
                    "MasterSerial": "",
                    "CanOperate": True,
                }
            },
        )
        status.parse_nested_components()
        status.set_api(mock_api)

        assert status.ac_system is not None
        with pytest.raises(ValueError, match="No serial number available"):
            await status.ac_system.set_system_mode("COOL")

    @pytest.mark.asyncio
    async def test_set_mode_falls_back_to_status_serial(self, mock_api: Any) -> None:
        """Test set_mode uses status.serial_number when master_serial is empty."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "AirconSystem": {
                    "MasterSerial": "",
                    "CanOperate": True,
                },
                "UserAirconSettings": {
                    "isOn": False,
                    "Mode": "FAN",
                    "FanMode": "AUTO",
                },
            },
            serial_number="EXTERNAL123",
        )
        status.parse_nested_components()
        status.set_api(mock_api)

        assert status.ac_system is not None
        await status.ac_system.set_system_mode("COOL")

        assert mock_api.last_serial == "EXTERNAL123"


class TestOutdoorUnitAliasParsing:
    """Test that OutdoorUnit fields parse from API aliases correctly."""

    def test_model_number_parses_from_alias(self) -> None:
        """model_number correctly parses from ModelNumber alias."""
        unit = ActronAirOutdoorUnit.model_validate(
            {"ModelNumber": "ESP-PLUS-7", "SerialNumber": "SN123", "SoftwareVersion": "v2.1"}
        )
        assert unit.model_number == "ESP-PLUS-7"

    def test_software_version_parses_from_alias(self) -> None:
        """software_version correctly parses from SoftwareVersion alias."""
        unit = ActronAirOutdoorUnit.model_validate({"SoftwareVersion": "v3.5.1"})
        assert unit.software_version == "v3.5.1"

    def test_software_version_coerces_integer_value(self) -> None:
        """software_version accepts integer payloads and normalizes to string."""
        unit = ActronAirOutdoorUnit.model_validate({"SoftwareVersion": 0})
        assert unit.software_version == "0"

    def test_software_version_handles_none_value(self) -> None:
        """software_version normalizes explicit None payloads to empty string."""
        unit = ActronAirOutdoorUnit.model_validate({"SoftwareVersion": None})
        assert unit.software_version == ""

    def test_model_number_coerces_integer_value(self) -> None:
        """model_number accepts integer payloads (seen in the wild as 561)."""
        unit = ActronAirOutdoorUnit.model_validate({"ModelNumber": 561})
        assert unit.model_number == "561"

    def test_serial_number_coerces_integer_value(self) -> None:
        """serial_number accepts integer payloads and normalizes to string."""
        unit = ActronAirOutdoorUnit.model_validate({"SerialNumber": 12345})
        assert unit.serial_number == "12345"

    def test_family_coerces_integer_value(self) -> None:
        """family accepts integer payloads and normalizes to string."""
        unit = ActronAirOutdoorUnit.model_validate({"Family": 7})
        assert unit.family == "7"

    def test_identification_fields_handle_none_value(self) -> None:
        """Identification fields normalize explicit None payloads to empty string."""
        unit = ActronAirOutdoorUnit.model_validate(
            {"ModelNumber": None, "SerialNumber": None, "Family": None}
        )
        assert unit.model_number == ""
        assert unit.serial_number == ""
        assert unit.family == ""

    def test_non_scalar_identification_value_still_rejected(self) -> None:
        """Malformed non-numeric payloads are not silently stringified."""
        with pytest.raises(ValidationError):
            ActronAirOutdoorUnit.model_validate({"ModelNumber": [5, 6, 1]})

    def test_defaults_to_empty_when_missing(self) -> None:
        """Fields default to empty values when not in data."""
        unit = ActronAirOutdoorUnit.model_validate({})
        assert unit.model_number == ""
        assert unit.software_version == ""


class TestACSystemIdentificationParsing:
    """Test that ACSystem identification fields tolerate numeric payloads."""

    def test_identification_fields_coerce_integer_values(self) -> None:
        """Wall controller model, serial and firmware accept integer payloads."""
        system = ActronAirACSystem.model_validate(
            {"MasterWCModel": 561, "MasterSerial": 12345, "MasterWCFirmwareVersion": 23}
        )
        assert system.master_wc_model == "561"
        assert system.master_serial == "12345"
        assert system.master_wc_firmware_version == "23"

    def test_identification_fields_handle_none_value(self) -> None:
        """Explicit None payloads normalize to empty string."""
        system = ActronAirACSystem.model_validate(
            {"MasterWCModel": None, "MasterSerial": None, "MasterWCFirmwareVersion": None}
        )
        assert system.master_wc_model == ""
        assert system.master_serial == ""
        assert system.master_wc_firmware_version == ""

    def test_string_values_unchanged(self) -> None:
        """String payloads pass through unchanged."""
        system = ActronAirACSystem.model_validate(
            {"MasterWCModel": "NEO-W", "MasterSerial": "ABC1"}
        )
        assert system.master_wc_model == "NEO-W"
        assert system.master_serial == "ABC1"


# A running three-phase Advance outdoor unit (CRV240T), from the cloud push
# channel on 2026-11-12; identifiers removed.
ADVANCE_RUNNING_OUTDOOR = {
    "AmbTemp": 22.4,
    "AmbientSensErr": False,
    "CoilSenseErr": False,
    "CoilTemp": 38.7,
    "CompPower": 0,
    "CompRunningPWM": 97,
    "CompSpeed": 97.0,
    "CompressorOn": True,
    "CompressorSetSpeed": 97,
    "CondPc": 24.7,
    "DefrostMode": 0,
    "DischargeTemp": 68.3,
    "DriveTemp": 143.5,
    "EEV": {"Opening_pc": 214, "SuperHeat": 9.5, "SuperHeatRef": 9, "Type": "UKV"},
    "EXV": True,
    "EnvelopeProtection": False,
    "FanSpeed": 0,
    "HPErr": False,
    "LPErr": False,
    "ODFan": "NA",
    "OHP": {"StartTemp_oC": 0.0, "TargetCondTemp_oC": 0.0, "TargetLine": 0},
    "OilReturn": False,
    "OilReturnEnable": False,
    "OutputPowerRMS_W": 0.0,
    "OverheatProtection": False,
    "ReverseValvePosition": "Cool",
    "SuctP0": 7.1,
    "SuctTemp": 9.9,
    "SupplyCurrentRMS_A": 0.0,
    "SupplyPowerRMS_W": 0.0,
    "SupplyVoltage_Vac": 0.0,
    "VSDODUCommsStatus": "OK",
}


class TestOutdoorUnitDiagnostics:
    """Refrigerant-circuit and drive diagnostics on the outdoor unit."""

    def test_running_advance_unit_parses_all_diagnostics(self) -> None:
        """Every documented diagnostic from a running Advance unit is parsed."""
        unit = ActronAirOutdoorUnit.model_validate(ADVANCE_RUNNING_OUTDOOR)
        assert unit.suction_pressure == 7.1
        assert unit.condensing_pressure == 24.7
        assert unit.suction_temp == 9.9
        assert unit.discharge_temp == 68.3
        assert unit.coil_temp == 38.7
        assert unit.drive_temp == 143.5
        assert unit.compressor_set_speed == 97.0
        assert unit.defrost_mode == 0.0
        assert unit.supply_power == 0.0
        assert unit.eev is not None
        assert unit.eev.opening_pc == 214.0
        assert unit.eev.superheat == 9.5
        assert unit.eev.superheat_ref == 9.0
        assert unit.eev.valve_type == "UKV"
        assert unit.exv is True
        assert unit.oil_return is False
        assert unit.envelope_protection is False
        assert unit.low_pressure_error is False
        assert unit.high_pressure_error is False
        assert unit.reverse_valve_position == "Cool"
        assert unit.drive_comms_status == "OK"

    def test_missing_diagnostics_are_none(self) -> None:
        """A unit that reports no diagnostics leaves every new field as None."""
        unit = ActronAirOutdoorUnit.model_validate({"CompSpeed": 50.0})
        assert unit.suction_pressure is None
        assert unit.condensing_pressure is None
        assert unit.eev is None
        assert unit.oil_return is None
        assert unit.reverse_valve_position is None

    @pytest.mark.parametrize("value", ["NA", None, [1, 2], {"x": 1}, True])
    def test_odd_numeric_values_become_none(self, value: Any) -> None:
        """A non-numeric pressure reading becomes None instead of failing."""
        unit = ActronAirOutdoorUnit.model_validate({"SuctP0": value})
        assert unit.suction_pressure is None

    @pytest.mark.parametrize("value", [10**400, "1e400", float("inf"), float("nan"), "nan"])
    def test_overflowing_or_non_finite_values_become_none(self, value: Any) -> None:
        """A reading too large for a float, or not finite, becomes None."""
        unit = ActronAirOutdoorUnit.model_validate({"SuctP0": value, "CondPc": 24.7})
        assert unit.suction_pressure is None
        assert unit.condensing_pressure == 24.7

    def test_eev_model_instance_is_kept(self) -> None:
        """An already built ActronAirEEV is kept, not discarded."""
        unit = ActronAirOutdoorUnit(EEV=ActronAirEEV(Opening_pc=214, SuperHeat=9.5))
        assert unit.eev is not None
        assert unit.eev.opening_pc == 214.0
        assert unit.eev.superheat == 9.5

    def test_numeric_strings_are_coerced(self) -> None:
        """A numeric string reading is parsed as a float."""
        unit = ActronAirOutdoorUnit.model_validate({"CondPc": "24.7"})
        assert unit.condensing_pressure == 24.7

    def test_non_object_eev_is_ignored(self) -> None:
        """An EEV value that is not an object becomes None."""
        unit = ActronAirOutdoorUnit.model_validate({"EEV": "NA"})
        assert unit.eev is None

    def test_odd_flags_become_none(self) -> None:
        """A flag that is not a boolean (or 0/1) becomes None."""
        unit = ActronAirOutdoorUnit.model_validate({"OilReturn": "NA", "LPErr": 1})
        assert unit.oil_return is None
        assert unit.low_pressure_error is True

    def test_odd_values_do_not_discard_live_status(self) -> None:
        """Odd diagnostic values never discard the rest of the live status."""
        status = ActronAirStatus.model_validate(
            {
                "lastKnownState": {
                    "LiveAircon": {
                        "SystemOn": True,
                        "CompressorCapacity": 97,
                        "CoilInlet": "NA",
                        "FanPWM": 85,
                        "OutdoorUnit": {
                            **ADVANCE_RUNNING_OUTDOOR,
                            "SuctP0": "NA",
                            "EEV": [],
                        },
                    }
                }
            }
        )
        status.parse_nested_components()
        live = status.live_aircon
        assert live is not None
        assert live.is_on is True
        assert live.compressor_capacity == 97
        assert live.coil_inlet_temp is None
        assert live.fan_pwm == 85.0
        assert live.outdoor_unit.suction_pressure is None
        assert live.outdoor_unit.eev is None
        assert live.outdoor_unit.condensing_pressure == 24.7
