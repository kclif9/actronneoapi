"""Settings models for Actron Air API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

from ..const import (
    AC_MODE_AUTO,
    AC_MODE_COOL,
    AC_MODE_DRY,
    AC_MODE_FAN,
    AC_MODE_HEAT,
    AC_MODE_OFF,
    DEFAULT_MAX_SETPOINT,
    DEFAULT_MIN_SETPOINT,
    TEMP_AUTO_HEAT_MIN,
    TEMP_PHYSICAL_MAX,
    TEMP_PHYSICAL_MIN,
)

if TYPE_CHECKING:
    from .status import ActronAirStatus

# Mapping from ModeSupport keys to AC_MODE constants
_MODE_SUPPORT_MAP: dict[str, str] = {
    "Cool": AC_MODE_COOL,
    "Heat": AC_MODE_HEAT,
    "Fan": AC_MODE_FAN,
    "Auto": AC_MODE_AUTO,
    "Dry": AC_MODE_DRY,
}


class ActronAirModeSupport(BaseModel):
    """Mode support flags from the AC system.

    Indicates which HVAC modes the system hardware supports.
    """

    model_config = ConfigDict(populate_by_name=True)

    cool: bool = Field(True, alias="Cool")
    heat: bool = Field(True, alias="Heat")
    fan: bool = Field(True, alias="Fan")
    auto: bool = Field(True, alias="Auto")
    dry: bool = Field(False, alias="Dry")


class ActronAirUserAirconSettings(BaseModel):
    """User-configurable settings for an Actron Air AC system.

    Contains all user-adjustable parameters including power state, mode,
    temperature setpoints, fan settings, and special modes (quiet, turbo, away).
    Provides async methods to send commands to modify these settings.
    """

    model_config = ConfigDict(populate_by_name=True)

    is_on: bool = Field(False, alias="isOn")
    mode: str = Field("", alias="Mode")
    fan_mode: str = Field("", alias="FanMode")
    away_mode: bool = Field(False, alias="AwayMode")
    temperature_setpoint_cool_c: float = Field(0.0, alias="TemperatureSetpoint_Cool_oC")
    temperature_setpoint_heat_c: float = Field(0.0, alias="TemperatureSetpoint_Heat_oC")
    zone_temperature_setpoint_variance: float = Field(
        0.0, alias="ZoneTemperatureSetpointVariance_oC"
    )
    enabled_zones: list[bool] = Field(default_factory=list, alias="EnabledZones")
    quiet_mode_enabled: bool = Field(False, alias="QuietModeEnabled")
    turbo_mode_enabled: bool | dict[str, bool] = Field(
        default_factory=lambda: {"Enabled": False}, alias="TurboMode"
    )
    mode_support: ActronAirModeSupport = Field(
        default_factory=lambda: ActronAirModeSupport.model_validate({}),
        alias="ModeSupport",
    )
    _parent_status: "ActronAirStatus | None" = None

    def set_parent_status(self, parent: "ActronAirStatus") -> None:
        """Set reference to parent ActronStatus object.

        Args:
            parent: Parent ActronAirStatus instance

        """
        self._parent_status = parent

    @property
    def supported_modes(self) -> list[str]:
        """Get the list of HVAC modes supported by this system.

        Returns:
            List of supported mode strings (e.g., ['COOL', 'HEAT', 'FAN', 'AUTO'])

        """
        return [
            mode_const
            for key, mode_const in _MODE_SUPPORT_MAP.items()
            if getattr(self.mode_support, key.lower(), False)
        ]

    @property
    def current_setpoint(self) -> float:
        """Get the current active temperature setpoint based on the AC mode.

        Returns:
            The active temperature setpoint in degrees Celsius

        Note:
            In AUTO mode, the cooling setpoint is typically the active one,
            but this may depend on the current operating state of the system.
            For simplicity, this property returns the cooling setpoint for AUTO mode.

        """
        if self.mode.upper() == AC_MODE_HEAT:
            return self.temperature_setpoint_heat_c
        return self.temperature_setpoint_cool_c

    @property
    def turbo_supported(self) -> bool:
        """Check if turbo mode is supported by this system.

        Returns:
            True if turbo mode is supported, False otherwise

        Note:
            Handles both boolean and dictionary representations of turbo mode data

        """
        if isinstance(self.turbo_mode_enabled, dict):
            return self.turbo_mode_enabled.get("Supported", False)
        return False

    @property
    def turbo_enabled(self) -> bool:
        """Get the current turbo mode status.

        Returns:
            True if turbo mode is currently enabled, False otherwise

        Note:
            Handles both boolean and dictionary representations from API

        """
        if isinstance(self.turbo_mode_enabled, dict):
            return self.turbo_mode_enabled.get("Enabled", False)
        return self.turbo_mode_enabled

    @property
    def continuous_fan_enabled(self) -> bool:
        """Check if continuous fan mode is currently enabled.

        Returns:
            True if fan will run continuously, False if it cycles with compressor

        """
        return "CONT" in self.fan_mode

    @property
    def base_fan_mode(self) -> str:
        """Get the base fan mode without the continuous mode suffix.

        Returns:
            Fan mode string (e.g., "AUTO", "LOW", "HIGH") without "+CONT" suffix

        """
        if self.continuous_fan_enabled:
            if "+CONT" in self.fan_mode:
                return self.fan_mode.split("+CONT")[0]
            elif "-CONT" in self.fan_mode:
                return self.fan_mode.split("-CONT")[0]
        return self.fan_mode

    # Command generation methods
    def _set_system_mode_command(self, mode: str) -> dict[str, Any]:
        """Create a command to set the AC system mode.

        Args:
            mode: Mode to set ('AUTO', 'COOL', 'FAN', 'HEAT', 'OFF')
                 Use 'OFF' to turn the system off.

        Returns:
            Command dictionary

        """
        # Determine if system should be on or off based on mode
        is_on = mode.upper() != AC_MODE_OFF

        command = {
            "command": {
                "UserAirconSettings.isOn": is_on,
                "type": "set-settings",
            }
        }

        # When turning off, preserve the current mode, otherwise set the new mode
        if not is_on:
            command["command"]["UserAirconSettings.Mode"] = self.mode
        else:
            command["command"]["UserAirconSettings.Mode"] = mode

        return command

    def _set_fan_mode_command(self, fan_mode: str) -> dict[str, Any]:
        """Create a command to set the fan mode, preserving continuous mode setting.

        Args:
            fan_mode: The fan mode (e.g., "AUTO", "LOW", "MEDIUM", "HIGH")

        Returns:
            Command dictionary

        """
        # Preserve the continuous mode setting
        mode = fan_mode
        if self.continuous_fan_enabled:
            mode = f"{fan_mode}+CONT"

        return {
            "command": {
                "UserAirconSettings.FanMode": mode,
                "type": "set-settings",
            }
        }

    def _set_continuous_mode_command(self, enabled: bool) -> dict[str, Any]:
        """Create a command to enable/disable continuous fan mode.

        Args:
            enabled: True to enable continuous mode, False to disable

        Returns:
            Command dictionary

        """
        base_mode = self.base_fan_mode
        mode = f"{base_mode}+CONT" if enabled else base_mode

        return {
            "command": {
                "UserAirconSettings.FanMode": mode,
                "type": "set-settings",
            }
        }

    def _set_temperature_command(self, temperature: float) -> dict[str, Any]:
        """Create a command to set temperature for the system based on the current AC mode.

        Args:
            temperature: The temperature to set

        Returns:
            Command dictionary

        """
        if not self.mode:
            raise ValueError("No mode available in settings")

        mode = self.mode.upper()

        if mode in (AC_MODE_FAN, AC_MODE_OFF):
            raise ValueError(f"Cannot set temperature in {mode} mode")

        command: dict[str, Any] = {"command": {"type": "set-settings"}}

        if mode == AC_MODE_COOL:
            command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = float(
                temperature
            )
        elif mode == AC_MODE_HEAT:
            command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = float(
                temperature
            )
        elif mode == AC_MODE_AUTO:
            # AUTO: maintain the temperature differential between cooling and heating
            differential = self.temperature_setpoint_cool_c - self.temperature_setpoint_heat_c

            # Apply the same differential to the new temperature
            # For AUTO mode, we assume the provided temperature is for cooling
            cool_setpoint = float(temperature)
            heat_setpoint = float(max(TEMP_AUTO_HEAT_MIN, temperature - differential))

            command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = cool_setpoint
            command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = heat_setpoint

        return command

    def _set_away_mode_command(self, enabled: bool = False) -> dict[str, Any]:
        """Create a command to enable/disable away mode.

        Args:
            enabled: True to enable, False to disable

        Returns:
            Command dictionary

        """
        return {
            "command": {
                "UserAirconSettings.AwayMode": enabled,
                "type": "set-settings",
            }
        }

    def _set_quiet_mode_command(self, enabled: bool = False) -> dict[str, Any]:
        """Create a command to enable/disable quiet mode.

        Args:
            enabled: True to enable, False to disable

        Returns:
            Command dictionary

        """
        return {
            "command": {
                "UserAirconSettings.QuietModeEnabled": enabled,
                "type": "set-settings",
            }
        }

    def _set_turbo_mode_command(self, enabled: bool = False) -> dict[str, Any]:
        """Create a command to enable/disable turbo mode.

        Args:
            enabled: True to enable, False to disable

        Returns:
            Command dictionary

        """
        return {
            "command": {
                "UserAirconSettings.TurboMode.Enabled": enabled,
                "type": "set-settings",
            }
        }

    async def set_system_mode(self, mode: str) -> None:
        """Set the AC system mode and send the command.

        After successful command delivery the local ``mode`` and ``is_on``
        fields are updated optimistically.

        Args:
            mode: Mode to set ('AUTO', 'COOL', 'FAN', 'HEAT', 'OFF')
                 Use 'OFF' to turn the system off.

        """
        command = self._set_system_mode_command(mode)
        if self._parent_status and self._parent_status.api and self._parent_status.serial_number:
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)

            # Optimistic local state update
            if mode.upper() == AC_MODE_OFF:
                self.is_on = False
            else:
                self.is_on = True
                self.mode = mode
        else:
            raise ValueError("No API reference available to send command")

    async def set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode and send the command. Preserves current continuous mode setting.

        After successful command delivery the local ``fan_mode`` field is
        updated optimistically.

        Args:
            fan_mode: The fan mode (e.g., "AUTO", "LOW", "MEDIUM", "HIGH")

        """
        command = self._set_fan_mode_command(fan_mode)
        if self._parent_status and self._parent_status.api and self._parent_status.serial_number:
            # Capture optimistic value before await to avoid races
            optimistic_fan = f"{fan_mode}+CONT" if self.continuous_fan_enabled else fan_mode

            await self._parent_status.api.send_command(self._parent_status.serial_number, command)

            # Optimistic local state update
            self.fan_mode = optimistic_fan
        else:
            raise ValueError("No API reference available to send command")

    async def set_continuous_mode(self, enabled: bool) -> None:
        """Enable or disable continuous fan mode and send the command.

        After successful command delivery the local ``fan_mode`` field is
        updated optimistically.

        Args:
            enabled: True to enable continuous mode, False to disable

        """
        command = self._set_continuous_mode_command(enabled)
        if self._parent_status and self._parent_status.api and self._parent_status.serial_number:
            # Capture optimistic value before await to avoid races
            base = self.base_fan_mode
            optimistic_fan = f"{base}+CONT" if enabled else base

            await self._parent_status.api.send_command(self._parent_status.serial_number, command)

            # Optimistic local state update
            self.fan_mode = optimistic_fan
        else:
            raise ValueError("No API reference available to send command")

    async def set_temperature(self, temperature: float) -> None:
        """Set temperature for the system based on the current AC mode and send the command.

        Args:
            temperature: The temperature to set (in degrees Celsius)

        Raises:
            ValueError: If temperature is invalid or no API reference available

        """
        # Validate temperature is a reasonable value
        if not isinstance(temperature, (int, float)):
            raise ValueError(f"Temperature must be a number, got {type(temperature).__name__}")
        if not TEMP_PHYSICAL_MIN <= temperature <= TEMP_PHYSICAL_MAX:
            raise ValueError(
                f"Temperature {temperature}°C is outside reasonable range "
                f"({TEMP_PHYSICAL_MIN} to {TEMP_PHYSICAL_MAX})"
            )

        # Apply limits if they are available
        if self._parent_status and self._parent_status.last_known_state:
            limits = self._parent_status.last_known_state.get("NV_Limits", {}).get(
                "UserSetpoint_oC", {}
            )

            if self.mode.upper() == AC_MODE_COOL:
                min_temp = limits.get("setCool_Min", DEFAULT_MIN_SETPOINT)
                max_temp = limits.get("setCool_Max", DEFAULT_MAX_SETPOINT)
                temperature = max(min_temp, min(max_temp, temperature))
            elif self.mode.upper() == AC_MODE_HEAT:
                min_temp = limits.get("setHeat_Min", DEFAULT_MIN_SETPOINT)
                max_temp = limits.get("setHeat_Max", DEFAULT_MAX_SETPOINT)
                temperature = max(min_temp, min(max_temp, temperature))

        command = self._set_temperature_command(temperature)
        if self._parent_status and self._parent_status.api and self._parent_status.serial_number:
            # Capture optimistic values before await to avoid races
            mode = self.mode.upper()
            optimistic_cool: float | None = None
            optimistic_heat: float | None = None
            if mode == AC_MODE_COOL:
                optimistic_cool = temperature
            elif mode == AC_MODE_HEAT:
                optimistic_heat = temperature
            elif mode == AC_MODE_AUTO:
                differential = self.temperature_setpoint_cool_c - self.temperature_setpoint_heat_c
                optimistic_cool = temperature
                optimistic_heat = max(TEMP_AUTO_HEAT_MIN, temperature - differential)

            await self._parent_status.api.send_command(self._parent_status.serial_number, command)

            # Optimistic local state update
            if optimistic_cool is not None:
                self.temperature_setpoint_cool_c = optimistic_cool
            if optimistic_heat is not None:
                self.temperature_setpoint_heat_c = optimistic_heat
        else:
            raise ValueError("No API reference available to send command")

    async def set_away_mode(self, enabled: bool = False) -> None:
        """Enable/disable away mode and send the command.

        After successful command delivery the local ``away_mode`` field is
        updated optimistically.

        Args:
            enabled: True to enable, False to disable

        """
        command = self._set_away_mode_command(enabled)
        if self._parent_status and self._parent_status.api and self._parent_status.serial_number:
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)

            # Optimistic local state update
            self.away_mode = enabled
        else:
            raise ValueError("No API reference available to send command")

    async def set_quiet_mode(self, enabled: bool = False) -> None:
        """Enable/disable quiet mode and send the command.

        After successful command delivery the local ``quiet_mode_enabled``
        field is updated optimistically.

        Args:
            enabled: True to enable, False to disable

        """
        command = self._set_quiet_mode_command(enabled)
        if self._parent_status and self._parent_status.api and self._parent_status.serial_number:
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)

            # Optimistic local state update
            self.quiet_mode_enabled = enabled
        else:
            raise ValueError("No API reference available to send command")

    async def set_turbo_mode(self, enabled: bool = False) -> None:
        """Enable/disable turbo mode and send the command.

        After successful command delivery the local ``turbo_mode_enabled``
        field is updated optimistically.

        Args:
            enabled: True to enable, False to disable

        """
        command = self._set_turbo_mode_command(enabled)
        if self._parent_status and self._parent_status.api and self._parent_status.serial_number:
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)

            # Optimistic local state update
            if isinstance(self.turbo_mode_enabled, dict):
                self.turbo_mode_enabled["Enabled"] = enabled
            else:
                self.turbo_mode_enabled = enabled
        else:
            raise ValueError("No API reference available to send command")
