"""Tests to achieve 100% coverage for remaining uncovered lines."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from actron_neo_api import ActronAirAPI
from actron_neo_api.exceptions import ActronAirAuthError
from actron_neo_api.models import ActronAirStatus


class TestActronAPIContextManagerExit:
    """Test __aexit__ method (line 260)."""

    @pytest.mark.asyncio
    async def test_aexit_closes_session(self):
        """Test __aexit__ calls close on context manager exit."""
        api = ActronAirAPI()
        # Create a mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        api._session = mock_session

        # Call __aexit__
        await api.__aexit__(None, None, None)

        # Verify close was called and session set to None
        mock_session.close.assert_called_once()
        assert api._session is None


class TestActronAPIAuthErrors:
    """Test authentication error paths (lines 349-361)."""

    @pytest.mark.asyncio
    async def test_401_refresh_token_network_error(self):
        """Test 401 response with refresh token that fails with network error."""
        api = ActronAirAPI(refresh_token="test_refresh")

        # Set tokens directly to avoid initialization issues
        api.oauth2_auth.access_token = "test_access"
        api.oauth2_auth.token_expiry = time.time() + 3600  # Valid token
        api._initialized = True

        # Create a mock session
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Unauthorized")

        # Mock the refresh to raise TypeError (caught in the 401 block)
        api.oauth2_auth.refresh_access_token = AsyncMock(side_effect=TypeError("Network error"))

        # Create a context manager for the request
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_context.__aexit__ = AsyncMock(return_value=None)

        # Make request() return the context manager directly (not a coroutine)
        mock_session.request = lambda *args, **kwargs: mock_context

        # Patch _get_session to return our mock
        async def mock_get_session():
            return mock_session

        api._get_session = mock_get_session

        with pytest.raises(
            ActronAirAuthError, match="Authentication failed and token refresh failed"
        ):
            await api._make_request("get", "/test")


class TestSettingsTurboUnsupported:
    """Test turbo_supported property edge case (line 54)."""

    def test_turbo_supported_false_for_bool_false(self):
        """Test turbo_supported returns False when turbo_mode_enabled is bool False."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "TurboMode": False,  # Boolean instead of dict
                }
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        assert status.user_aircon_settings.turbo_supported is False


class TestStatusPeripheralEdgeCases:
    """Test peripheral processing edge cases (lines 218-220, 236-249)."""

    def test_process_peripherals_with_invalid_structure(self):
        """Test peripheral processing with invalid nested structure."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {
                    "MasterSerial": "TEST123",
                    "Peripherals": [
                        "invalid_string",  # Not a dict - will trigger TypeError
                    ],
                },
                "RemoteZoneInfo": [],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        # Should not raise, just log warning and skip invalid peripheral
        status.parse_nested_components()
        assert len(status.peripherals) == 0

    def test_map_peripheral_data_zone_out_of_range(self):
        """Test mapping peripheral data when zone index is out of range."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {
                    "MasterSerial": "TEST123",
                    "Peripherals": [
                        {
                            "ZoneAssignment": [99],  # Out of range
                            "SensorInputs": {
                                "SHTC1": {
                                    "Temperature_oC": 22.5,
                                    "RelativeHumidity_pc": 55.0,
                                }
                            },
                        }
                    ],
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()
        # Peripheral should be parsed but not mapped to any zone
        assert len(status.peripherals) == 1
        assert status.remote_zone_info[0].actual_humidity_pc is None

    def test_map_peripheral_data_updates_zone_humidity(self):
        """Test _map_peripheral_data_to_zones updates actual_humidity_pc."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {
                    "MasterSerial": "TEST123",
                    "Peripherals": [
                        {
                            "ZoneAssignment": [0],
                            "SensorInputs": {
                                "SHTC1": {
                                    "Temperature_oC": 22.5,
                                    "RelativeHumidity_pc": 55.0,
                                }
                            },
                        }
                    ],
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()
        # Peripheral mapping runs and updates humidity
        # Verify peripheral was created
        assert len(status.peripherals) == 1
        assert status.peripherals[0].humidity == 55.0
        # Test that code path for updating zone humidity is executed
        status._map_peripheral_data_to_zones()
        # After mapping, zone should have humidity
        assert status.remote_zone_info[0].actual_humidity_pc == 55.0


class TestOAuthEdgeCases:
    """Test OAuth edge cases (lines 254, 305)."""

    @pytest.mark.asyncio
    async def test_refresh_token_none_check(self, mock_aiohttp_session):
        """Test refresh check for None access_token and token_expiry after refresh."""
        from actron_neo_api.oauth import ActronAirOAuth2DeviceCodeAuth

        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.refresh_token = "test_refresh"

        # Mock response that sets access_token but then it becomes None somehow
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "access_token": None,  # None value
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_session(mock_resp)):
            with pytest.raises(
                ActronAirAuthError, match="Access token missing or invalid in response"
            ):
                await auth.refresh_access_token()

    @pytest.mark.asyncio
    async def test_ensure_token_valid_no_token_raises(self):
        """Test ensure_token_valid raises when no token available."""
        from actron_neo_api.oauth import ActronAirOAuth2DeviceCodeAuth

        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.access_token = None
        auth.refresh_token = None

        with pytest.raises(ActronAirAuthError, match="Refresh token is required"):
            await auth.ensure_token_valid()


class TestStateManagerPeripheralMapping:
    """Test state manager peripheral mapping (line 129)."""

    def test_map_peripheral_humidity_skips_none(self):
        """Test that peripheral humidity mapping skips None humidity values."""
        from actron_neo_api.state import StateManager

        state_manager = StateManager()

        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {
                    "MasterSerial": "TEST123",
                    "Peripherals": [
                        {
                            "ZoneAssignment": [0],
                            "SensorInputs": {},  # No humidity sensor
                        }
                    ],
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # This should execute the continue statement on line 129
        state_manager._map_peripheral_humidity_to_zones(status)

        # Zone should not have humidity data
        assert status.remote_zone_info[0].actual_humidity_pc is None


class TestZoneEdgeCases:
    """Test zone property edge cases."""

    def test_is_active_zone_id_out_of_range(self):
        """Test is_active when zone_id is out of range (line 144)."""
        from actron_neo_api.models import ActronAirZone

        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "EnabledZones": [True, False],  # Only 2 zones
                },
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Create a zone manually with out of range zone_id
        zone = ActronAirZone(zone_id=5, can_operate=True)  # id 5 >= len([True, False])
        zone.set_parent_status(status, zone_index=5)

        # Should return False due to out of range
        assert zone.is_active is False

    def test_peripheral_temperature_no_parent(self):
        """Test peripheral_temperature returns None without parent (line 202)."""
        from actron_neo_api.models import ActronAirZone

        zone = ActronAirZone(zone_id=0, can_operate=True)
        # No parent status
        assert zone.peripheral_temperature is None

    def test_peripheral_humidity_no_parent(self):
        """Test peripheral_humidity returns None without parent (line 216)."""
        from actron_neo_api.models import ActronAirZone

        zone = ActronAirZone(zone_id=0, can_operate=True)
        # No parent status
        assert zone.peripheral_humidity is None

    def test_peripheral_no_parent(self):
        """Test peripheral property returns None without parent (line 230)."""
        from actron_neo_api.models import ActronAirZone

        zone = ActronAirZone(zone_id=0, can_operate=True)
        # No parent status
        assert zone.peripheral is None

    def test_max_temp_returns_clamped_value(self):
        """Test max_temp returns clamped value when limit is lower (line 251)."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {
                    "TemperatureSetpoint_Cool_oC": 30.0,  # High target
                    "ZoneTemperatureSetpointVariance_oC": 5.0,
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Max": 28.0,  # Lower than target + variance
                    }
                },
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Should return the limit instead of target + variance
        assert status.remote_zone_info[0].max_temp == 28.0

    def test_min_temp_returns_clamped_value(self):
        """Test min_temp returns clamped value when limit is higher (line 271)."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {
                    "TemperatureSetpoint_Cool_oC": 18.0,  # Low target
                    "ZoneTemperatureSetpointVariance_oC": 5.0,
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
                "NV_Limits": {
                    "UserSetpoint_oC": {
                        "setCool_Min": 16.0,  # Higher than target - variance
                    }
                },
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Should return the limit instead of target - variance
        assert status.remote_zone_info[0].min_temp == 16.0

    @pytest.mark.asyncio
    async def test_set_temperature_no_api_raises(self):
        """Test set_temperature raises without API (line 380)."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {"Mode": "COOL"},
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # No API set
        with pytest.raises(ValueError, match="No API reference available"):
            await status.remote_zone_info[0].set_temperature(24.0)

    @pytest.mark.asyncio
    async def test_enable_no_api_raises(self, mock_api):
        """Test enable raises without API (line 401)."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {
                    "EnabledZones": [True, False],
                },
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
            },
            "serial_number": "TEST123",
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Set API but clear it to test the error path
        status.set_api(mock_api)
        status._api = None  # Clear API to trigger error

        # No API set
        with pytest.raises(ValueError, match="No API reference available"):
            await status.remote_zone_info[0].enable(True)
