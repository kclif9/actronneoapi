"""Tests for settings async command methods."""

from typing import Any

import pytest

from actron_neo_api.models import ActronAirStatus, ActronAirUserAirconSettings


@pytest.fixture
def settings_with_api(mock_api: Any) -> ActronAirUserAirconSettings:
    """Create settings object with API reference."""
    status = ActronAirStatus(
        isOnline=True,
        lastKnownState={
            "UserAirconSettings": {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "SetPoint": 22.0,
            },
            "NV_Limits": {
                "UserSetpoint_oC": {
                    "setCool_Min": 18.0,
                    "setCool_Max": 30.0,
                    "setHeat_Min": 16.0,
                    "setHeat_Max": 28.0,
                }
            },
        },
        serial_number="TEST123",
    )
    status.parse_nested_components()
    status.set_api(mock_api)
    return status.user_aircon_settings


@pytest.fixture
def settings_without_api() -> ActronAirUserAirconSettings:
    """Create settings object without API reference."""
    status = ActronAirStatus(
        isOnline=True,
        lastKnownState={
            "UserAirconSettings": {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "SetPoint": 22.0,
            }
        },
    )
    status.parse_nested_components()
    return status.user_aircon_settings


class TestSettingsAsyncSetSystemMode:
    """Test async set_system_mode method."""

    @pytest.mark.asyncio
    async def test_set_system_mode_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test setting system mode with API reference."""
        result = await settings_with_api.set_system_mode("HEAT")

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.Mode"] == "HEAT"

    @pytest.mark.asyncio
    async def test_set_system_mode_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting system mode without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_system_mode("HEAT")


class TestSettingsAsyncSetFanMode:
    """Test async set_fan_mode method."""

    @pytest.mark.asyncio
    async def test_set_fan_mode_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test setting fan mode with API reference."""
        result = await settings_with_api.set_fan_mode("HIGH")

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.FanMode"] == "HIGH"

    @pytest.mark.asyncio
    async def test_set_fan_mode_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting fan mode without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_fan_mode("HIGH")


class TestSettingsAsyncSetContinuousMode:
    """Test async set_continuous_mode method."""

    @pytest.mark.asyncio
    async def test_set_continuous_mode_enable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test enabling continuous mode with API reference."""
        result = await settings_with_api.set_continuous_mode(True)

        assert result is None  # Commands return None on success
        assert mock_api.last_command["command"]["UserAirconSettings.FanMode"] == "AUTO+CONT"

    @pytest.mark.asyncio
    async def test_set_continuous_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling continuous mode with API reference."""
        result = await settings_with_api.set_continuous_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.FanMode"] == "AUTO"

    @pytest.mark.asyncio
    async def test_set_continuous_mode_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting continuous mode without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_continuous_mode(True)


class TestSettingsAsyncSetTemperature:
    """Test async set_temperature method."""

    @pytest.mark.asyncio
    async def test_set_temperature_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test setting temperature with API reference."""
        result = await settings_with_api.set_temperature(24.0)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        # Temperature command uses mode-specific fields
        assert "UserAirconSettings.TemperatureSetpoint_Cool_oC" in mock_api.last_command["command"]

    @pytest.mark.asyncio
    async def test_set_temperature_clamps_to_cool_limits(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test temperature clamping to cool mode limits."""
        # Try to set below minimum
        await settings_with_api.set_temperature(15.0)
        assert (
            mock_api.last_command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"]
            == 18.0
        )

        # Try to set above maximum
        await settings_with_api.set_temperature(35.0)
        assert (
            mock_api.last_command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"]
            == 30.0
        )

    @pytest.mark.asyncio
    async def test_set_temperature_clamps_to_heat_limits(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test temperature clamping to heat mode limits."""
        # Set to HEAT mode first
        settings_with_api.mode = "HEAT"

        # Try to set below minimum
        await settings_with_api.set_temperature(14.0)
        assert (
            mock_api.last_command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"]
            == 16.0
        )

        # Try to set above maximum
        await settings_with_api.set_temperature(32.0)
        assert (
            mock_api.last_command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"]
            == 28.0
        )

    @pytest.mark.asyncio
    async def test_set_temperature_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting temperature without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_temperature(24.0)


class TestSettingsAsyncSetAwayMode:
    """Test async set_away_mode method."""

    @pytest.mark.asyncio
    async def test_set_away_mode_enable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test enabling away mode with API reference."""
        result = await settings_with_api.set_away_mode(True)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.AwayMode"] is True

    @pytest.mark.asyncio
    async def test_set_away_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling away mode with API reference."""
        result = await settings_with_api.set_away_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.AwayMode"] is False

    @pytest.mark.asyncio
    async def test_set_away_mode_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting away mode without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_away_mode(True)


class TestSettingsAsyncSetQuietMode:
    """Test async set_quiet_mode method."""

    @pytest.mark.asyncio
    async def test_set_quiet_mode_enable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test enabling quiet mode with API reference."""
        result = await settings_with_api.set_quiet_mode(True)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.QuietModeEnabled"] is True

    @pytest.mark.asyncio
    async def test_set_quiet_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling quiet mode with API reference."""
        result = await settings_with_api.set_quiet_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.QuietModeEnabled"] is False

    @pytest.mark.asyncio
    async def test_set_quiet_mode_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting quiet mode without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_quiet_mode(True)


class TestSettingsAsyncSetTurboMode:
    """Test async set_turbo_mode method."""

    @pytest.mark.asyncio
    async def test_set_turbo_mode_enable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test enabling turbo mode with API reference."""
        result = await settings_with_api.set_turbo_mode(True)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.TurboMode.Enabled"] is True

    @pytest.mark.asyncio
    async def test_set_turbo_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling turbo mode with API reference."""
        result = await settings_with_api.set_turbo_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.TurboMode.Enabled"] is False

    @pytest.mark.asyncio
    async def test_set_turbo_mode_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting turbo mode without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_turbo_mode(True)
