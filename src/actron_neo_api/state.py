import logging
import re
from typing import Dict, List, Optional, Any, Callable, Set, Tuple

from .models import ActronStatus, EventsResponse

_LOGGER = logging.getLogger(__name__)

class StateManager:
    """
    Manages the state of Actron Neo systems, handling updates and state merging.
    """

    def __init__(self):
        self.status: Dict[str, ActronStatus] = {}
        self.latest_event_id: Dict[str, str] = {}
        self._observers: List[Callable[[str, Dict[str, Any]], None]] = []
        self._api: Optional[Any] = None

    def set_api(self, api: Any) -> None:
        """
        Set the API reference to be passed to status objects.

        Args:
            api: Reference to the ActronNeoAPI instance
        """
        self._api = api

        # Update existing status objects with the API reference
        for status in self.status.values():
            status.set_api(api)

    def add_observer(self, observer: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add an observer to be notified of state changes."""
        self._observers.append(observer)

    def get_status(self, serial_number: str) -> Optional[ActronStatus]:
        """Get the status for a specific system."""
        return self.status.get(serial_number)

    def process_status_update(self, serial_number: str, status_data: Dict[str, Any]) -> ActronStatus:
        """Process a full status update for a system."""
        status = ActronStatus.model_validate(status_data)
        status.parse_nested_components()

        # Set serial number and API reference
        status.serial_number = serial_number
        if self._api:
            status.set_api(self._api)

        # Extract zone-specific humidity from peripherals
        self._map_peripheral_humidity_to_zones(status)

        self.status[serial_number] = status

        # Notify observers
        for observer in self._observers:
            observer(serial_number, status_data)

        return status

    def process_events(self, serial_number: str, events_data: Dict[str, Any]) -> Optional[ActronStatus]:
        """Process events for a system and update state accordingly."""
        events_response = EventsResponse.model_validate(events_data)

        if not events_response.events:
            return self.status.get(serial_number)

        # Track the latest event ID
        self.latest_event_id[serial_number] = events_response.events[0].id

        # Process events in reverse order (oldest to newest)
        for event in reversed(events_response.events):
            if event.type == "full-status-broadcast":
                # Replace the full state
                if serial_number in self.status:
                    self.status[serial_number].last_known_state = event.data
                    self.status[serial_number].parse_nested_components()
                else:
                    status = ActronStatus(isOnline=True, lastKnownState=event.data)
                    status.parse_nested_components()
                    # Set serial number and API reference
                    status.serial_number = serial_number
                    if self._api:
                        status.set_api(self._api)
                    self.status[serial_number] = status

                # Extract zone-specific humidity from peripherals
                self._map_peripheral_humidity_to_zones(self.status[serial_number])

                # Notify observers
                for observer in self._observers:
                    observer(serial_number, event.data)

            elif event.type == "status-change-broadcast":
                # Incremental update
                if serial_number in self.status:
                    self._merge_incremental_update(
                        self.status[serial_number].last_known_state,
                        event.data
                    )
                    self.status[serial_number].parse_nested_components()

                    # Extract zone-specific humidity from peripherals after update
                    self._map_peripheral_humidity_to_zones(self.status[serial_number])

                    # Notify observers
                    changed_paths = self._get_changed_paths(event.data)
                    for observer in self._observers:
                        observer(serial_number, {"changed_paths": changed_paths})

        return self.status.get(serial_number)

    def _map_peripheral_humidity_to_zones(self, status: ActronStatus) -> None:
        """
        Map humidity values from peripherals to their respective zones.

        The Actron Neo API reports the same central humidity value for all zones,
        but each zone controller has its own humidity sensor. This method extracts
        the actual zone-specific humidity values and associates them with the correct zones.
        """
        if not status or "AirconSystem" not in status.last_known_state:
            return

        # Create a mapping of peripheral zone assignments to zone indices
        peripherals = status.last_known_state.get("AirconSystem", {}).get("Peripherals", [])
        if not peripherals:
            return

        # Track zone assignments from peripherals
        zone_humidity_map = {}

        for peripheral in peripherals:
            # Check if peripheral has humidity sensor data
            humidity = self._extract_peripheral_humidity(peripheral)
            if humidity is None:
                continue

            # Get zone assignments for this peripheral
            zone_assignments = peripheral.get("ZoneAssignment", [])
            for zone_index in zone_assignments:
                if isinstance(zone_index, int) and 0 <= zone_index < len(status.remote_zone_info):
                    zone_humidity_map[zone_index] = humidity

        # Update zones with actual humidity values
        for i, zone in enumerate(status.remote_zone_info):
            if i in zone_humidity_map:
                zone.actual_humidity_pc = zone_humidity_map[i]

    def _extract_peripheral_humidity(self, peripheral: Dict[str, Any]) -> Optional[float]:
        """
        Extract humidity reading from a peripheral device.

        Args:
            peripheral: Peripheral device data from API response

        Returns:
            Humidity value as float or None if not available
        """
        sensor_inputs = peripheral.get("SensorInputs", {})
        if not sensor_inputs:
            return None

        # Extract humidity from SHTC1 sensor if available
        shtc1 = sensor_inputs.get("SHTC1", {})
        if shtc1:
            humidity = shtc1.get("RelativeHumidity_pc")
            if humidity and isinstance(humidity, (int, float)) and 0 <= humidity <= 100:
                return float(humidity)

        return None

    def _get_changed_paths(self, incremental_data: Dict[str, Any]) -> Set[str]:
        """Get the paths (dot notation) of changed fields in the incremental update."""
        paths = set()
        for key in incremental_data:
            if not key.startswith('@'):
                paths.add(key)
        return paths

    def _merge_incremental_update(self, full_state: Dict[str, Any], incremental_data: Dict[str, Any]) -> None:
        """Merge incremental updates into the full state."""
        for key, value in incremental_data.items():
            if key.startswith("@"):
                continue

            keys = key.split(".")
            current = full_state

            for part in keys[:-1]:
                match = re.match(r"(.+)\[(\d+)\]$", part)
                if match:
                    array_key, index = match.groups()
                    index = int(index)

                    if array_key not in current:
                        current[array_key] = []

                    while len(current[array_key]) <= index:
                        current[array_key].append({})

                    current = current[array_key][index]
                else:
                    if part not in current:
                        current[part] = {}
                    current = current[part]

            final_key = keys[-1]
            match = re.match(r"(.+)\[(\d+)\]$", final_key)
            if match:
                array_key, index = match.groups()
                index = int(index)

                if array_key not in current:
                    current[array_key] = []

                while len(current[array_key]) <= index:
                    current[array_key].append({})

                if isinstance(current[array_key][index], dict) and isinstance(value, dict):
                    current[array_key][index].update(value)
                else:
                    current[array_key][index] = value
            else:
                current[final_key] = value
