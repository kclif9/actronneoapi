"""Status models for Actron Neo API"""
from typing import Dict, List, Optional, Union, Any, Tuple
from pydantic import BaseModel, Field

# Forward references for imports from other modules
from .zone import ActronAirNeoZone, ActronAirNeoPeripheral
from .system import ActronAirNeoACSystem, ActronAirNeoLiveAircon, ActronAirNeoMasterInfo
from .settings import ActronAirNeoUserAirconSettings


class SensorDefinition:
    """Define a sensor with its path and attribute name"""
    def __init__(self, path: List[str], attribute: str, default: Any = None):
        self.path = path
        self.attribute = attribute
        self.default = default


class ActronAirNeoStatus(BaseModel):
    is_online: bool = Field(False, alias="isOnline")
    last_known_state: Dict[str, Any] = Field({}, alias="lastKnownState")
    ac_system: Optional[ActronAirNeoACSystem] = None
    user_aircon_settings: Optional[ActronAirNeoUserAirconSettings] = None
    master_info: Optional[ActronAirNeoMasterInfo] = None
    live_aircon: Optional[ActronAirNeoLiveAircon] = None
    remote_zone_info: List[ActronAirNeoZone] = Field([], alias="RemoteZoneInfo")
    peripherals: List[ActronAirNeoPeripheral] = []
    _api: Optional[Any] = None  # Reference to the API instance
    serial_number: Optional[str] = None  # Serial number of the AC system

    # Define all sensors in a single place for easier maintenance
    _sensors = {
        "clean_filter": SensorDefinition(["Alerts"], "CleanFilter", False),
        "defrost_mode": SensorDefinition(["Alerts"], "Defrosting", False),
        "compressor_chasing_temperature": SensorDefinition(["LiveAircon"], "CompressorChasingTemperature"),
        "compressor_live_temperature": SensorDefinition(["LiveAircon"], "CompressorLiveTemperature"),
        "compressor_mode": SensorDefinition(["LiveAircon"], "CompressorMode"),
        "system_on": SensorDefinition(["LiveAircon"], "SystemOn", False),
        "compressor_speed": SensorDefinition(["LiveAircon", "OutdoorUnit"], "CompSpeed", 0.0),
        "compressor_power": SensorDefinition(["LiveAircon", "OutdoorUnit"], "CompPower", 0),
        "outdoor_temperature": SensorDefinition(["MasterInfo"], "LiveOutdoorTemp_oC"),
        "humidity": SensorDefinition(["MasterInfo"], "LiveHumidity_pc"),
    }

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

            # Process peripherals if available
            self._process_peripherals()

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

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature that can be set."""
        return (
            self.last_known_state.get("NV_Limits", {})
            .get("UserSetpoint_oC", {})
            .get("setCool_Min", 16.0)
        )

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature that can be set."""
        return (
            self.last_known_state.get("NV_Limits", {})
            .get("UserSetpoint_oC", {})
            .get("setCool_Max", 32.0)
        )

    def _process_peripherals(self) -> None:
        """Process peripheral devices from the last_known_state and extract their sensor data"""
        if not self.last_known_state.get("AirconSystem", {}).get("Peripherals"):
            return

        peripherals_data = self.last_known_state["AirconSystem"]["Peripherals"]
        self.peripherals = []

        for peripheral_data in peripherals_data:
            if not peripheral_data:
                continue

            peripheral = ActronAirNeoPeripheral.from_peripheral_data(peripheral_data)
            if peripheral:
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

    def get_peripheral_for_zone(self, zone_index: int) -> Optional[ActronAirNeoPeripheral]:
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
        return self.get_value_by_path(sensor.path, sensor.attribute, sensor.default)

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

        # Try direct access to raw JSON data in last_known_state
        try:
            current = self.last_known_state
            for key in path:
                if key not in current:
                    raise KeyError(f"Key {key} not found")
                current = current[key]
            return current.get(attribute_name, default)
        except (KeyError, AttributeError, TypeError):
            pass  # Fall back to object-oriented access

        # Map the top-level path to the corresponding attribute
        current = None
        if path[0] == "LiveAircon":
            current = self.live_aircon
        elif path[0] == "UserAirconSettings":
            current = self.user_aircon_settings
        elif path[0] == "MasterInfo":
            current = self.master_info
        elif path[0] == "Alerts":
            current = self.last_known_state.get("Alerts", {})

        # If we couldn't find the top-level object, return the default
        if current is None and path[0] != "Alerts":
            return default

        # Follow the rest of the path
        for key in path[1:]:
            if current is None:
                return default

            # Handle nested dictionaries vs objects
            if isinstance(current, dict):
                current = current.get(key, None)
            else:
                # For objects, try to get the attribute
                try:
                    current = getattr(current, key, None)
                except (AttributeError, TypeError):
                    return default

        # Get the final attribute
        if isinstance(current, dict):
            return current.get(attribute_name, default)
        else:
            try:
                return getattr(current, attribute_name, default)
            except (AttributeError, TypeError):
                return default

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic property access for sensors

        This allows direct access to sensor values as properties:
        - status.clean_filter
        - status.outdoor_temperature
        - etc.
        """
        if name in self._sensors:
            return self.get_sensor_value(name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class ActronAirNeoEventType(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]


class ActronAirNeoEventsResponse(BaseModel):
    events: List[ActronAirNeoEventType]
