"""Zone models for Actron Neo API"""
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field


class ZoneSensor(BaseModel):
    connected: bool = Field(False, alias="Connected")
    kind: str = Field("", alias="NV_Kind")
    is_paired: bool = Field(False, alias="NV_isPaired")
    signal_strength: str = Field("NA", alias="Signal_of3")


class Zone(BaseModel):
    can_operate: bool = Field(False, alias="CanOperate")
    common_zone: bool = Field(False, alias="CommonZone")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    title: str = Field("", alias="NV_Title")
    exists: bool = Field(False, alias="NV_Exists")
    temperature_setpoint_cool_c: float = Field(0.0, alias="TemperatureSetpoint_Cool_oC")
    temperature_setpoint_heat_c: float = Field(0.0, alias="TemperatureSetpoint_Heat_oC")
    sensors: Dict[str, ZoneSensor] = Field({}, alias="Sensors")
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

    # Command generation methods
    def set_temperature_command(self, mode: str, temperature: Union[float, Dict[str, float]],
                               zone_index: int) -> Dict[str, Any]:
        """
        Create a command to set temperature for this zone.

        Args:
            mode: The mode ('COOL', 'HEAT', 'AUTO')
            temperature: The temperature to set (float or dict with 'cool' and 'heat' keys)
            zone_index: The index of this zone in the system

        Returns:
            Command dictionary
        """
        command = {"command": {"type": "set-settings"}}

        if mode.upper() == "COOL":
            command["command"][f"RemoteZoneInfo[{zone_index}].TemperatureSetpoint_Cool_oC"] = temperature
        elif mode.upper() == "HEAT":
            command["command"][f"RemoteZoneInfo[{zone_index}].TemperatureSetpoint_Heat_oC"] = temperature
        elif mode.upper() == "AUTO":
            if isinstance(temperature, dict) and "cool" in temperature and "heat" in temperature:
                command["command"][f"RemoteZoneInfo[{zone_index}].TemperatureSetpoint_Cool_oC"] = temperature["cool"]
                command["command"][f"RemoteZoneInfo[{zone_index}].TemperatureSetpoint_Heat_oC"] = temperature["heat"]

        return command

    def set_enable_command(self, zone_index: int, is_enabled: bool,
                          current_zones: List[bool]) -> Dict[str, Any]:
        """
        Create a command to enable or disable this zone.

        Args:
            zone_index: The index of this zone in the system
            is_enabled: True to enable, False to disable
            current_zones: Current state of all zones

        Returns:
            Command dictionary
        """
        # Create a copy of the current zones
        updated_zones = current_zones.copy()

        # Update the specific zone
        if zone_index < len(updated_zones):
            updated_zones[zone_index] = is_enabled

        return {
            "command": {
                "UserAirconSettings.EnabledZones": updated_zones,
                "type": "set-settings",
            }
        }

    def set_parent_status(self, parent: "ActronStatus", zone_index: int) -> None:
        """Set reference to parent ActronStatus object and this zone's index"""
        self._parent_status = parent
        self._zone_index = zone_index

    async def set_temperature(self, mode: str, temperature: Union[float, Dict[str, float]]) -> Dict[str, Any]:
        """
        Set temperature for this zone and send the command.

        Args:
            mode: The mode ('COOL', 'HEAT', 'AUTO')
            temperature: The temperature to set (float or dict with 'cool' and 'heat' keys)

        Returns:
            API response dictionary
        """
        if self._zone_index is None:
            raise ValueError("Zone index not set")

        command = self.set_temperature_command(mode, temperature, self._zone_index)
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
        if self._zone_index is None:
            raise ValueError("Zone index not set")

        if self._parent_status and self._parent_status.user_aircon_settings:
            command = self.set_enable_command(
                self._zone_index,
                is_enabled,
                self._parent_status.user_aircon_settings.enabled_zones
            )
            if self._parent_status._api and hasattr(self._parent_status, "serial_number"):
                return await self._parent_status._api.send_command(self._parent_status.serial_number, command)
        raise ValueError("No API reference available to send command")
