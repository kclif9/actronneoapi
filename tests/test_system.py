"""Additional tests for system model methods."""

import pytest

from actron_neo_api.models import ActronAirStatus
from actron_neo_api.models.system import ActronAirACSystem


@pytest.fixture
def ac_system_with_api(mock_api):
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
    return status.ac_system


class TestACSystemSetMode:
    """Test ACSystem set_mode method."""

    @pytest.mark.asyncio
    async def test_set_mode_to_cool(self, ac_system_with_api, mock_api):
        """Test setting AC mode to COOL."""
        result = await ac_system_with_api.set_system_mode("COOL")

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.isOn"] is True
        assert mock_api.last_command["command"]["UserAirconSettings.Mode"] == "COOL"

    @pytest.mark.asyncio
    async def test_set_mode_to_off(self, ac_system_with_api, mock_api):
        """Test setting AC mode to OFF."""
        result = await ac_system_with_api.set_system_mode("OFF")

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.isOn"] is False
        # Mode should not be set when turning off
        assert "UserAirconSettings.Mode" not in mock_api.last_command["command"]

    @pytest.mark.asyncio
    async def test_set_mode_without_api(self):
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

        with pytest.raises(ValueError, match="No API reference available"):
            await status.ac_system.set_system_mode("COOL")

    @pytest.mark.asyncio
    async def test_set_mode_without_parent(self):
        """Test set_mode without parent status raises ValueError."""
        ac_system = ActronAirACSystem(master_serial="TEST123")

        with pytest.raises(ValueError, match="No API reference available"):
            await ac_system.set_system_mode("HEAT")
