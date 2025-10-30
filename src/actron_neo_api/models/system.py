"""System models for Actron Air API"""
from typing import Dict, Optional, Any
from pydantic import BaseModel, Field


class ActronAirOutdoorUnit(BaseModel):
    """Model for outdoor unit data in the AC system"""
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
    is_on: bool = Field(False, alias="SystemOn")
    compressor_mode: str = Field("", alias="CompressorMode")
    compressor_capacity: int = Field(0, alias="CompressorCapacity")
    fan_rpm: int = Field(0, alias="FanRPM")
    defrost: bool = Field(False, alias="Defrost")
    compressor_chasing_temperature: Optional[float] = Field(None, alias="CompressorChasingTemperature")
    compressor_live_temperature: Optional[float] = Field(None, alias="CompressorLiveTemperature")
    outdoor_unit: Optional[ActronAirOutdoorUnit] = Field(None, alias="OutdoorUnit")


class ActronAirMasterInfo(BaseModel):
    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_outdoor_temp_c: float = Field(0.0, alias="LiveOutdoorTemp_oC")


class ActronAirAlerts(BaseModel):
    """Model for AC system alerts"""
    clean_filter: bool = Field(False, alias="CleanFilter")
    defrosting: bool = Field(False, alias="Defrosting")


class ActronAirACSystem(BaseModel):
    master_wc_model: str = Field("", alias="MasterWCModel")
    master_serial: str = Field("", alias="MasterSerial")
    master_wc_firmware_version: str = Field("", alias="MasterWCFirmwareVersion")
    system_name: str = Field("", alias="SystemName")
    outdoor_unit: Optional[ActronAirOutdoorUnit] = Field(None, alias="OutdoorUnit")
    _parent_status: Optional["ActronStatus"] = None

    def set_parent_status(self, parent: "ActronStatus") -> None:
        """Set reference to parent ActronStatus object"""
        self._parent_status = parent

    async def get_outdoor_unit_model(self) -> Optional[str]:
        """
        Get the outdoor unit model for this AC system.

        Returns:
            The outdoor unit model or None if not available
        """
        # First check if we already have the data in our model
        if self.outdoor_unit and self.outdoor_unit.model_number:
            return self.outdoor_unit.model_number

        # If not, try to get it from the API
        if not self._parent_status or not self._parent_status._api:
            return None

        try:
            return await self._parent_status._api.get_outdoor_unit_model(self.master_serial)
        except Exception:
            return None

    async def get_firmware_version(self) -> Optional[str]:
        """
        Get the firmware version for this AC system.

        Returns:
            The firmware version or None if not available
        """
        if not self._parent_status or not self._parent_status._api:
            raise ValueError("No API reference available")

        return await self._parent_status._api.get_master_firmware(self.master_serial)

    async def update_status(self) -> Optional["ActronStatus"]:
        """
        Update the status of this AC system.

        Returns:
            Updated ActronStatus object or None if update failed
        """
        if not self._parent_status or not self._parent_status._api:
            raise ValueError("No API reference available")

        # Update status for this specific AC unit
        await self._parent_status._api._fetch_full_update(self.master_serial)

        # Return the updated status
        return self._parent_status._api.state_manager.get_status(self.master_serial)

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

        command = {
            "command": {
                "UserAirconSettings.isOn": is_on,
                "type": "set-settings"
            }
        }

        if is_on:
            command["command"]["UserAirconSettings.Mode"] = mode

        return await self._parent_status._api.send_command(self.master_serial, command)
