"""Status models for Actron Air API."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from .settings import ActronAirUserAirconSettings
from .system import ActronAirACSystem, ActronAirAlerts, ActronAirLiveAircon, ActronAirMasterInfo

# Forward references for imports from other modules
from .zone import ActronAirPeripheral, ActronAirZone

_LOGGER = logging.getLogger(__name__)


class ActronAirStatus(BaseModel):
    """Complete status model for an Actron Air AC system.

    Contains all system data including settings, live data, zones, and peripherals.
    Provides properties to access common status information and methods to parse
    nested components from the API response.
    """

    is_online: bool = Field(False, alias="isOnline")
    last_known_state: dict[str, Any] = Field({}, alias="lastKnownState")
    ac_system: ActronAirACSystem | None = None
    user_aircon_settings: ActronAirUserAirconSettings | None = None
    master_info: ActronAirMasterInfo | None = None
    live_aircon: ActronAirLiveAircon | None = None
    alerts: ActronAirAlerts | None = None
    remote_zone_info: list[ActronAirZone] = Field([], alias="RemoteZoneInfo")
    peripherals: list[ActronAirPeripheral] = []
    _api: Any | None = None
    serial_number: str | None = None

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization hook to parse nested components."""
        self.parse_nested_components()

    @property
    def zones(self) -> dict[int, ActronAirZone]:
        """Return zones as a dictionary with their ID as keys.

        Returns:
            Dictionary mapping zone IDs (integers) to zone objects

        """
        return dict(enumerate(self.remote_zone_info))

    @property
    def clean_filter(self) -> bool:
        """Clean filter alert status."""
        return self.alerts.clean_filter if self.alerts else False

    @property
    def defrost_mode(self) -> bool:
        """Defrost mode status."""
        return self.alerts.defrosting if self.alerts else False

    @property
    def compressor_chasing_temperature(self) -> float | None:
        """Compressor target temperature."""
        return self.live_aircon.compressor_chasing_temperature if self.live_aircon else None

    @property
    def compressor_live_temperature(self) -> float | None:
        """Current compressor temperature."""
        return self.live_aircon.compressor_live_temperature if self.live_aircon else None

    @property
    def compressor_mode(self) -> str | None:
        """Current compressor mode."""
        return self.live_aircon.compressor_mode if self.live_aircon else None

    @property
    def system_on(self) -> bool:
        """Whether the system is currently on."""
        return self.live_aircon.is_on if self.live_aircon else False

    @property
    def outdoor_temperature(self) -> float | None:
        """Current outdoor temperature in Celsius."""
        return self.master_info.live_outdoor_temp_c if self.master_info else None

    @property
    def humidity(self) -> float | None:
        """Current humidity percentage."""
        return self.master_info.live_humidity_pc if self.master_info else None

    @property
    def compressor_speed(self) -> float | None:
        """Current compressor speed."""
        if self.live_aircon and self.live_aircon.outdoor_unit:
            return self.live_aircon.outdoor_unit.comp_speed
        return 0.0

    @property
    def compressor_power(self) -> int | None:
        """Current compressor power consumption in watts."""
        if self.live_aircon and self.live_aircon.outdoor_unit:
            return self.live_aircon.outdoor_unit.comp_power
        return 0

    def parse_nested_components(self) -> None:
        """Parse nested components from the last_known_state.

        Extracts and validates nested objects like AirconSystem, UserAirconSettings,
        MasterInfo, LiveAircon, Alerts, and RemoteZoneInfo from the raw API response.
        Sets parent references on all child objects to enable bidirectional navigation.
        """
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
            self.user_aircon_settings = ActronAirUserAirconSettings.model_validate(
                self.last_known_state["UserAirconSettings"]
            )
            # Set parent reference
            if self.user_aircon_settings:
                self.user_aircon_settings.set_parent_status(self)

        if "MasterInfo" in self.last_known_state:
            self.master_info = ActronAirMasterInfo.model_validate(
                self.last_known_state["MasterInfo"]
            )

        if "LiveAircon" in self.last_known_state:
            self.live_aircon = ActronAirLiveAircon.model_validate(
                self.last_known_state["LiveAircon"]
            )

        if "Alerts" in self.last_known_state:
            self.alerts = ActronAirAlerts.model_validate(self.last_known_state["Alerts"])

        if "RemoteZoneInfo" in self.last_known_state:
            self.remote_zone_info = [
                ActronAirZone.model_validate(zone)
                for zone in self.last_known_state["RemoteZoneInfo"]
            ]
            # Set parent reference for each zone
            for i, zone in enumerate(self.remote_zone_info):
                zone.set_parent_status(self, i)

    def set_api(self, api: Any) -> None:
        """Set the API reference to enable direct command sending.

        Args:
            api: Reference to the ActronAirAPI instance

        """
        self._api = api

    @property
    def api(self) -> Any | None:
        """Get the API reference for sending commands.

        Returns:
            The ActronAirAPI instance or None if not set

        """
        return self._api

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature that can be set."""
        try:
            return self.last_known_state["NV_Limits"]["UserSetpoint_oC"]["setCool_Min"]
        except (KeyError, TypeError):
            return 16.0  # Sensible default minimum temperature

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature that can be set."""
        try:
            return self.last_known_state["NV_Limits"]["UserSetpoint_oC"]["setCool_Max"]
        except (KeyError, TypeError):
            return 32.0  # Sensible default maximum temperature

    def _process_peripherals(self) -> None:
        """Process peripheral devices from the last_known_state and extract their sensor data.

        Peripherals are additional sensors (temperature, humidity) that can be assigned
        to zones. This method creates ActronAirPeripheral objects from the raw data
        and maps their readings to the appropriate zones.
        """
        aircon_system = self.last_known_state.get("AirconSystem", {})
        peripherals_data = aircon_system.get("Peripherals")

        if not peripherals_data:
            self.peripherals = []
            return

        self.peripherals = []

        for peripheral_data in peripherals_data:
            if not peripheral_data:
                continue

            try:
                peripheral = ActronAirPeripheral.from_peripheral_data(peripheral_data)
                if peripheral:
                    # Set parent reference so zones property can work
                    peripheral.set_parent_status(self)
                    self.peripherals.append(peripheral)
            except (ValidationError, ValueError, TypeError, KeyError) as e:
                # Graceful degradation: log warning and continue with other peripherals
                _LOGGER.warning("Failed to parse peripheral: %s", e)

        # Map peripheral sensor data to zones
        self._map_peripheral_data_to_zones()

    def _map_peripheral_data_to_zones(self) -> None:
        """Map peripheral sensor data to their assigned zones.

        Updates zone objects with actual humidity readings from their assigned
        peripheral devices, replacing the default system-wide humidity value
        with zone-specific sensor data.
        """
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

    def get_peripheral_for_zone(self, zone_index: int) -> ActronAirPeripheral | None:
        """Get the peripheral device assigned to a specific zone.

        Args:
            zone_index: The index of the zone

        Returns:
            The peripheral device assigned to the zone, or None if not found

        Raises:
            ValueError: If zone_index is negative

        """
        if zone_index < 0:
            raise ValueError(f"zone_index must be non-negative, got {zone_index}")

        if not self.peripherals:
            return None

        for peripheral in self.peripherals:
            if zone_index in peripheral.zone_assignments:
                return peripheral

        return None
