"""Const definition for the Actron Air module."""

from typing import Final

PLATFORM_NEO: Final[str] = "neo"
PLATFORM_QUE: Final[str] = "que"

BASE_URL_NIMBUS: Final[str] = "https://nimbus.actronair.com.au"
BASE_URL_QUE: Final[str] = "https://que.actronair.com.au"
BASE_URL_DEFAULT: Final[str] = BASE_URL_NIMBUS

COMMAND_DEBOUNCE_SECONDS: Final[float] = 0.1

DEFAULT_MIN_SETPOINT: Final[float] = 16.0
DEFAULT_MAX_SETPOINT: Final[float] = 30.0

AC_MODE_COOL: Final[str] = "COOL"
AC_MODE_HEAT: Final[str] = "HEAT"
AC_MODE_AUTO: Final[str] = "AUTO"
AC_MODE_FAN: Final[str] = "FAN"
AC_MODE_OFF: Final[str] = "OFF"
