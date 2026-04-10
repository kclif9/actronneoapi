"""Tests for settings async command methods."""

from typing import Any

import pytest

from actron_neo_api.exceptions import ActronAirAPIError
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

        # Optimistic local state update
        assert settings_with_api.is_on is True
        assert settings_with_api.mode == "HEAT"

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

        # Optimistic local state update
        assert settings_with_api.fan_mode == "HIGH"

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

        # Optimistic local state update
        assert settings_with_api.fan_mode == "AUTO+CONT"

    @pytest.mark.asyncio
    async def test_set_continuous_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling continuous mode with API reference."""
        result = await settings_with_api.set_continuous_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.FanMode"] == "AUTO"

        # Optimistic local state update
        assert settings_with_api.fan_mode == "AUTO"

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

        # Optimistic local state update
        assert settings_with_api.temperature_setpoint_cool_c == 24.0

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

    @pytest.mark.asyncio
    async def test_set_temperature_raises_in_fan_mode(
        self, settings_with_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting temperature in FAN mode raises ValueError."""
        settings_with_api.mode = "FAN"
        with pytest.raises(ValueError, match="Cannot set temperature in FAN mode"):
            await settings_with_api.set_temperature(22.0)

    @pytest.mark.asyncio
    async def test_set_temperature_raises_in_off_mode(
        self, settings_with_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting temperature in OFF mode raises ValueError."""
        settings_with_api.mode = "OFF"
        with pytest.raises(ValueError, match="Cannot set temperature in OFF mode"):
            await settings_with_api.set_temperature(22.0)


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

        # Optimistic local state update
        assert settings_with_api.away_mode is True

    @pytest.mark.asyncio
    async def test_set_away_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling away mode with API reference."""
        result = await settings_with_api.set_away_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.AwayMode"] is False

        # Optimistic local state update
        assert settings_with_api.away_mode is False

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

        # Optimistic local state update
        assert settings_with_api.quiet_mode_enabled is True

    @pytest.mark.asyncio
    async def test_set_quiet_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling quiet mode with API reference."""
        result = await settings_with_api.set_quiet_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.QuietModeEnabled"] is False

        # Optimistic local state update
        assert settings_with_api.quiet_mode_enabled is False

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

        # Optimistic local state update
        assert settings_with_api.turbo_enabled is True

    @pytest.mark.asyncio
    async def test_set_turbo_mode_disable_with_api(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Test disabling turbo mode with API reference."""
        result = await settings_with_api.set_turbo_mode(False)

        assert result is None  # Commands return None on success
        assert mock_api.last_serial == "TEST123"
        assert mock_api.last_command["command"]["UserAirconSettings.TurboMode.Enabled"] is False

        # Optimistic local state update
        assert settings_with_api.turbo_enabled is False

    @pytest.mark.asyncio
    async def test_set_turbo_mode_without_api(
        self, settings_without_api: ActronAirUserAirconSettings
    ) -> None:
        """Test setting turbo mode without API reference raises."""
        with pytest.raises(ValueError, match="No API reference available"):
            await settings_without_api.set_turbo_mode(True)


class TestOptimisticStateNotUpdatedOnError:
    """Verify optimistic state is NOT updated when send_command raises."""

    @pytest.fixture
    def settings_with_failing_api(self) -> ActronAirUserAirconSettings:
        """Create settings with an API that raises on send_command."""

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
                    "AwayMode": False,
                    "QuietModeEnabled": False,
                    "TurboMode": {"Enabled": False, "Supported": True},
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "TemperatureSetpoint_Heat_oC": 20.0,
                },
            },
            serial_number="TEST123",
        )
        status.parse_nested_components()
        status.set_api(FailingAPI())
        return status.user_aircon_settings

    @pytest.mark.asyncio
    async def test_mode_not_updated_on_error(
        self, settings_with_failing_api: ActronAirUserAirconSettings
    ) -> None:
        """System mode unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await settings_with_failing_api.set_system_mode("HEAT")
        assert settings_with_failing_api.mode == "COOL"
        assert settings_with_failing_api.is_on is True

    @pytest.mark.asyncio
    async def test_fan_mode_not_updated_on_error(
        self, settings_with_failing_api: ActronAirUserAirconSettings
    ) -> None:
        """Fan mode unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await settings_with_failing_api.set_fan_mode("HIGH")
        assert settings_with_failing_api.fan_mode == "AUTO"

    @pytest.mark.asyncio
    async def test_temperature_not_updated_on_error(
        self, settings_with_failing_api: ActronAirUserAirconSettings
    ) -> None:
        """Temperature unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await settings_with_failing_api.set_temperature(28.0)
        assert settings_with_failing_api.temperature_setpoint_cool_c == 24.0

    @pytest.mark.asyncio
    async def test_away_mode_not_updated_on_error(
        self, settings_with_failing_api: ActronAirUserAirconSettings
    ) -> None:
        """Away mode unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await settings_with_failing_api.set_away_mode(True)
        assert settings_with_failing_api.away_mode is False

    @pytest.mark.asyncio
    async def test_quiet_mode_not_updated_on_error(
        self, settings_with_failing_api: ActronAirUserAirconSettings
    ) -> None:
        """Quiet mode unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await settings_with_failing_api.set_quiet_mode(True)
        assert settings_with_failing_api.quiet_mode_enabled is False

    @pytest.mark.asyncio
    async def test_turbo_mode_not_updated_on_error(
        self, settings_with_failing_api: ActronAirUserAirconSettings
    ) -> None:
        """Turbo mode unchanged when API call fails."""
        with pytest.raises(ActronAirAPIError):
            await settings_with_failing_api.set_turbo_mode(True)
        assert settings_with_failing_api.turbo_enabled is False


class TestOptimisticStateOff:
    """Test optimistic state for OFF mode."""

    @pytest.mark.asyncio
    async def test_set_system_mode_off_updates_is_on(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Setting mode to OFF optimistically sets is_on=False, preserves mode."""
        original_mode = settings_with_api.mode
        await settings_with_api.set_system_mode("OFF")

        assert settings_with_api.is_on is False
        assert settings_with_api.mode == original_mode

    @pytest.mark.asyncio
    async def test_set_temperature_heat_mode(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Setting temperature in HEAT mode updates heat setpoint."""
        settings_with_api.mode = "HEAT"
        await settings_with_api.set_temperature(22.0)

        assert settings_with_api.temperature_setpoint_heat_c == 22.0

    @pytest.mark.asyncio
    async def test_set_temperature_auto_mode(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Setting temperature in AUTO mode updates both cool and heat setpoints."""
        settings_with_api.mode = "AUTO"
        settings_with_api.temperature_setpoint_cool_c = 24.0
        settings_with_api.temperature_setpoint_heat_c = 20.0
        await settings_with_api.set_temperature(26.0)

        assert settings_with_api.temperature_setpoint_cool_c == 26.0
        assert settings_with_api.temperature_setpoint_heat_c == 22.0

    @pytest.mark.asyncio
    async def test_set_turbo_mode_bool_optimistic(
        self, settings_with_api: ActronAirUserAirconSettings, mock_api: Any
    ) -> None:
        """Setting turbo mode when turbo_mode_enabled is a plain bool."""
        settings_with_api.turbo_mode_enabled = False
        await settings_with_api.set_turbo_mode(True)

        assert settings_with_api.turbo_mode_enabled is True


class TestModeSupport:
    """Test ModeSupport parsing and supported_modes property."""

    def test_default_mode_support(self) -> None:
        """Default mode support includes cool, heat, fan, auto but not dry."""
        settings = ActronAirUserAirconSettings.model_validate({})
        assert "COOL" in settings.supported_modes
        assert "HEAT" in settings.supported_modes
        assert "FAN" in settings.supported_modes
        assert "AUTO" in settings.supported_modes
        assert "DRY" not in settings.supported_modes

    def test_mode_support_from_api_data(self) -> None:
        """Mode support is parsed from API data."""
        settings = ActronAirUserAirconSettings.model_validate(
            {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "ModeSupport": {
                    "Cool": True,
                    "Heat": True,
                    "Fan": True,
                    "Auto": True,
                    "Dry": False,
                },
            }
        )
        assert "COOL" in settings.supported_modes
        assert "HEAT" in settings.supported_modes
        assert "FAN" in settings.supported_modes
        assert "AUTO" in settings.supported_modes
        assert "DRY" not in settings.supported_modes

    def test_mode_support_with_dry_enabled(self) -> None:
        """Dry mode appears in supported_modes when enabled."""
        settings = ActronAirUserAirconSettings.model_validate(
            {
                "ModeSupport": {
                    "Cool": True,
                    "Heat": True,
                    "Fan": True,
                    "Auto": True,
                    "Dry": True,
                },
            }
        )
        assert "DRY" in settings.supported_modes

    def test_mode_support_partial(self) -> None:
        """Only supported modes are returned when some are disabled."""
        settings = ActronAirUserAirconSettings.model_validate(
            {
                "ModeSupport": {
                    "Cool": True,
                    "Heat": False,
                    "Fan": True,
                    "Auto": False,
                    "Dry": False,
                },
            }
        )
        assert settings.supported_modes == ["COOL", "FAN"]

    def test_mode_support_via_status_parsing(self) -> None:
        """Mode support is parsed correctly through ActronAirStatus."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "FanMode": "AUTO",
                    "ModeSupport": {
                        "Cool": True,
                        "Heat": True,
                        "Fan": True,
                        "Auto": True,
                        "Dry": False,
                    },
                },
            },
        )
        status.parse_nested_components()
        assert "COOL" in status.user_aircon_settings.supported_modes
        assert "DRY" not in status.user_aircon_settings.supported_modes
