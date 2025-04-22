"""System models for Actron Neo API"""
from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field


class LiveAircon(BaseModel):
    is_on: bool = Field(False, alias="SystemOn")
    compressor_mode: str = Field("", alias="CompressorMode")
    compressor_capacity: int = Field(0, alias="CompressorCapacity")
    fan_rpm: int = Field(0, alias="FanRPM")
    defrost: bool = Field(False, alias="Defrost")


class MasterInfo(BaseModel):
    live_temp_c: float = Field(0.0, alias="LiveTemp_oC")
    live_humidity_pc: float = Field(0.0, alias="LiveHumidity_pc")
    live_outdoor_temp_c: float = Field(0.0, alias="LiveOutdoorTemp_oC")


class ACSystem(BaseModel):
    master_wc_model: str = Field("", alias="MasterWCModel")
    master_serial: str = Field("", alias="MasterSerial")
    master_wc_firmware_version: str = Field("", alias="MasterWCFirmwareVersion")
    system_name: str = Field("", alias="SystemName")
