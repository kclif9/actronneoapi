"""Actron Air API Models.

This package contains all data models used in the Actron Air API
"""

# Re-export all models for easy access
from .auth import ActronAirDeviceCode, ActronAirToken

# For backward compatibility
from .settings import ActronAirUserAirconSettings
from .status import ActronAirStatus
from .system import (
    ActronAirACSystem,
    ActronAirLiveAircon,
    ActronAirMasterInfo,
    ActronAirSystemInfo,
)
from .zone import ActronAirPeripheral, ActronAirZone, ActronAirZoneSensor

__all__ = [
    "ActronAirDeviceCode",
    "ActronAirToken",
    "ActronAirZone",
    "ActronAirZoneSensor",
    "ActronAirPeripheral",
    "ActronAirUserAirconSettings",
    "ActronAirLiveAircon",
    "ActronAirMasterInfo",
    "ActronAirACSystem",
    "ActronAirSystemInfo",
    "ActronAirStatus",
]
