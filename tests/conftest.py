"""Shared fixtures for ActronNeoAPI tests."""

from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest


# Sample API Response Fixtures
@pytest.fixture
def sample_system_neo() -> Dict[str, Any]:
    """Sample AC system response for Neo platform."""
    return {
        "serial": "abc123",
        "type": "standard",
        "_links": {
            "ac-status": {"href": "/api/v0/client/ac-systems/abc123/status"},
            "commands": {"href": "/api/v0/client/ac-systems/abc123/commands"},
        },
    }


@pytest.fixture
def sample_system_que_nxgen() -> Dict[str, Any]:
    """Sample AC system response with NX Gen type (Que platform)."""
    return {
        "serial": "xyz789",
        "type": "NX-Gen",
        "_links": {
            "ac-status": {"href": "/api/v0/client/ac-systems/xyz789/status"},
            "commands": {"href": "/api/v0/client/ac-systems/xyz789/commands"},
        },
    }


@pytest.fixture
def sample_systems_response_neo(sample_system_neo) -> Dict[str, Any]:
    """Sample get_ac_systems response for Neo platform."""
    return {"_embedded": {"ac-system": [sample_system_neo]}}


@pytest.fixture
def sample_systems_response_que(sample_system_que_nxgen) -> Dict[str, Any]:
    """Sample get_ac_systems response with NX Gen system."""
    return {"_embedded": {"ac-system": [sample_system_que_nxgen]}}


@pytest.fixture
def sample_status_full() -> Dict[str, Any]:
    """Sample full status response with all data."""
    return {
        "isOnline": True,
        "lastKnownState": {
            "AirconSystem": {
                "MasterWCModel": "WC2",
                "MasterSerial": "ABC123",
                "MasterWCFirmwareVersion": "1.2.3",
            },
            "UserAirconSettings": {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "AwayMode": False,
                "TemperatureSetpoint_Cool_oC": 24.0,
                "TemperatureSetpoint_Heat_oC": 20.0,
                "EnabledZones": [True, False, True, False, False, False, False, False],
                "QuietModeEnabled": False,
                "TurboMode": {"Enabled": False, "Supported": True},
            },
            "MasterInfo": {
                "LiveTemp_oC": 22.5,
                "LiveHumidity_pc": 55.0,
                "LiveOutdoorTemp_oC": 28.0,
            },
            "LiveAircon": {
                "SystemOn": True,
                "CompressorMode": "COOL",
                "CompressorCapacity": 75,
                "FanRPM": 450,
                "Defrost": False,
                "CompressorChasingTemperature": 24.0,
                "CompressorLiveTemperature": 22.5,
                "OutdoorUnit": {
                    "ModelNumber": "OU123",
                    "SerialNumber": "OU456",
                    "CompSpeed": 65.5,
                    "CompPower": 2500,
                    "CompRunningPWM": 70,
                    "CompressorOn": True,
                },
            },
            "Alerts": {"CleanFilter": False, "Defrosting": False},
            "RemoteZoneInfo": [
                {
                    "CanOperate": True,
                    "CommonZone": False,
                    "LiveHumidity_pc": 55.0,
                    "LiveTemp_oC": 22.5,
                    "ZonePosition": 100.0,
                    "NV_Title": "Living Room",
                    "NV_Exists": True,
                    "TemperatureSetpoint_Cool_oC": 24.0,
                    "TemperatureSetpoint_Heat_oC": 20.0,
                    "Sensors": {},
                },
            ],
            "NV_Limits": {
                "UserSetpoint_oC": {
                    "setCool_Min": 16.0,
                    "setCool_Max": 32.0,
                    "setHeat_Min": 10.0,
                    "setHeat_Max": 30.0,
                }
            },
        },
    }


@pytest.fixture
def sample_command_response() -> Dict[str, Any]:
    """Sample command response."""
    return {"success": True, "message": "Command executed"}


# Mock OAuth2 Fixtures
@pytest.fixture
def mock_oauth():
    """Mock OAuth2 authentication handler."""
    oauth = MagicMock()
    oauth.access_token = "test_access_token"
    oauth.refresh_token = "test_refresh_token"
    oauth.token_type = "Bearer"
    oauth.is_token_valid = True
    oauth.is_token_expiring_soon = False
    oauth.authenticated_platform = "https://nimbus.actronair.com.au"
    oauth.authorization_header = {"Authorization": "Bearer test_access_token"}
    oauth.ensure_token_valid = AsyncMock(return_value="test_access_token")
    oauth.refresh_access_token = AsyncMock(return_value=("test_access_token", 1234567890.0))
    return oauth


# Mock API Response Fixtures
@pytest.fixture
def mock_aiohttp_response():
    """Factory for creating mock aiohttp responses."""

    def _create_response(status=200, json_data=None, text=""):
        mock_resp = AsyncMock()
        mock_resp.status = status
        mock_resp.json = AsyncMock(return_value=json_data or {})
        mock_resp.text = AsyncMock(return_value=text)
        return mock_resp

    return _create_response


@pytest.fixture
def mock_session(mock_aiohttp_response):
    """Mock aiohttp ClientSession."""
    session = MagicMock()
    session.closed = False
    session.close = AsyncMock()

    # Create async context manager for request()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_aiohttp_response(status=200, json_data={}))
    mock_ctx.__aexit__ = AsyncMock(return_value=False)

    session.request = MagicMock(return_value=mock_ctx)

    return session


@pytest.fixture
def mock_api():
    """Create a reusable mock API for testing async methods."""

    class MockAPI:
        def __init__(self):
            self.last_command = None
            self.last_serial = None

        async def send_command(self, serial_number, command):
            self.last_serial = serial_number
            self.last_command = command
            return {"success": True}

    return MockAPI()


@pytest.fixture
def mock_aiohttp_session():
    """Factory for creating properly mocked aiohttp ClientSession.

    This fixture provides a helper function to create properly structured
    async context manager mocks for aiohttp.ClientSession, reducing
    repetitive boilerplate in OAuth and API tests.

    Returns:
        Callable that accepts a mock response and returns configured session mock
    """

    def _create_session(mock_response: AsyncMock):
        """Create a mocked session with proper async context managers.

        Args:
            mock_response: AsyncMock object with status, json, text attributes

        Returns:
            Configured session mock ready for use with aiohttp.ClientSession patch
        """
        # Create async context manager for HTTP method (post/get/etc)
        mock_method = AsyncMock()
        mock_method.__aenter__ = AsyncMock(return_value=mock_response)
        mock_method.__aexit__ = AsyncMock(return_value=None)

        # Create session instance with methods
        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_method)
        mock_session_instance.get = MagicMock(return_value=mock_method)

        # Create session context manager
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        return mock_session

    return _create_session
