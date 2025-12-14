"""Test OAuth2 device code flow implementation."""

import time
from unittest.mock import AsyncMock, patch

import pytest

from actron_neo_api import ActronAirAPI, ActronAirOAuth2DeviceCodeAuth


class TestActronAirOAuth2DeviceCodeAuth:
    """Test OAuth2 device code flow authentication."""

    def test_init(self):
        """Test ActronAirOAuth2DeviceCodeAuth initialization."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        assert auth.base_url == "https://example.com"
        assert auth.client_id == "test_client"
        assert auth.access_token is None
        assert auth.refresh_token is None
        assert auth.token_type == "Bearer"
        assert auth.token_expiry is None
        assert not auth.is_token_valid
        assert not auth.is_token_expiring_soon

    @pytest.mark.asyncio
    async def test_request_device_code_success(self):
        """Test successful device code request."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_response = {
            "device_code": "test_device_code",
            "user_code": "TEST123",
            "verification_uri": "https://example.com/device",
            "expires_in": 600,
            "interval": 5,
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.request_device_code()

            assert result["device_code"] == "test_device_code"
            assert result["user_code"] == "TEST123"
            assert result["verification_uri"] == "https://example.com/device"
            assert "verification_uri_complete" in result

    @pytest.mark.asyncio
    async def test_poll_for_token_success(self):
        """Test successful token polling."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.poll_for_token("test_device_code")

            assert result["access_token"] == "test_access_token"
            assert auth.access_token == "test_access_token"
            assert auth.refresh_token == "test_refresh_token"
            assert auth.is_token_valid

    @pytest.mark.asyncio
    async def test_poll_for_token_pending(self):
        """Test token polling when authorization is pending and times out."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_response = {"error": "authorization_pending"}

        with patch("aiohttp.ClientSession.post") as mock_post, patch("time.time") as mock_time:
            # Simulate timeout by advancing time past the threshold
            # start_time, first check, second check (past timeout)
            mock_time.side_effect = [0, 0, 601]

            mock_post.return_value.__aenter__.return_value.status = 400
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.poll_for_token("test_device_code", interval=1, timeout=1)

            assert result is None

    @pytest.mark.asyncio
    async def test_refresh_access_token(self):
        """Test access token refresh."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.refresh_token = "test_refresh_token"

        mock_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            token, expiry = await auth.refresh_access_token()

            assert token == "new_access_token"
            assert auth.access_token == "new_access_token"
            assert auth.refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_get_user_info(self):
        """Test getting user information."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.access_token = "test_access_token"
        auth.refresh_token = "test_refresh_token"  # Add refresh token to avoid error
        auth.token_expiry = time.time() + 3600  # Set token as valid

        mock_response = {"id": "test_user_id", "email": "test@example.com", "name": "Test User"}

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.get_user_info()

            assert result["id"] == "test_user_id"
            assert result["email"] == "test@example.com"

    def test_set_tokens(self):
        """Test manually setting tokens."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        auth.set_tokens(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600,
            token_type="Bearer",
        )

        assert auth.access_token == "test_access_token"
        assert auth.refresh_token == "test_refresh_token"
        assert auth.token_type == "Bearer"
        assert auth.is_token_valid


class TestActronAirAPIWithOAuth2:
    """Test ActronAirAPI with OAuth2 integration."""

    def test_init_default(self):
        """Test ActronAirAPI initialization with default parameters."""
        api = ActronAirAPI()
        assert api.oauth2_auth is not None
        assert api.oauth2_auth.base_url == "https://nimbus.actronair.com.au"
        assert api.oauth2_auth.client_id == "home_assistant"
        assert api.oauth2_auth.refresh_token is None

    def test_init_with_refresh_token(self):
        """Test ActronAirAPI initialization with refresh token."""
        api = ActronAirAPI(refresh_token="test_refresh_token")
        assert api.oauth2_auth is not None
        assert api.oauth2_auth.refresh_token == "test_refresh_token"

    def test_init_with_custom_params(self):
        """Test ActronAirAPI initialization with custom parameters."""
        api = ActronAirAPI(
            oauth2_client_id="custom_client",
            refresh_token="custom_token",
            platform="neo",
        )
        assert api.oauth2_auth.client_id == "custom_client"
        assert api.oauth2_auth.refresh_token == "custom_token"
        assert api.base_url == "https://nimbus.actronair.com.au"

    @pytest.mark.asyncio
    async def test_oauth2_methods_available(self):
        """Test OAuth2 methods are available."""
        api = ActronAirAPI()

        # Mock the OAuth2 auth methods
        api.oauth2_auth.request_device_code = AsyncMock(return_value={"device_code": "test"})
        api.oauth2_auth.poll_for_token = AsyncMock(return_value={"access_token": "test"})
        api.oauth2_auth.get_user_info = AsyncMock(return_value={"id": "test"})

        # Test methods
        device_code = await api.request_device_code()
        token_data = await api.poll_for_token("test_device_code")
        user_info = await api.get_user_info()

        assert device_code["device_code"] == "test"
        assert token_data["access_token"] == "test"
        assert user_info["id"] == "test"

    def test_token_properties(self):
        """Test token properties work correctly."""
        api = ActronAirAPI(refresh_token="test_refresh_token")
        api.oauth2_auth.access_token = "test_access_token"

        assert api.access_token == "test_access_token"
        assert api.refresh_token_value == "test_refresh_token"


if __name__ == "__main__":
    pytest.main([__file__])
