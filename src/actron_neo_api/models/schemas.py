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

    @property
    def turbo_enabled(self) -> bool:
        """Get the turbo mode status, handling both the boolean and object representation"""
        if isinstance(self.turbo_mode_enabled, dict):
            return self.turbo_mode_enabled.get("Enabled", False)
        return self.turbo_mode_enabled

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

    def parse_nested_components(self):
        """Parse nested components from the last_known_state"""
        if "AirconSystem" in self.last_known_state:
            self.ac_system = ACSystem.model_validate(self.last_known_state["AirconSystem"])
            # Set the system name from NV_SystemSettings if available
            if "NV_SystemSettings" in self.last_known_state:
                system_name = self.last_known_state["NV_SystemSettings"].get("SystemName", "")
                if system_name and self.ac_system:
                    self.ac_system.system_name = system_name
        if "UserAirconSettings" in self.last_known_state:
            self.user_aircon_settings = UserAirconSettings.model_validate(self.last_known_state["UserAirconSettings"])
        if "MasterInfo" in self.last_known_state:
            self.master_info = MasterInfo.model_validate(self.last_known_state["MasterInfo"])
        if "LiveAircon" in self.last_known_state:
            self.live_aircon = LiveAircon.model_validate(self.last_known_state["LiveAircon"])
        if "RemoteZoneInfo" in self.last_known_state:
            self.remote_zone_info = [Zone.model_validate(zone) for zone in self.last_known_state["RemoteZoneInfo"]]

class EventType(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]

class EventsResponse(BaseModel):
    events: List[EventType]
