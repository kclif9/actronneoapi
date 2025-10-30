"""Status models for Actron Air API"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

# Forward references for imports from other modules
from .zone import ActronAirZone, ActronAirPeripheral
from .system import (
    ActronAirACSystem,
    ActronAirLiveAircon,
    ActronAirMasterInfo,
    ActronAirAlerts
)
from .settings import ActronAirUserAirconSettings


class ActronAirStatus(BaseModel):
    is_online: bool = Field(False, alias="isOnline")
    last_known_state: Dict[str, Any] = Field({}, alias="lastKnownState")
    ac_system: Optional[ActronAirACSystem] = None
    user_aircon_settings: Optional[ActronAirUserAirconSettings] = None
    master_info: Optional[ActronAirMasterInfo] = None
    live_aircon: Optional[ActronAirLiveAircon] = None
    alerts: Optional[ActronAirAlerts] = None
    remote_zone_info: List[ActronAirZone] = Field([], alias="RemoteZoneInfo")
    peripherals: List[ActronAirPeripheral] = []
    _api: Optional[Any] = None
    serial_number: Optional[str] = None

    @property
    def zones(self) -> Dict[int, ActronAirZone]:
        """
        Return zones as a dictionary with their ID as keys.

        Returns:
            Dictionary mapping zone IDs (integers) to zone objects
        """
        return dict(enumerate(self.remote_zone_info))

    @property
    def clean_filter(self) -> bool:
        """Clean filter alert status"""
        return self.alerts.clean_filter if self.alerts else False

    @property
    def defrost_mode(self) -> bool:
        """Defrost mode status"""
        return self.alerts.defrosting if self.alerts else False

    @property
    def compressor_chasing_temperature(self) -> Optional[float]:
        """Compressor target temperature"""
        return self.live_aircon.compressor_chasing_temperature if self.live_aircon else None

    @property
    def compressor_live_temperature(self) -> Optional[float]:
        """Current compressor temperature"""
        return self.live_aircon.compressor_live_temperature if self.live_aircon else None

    @property
    def compressor_mode(self) -> Optional[str]:
        """Current compressor mode"""
        return self.live_aircon.compressor_mode if self.live_aircon else None

    @property
    def system_on(self) -> bool:
        """Whether the system is currently on"""
        return self.live_aircon.is_on if self.live_aircon else False

    @property
    def outdoor_temperature(self) -> Optional[float]:
        """Current outdoor temperature in Celsius"""
        return self.master_info.live_outdoor_temp_c if self.master_info else None

    @property
    def humidity(self) -> Optional[float]:
        """Current humidity percentage"""
        return self.master_info.live_humidity_pc if self.master_info else None

    @property
    def compressor_speed(self) -> Optional[float]:
        """Current compressor speed"""
        if self.live_aircon and self.live_aircon.outdoor_unit:
            return self.live_aircon.outdoor_unit.comp_speed
        return 0.0

    @property
    def compressor_power(self) -> Optional[int]:
        """Current compressor power consumption in watts"""
        if self.live_aircon and self.live_aircon.outdoor_unit:
            return self.live_aircon.outdoor_unit.comp_power
        return 0

    def parse_nested_components(self):
        """Parse nested components from the last_known_state"""
        if "AirconSystem" in self.last_known_state:
            self.ac_system = ActronAirACSystem.model_validate(self.last_known_state["AirconSystem"])
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

            # Process peripherals if available
            self._process_peripherals()

        if "UserAirconSettings" in self.last_known_state:
            self.user_aircon_settings = ActronAirUserAirconSettings.model_validate(self.last_known_state["UserAirconSettings"])
            # Set parent reference
            if self.user_aircon_settings:
                self.user_aircon_settings.set_parent_status(self)

        if "MasterInfo" in self.last_known_state:
            self.master_info = ActronAirMasterInfo.model_validate(self.last_known_state["MasterInfo"])

        if "LiveAircon" in self.last_known_state:
            self.live_aircon = ActronAirLiveAircon.model_validate(self.last_known_state["LiveAircon"])

        if "Alerts" in self.last_known_state:
            self.alerts = ActronAirAlerts.model_validate(self.last_known_state["Alerts"])

        if "RemoteZoneInfo" in self.last_known_state:
            self.remote_zone_info = [ActronAirZone.model_validate(zone) for zone in self.last_known_state["RemoteZoneInfo"]]
            # Set parent reference for each zone
            for i, zone in enumerate(self.remote_zone_info):
                zone.set_parent_status(self, i)

    def set_api(self, api: Any) -> None:
        """
        Set the API reference to enable direct command sending.

        Args:
            api: Reference to the ActronAirAPI instance
        """
        self._api = api

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature that can be set."""
        return (
            self.last_known_state['NV_Limits']['UserSetpoint_oC']['setCool_Min']
        )

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature that can be set."""
        return (
            self.last_known_state['NV_Limits']['UserSetpoint_oC']['setCool_Max']
        )

    def _process_peripherals(self) -> None:
        """Process peripheral devices from the last_known_state and extract their sensor data"""
        if not self.last_known_state['AirconSystem']['Peripherals']:
            return

        peripherals_data = self.last_known_state["AirconSystem"]["Peripherals"]
        self.peripherals = []

        for peripheral_data in peripherals_data:
            if not peripheral_data:
                continue

            peripheral = ActronAirPeripheral.from_peripheral_data(peripheral_data)
            if peripheral:
                # Set parent reference so zones property can work
                peripheral.set_parent_status(self)
                self.peripherals.append(peripheral)

        # Map peripheral sensor data to zones
        self._map_peripheral_data_to_zones()

    def _map_peripheral_data_to_zones(self) -> None:
        """Map peripheral sensor data to their assigned zones"""
        if not self.peripherals or not self.remote_zone_info:
            return

        # Create mapping of zone index to peripheral
        zone_peripheral_map = {}

        for peripheral in self.peripherals:
            for zone_index in peripheral.zone_assignments:
                if isinstance(zone_index, int) and 0 <= zone_index < len(self.remote_zone_info):
                    zone_peripheral_map[zone_index] = peripheral

        # Update zones with peripheral data
        for i, zone in enumerate(self.remote_zone_info):
            if i in zone_peripheral_map:
                peripheral = zone_peripheral_map[i]
                # Update zone with peripheral sensor data
                if peripheral.humidity is not None:
                    zone.actual_humidity_pc = peripheral.humidity
                # The temperature will be automatically used through the existing properties

    def get_peripheral_for_zone(self, zone_index: int) -> Optional[ActronAirPeripheral]:
        """
        Get the peripheral device assigned to a specific zone

        Args:
            zone_index: The index of the zone

        Returns:
            The peripheral device assigned to the zone, or None if not found
        """
        if not self.peripherals:
            return None

        for peripheral in self.peripherals:
            if zone_index in peripheral.zone_assignments:
                return peripheral

        return None

    def get_sensor_value(self, sensor_name: str) -> Any:
        """
        Get a sensor value by its name.

        Args:
            sensor_name: The name of the sensor

        Returns:
            The value of the sensor, or None if not found
        """
        if sensor_name not in self._sensors:
            return None

        sensor = self._sensors[sensor_name]
        return self._get_value_by_path_direct(sensor.path, sensor.attribute, sensor.default)

    def _get_value_by_path_direct(self, path: List[str], attribute_name: str, default: Any = None) -> Any:
        """
        Direct access to the raw JSON data in last_known_state
        This is a simplified version used by sensor properties to avoid recursion
        """
        if not path:
            return self.last_known_state.get(attribute_name, default)

        try:
            current = self.last_known_state
            for key in path:
                if key not in current:
                    return default
                current = current[key]
            return current.get(attribute_name, default)
        except (KeyError, AttributeError, TypeError):
            return default

    def get_value_by_path(self, path: List[str], attribute_name: str, default: Any = None) -> Any:
        """
        Get a value from the nested structure by following a path of keys.

        Args:
            path: A list of keys to follow in the hierarchy
            attribute_name: The name of the attribute to retrieve at the end of the path
            default: Default value to return if the path or attribute doesn't exist

        Returns:
            The value at the specified path, or the default if not found
        """
        if not path:
            return self.last_known_state.get(attribute_name, default)

        try:
            current = self.last_known_state
            for key in path:
                if key not in current:
                    return default
                current = current[key]
            return current.get(attribute_name, default)
        except (KeyError, AttributeError, TypeError):
            return default


class ActronAirEventType(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]


class ActronAirEventsResponse(BaseModel):
    events: List[ActronAirEventType]
