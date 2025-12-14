"""System models for Actron Air API"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .status import ActronAirStatus


class ActronAirOutdoorUnit(BaseModel):
    """
    Outdoor unit data for an Actron Air AC system.

    Contains information about the compressor unit including model, serial number,
    compressor speed, power consumption, and operational status.
    """

    model_number: Optional[str] = str(Field(None, alias="ModelNumber"))
    serial_number: Optional[str] = Field(None, alias="SerialNumber")
    software_version: Optional[str] = str(Field(None, alias="SoftwareVersion"))
    comp_speed: Optional[float] = Field(None, alias="CompSpeed")
    comp_power: Optional[int] = Field(None, alias="CompPower")
    comp_running_pwm: Optional[int] = Field(None, alias="CompRunningPWM")
    compressor_on: Optional[bool] = Field(None, alias="CompressorOn")
    amb_temp: Optional[float] = Field(None, alias="AmbTemp")
    family: Optional[str] = Field(None, alias="Family")


class ActronAirLiveAircon(BaseModel):
    """
    Live operational data for the air conditioning system.

    Contains real-time information about system operation including power state,
    compressor mode and capacity, fan speed, defrost status, and temperature targets.
    """

    is_on: bool = Field(False, alias="SystemOn")
    compressor_mode: str = Field("", alias="CompressorMode")
    compressor_capacity: int = Field(0, alias="CompressorCapacity")
    fan_rpm: int = Field(0, alias="FanRPM")
    defrost: bool = Field(False, alias="Defrost")
    compressor_chasing_temperature: Optional[float] = Field(
        None, alias="CompressorChasingTemperature"
    )
    compressor_live_temperature: Optional[float] = Field(None, alias="CompressorLiveTemperature")
    outdoor_unit: Optional[ActronAirOutdoorUnit] = Field(None, alias="OutdoorUnit")


class ActronAirMasterInfo(BaseModel):
    """
    Master controller information and sensor readings.

    Contains live sensor data from the main controller including indoor temperature,
    humidity, and outdoor temperature readings.
    """

    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_outdoor_temp_c: float = Field(0.0, alias="LiveOutdoorTemp_oC")


class ActronAirAlerts(BaseModel):
    """
    System alert and notification flags.

    Contains boolean flags for system alerts such as filter cleaning reminders
    and defrost cycle status.
    """

    clean_filter: bool = Field(False, alias="CleanFilter")
    defrosting: bool = Field(False, alias="Defrosting")


class ActronAirACSystem(BaseModel):
    """
    Complete AC system information including hardware and firmware details.

    Represents the main air conditioning system with its master controller,
    outdoor unit, and system identification. Provides methods to control
    system-level settings like operating mode.
    """

    master_wc_model: str = Field("", alias="MasterWCModel")
    master_serial: str = Field("", alias="MasterSerial")
    master_wc_firmware_version: str = Field("", alias="MasterWCFirmwareVersion")
    system_name: str = Field("", alias="SystemName")
    outdoor_unit: Optional[ActronAirOutdoorUnit] = Field(None, alias="OutdoorUnit")
    _parent_status: Optional["ActronAirStatus"] = None

    def set_parent_status(self, parent: "ActronAirStatus") -> None:
        """
        Set reference to parent ActronStatus object.

        Args:
            parent: Parent ActronAirStatus instance
        """
        self._parent_status = parent

    async def set_system_mode(self, mode: str) -> Dict[str, Any]:
        """
        Set the system mode for this AC unit.

        Args:
            mode: Mode to set ('AUTO', 'COOL', 'FAN', 'HEAT', 'OFF')
                 Use 'OFF' to turn the system off.

        Returns:
            API response dictionary
        """
        if not self._parent_status or not self._parent_status._api:
            raise ValueError("No API reference available")

        # Determine if system should be on or off based on mode
        is_on = mode.upper() != "OFF"

        command = {"command": {"UserAirconSettings.isOn": is_on, "type": "set-settings"}}

        if is_on:
            command["command"]["UserAirconSettings.Mode"] = mode

        return await self._parent_status._api.send_command(self.master_serial, command)
