"""Zone models for Actron Air API."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from ..const import (
    AC_MODE_AUTO,
    AC_MODE_COOL,
    AC_MODE_FAN,
    AC_MODE_HEAT,
    AC_MODE_OFF,
    TEMP_AUTO_HEAT_MIN,
    TEMP_PHYSICAL_MAX,
    TEMP_PHYSICAL_MIN,
)

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .status import ActronAirStatus


class ActronAirZoneSensor(BaseModel):
    """Sensor data for a zone controller.

    Represents sensor readings from zone control units including
    temperature, humidity, battery level, and connection status.
    """

    connected: bool = Field(False, alias="Connected")
    kind: str = Field("", alias="NV_Kind")
    is_paired: bool = Field(False, alias="NV_isPaired")
    signal_strength: str = Field("NA", alias="Signal_of3")
    temperature: float = Field(0.0, alias="LiveTemp_oC")
    humidity: float = Field(0.0, alias="RelativeHumidity_pc")
    battery_level: float = Field(0.0, alias="RemainingBatteryCapacity_pc")


class ActronAirPeripheral(BaseModel):
    """Peripheral device that provides sensor data for zones.

    Peripherals are additional sensor devices that can be assigned to one or
    more zones to provide more accurate temperature and humidity readings
    than the central controller.
    """

    logical_address: int = Field(0, alias="LogicalAddress")
    device_type: str = Field("", alias="DeviceType")
    zone_assignments: list[int] = Field(default_factory=list, alias="ZoneAssignment")
    serial_number: str = Field("", alias="SerialNumber")
    battery_level: float = Field(0.0, alias="RemainingBatteryCapacity_pc")
    temperature: float | None = None
    humidity: float | None = None
    _parent_status: "ActronAirStatus | None" = None

    @property
    def zones(self) -> list["ActronAirZone"]:
        """Get the actual zone objects assigned to this peripheral.

        Returns:
            List of zone objects this peripheral is assigned to

        """
        if not self._parent_status or not self._parent_status.remote_zone_info:
            return []

        result = []
        for zone_idx in self.zone_assignments:
            adjusted_idx = zone_idx - 1
            if 0 <= adjusted_idx < len(self._parent_status.remote_zone_info):
                result.append(self._parent_status.remote_zone_info[adjusted_idx])
        return result

    @classmethod
    def from_peripheral_data(cls, peripheral_data: dict[str, Any]) -> "ActronAirPeripheral":
        """Create a peripheral instance from raw peripheral data.

        Args:
            peripheral_data: Raw peripheral data dictionary from API

        Returns:
            ActronAirPeripheral instance with extracted sensor data

        Raises:
            ValueError: If peripheral_data is None or empty

        """
        if not peripheral_data:
            raise ValueError("peripheral_data cannot be None or empty")

        peripheral = cls.model_validate(peripheral_data)

        sensor_inputs = peripheral_data.get("SensorInputs")
        if sensor_inputs and isinstance(sensor_inputs, dict):
            shtc1 = sensor_inputs.get("SHTC1")
            if shtc1 and isinstance(shtc1, dict):
                if "Temperature_oC" in shtc1:
                    try:
                        temp_value = shtc1["Temperature_oC"]
                        if isinstance(temp_value, (int, float)):
                            peripheral.temperature = float(temp_value)
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning("Invalid temperature value in peripheral data: %s", e)
                        peripheral.temperature = None
                if "RelativeHumidity_pc" in shtc1:
                    try:
                        humidity_value = shtc1["RelativeHumidity_pc"]
                        if isinstance(humidity_value, (int, float)):
                            peripheral.humidity = float(humidity_value)
                    except (ValueError, TypeError) as e:
                        _LOGGER.warning("Invalid humidity value in peripheral data: %s", e)
                        peripheral.humidity = None
        return peripheral

    def set_parent_status(self, parent: "ActronAirStatus") -> None:
        """Set reference to parent ActronStatus object.

        Args:
            parent: Parent ActronAirStatus instance

        """
        self._parent_status = parent


class ActronAirZone(BaseModel):
    """Individual climate control zone in an Actron Air system.

    Represents a single controllable zone with its own temperature settings,
    sensors, and control capabilities. Provides methods to enable/disable
    the zone and adjust temperature setpoints.
    """

    can_operate: bool = Field(False, alias="CanOperate")
    common_zone: bool = Field(False, alias="CommonZone")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    zone_position: float = Field(0.0, alias="ZonePosition")
    title: str = Field("", alias="NV_Title")
    exists: bool = Field(False, alias="NV_Exists")
    temperature_setpoint_cool_c: float = Field(0.0, alias="TemperatureSetpoint_Cool_oC")
    temperature_setpoint_heat_c: float = Field(0.0, alias="TemperatureSetpoint_Heat_oC")
    sensors: dict[str, ActronAirZoneSensor] = Field(default_factory=dict, alias="Sensors")
    variable_air_volume: bool = Field(False, alias="NV_VAV")
    individual_temperature_control: bool = Field(False, alias="NV_ITC")
    individual_temperature_deadband: bool = Field(False, alias="NV_ITD")
    integrated_humidity_tracking: bool = Field(False, alias="NV_IHD")
    indoor_air_compensation: bool = Field(False, alias="NV_IAC")
    zone_id: int
    _parent_status: "ActronAirStatus | None" = None

    @property
    def parent_status(self) -> "ActronAirStatus":
        """Get the parent status object.

        Zones are always created via status parsing and must have a parent.
        The ``| None`` default exists only because Pydantic requires one.

        Raises:
            RuntimeError: If accessed before ``set_parent_status`` is called

        """
        if self._parent_status is None:
            raise RuntimeError("Zone must be attached to a parent status")
        return self._parent_status

    @property
    def is_active(self) -> bool:
        """Check if this zone is currently active.

        Returns:
            True if zone is enabled and can operate, False otherwise

        """
        enabled_zones = self.parent_status.user_aircon_settings.enabled_zones

        if not self.can_operate:
            return False
        if self.zone_id >= len(enabled_zones):
            return False
        return enabled_zones[self.zone_id]

    @property
    def hvac_mode(self) -> str:
        """Get the current HVAC mode for this zone, accounting for zone and system state.

        Returns:
            String representing the mode ("OFF", "COOL", "HEAT", "AUTO", "FAN")
            "OFF" is returned if the system is off or the zone is inactive

        """
        settings = self.parent_status.user_aircon_settings

        if not settings.is_on:
            return AC_MODE_OFF

        if not self.is_active:
            return AC_MODE_OFF

        return settings.mode

    @property
    def temperature(self) -> float:
        """Get the current temperature reading for this zone.

        Returns the zone controller's live temperature.
        """
        return self.live_temp_c

    @property
    def humidity(self) -> float:
        """Get the humidity reading for this zone.

        Returns the zone controller's live humidity.
        """
        return self.live_humidity_pc

    @property
    def current_setpoint(self) -> float:
        """Get the active temperature setpoint based on the current AC mode.

        Returns the heating setpoint when in HEAT mode, otherwise the
        cooling setpoint (COOL, AUTO, FAN, etc.).

        Returns:
            The active temperature setpoint in degrees Celsius

        """
        settings = self.parent_status.user_aircon_settings
        if settings.mode.upper() == AC_MODE_HEAT:
            return self.temperature_setpoint_heat_c
        return self.temperature_setpoint_cool_c

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature that can be set.

        Mode-aware: uses heat limits/setpoint when in HEAT mode,
        cool limits/setpoint otherwise (COOL, AUTO, FAN).
        """
        settings = self.parent_status.user_aircon_settings
        limit = self.parent_status.max_temp
        target = settings.current_setpoint
        variance = settings.zone_temperature_setpoint_variance
        return min(limit, target + variance)

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature that can be set.

        Mode-aware: uses heat limits/setpoint when in HEAT mode,
        cool limits/setpoint otherwise (COOL, AUTO, FAN).
        """
        settings = self.parent_status.user_aircon_settings
        limit = self.parent_status.min_temp
        target = settings.current_setpoint
        variance = settings.zone_temperature_setpoint_variance
        return max(limit, target - variance)

    # Command generation methods
    def _set_temperature_command(self, temperature: float) -> dict[str, Any]:
        """Create a command to set temperature for this zone based on the current AC mode.

        Args:
            temperature: The temperature to set

        Returns:
            Command dictionary

        """
        if not self.parent_status.user_aircon_settings.mode:
            raise ValueError("No AC mode available to determine temperature setpoint")

        mode = self.parent_status.user_aircon_settings.mode.upper()

        if mode in (AC_MODE_FAN, AC_MODE_OFF):
            raise ValueError(f"Cannot set temperature in {mode} mode")

        command: dict[str, Any] = {"type": "set-settings"}

        if mode == AC_MODE_COOL:
            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Cool_oC"] = float(
                temperature
            )
        elif mode == AC_MODE_HEAT:
            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Heat_oC"] = float(
                temperature
            )
        elif mode == AC_MODE_AUTO:
            # AUTO: maintain the temperature differential between cooling and heating
            # Get the current differential from parent settings
            cool_temp = self.parent_status.user_aircon_settings.temperature_setpoint_cool_c
            heat_temp = self.parent_status.user_aircon_settings.temperature_setpoint_heat_c
            differential = cool_temp - heat_temp

            # Apply the same differential to the new temperature
            # For AUTO mode, we assume the provided temperature is for cooling
            cool_setpoint = float(temperature)
            heat_setpoint = float(max(TEMP_AUTO_HEAT_MIN, temperature - differential))

            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Cool_oC"] = cool_setpoint
            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Heat_oC"] = heat_setpoint

        return {"command": command}

    def _set_enable_command(self, is_enabled: bool) -> dict[str, Any]:
        """Create a command to enable or disable this zone.

        Args:
            is_enabled: True to enable, False to disable

        Returns:
            Command dictionary

        """
        if not self.parent_status.user_aircon_settings.enabled_zones:
            raise ValueError("No enabled zones available to determine current zones")

        # Get current zones from parent
        current_zones = self.parent_status.user_aircon_settings.enabled_zones.copy()

        # Update the specific zone
        if self.zone_id < len(current_zones):
            current_zones[self.zone_id] = is_enabled
        else:
            raise ValueError(f"Zone index {self.zone_id} out of range for zones list")

        return {
            "command": {"type": "set-settings", "UserAirconSettings.EnabledZones": current_zones}
        }

    def set_parent_status(self, parent: "ActronAirStatus") -> None:
        """Set reference to parent ActronStatus object.

        Args:
            parent: Parent ActronAirStatus instance

        """
        self._parent_status = parent

    async def set_temperature(self, temperature: float) -> None:
        """Set temperature for this zone based on the current AC mode and send the command.

        After successful command delivery the local temperature setpoint is
        updated optimistically so that subsequent reads reflect the change
        before the next status poll.

        Args:
            temperature: The temperature to set (in degrees Celsius)

        Raises:
            ValueError: If temperature is invalid or no API reference

        """
        # Validate temperature is a reasonable value
        if not isinstance(temperature, (int, float)):
            raise ValueError(f"Temperature must be a number, got {type(temperature).__name__}")
        if not TEMP_PHYSICAL_MIN <= temperature <= TEMP_PHYSICAL_MAX:
            raise ValueError(
                f"Temperature {temperature}°C is outside reasonable range "
                f"({TEMP_PHYSICAL_MIN} to {TEMP_PHYSICAL_MAX})"
            )

        # Ensure temperature is within valid range for this zone
        temperature = max(self.min_temp, min(self.max_temp, temperature))

        command = self._set_temperature_command(temperature)
        if self.parent_status.api and self.parent_status.serial_number:
            # Capture optimistic values before await to avoid races
            settings = self.parent_status.user_aircon_settings
            mode = settings.mode.upper()
            optimistic_cool: float | None = None
            optimistic_heat: float | None = None
            if mode == AC_MODE_COOL:
                optimistic_cool = temperature
            elif mode == AC_MODE_HEAT:
                optimistic_heat = temperature
            elif mode == AC_MODE_AUTO:
                cool = settings.temperature_setpoint_cool_c
                heat = settings.temperature_setpoint_heat_c
                differential = cool - heat
                optimistic_cool = temperature
                optimistic_heat = max(TEMP_AUTO_HEAT_MIN, temperature - differential)

            await self.parent_status.api.send_command(self.parent_status.serial_number, command)

            # Optimistic local state update using values captured before await
            if optimistic_cool is not None:
                self.temperature_setpoint_cool_c = optimistic_cool
            if optimistic_heat is not None:
                self.temperature_setpoint_heat_c = optimistic_heat
        else:
            raise ValueError("No API reference available to send command")

    async def enable(self, is_enabled: bool = True) -> None:
        """Enable or disable this zone and send the command.

        After successful command delivery the local ``enabled_zones`` list is
        updated optimistically so that subsequent reads reflect the change
        before the next status poll.

        Args:
            is_enabled: True to enable, False to disable

        """
        command = self._set_enable_command(is_enabled)
        if self.parent_status.api and self.parent_status.serial_number:
            await self.parent_status.api.send_command(self.parent_status.serial_number, command)

            # Optimistic local state update — apply the exact EnabledZones sent
            sent_zones = command.get("command", {}).get("UserAirconSettings.EnabledZones")
            if isinstance(sent_zones, list):
                self.parent_status.user_aircon_settings.enabled_zones = list(sent_zones)
        else:
            raise ValueError("No API reference available to send command")
