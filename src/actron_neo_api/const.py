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
AC_MODE_DRY: Final[str] = "DRY"
AC_MODE_OFF: Final[str] = "OFF"

# Fallback supported modes for controllers (e.g. Que) that don't report ModeSupport
FALLBACK_SUPPORTED_MODES: Final[tuple[str, ...]] = (
    AC_MODE_COOL,
    AC_MODE_HEAT,
    AC_MODE_FAN,
    AC_MODE_AUTO,
)

# HTTP timeout defaults (seconds)
HTTP_CONNECT_TIMEOUT: Final[float] = 10.0
HTTP_TOTAL_TIMEOUT: Final[float] = 30.0

# OAuth2 defaults
OAUTH_CLIENT_ID: Final[str] = "home_assistant"
OAUTH_TOKEN_REFRESH_MARGIN: Final[int] = 900  # 15 minutes in seconds
OAUTH_DEFAULT_EXPIRY: Final[int] = 3600  # 1 hour in seconds

# Temperature validation
TEMP_PHYSICAL_MIN: Final[float] = -50.0
TEMP_PHYSICAL_MAX: Final[float] = 100.0
TEMP_AUTO_HEAT_MIN: Final[float] = 10.0

# Response sanitization
MAX_ERROR_RESPONSE_LENGTH: Final[int] = 200
