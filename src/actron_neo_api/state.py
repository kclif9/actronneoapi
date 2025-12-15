"""State management module for Actron Air systems."""

from typing import Any, Callable, Dict, List, Optional

from .models import ActronAirStatus


class StateManager:
    """Manages the state of Actron Air systems, handling updates and state merging."""

    def __init__(self) -> None:
        """Initialize the state manager.

        Creates empty dictionaries for system status tracking and event IDs,
        and initializes observer list for state change notifications.
        """
        self.status: Dict[str, ActronAirStatus] = {}
        self.latest_event_id: Dict[str, str] = {}
        self._observers: List[Callable[[str, Dict[str, Any]], None]] = []
        self._api: Optional[Any] = None

    def set_api(self, api: Any) -> None:
        """Set the API reference to be passed to status objects.

        Args:
            api: Reference to the ActronAirAPI instance

        """
        self._api = api

        # Update existing status objects with the API reference
        for status in self.status.values():
            status.set_api(api)

    def add_observer(self, observer: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add an observer to be notified of state changes.

        Args:
            observer: Callback function that takes (serial_number, status_data)

        """
        self._observers.append(observer)

    def get_status(self, serial_number: str) -> Optional[ActronAirStatus]:
        """Get the status for a specific system.

        Args:
            serial_number: Serial number of the AC system

        Returns:
            ActronAirStatus object if found, None otherwise

        """
        # Normalize serial number to lowercase for consistent lookup
        return self.status.get(serial_number.lower())

    def process_status_update(
        self, serial_number: str, status_data: Dict[str, Any]
    ) -> ActronAirStatus:
        """Process a full status update for a system.

        Args:
            serial_number: Serial number of the AC system
            status_data: Complete status data from API

        Returns:
            Updated ActronAirStatus object

        Note:
            This parses nested components, maps peripheral data to zones,
            and notifies all registered observers.

        """
        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Normalize serial number to lowercase for consistent storage
        serial_number = serial_number.lower()

        # Set serial number and API reference
        status.serial_number = serial_number
        if self._api:
            status.set_api(self._api)

        # Extract zone-specific humidity from peripherals
        self._map_peripheral_humidity_to_zones(status)

        self.status[serial_number] = status

        # Notify observers - don't let observer errors break the update
        for observer in self._observers:
            observer(serial_number, status_data)

        return status

    def _map_peripheral_humidity_to_zones(self, status: ActronAirStatus) -> None:
        """Map humidity values from peripherals to their respective zones.

        The Actron Air API reports the same central humidity value for all zones,
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
        """Extract humidity reading from a peripheral device.

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
