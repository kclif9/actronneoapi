"""Settings models for Actron Air API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .status import ActronAirStatus


class ActronAirUserAirconSettings(BaseModel):
    """User-configurable settings for an Actron Air AC system.

    Contains all user-adjustable parameters including power state, mode,
    temperature setpoints, fan settings, and special modes (quiet, turbo, away).
    Provides async methods to send commands to modify these settings.
    """

    is_on: bool = Field(False, alias="isOn")
    mode: str = Field("", alias="Mode")
    fan_mode: str = Field("", alias="FanMode")
    away_mode: bool = Field(False, alias="AwayMode")
    temperature_setpoint_cool_c: float = Field(0.0, alias="TemperatureSetpoint_Cool_oC")
    temperature_setpoint_heat_c: float = Field(0.0, alias="TemperatureSetpoint_Heat_oC")
    enabled_zones: list[bool] = Field([], alias="EnabledZones")
    quiet_mode_enabled: bool = Field(False, alias="QuietModeEnabled")
    turbo_mode_enabled: bool | dict[str, bool] = Field(
        default_factory=lambda: {"Enabled": False}, alias="TurboMode"
    )
    _parent_status: "ActronAirStatus | None" = None

    def set_parent_status(self, parent: "ActronAirStatus") -> None:
        """Set reference to parent ActronStatus object.

        Args:
            parent: Parent ActronAirStatus instance

        """
        self._parent_status = parent

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
        is_on = mode.upper() != "OFF"

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
        command: dict[str, Any] = {"command": {"type": "set-settings"}}

        if mode == "COOL":
            command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = float(
                temperature
            )
        elif mode == "HEAT":
            command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = float(
                temperature
            )
        elif mode == "AUTO":
            # AUTO: maintain the temperature differential between cooling and heating
            differential = self.temperature_setpoint_cool_c - self.temperature_setpoint_heat_c

            # Apply the same differential to the new temperature
            # For AUTO mode, we assume the provided temperature is for cooling
            cool_setpoint = float(temperature)
            heat_setpoint = float(
                max(10.0, temperature - differential)
            )  # Ensure we don't go below a reasonable minimum

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

        Args:
            mode: Mode to set ('AUTO', 'COOL', 'FAN', 'HEAT', 'OFF')
                 Use 'OFF' to turn the system off.

        """
        command = self._set_system_mode_command(mode)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)
        else:
            raise ValueError("No API reference available to send command")

    async def set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode and send the command. Preserves current continuous mode setting.

        Args:
            fan_mode: The fan mode (e.g., "AUTO", "LOW", "MEDIUM", "HIGH")

        """
        command = self._set_fan_mode_command(fan_mode)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)
        else:
            raise ValueError("No API reference available to send command")

    async def set_continuous_mode(self, enabled: bool) -> None:
        """Enable or disable continuous fan mode and send the command.

        Args:
            enabled: True to enable continuous mode, False to disable

        """
        command = self._set_continuous_mode_command(enabled)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)
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
        if not -50 <= temperature <= 100:  # Reasonable physical limits
            raise ValueError(
                f"Temperature {temperature}°C is outside reasonable range (-50 to 100)"
            )

        # Apply limits if they are available
        if self._parent_status and self._parent_status.last_known_state:
            limits = self._parent_status.last_known_state.get("NV_Limits", {}).get(
                "UserSetpoint_oC", {}
            )

            if self.mode.upper() == "COOL":
                min_temp = limits.get("setCool_Min", 16.0)
                max_temp = limits.get("setCool_Max", 30.0)
                temperature = max(min_temp, min(max_temp, temperature))
            elif self.mode.upper() == "HEAT":
                min_temp = limits.get("setHeat_Min", 16.0)
                max_temp = limits.get("setHeat_Max", 30.0)
                temperature = max(min_temp, min(max_temp, temperature))

        command = self._set_temperature_command(temperature)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)
        else:
            raise ValueError("No API reference available to send command")

    async def set_away_mode(self, enabled: bool = False) -> None:
        """Enable/disable away mode and send the command.

        Args:
            enabled: True to enable, False to disable

        """
        command = self._set_away_mode_command(enabled)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)
        else:
            raise ValueError("No API reference available to send command")

    async def set_quiet_mode(self, enabled: bool = False) -> None:
        """Enable/disable quiet mode and send the command.

        Args:
            enabled: True to enable, False to disable

        """
        command = self._set_quiet_mode_command(enabled)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)
        else:
            raise ValueError("No API reference available to send command")

    async def set_turbo_mode(self, enabled: bool = False) -> None:
        """Enable/disable turbo mode and send the command.

        Args:
            enabled: True to enable, False to disable

        """
        command = self._set_turbo_mode_command(enabled)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            await self._parent_status.api.send_command(self._parent_status.serial_number, command)
        else:
            raise ValueError("No API reference available to send command")
