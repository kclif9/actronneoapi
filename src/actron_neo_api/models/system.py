"""System models for Actron Neo API"""
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field


class ActronAirNeoLiveAircon(BaseModel):
    is_on: bool = Field(False, alias="SystemOn")
    compressor_mode: str = Field("", alias="CompressorMode")
    compressor_capacity: int = Field(0, alias="CompressorCapacity")
    fan_rpm: int = Field(0, alias="FanRPM")
    defrost: bool = Field(False, alias="Defrost")


class ActronAirNeoMasterInfo(BaseModel):
    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_outdoor_temp_c: float = Field(0.0, alias="LiveOutdoorTemp_oC")


class ActronAirNeoACSystem(BaseModel):
    master_wc_model: str = Field("", alias="MasterWCModel")
    master_serial: str = Field("", alias="MasterSerial")
    master_wc_firmware_version: str = Field("", alias="MasterWCFirmwareVersion")
    system_name: str = Field("", alias="SystemName")
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
        if not self._parent_status or not self._parent_status._api:
            raise ValueError("No API reference available")

        return await self._parent_status._api.get_outdoor_unit_model(self.master_serial)

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
