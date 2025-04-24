"""Zone models for Actron Neo API"""
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field


class ActronAirNeoZoneSensor(BaseModel):
    connected: bool = Field(False, alias="Connected")
    kind: str = Field("", alias="NV_Kind")
    is_paired: bool = Field(False, alias="NV_isPaired")
    signal_strength: str = Field("NA", alias="Signal_of3")


class ActronAirNeoZone(BaseModel):
    can_operate: bool = Field(False, alias="CanOperate")
    common_zone: bool = Field(False, alias="CommonZone")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    title: str = Field("", alias="NV_Title")
    exists: bool = Field(False, alias="NV_Exists")
    temperature_setpoint_cool_c: float = Field(0.0, alias="TemperatureSetpoint_Cool_oC")
    temperature_setpoint_heat_c: float = Field(0.0, alias="TemperatureSetpoint_Heat_oC")
    sensors: Dict[str, ActronAirNeoZoneSensor] = Field({}, alias="Sensors")
    actual_humidity_pc: Optional[float] = None
    _parent_status: Optional["ActronStatus"] = None
    _zone_index: Optional[int] = None

    def is_active(self, enabled_zones: List[bool], position: int) -> bool:
        """Check if this zone is currently active"""
        if not self.can_operate:
            return False
        if position >= len(enabled_zones):
            return False
        return enabled_zones[position]

    @property
    def humidity(self) -> float:
        """Get the best available humidity reading for this zone.
        Returns the actual sensor reading if available, otherwise the system-reported value.
        """
        if self.actual_humidity_pc is not None:
            return self.actual_humidity_pc
        return self.live_humidity_pc

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature that can be set."""
        if not self._parent_status or not self._parent_status.last_known_state:
            return 30.0  # Default fallback value

        max_setpoint = self._parent_status.last_known_state.get("NV_Limits", {}).get(
            "UserSetpoint_oC", {}).get("setCool_Max", 30.0)

        user_settings = self._parent_status.last_known_state.get("UserAirconSettings", {})
        target_setpoint = user_settings.get("TemperatureSetpoint_Cool_oC", 24.0)
        temp_variance = user_settings.get("ZoneTemperatureSetpointVariance_oC", 3.0)

        if max_setpoint < target_setpoint + temp_variance:
            return max_setpoint
        return target_setpoint + temp_variance

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature that can be set."""
        if not self._parent_status or not self._parent_status.last_known_state:
            return 16.0  # Default fallback value

        min_setpoint = self._parent_status.last_known_state.get("NV_Limits", {}).get(
            "UserSetpoint_oC", {}).get("setCool_Min", 16.0)

        user_settings = self._parent_status.last_known_state.get("UserAirconSettings", {})
        target_setpoint = user_settings.get("TemperatureSetpoint_Cool_oC", 24.0)
        temp_variance = user_settings.get("ZoneTemperatureSetpointVariance_oC", 3.0)

        if min_setpoint > target_setpoint - temp_variance:
            return min_setpoint
        return target_setpoint - temp_variance

    # Command generation methods
    def set_temperature_command(self, temperature: float) -> Dict[str, Any]:
        """
        Create a command to set temperature for this zone based on the current AC mode.

        Args:
            temperature: The temperature to set

        Returns:
            Command dictionary
        """
        if self._zone_index is None:
            raise ValueError("Zone index not set")

        if not self._parent_status or not self._parent_status.user_aircon_settings:
            raise ValueError("No parent AC status available to determine mode")

        mode = self._parent_status.user_aircon_settings.mode.upper()
        command = {"command": {"type": "set-settings"}}

        if mode == "COOL":
            command["command"][f"RemoteZoneInfo[{self._zone_index}].TemperatureSetpoint_Cool_oC"] = temperature
        elif mode == "HEAT":
            command["command"][f"RemoteZoneInfo[{self._zone_index}].TemperatureSetpoint_Heat_oC"] = temperature
        elif mode == "AUTO":
            # When in AUTO mode, we maintain the temperature differential between cooling and heating
            # Get the current differential from parent settings
            cool_temp = self._parent_status.user_aircon_settings.temperature_setpoint_cool_c
            heat_temp = self._parent_status.user_aircon_settings.temperature_setpoint_heat_c
            differential = cool_temp - heat_temp

            # Apply the same differential to the new temperature
            # For AUTO mode, we assume the provided temperature is for cooling
            cool_setpoint = temperature
            heat_setpoint = max(10.0, temperature - differential)  # Ensure we don't go below a reasonable minimum

            command["command"][f"RemoteZoneInfo[{self._zone_index}].TemperatureSetpoint_Cool_oC"] = cool_setpoint
            command["command"][f"RemoteZoneInfo[{self._zone_index}].TemperatureSetpoint_Heat_oC"] = heat_setpoint

        return command

    def set_enable_command(self, is_enabled: bool) -> Dict[str, Any]:
        """
        Create a command to enable or disable this zone.

        Args:
            is_enabled: True to enable, False to disable

        Returns:
            Command dictionary
        """
        if self._zone_index is None:
            raise ValueError("Zone index not set")

        if not self._parent_status or not self._parent_status.user_aircon_settings:
            raise ValueError("No parent AC status available to determine current zones")

        # Get current zones from parent
        current_zones = self._parent_status.user_aircon_settings.enabled_zones.copy()

        # Update the specific zone
        if self._zone_index < len(current_zones):
            current_zones[self._zone_index] = is_enabled
        else:
            raise ValueError(f"Zone index {self._zone_index} out of range for zones list")

        return {
            "command": {
                "UserAirconSettings.EnabledZones": current_zones,
                "type": "set-settings",
            }
        }

    def set_parent_status(self, parent: "ActronStatus", zone_index: int) -> None:
        """Set reference to parent ActronStatus object and this zone's index"""
        self._parent_status = parent
        self._zone_index = zone_index

    async def set_temperature(self, temperature: float) -> Dict[str, Any]:
        """
        Set temperature for this zone based on the current AC mode and send the command.

        Args:
            temperature: The temperature to set

        Returns:
            API response dictionary
        """
        if self._zone_index is None:
            raise ValueError("Zone index not set")

        # Ensure temperature is within valid range
        temperature = max(self.min_temp, min(self.max_temp, temperature))

        command = self.set_temperature_command(temperature)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")

    async def enable(self, is_enabled: bool = True) -> Dict[str, Any]:
        """
        Enable or disable this zone and send the command.

        Args:
            is_enabled: True to enable, False to disable

        Returns:
            API response dictionary
        """
        command = self.set_enable_command(is_enabled)
        if self._parent_status and self._parent_status._api and hasattr(self._parent_status, "serial_number"):
            return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")
