"""Status models for Actron Neo API"""
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field

# Forward references for imports from other modules
from .zone import ActronAirNeoZone
from .system import ActronAirNeoACSystem, ActronAirNeoLiveAircon, ActronAirNeoMasterInfo
from .settings import ActronAirNeoUserAirconSettings


class ActronAirNeoStatus(BaseModel):
    is_online: bool = Field(False, alias="isOnline")
    last_known_state: Dict[str, Any] = Field({}, alias="lastKnownState")
    ac_system: Optional[ActronAirNeoACSystem] = None
    user_aircon_settings: Optional[ActronAirNeoUserAirconSettings] = None
    master_info: Optional[ActronAirNeoMasterInfo] = None
    live_aircon: Optional[ActronAirNeoLiveAircon] = None
    remote_zone_info: List[ActronAirNeoZone] = Field([], alias="RemoteZoneInfo")
    _api: Optional[Any] = None  # Reference to the API instance
    serial_number: Optional[str] = None  # Serial number of the AC system

    def parse_nested_components(self):
        """Parse nested components from the last_known_state"""
        if "AirconSystem" in self.last_known_state:
            self.ac_system = ActronAirNeoACSystem.model_validate(self.last_known_state["AirconSystem"])
            # Set the system name from NV_SystemSettings if available
            if "NV_SystemSettings" in self.last_known_state:
                system_name = self.last_known_state["NV_SystemSettings"].get("SystemName", "")
                if system_name and self.ac_system:
                    self.ac_system.system_name = system_name

            # Set serial number from the AirconSystem data
            if self.ac_system and self.ac_system.master_serial:
                self.serial_number = self.ac_system.master_serial

            # Set parent reference for ACSystem
            if self.ac_system:
                self.ac_system.set_parent_status(self)

        if "UserAirconSettings" in self.last_known_state:
            self.user_aircon_settings = ActronAirNeoUserAirconSettings.model_validate(self.last_known_state["UserAirconSettings"])
            # Set parent reference
            if self.user_aircon_settings:
                self.user_aircon_settings.set_parent_status(self)

        if "MasterInfo" in self.last_known_state:
            self.master_info = ActronAirNeoMasterInfo.model_validate(self.last_known_state["MasterInfo"])

        if "LiveAircon" in self.last_known_state:
            self.live_aircon = ActronAirNeoLiveAircon.model_validate(self.last_known_state["LiveAircon"])

        if "RemoteZoneInfo" in self.last_known_state:
            self.remote_zone_info = [ActronAirNeoZone.model_validate(zone) for zone in self.last_known_state["RemoteZoneInfo"]]
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


class ActronAirNeoEventType(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]


class ActronAirNeoEventsResponse(BaseModel):
    events: List[ActronAirNeoEventType]
