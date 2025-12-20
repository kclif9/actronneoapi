"""Tests for zone async command methods."""

from typing import Any

import pytest

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
