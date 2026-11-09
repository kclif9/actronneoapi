"""Additional tests for system model methods."""

from typing import Any

import pytest
from pydantic import ValidationError

from actron_neo_api.models import ActronAirStatus
from actron_neo_api.models.system import ActronAirACSystem, ActronAirOutdoorUnit


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
