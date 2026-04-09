"""Status models for Actron Air API."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..const import AC_MODE_HEAT, DEFAULT_MAX_SETPOINT, DEFAULT_MIN_SETPOINT
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
    last_known_state: dict[str, Any] = Field(default_factory=dict, alias="lastKnownState")
    ac_system: ActronAirACSystem = Field(
        default_factory=lambda: ActronAirACSystem.model_validate({})
    )
    user_aircon_settings: ActronAirUserAirconSettings = Field(
        default_factory=lambda: ActronAirUserAirconSettings.model_validate({})
    )
    master_info: ActronAirMasterInfo = Field(
        default_factory=lambda: ActronAirMasterInfo.model_validate({})
    )
    live_aircon: ActronAirLiveAircon = Field(
        default_factory=lambda: ActronAirLiveAircon.model_validate({})
    )
    alerts: ActronAirAlerts = Field(default_factory=lambda: ActronAirAlerts.model_validate({}))
    remote_zone_info: list[ActronAirZone] = Field(default_factory=list, alias="RemoteZoneInfo")
    peripherals: list[ActronAirPeripheral] = Field(default_factory=list)
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
        return self.alerts.clean_filter

    @property
    def defrost_mode(self) -> bool:
        """Defrost mode status."""
        return self.alerts.defrosting

    @property
    def compressor_chasing_temperature(self) -> float:
        """Compressor target temperature."""
        return self.live_aircon.compressor_chasing_temperature

    @property
    def compressor_live_temperature(self) -> float:
        """Current compressor temperature."""
        return self.live_aircon.compressor_live_temperature

    @property
    def compressor_mode(self) -> str:
        """Current compressor mode."""
        return self.live_aircon.compressor_mode

    @property
    def system_on(self) -> bool:
        """Whether the system is currently on."""
        return self.live_aircon.is_on

    @property
    def outdoor_temperature(self) -> float:
        """Current outdoor temperature in Celsius."""
        return self.master_info.live_outdoor_temp_c

    @property
    def humidity(self) -> float:
        """Current humidity percentage."""
        return self.master_info.live_humidity_pc

    @property
    def compressor_speed(self) -> float:
        """Current compressor speed."""
        return self.live_aircon.outdoor_unit.comp_speed

    @property
    def compressor_power(self) -> int:
        """Current compressor power consumption in watts."""
        return self.live_aircon.outdoor_unit.comp_power

    def parse_nested_components(self) -> None:
        """Parse nested components from the last_known_state.

        Extracts and validates nested objects like AirconSystem, UserAirconSettings,
        MasterInfo, LiveAircon, Alerts, and RemoteZoneInfo from the raw API response.
        Sets parent references on all child objects to enable bidirectional navigation.

        Each nested component is parsed independently with graceful degradation:
        a malformed section is logged and skipped so the remaining components are
        still available.
        """
        # Reset all parsed fields so a re-parse after last_known_state
        # changes never leaves stale objects from a previous call.
        # serial_number is intentionally preserved: it may have been set
        # externally and will be overwritten by _parse_aircon_system when
        # AirconSystem data is present.
        self.ac_system = ActronAirACSystem.model_validate({})
        self.user_aircon_settings = ActronAirUserAirconSettings.model_validate({})
        self.master_info = ActronAirMasterInfo.model_validate({})
        self.live_aircon = ActronAirLiveAircon.model_validate({})
        self.alerts = ActronAirAlerts.model_validate({})
        self.remote_zone_info = []
        self.peripherals = []

        # Set parent references on default instances so callers can
        # safely access properties even when sections are missing/malformed.
        self.ac_system.set_parent_status(self)
        self.user_aircon_settings.set_parent_status(self)

        self._parse_aircon_system()
        self._parse_user_aircon_settings()
        self._parse_master_info()
        self._parse_live_aircon()
        self._parse_alerts()
        self._parse_remote_zones()

        # Map peripheral sensor data to zones (must run after both peripherals and zones are parsed)
        self._map_peripheral_data_to_zones()

    def _parse_aircon_system(self) -> None:
        """Parse AirconSystem data from last_known_state."""
        aircon_system_data = self.last_known_state.get("AirconSystem")
        if not isinstance(aircon_system_data, dict):
            return

        # Peripherals live under AirconSystem but are parsed independently
        # so they survive even when the ACSystem model itself is invalid.
        self._process_peripherals()

        try:
            self.ac_system = ActronAirACSystem.model_validate(aircon_system_data)
        except (ValidationError, ValueError, TypeError) as e:
            _LOGGER.warning("Failed to parse AirconSystem: %s", e)
            return

        # Set the system name from NV_SystemSettings if available
        nv_system_settings = self.last_known_state.get("NV_SystemSettings")
        if isinstance(nv_system_settings, dict):
            system_name = nv_system_settings.get("SystemName", "")
            if system_name and self.ac_system:
                self.ac_system.system_name = system_name

        # Set serial number from the AirconSystem data
        if self.ac_system and self.ac_system.master_serial:
            self.serial_number = self.ac_system.master_serial

        # Set parent reference for ACSystem
        if self.ac_system:
            self.ac_system.set_parent_status(self)

    def _parse_user_aircon_settings(self) -> None:
        """Parse UserAirconSettings data from last_known_state."""
        user_aircon_settings_data = self.last_known_state.get("UserAirconSettings")
        if not isinstance(user_aircon_settings_data, dict):
            return
        try:
            self.user_aircon_settings = ActronAirUserAirconSettings.model_validate(
                user_aircon_settings_data
            )
        except (ValidationError, ValueError, TypeError) as e:
            _LOGGER.warning("Failed to parse UserAirconSettings: %s", e)
            return
        # Set parent reference
        if self.user_aircon_settings:
            self.user_aircon_settings.set_parent_status(self)

    def _parse_master_info(self) -> None:
        """Parse MasterInfo data from last_known_state."""
        master_info_data = self.last_known_state.get("MasterInfo")
        if not isinstance(master_info_data, dict):
            return
        try:
            self.master_info = ActronAirMasterInfo.model_validate(master_info_data)
        except (ValidationError, ValueError, TypeError) as e:
            _LOGGER.warning("Failed to parse MasterInfo: %s", e)

    def _parse_live_aircon(self) -> None:
        """Parse LiveAircon data from last_known_state."""
        live_aircon_data = self.last_known_state.get("LiveAircon")
        if not isinstance(live_aircon_data, dict):
            return
        try:
            self.live_aircon = ActronAirLiveAircon.model_validate(live_aircon_data)
        except (ValidationError, ValueError, TypeError) as e:
            _LOGGER.warning("Failed to parse LiveAircon: %s", e)

    def _parse_alerts(self) -> None:
        """Parse Alerts data from last_known_state."""
        alerts_data = self.last_known_state.get("Alerts")
        if not isinstance(alerts_data, dict):
            return
        try:
            self.alerts = ActronAirAlerts.model_validate(alerts_data)
        except (ValidationError, ValueError, TypeError) as e:
            _LOGGER.warning("Failed to parse Alerts: %s", e)

    def _parse_remote_zones(self) -> None:
        """Parse RemoteZoneInfo data from last_known_state."""
        remote_zone_data = self.last_known_state.get("RemoteZoneInfo")
        if not isinstance(remote_zone_data, list):
            return
        # Validate all entries are dicts before parsing to preserve positional
        # indices. Silently dropping non-dict entries would shift zone indices,
        # causing commands and peripheral mapping to target the wrong zone.
        if not all(isinstance(zone, dict) for zone in remote_zone_data):
            _LOGGER.warning(
                "RemoteZoneInfo contains non-dict entries, skipping zone parsing "
                "to prevent index misalignment"
            )
            return
        try:
            self.remote_zone_info = [
                ActronAirZone.model_validate(zone) for zone in remote_zone_data
            ]
        except (ValidationError, ValueError, TypeError) as e:
            _LOGGER.warning("Failed to parse RemoteZoneInfo: %s", e)
            self.remote_zone_info = []
            return
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

    def _get_current_mode(self) -> str:
        """Get the current AC mode from user settings.

        Returns:
            Uppercase mode string, e.g. 'COOL', 'HEAT', 'AUTO', 'FAN'.
            Returns empty string if mode is unavailable.

        """
        if self.user_aircon_settings and self.user_aircon_settings.mode:
            return self.user_aircon_settings.mode.upper()
        return ""

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature that can be set.

        Mode-aware: uses heat limits when in HEAT mode,
        cool limits otherwise (COOL, AUTO, FAN).
        """
        is_heat = self._get_current_mode() == AC_MODE_HEAT
        limit_key = "setHeat_Min" if is_heat else "setCool_Min"
        try:
            return float(self.last_known_state["NV_Limits"]["UserSetpoint_oC"][limit_key])
        except (KeyError, TypeError, ValueError):
            return DEFAULT_MIN_SETPOINT

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature that can be set.

        Mode-aware: uses heat limits when in HEAT mode,
        cool limits otherwise (COOL, AUTO, FAN).
        """
        is_heat = self._get_current_mode() == AC_MODE_HEAT
        limit_key = "setHeat_Max" if is_heat else "setCool_Max"
        try:
            return float(self.last_known_state["NV_Limits"]["UserSetpoint_oC"][limit_key])
        except (KeyError, TypeError, ValueError):
            return DEFAULT_MAX_SETPOINT

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

    def _map_peripheral_data_to_zones(self) -> None:
        """Map peripheral sensor data to their assigned zones.

        Updates zone objects with actual humidity readings from their assigned
        peripheral devices, replacing the default system-wide humidity value
        with zone-specific sensor data.

        Note:
            ZoneAssignment values from the API are 1-based (Zone 1, Zone 2, etc.)
            while remote_zone_info is a 0-based list. The offset is applied here.
        """
        if not self.peripherals or not self.remote_zone_info:
            return

        # Create mapping of zone list index to peripheral
        zone_peripheral_map: dict[int, ActronAirPeripheral] = {}

        for peripheral in self.peripherals:
            for zone_assignment in peripheral.zone_assignments:
                # API zone assignments are 1-based; convert to 0-based list index
                if not isinstance(zone_assignment, int):
                    continue
                adjusted_idx = zone_assignment - 1
                if 0 <= adjusted_idx < len(self.remote_zone_info):
                    zone_peripheral_map[adjusted_idx] = peripheral

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
            zone_index: The 0-based index of the zone in remote_zone_info

        Returns:
            The peripheral device assigned to the zone, or None if not found

        Raises:
            ValueError: If zone_index is negative

        """
        if zone_index < 0:
            raise ValueError(f"zone_index must be non-negative, got {zone_index}")

        if not self.peripherals:
            return None

        # API zone assignments are 1-based; convert zone_index to match
        api_zone_number = zone_index + 1
        for peripheral in self.peripherals:
            if api_zone_number in peripheral.zone_assignments:
                return peripheral

        return None
