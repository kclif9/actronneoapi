from typing import Dict, List, Optional, Union, Any, Literal
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

    def set_temperature_command(self, mode: str, temperature: Union[float, Dict[str, float]]) -> Dict[str, Any]:
        """
        Create a command to set temperature for the main system.

        Args:
            mode: The mode ('COOL', 'HEAT', 'AUTO')
            temperature: The temperature to set (float or dict with 'cool' and 'heat' keys)

        Returns:
            Command dictionary
        """
        command = {"command": {"type": "set-settings"}}

        if mode.upper() == "COOL":
            command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = temperature
        elif mode.upper() == "HEAT":
            command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = temperature
        elif mode.upper() == "AUTO":
            if isinstance(temperature, dict) and "cool" in temperature and "heat" in temperature:
                command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = temperature["cool"]
                command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = temperature["heat"]

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

    async def set_temperature(self, mode: str, temperature: Union[float, Dict[str, float]]) -> Dict[str, Any]:
        """
        Set temperature for the main system and send the command.

        Args:
            mode: The mode ('COOL', 'HEAT', 'AUTO')
            temperature: The temperature to set (float or dict with 'cool' and 'heat' keys)

        Returns:
            API response dictionary
        """
        command = self.set_temperature_command(mode, temperature)
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

class LiveAircon(BaseModel):
    is_on: bool = Field(False, alias="SystemOn")
    compressor_mode: str = Field("", alias="CompressorMode")
    compressor_capacity: int = Field(0, alias="CompressorCapacity")
    fan_rpm: int = Field(0, alias="FanRPM")
    defrost: bool = Field(False, alias="Defrost")

class MasterInfo(BaseModel):
    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_outdoor_temp_c: float = Field(0.0, alias="LiveOutdoorTemp_oC")

class ACSystem(BaseModel):
    master_wc_model: str = Field("", alias="MasterWCModel")
    master_serial: str = Field("", alias="MasterSerial")
    master_wc_firmware_version: str = Field("", alias="MasterWCFirmwareVersion")
    system_name: str = Field("", alias="SystemName")

class ActronStatus(BaseModel):
    is_online: bool = Field(False, alias="isOnline")
    last_known_state: Dict[str, Any] = Field({}, alias="lastKnownState")
    ac_system: Optional[ACSystem] = None
    user_aircon_settings: Optional[UserAirconSettings] = None
    master_info: Optional[MasterInfo] = None
    live_aircon: Optional[LiveAircon] = None
    remote_zone_info: List[Zone] = Field([], alias="RemoteZoneInfo")
    _api: Optional[Any] = None  # Reference to the API instance
    serial_number: Optional[str] = None  # Serial number of the AC system

    def parse_nested_components(self):
        """Parse nested components from the last_known_state"""
        if "AirconSystem" in self.last_known_state:
            self.ac_system = ACSystem.model_validate(self.last_known_state["AirconSystem"])
            # Set the system name from NV_SystemSettings if available
            if "NV_SystemSettings" in self.last_known_state:
                system_name = self.last_known_state["NV_SystemSettings"].get("SystemName", "")
                if system_name and self.ac_system:
                    self.ac_system.system_name = system_name

            # Set serial number from the AirconSystem data
            if self.ac_system and self.ac_system.master_serial:
                self.serial_number = self.ac_system.master_serial

        if "UserAirconSettings" in self.last_known_state:
            self.user_aircon_settings = UserAirconSettings.model_validate(self.last_known_state["UserAirconSettings"])
            # Set parent reference
            if self.user_aircon_settings:
                self.user_aircon_settings.set_parent_status(self)

        if "MasterInfo" in self.last_known_state:
            self.master_info = MasterInfo.model_validate(self.last_known_state["MasterInfo"])

        if "LiveAircon" in self.last_known_state:
            self.live_aircon = LiveAircon.model_validate(self.last_known_state["LiveAircon"])

        if "RemoteZoneInfo" in self.last_known_state:
            self.remote_zone_info = [Zone.model_validate(zone) for zone in self.last_known_state["RemoteZoneInfo"]]
            # Set parent reference for each zone
            for i, zone in enumerate(self.remote_zone_info):
                zone.set_parent_status(self, i)

    def set_api(self, api: Any) -> None:
        """
        Set the API reference to enable direct command sending.

        Args:
            api: Reference to the ActronNeoAPI instance
        """
        self._api = api

class EventType(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]

class EventsResponse(BaseModel):
    events: List[EventType]
