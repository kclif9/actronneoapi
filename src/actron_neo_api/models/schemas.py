"""Schema models for Actron Air API.

This file re-exports models from their respective module files
for backward compatibility.
"""

# Re-export models from their respective module files
from .settings import ActronAirUserAirconSettings
from .status import ActronAirStatus
from .system import ActronAirACSystem, ActronAirLiveAircon, ActronAirMasterInfo
from .zone import ActronAirZone, ActronAirZoneSensor

__all__ = [
    "ActronAirZone",
    "ActronAirZoneSensor",
    "ActronAirUserAirconSettings",
    "ActronAirLiveAircon",
    "ActronAirMasterInfo",
    "ActronAirACSystem",
    "ActronAirStatus",
]
