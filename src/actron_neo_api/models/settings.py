"""Settings models for Actron Neo API"""
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field


class UserAirconSettings(BaseModel):
    is_on: bool = Field(False, alias="isOn")
    mode: str = Field("", alias="Mode")
    fan_mode: str = Field("", alias="FanMode")
    away_mode: bool = Field(False, alias="AwayMode")
    temperature_setpoint_cool_c: float = Field(0.0, alias="TemperatureSetpoint_Cool_oC")
    temperature_setpoint_heat_c: float = Field(0.0, alias="TemperatureSetpoint_Heat_oC")
    enabled_zones: List[bool] = Field([], alias="EnabledZones")
    quiet_mode_enabled: bool = Field(False, alias="QuietModeEnabled")
    turbo_mode_enabled: Union[bool, Dict[str, bool]] = Field(
        default_factory=lambda: {"Enabled": False},
        alias="TurboMode"
    )
    _parent_status: Optional["ActronStatus"] = None

    def set_parent_status(self, parent: "ActronStatus") -> None:
        """Set reference to parent ActronStatus object"""
        self._parent_status = parent

    @property
    def turbo_enabled(self) -> bool:
        """Get the turbo mode status, handling both the boolean and object representation"""
        if isinstance(self.turbo_mode_enabled, dict):
            return self.turbo_mode_enabled.get("Enabled", False)
        return self.turbo_mode_enabled

    # Command generation methods
    def set_system_mode_command(self, is_on: bool, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a command to set the AC system mode.

        Args:
            is_on: Boolean to turn the system on or off
            mode: Mode to set when the system is on ('AUTO', 'COOL', 'FAN', 'HEAT')

        Returns:
            Command dictionary
        """
        command = {
            "command": {
                "UserAirconSettings.isOn": is_on,
                "type": "set-settings"
            }
        }

        if is_on and mode:
            command["command"]["UserAirconSettings.Mode"] = mode

        return command

    def set_fan_mode_command(self, fan_mode: str, continuous: bool = False) -> Dict[str, Any]:
        """
        Create a command to set the fan mode.

        Args:
            fan_mode: The fan mode (e.g., "AUTO", "LOW", "MEDIUM", "HIGH")
            continuous: Whether to enable continuous fan mode

        Returns:
            Command dictionary
        """
        mode = fan_mode
        if continuous:
            mode = f"{fan_mode}-CONT"

        return {
            "command": {
                "UserAirconSettings.FanMode": mode,
                "type": "set-settings",
            }
        }

    def set_temperature_command(self, temperature: float) -> Dict[str, Any]:
        """
        Create a command to set temperature for the system based on the current AC mode.

        Args:
            temperature: The temperature to set

        Returns:
            Command dictionary
        """
        if not self.mode:
            raise ValueError("No mode available in settings")

        mode = self.mode.upper()
        command = {"command": {"type": "set-settings"}}

        if mode == "COOL":
            command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = temperature
        elif mode == "HEAT":
            command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = temperature
        elif mode == "AUTO":
            # When in AUTO mode, we maintain the temperature differential between cooling and heating
            differential = self.temperature_setpoint_cool_c - self.temperature_setpoint_heat_c

            # Apply the same differential to the new temperature
            # For AUTO mode, we assume the provided temperature is for cooling
            cool_setpoint = temperature
            heat_setpoint = max(10.0, temperature - differential)  # Ensure we don't go below a reasonable minimum

            command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = cool_setpoint
            command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = heat_setpoint

        return command

    def set_away_mode_command(self, enabled: bool = False) -> Dict[str, Any]:
        """
        Create a command to enable/disable away mode.

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

    def set_quiet_mode_command(self, enabled: bool = False) -> Dict[str, Any]:
        """
        Create a command to enable/disable quiet mode.

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

    def set_turbo_mode_command(self, enabled: bool = False) -> Dict[str, Any]:
        """
        Create a command to enable/disable turbo mode.

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

    def set_zone_command(self, zone_number: int, is_enabled: bool) -> Dict[str, Any]:
        """
        Create a command to set a specific zone.

        Args:
            zone_number: Zone number to control (starting from 0)
            is_enabled: True to turn ON, False to turn OFF

        Returns:
            Command dictionary
        """
        # Create a copy of the current zones
        updated_zones = self.enabled_zones.copy()

        # Update the specific zone
        if zone_number < len(updated_zones):
            updated_zones[zone_number] = is_enabled

        return {
            "command": {
                "UserAirconSettings.EnabledZones": updated_zones,
                "type": "set-settings",
            }
        }

    def set_multiple_zones_command(self, zone_settings: Dict[int, bool]) -> Dict[str, Any]:
        """
        Create a command to set multiple zones at once.

        Args:
            zone_settings: Dictionary where keys are zone numbers and values are True/False

        Returns:
            Command dictionary
        """
        return {
            "command": {
                **{f"UserAirconSettings.EnabledZones[{zone}]": state
                   for zone, state in zone_settings.items()},
                "type": "set-settings",
            }
        }

    async def set_system_mode(self, is_on: bool, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Set the AC system mode and send the command.

        Args:
            is_on: Boolean to turn the system on or off
            mode: Mode to set when the system is on ('AUTO', 'COOL', 'FAN', 'HEAT')

        Returns:
            API response dictionary
        """
        command = self.set_system_mode_command(is_on, mode)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def set_fan_mode(self, fan_mode: str, continuous: bool = False) -> Dict[str, Any]:
        """
        Set the fan mode and send the command.

        Args:
            fan_mode: The fan mode (e.g., "AUTO", "LOW", "MEDIUM", "HIGH")
            continuous: Whether to enable continuous fan mode

        Returns:
            API response dictionary
        """
        command = self.set_fan_mode_command(fan_mode, continuous)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def set_temperature(self, temperature: float) -> Dict[str, Any]:
        """
        Set temperature for the system based on the current AC mode and send the command.

        Args:
            temperature: The temperature to set

        Returns:
            API response dictionary
        """
        # Apply limits if they are available
        if self._parent_status and self._parent_status.last_known_state:
            limits = self._parent_status.last_known_state.get("NV_Limits", {}).get("UserSetpoint_oC", {})

            if self.mode.upper() == "COOL":
                min_temp = limits.get("setCool_Min", 16.0)
                max_temp = limits.get("setCool_Max", 30.0)
                temperature = max(min_temp, min(max_temp, temperature))
            elif self.mode.upper() == "HEAT":
                min_temp = limits.get("setHeat_Min", 16.0)
                max_temp = limits.get("setHeat_Max", 30.0)
                temperature = max(min_temp, min(max_temp, temperature))

        command = self.set_temperature_command(temperature)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def set_away_mode(self, enabled: bool = False) -> Dict[str, Any]:
        """
        Enable/disable away mode and send the command.

        Args:
            enabled: True to enable, False to disable

        Returns:
            API response dictionary
        """
        command = self.set_away_mode_command(enabled)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def set_quiet_mode(self, enabled: bool = False) -> Dict[str, Any]:
        """
        Enable/disable quiet mode and send the command.

        Args:
            enabled: True to enable, False to disable

        Returns:
            API response dictionary
        """
        command = self.set_quiet_mode_command(enabled)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def set_turbo_mode(self, enabled: bool = False) -> Dict[str, Any]:
        """
        Enable/disable turbo mode and send the command.

        Args:
            enabled: True to enable, False to disable

        Returns:
            API response dictionary
        """
        command = self.set_turbo_mode_command(enabled)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def set_zone(self, zone_number: int, is_enabled: bool) -> Dict[str, Any]:
        """
        Set a specific zone and send the command.

        Args:
            zone_number: Zone number to control (starting from 0)
            is_enabled: True to turn ON, False to turn OFF

        Returns:
            API response dictionary
        """
        command = self.set_zone_command(zone_number, is_enabled)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def set_multiple_zones(self, zone_settings: Dict[int, bool]) -> Dict[str, Any]:
        """
        Set multiple zones at once and send the command.

        Args:
            zone_settings: Dictionary where keys are zone numbers and values are True/False

        Returns:
            API response dictionary
        """
        command = self.set_multiple_zones_command(zone_settings)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")
