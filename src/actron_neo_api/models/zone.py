"""Zone models for Actron Air API."""

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

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
    signal_strength: str = str(Field("NA", alias="Signal_of3"))
    temperature: Optional[float] = Field(None, alias="Temperature_oC")
    humidity: Optional[float] = Field(None, alias="RelativeHumidity_pc")
    battery_level: Optional[float] = Field(None, alias="RemainingBatteryCapacity_pc")


class ActronAirPeripheral(BaseModel):
    """Peripheral device that provides sensor data for zones.

    Peripherals are additional sensor devices that can be assigned to one or
    more zones to provide more accurate temperature and humidity readings
    than the central controller.
    """

    logical_address: int = Field(0, alias="LogicalAddress")
    device_type: str = Field("", alias="DeviceType")
    zone_assignments: List[int] = Field([], alias="ZoneAssignment")
    serial_number: str = Field("", alias="SerialNumber")
    battery_level: Optional[float] = Field(None, alias="RemainingBatteryCapacity_pc")
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    _parent_status: Optional["ActronAirStatus"] = None

    @property
    def zones(self) -> List["ActronAirZone"]:
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
    def from_peripheral_data(cls, peripheral_data: Dict[str, Any]) -> "ActronAirPeripheral":
        """Create a peripheral instance from raw peripheral data.

        Args:
            peripheral_data: Raw peripheral data dictionary from API

        Returns:
            ActronAirPeripheral instance with extracted sensor data

        """
        peripheral = cls.model_validate(peripheral_data)

        sensor_inputs = peripheral_data.get("SensorInputs", {})
        if sensor_inputs:
            shtc1 = sensor_inputs.get("SHTC1", {})
            if shtc1:
                if "Temperature_oC" in shtc1:
                    peripheral.temperature = float(shtc1["Temperature_oC"])
                if "RelativeHumidity_pc" in shtc1:
                    peripheral.humidity = float(shtc1["RelativeHumidity_pc"])
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
    sensors: Dict[str, ActronAirZoneSensor] = Field({}, alias="Sensors")
    actual_humidity_pc: Optional[float] = None
    zone_id: Optional[int] = None
    _parent_status: Optional["ActronAirStatus"] = None

    @property
    def is_active(self) -> bool:
        """Check if this zone is currently active.

        Returns:
            True if zone is enabled and can operate, False otherwise

        """
        if not self._parent_status or not self._parent_status.user_aircon_settings:
            return False

        enabled_zones = self._parent_status.user_aircon_settings.enabled_zones

        if not self.can_operate:
            return False
        if self.zone_id is None or self.zone_id >= len(enabled_zones):
            return False
        return enabled_zones[self.zone_id]

    @property
    def hvac_mode(self) -> str:
        """Get the current HVAC mode for this zone, accounting for zone and system state.

        Returns:
            String representing the mode ("OFF", "COOL", "HEAT", "AUTO", "FAN")
            "OFF" is returned if the system is off or the zone is inactive

        """
        if not self._parent_status or not self._parent_status.user_aircon_settings:
            return "OFF"

        settings = self._parent_status.user_aircon_settings

        if not settings.is_on:
            return "OFF"

        if not self.is_active:
            return "OFF"

        return settings.mode

    @property
    def humidity(self) -> float:
        """Get the best available humidity reading for this zone.

        Returns the actual sensor reading if available, otherwise the system-reported value.
        """
        if self.actual_humidity_pc is not None:
            return self.actual_humidity_pc
        return self.live_humidity_pc

    @property
    def battery_level(self) -> Optional[float]:
        """Get the battery level of the peripheral sensor assigned to this zone.

        Returns:
            Battery level as a percentage or None if no peripheral sensor is assigned

        """
        if not self._parent_status or self.zone_id is None:
            return None

        peripheral = self._parent_status.get_peripheral_for_zone(self.zone_id)
        return peripheral.battery_level if peripheral else None

    @property
    def peripheral_temperature(self) -> Optional[float]:
        """Get the temperature reading from the peripheral sensor assigned to this zone.

        Returns:
            Temperature in degrees Celsius or None if no peripheral sensor is assigned

        """
        if not self._parent_status or self.zone_id is None:
            return None

        peripheral = self._parent_status.get_peripheral_for_zone(self.zone_id)
        return peripheral.temperature if peripheral else None

    @property
    def peripheral_humidity(self) -> Optional[float]:
        """Get the humidity reading from the peripheral sensor assigned to this zone.

        Returns:
            Relative humidity as a percentage or None if no peripheral sensor is assigned

        """
        if not self._parent_status or self.zone_id is None:
            return None

        peripheral = self._parent_status.get_peripheral_for_zone(self.zone_id)
        return peripheral.humidity if peripheral else None

    @property
    def peripheral(self) -> Optional["ActronAirPeripheral"]:
        """Get the peripheral device assigned to this zone.

        Returns:
            The peripheral device or None if no peripheral is assigned

        """
        if not self._parent_status or self.zone_id is None:
            return None

        return self._parent_status.get_peripheral_for_zone(self.zone_id)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature that can be set."""
        if not self._parent_status or not self._parent_status.last_known_state:
            return 30.0  # Default fallback value

        max_setpoint = (
            self._parent_status.last_known_state.get("NV_Limits", {})
            .get("UserSetpoint_oC", {})
            .get("setCool_Max", 30.0)
        )

        user_settings = self._parent_status.last_known_state.get("UserAirconSettings", {})
        target_setpoint = user_settings.get("TemperatureSetpoint_Cool_oC", 24.0)
        temp_variance = user_settings.get("ZoneTemperatureSetpointVariance_oC", 3.0)

        if max_setpoint < target_setpoint + temp_variance:
            return max_setpoint
        return target_setpoint + temp_variance

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature that can be set."""
        if not self._parent_status or not self._parent_status.last_known_state:
            return 16.0  # Default fallback value

        min_setpoint = (
            self._parent_status.last_known_state.get("NV_Limits", {})
            .get("UserSetpoint_oC", {})
            .get("setCool_Min", 16.0)
        )

        user_settings = self._parent_status.last_known_state.get("UserAirconSettings", {})
        target_setpoint = user_settings.get("TemperatureSetpoint_Cool_oC", 24.0)
        temp_variance = user_settings.get("ZoneTemperatureSetpointVariance_oC", 3.0)

        if min_setpoint > target_setpoint - temp_variance:
            return min_setpoint
        return target_setpoint - temp_variance

    # Command generation methods
    def set_temperature_command(self, temperature: float) -> Dict[str, Any]:
        """Create a command to set temperature for this zone based on the current AC mode.

        Args:
            temperature: The temperature to set

        Returns:
            Command dictionary

        """
        if self.zone_id is None:
            raise ValueError("Zone index not set")

        if not self._parent_status or not self._parent_status.user_aircon_settings:
            raise ValueError("No parent AC status available to determine mode")

        mode = self._parent_status.user_aircon_settings.mode.upper()
        command: Dict[str, Any] = {"type": "set-settings"}

        if mode == "COOL":
            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Cool_oC"] = float(
                temperature
            )
        elif mode == "HEAT":
            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Heat_oC"] = float(
                temperature
            )
        elif mode == "AUTO":
            # AUTO: maintain the temperature differential between cooling and heating
            # Get the current differential from parent settings
            cool_temp = self._parent_status.user_aircon_settings.temperature_setpoint_cool_c
            heat_temp = self._parent_status.user_aircon_settings.temperature_setpoint_heat_c
            differential = cool_temp - heat_temp

            # Apply the same differential to the new temperature
            # For AUTO mode, we assume the provided temperature is for cooling
            cool_setpoint = float(temperature)
            heat_setpoint = float(
                max(10.0, temperature - differential)
            )  # Ensure we don't go below a reasonable minimum

            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Cool_oC"] = cool_setpoint
            command[f"RemoteZoneInfo[{self.zone_id}].TemperatureSetpoint_Heat_oC"] = heat_setpoint

        return {"command": command}

    def set_enable_command(self, is_enabled: bool) -> Dict[str, Any]:
        """Create a command to enable or disable this zone.

        Args:
            is_enabled: True to enable, False to disable

        Returns:
            Command dictionary

        """
        if self.zone_id is None:
            raise ValueError("Zone index not set")

        if not self._parent_status or not self._parent_status.user_aircon_settings:
            raise ValueError("No parent AC status available to determine current zones")

        # Get current zones from parent
        current_zones = self._parent_status.user_aircon_settings.enabled_zones.copy()

        # Update the specific zone
        if self.zone_id < len(current_zones):
            current_zones[self.zone_id] = is_enabled
        else:
            raise ValueError(f"Zone index {self.zone_id} out of range for zones list")

        return {
            "command": {"type": "set-settings", "UserAirconSettings.EnabledZones": current_zones}
        }

    def set_parent_status(self, parent: "ActronAirStatus", zone_index: int) -> None:
        """Set reference to parent ActronStatus object and this zone's index."""
        self._parent_status = parent
        self.zone_id = zone_index

    async def set_temperature(self, temperature: float) -> Dict[str, Any]:
        """Set temperature for this zone based on the current AC mode and send the command.

        Args:
            temperature: The temperature to set

        Returns:
            API response dictionary

        """
        if self.zone_id is None:
            raise ValueError("Zone index not set")

        # Ensure temperature is within valid range
        temperature = max(self.min_temp, min(self.max_temp, temperature))

        command = self.set_temperature_command(temperature)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            return await self._parent_status.api.send_command(
                self._parent_status.serial_number, command
            )
        raise ValueError("No API reference available to send command")

    async def enable(self, is_enabled: bool = True) -> Dict[str, Any]:
        """Enable or disable this zone and send the command.

        Args:
            is_enabled: True to enable, False to disable

        Returns:
            API response dictionary

        """
        command = self.set_enable_command(is_enabled)
        if (
            self._parent_status
            and self._parent_status.api
            and hasattr(self._parent_status, "serial_number")
        ):
            return await self._parent_status.api.send_command(
                self._parent_status.serial_number, command
            )
        raise ValueError("No API reference available to send command")
