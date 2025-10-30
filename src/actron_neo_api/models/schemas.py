"""
Schema models for Actron Neo API

This file re-exports models from their respective module files
for backward compatibility.
"""

# Re-export models from their respective module files
from .zone import ActronAirZone, ActronAirZoneSensor
from .settings import ActronAirUserAirconSettings
from .system import ActronAirACSystem, ActronAirLiveAircon, ActronAirMasterInfo
from .status import ActronAirStatus, ActronAirEventType, ActronAirEventsResponse

__all__ = [
    'ActronAirZone',
    'ActronAirZoneSensor',
    'ActronAirUserAirconSettings',
    'ActronAirLiveAircon',
    'ActronAirMasterInfo',
    'ActronAirACSystem',
    'ActronAirStatus',
    'ActronAirEventType',
    'ActronAirEventsResponse',
]
