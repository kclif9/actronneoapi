"""Actron Air API client library for Neo and Que systems."""

from ._version import __version__
from .actron import ActronAirAPI
from .exceptions import ActronAirAPIError, ActronAirAuthError
from .models.status import ActronAirStatus
from .models.system import ActronAirACSystem
from .models.zone import ActronAirPeripheral, ActronAirZone
from .oauth import ActronAirOAuth2DeviceCodeAuth

__all__ = [
    "__version__",
    # API and Exceptions
    "ActronAirAPI",
    "ActronAirOAuth2DeviceCodeAuth",
    "ActronAirAuthError",
    "ActronAirAPIError",
    # Model Classes - Only classes directly imported by Home Assistant
    "ActronAirStatus",
    "ActronAirZone",
    "ActronAirPeripheral",
    "ActronAirACSystem",
]
