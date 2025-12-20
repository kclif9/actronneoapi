"""Test OAuth2 device code flow implementation."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from actron_neo_api import ActronAirAPI, ActronAirOAuth2DeviceCodeAuth
from actron_neo_api.exceptions import ActronAirAuthError
from actron_neo_api.models.auth import (
    ActronAirDeviceCode,
    ActronAirToken,
    ActronAirUserInfo,
)


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

            assert result.device_code == "test_device_code"
            assert result.user_code == "TEST123"
            assert result.verification_uri == "https://example.com/device"
            assert result.verification_uri_complete is not None

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

            assert result.access_token == "test_access_token"
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
            # Provide enough values for: start_time, while condition checks, and logging
            mock_time.side_effect = [0, 0, 601, 601, 601]

            mock_post.return_value.__aenter__.return_value.status = 400
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.poll_for_token("test_device_code", interval=1, timeout=10)

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

            assert result.sub == "test_user_id"
            assert result.email == "test@example.com"
            assert result.name == "Test User"

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

    def test_set_tokens_without_expires_in(self):
        """Test setting tokens without expires_in defaults to 1 hour."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        current_time = time.time()
        auth.set_tokens(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
        )

        assert auth.access_token == "test_access_token"
        # Should default to 3600 seconds (1 hour)
        assert auth.token_expiry is not None
        assert auth.token_expiry >= current_time + 3500  # Allow some slack

    def test_authorization_header_without_token(self):
        """Test authorization header without token raises error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        with pytest.raises(ActronAirAuthError, match="No access token available"):
            _ = auth.authorization_header

    def test_authorization_header_with_token(self):
        """Test authorization header with valid token."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.access_token = "test_token"
        auth.token_type = "Bearer"

        header = auth.authorization_header
        assert header == {"Authorization": "Bearer test_token"}

    def test_is_token_valid_properties(self):
        """Test token validity and expiry properties."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        # No token
        assert not auth.is_token_valid
        assert not auth.is_token_expiring_soon

        # Valid token
        auth.access_token = "test_token"
        auth.token_expiry = time.time() + 3600
        assert auth.is_token_valid
        assert not auth.is_token_expiring_soon

        # Expiring soon (within 15 minutes)
        auth.token_expiry = time.time() + 600  # 10 minutes
        assert auth.is_token_valid
        assert auth.is_token_expiring_soon

        # Expired
        auth.token_expiry = time.time() - 100
        assert not auth.is_token_valid
        assert auth.is_token_expiring_soon

    @pytest.mark.asyncio
    async def test_request_device_code_missing_field(self):
        """Test device code request with missing required field."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_response = {
            "user_code": "TEST123",
            # Missing device_code
            "verification_uri": "https://example.com/device",
            "expires_in": 600,
            "interval": 5,
        }

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value=mock_response)

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(
                ActronAirAuthError, match="Missing required fields in response: device_code"
            ):
                await auth.request_device_code()

    @pytest.mark.asyncio
    async def test_request_device_code_http_error(self):
        """Test device code request with HTTP error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.text = AsyncMock(return_value="Bad Request")

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="Failed to request device code"):
                await auth.request_device_code()

    @pytest.mark.asyncio
    async def test_poll_for_token_slow_down(self):
        """Test token polling with slow_down error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        # Return slow_down error twice, then timeout
        responses = [
            {"error": "authorization_pending"},
            {"error": "slow_down"},
            {"error": "authorization_pending"},
        ]
        response_index = [0]

        async def mock_json():
            result = responses[min(response_index[0], len(responses) - 1)]
            response_index[0] += 1
            return result

        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.json = mock_json

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await auth.poll_for_token("test_device", interval=1, timeout=10)
            assert result is None  # Timeout

    @pytest.mark.asyncio
    async def test_poll_for_token_expired(self):
        """Test token polling with expired_token error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.json = AsyncMock(return_value={"error": "expired_token"})

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="Device code has expired"):
                await auth.poll_for_token("test_device")

    @pytest.mark.asyncio
    async def test_poll_for_token_access_denied(self):
        """Test token polling with access_denied error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.json = AsyncMock(return_value={"error": "access_denied"})

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="User denied authorization"):
                await auth.poll_for_token("test_device")

    @pytest.mark.asyncio
    async def test_poll_for_token_unknown_error(self):
        """Test token polling with unknown error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_resp = AsyncMock()
        mock_resp.status = 400
        mock_resp.json = AsyncMock(return_value={"error": "unknown_error"})

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="Authorization error: unknown_error"):
                await auth.poll_for_token("test_device")

    @pytest.mark.asyncio
    async def test_poll_for_token_http_error(self):
        """Test token polling with HTTP error status."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_resp = AsyncMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="Token polling failed"):
                await auth.poll_for_token("test_device")

    @pytest.mark.asyncio
    async def test_poll_for_token_network_error(self):
        """Test token polling with network error continues polling."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise aiohttp.ClientError("Network error")
            # On third call, return timeout
            mock_resp = AsyncMock()
            mock_resp.status = 400
            mock_resp.json = AsyncMock(return_value={"error": "authorization_pending"})
            mock_post = AsyncMock()
            mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
            mock_post.__aexit__ = AsyncMock(return_value=None)
            return mock_post

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(side_effect=side_effect)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            result = await auth.poll_for_token("test_device", interval=1, timeout=10)
            assert result is None  # Should timeout

    @pytest.mark.asyncio
    async def test_poll_for_token_json_parsing_error(self):
        """Test token polling with JSON parsing error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(side_effect=ValueError("Invalid JSON"))

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="Polling failed"):
                await auth.poll_for_token("test_device")

    @pytest.mark.asyncio
    async def test_refresh_access_token_missing_token(self):
        """Test refresh token without refresh_token raises error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        # No refresh token set

        with pytest.raises(ActronAirAuthError, match="Refresh token is required"):
            await auth.refresh_access_token()

    @pytest.mark.asyncio
    async def test_refresh_access_token_missing_access_token_in_response(self):
        """Test refresh token with missing access_token in response."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.refresh_token = "test_refresh"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                # Missing access_token
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(
                ActronAirAuthError, match="Access token missing or invalid in response"
            ):
                await auth.refresh_access_token()

    @pytest.mark.asyncio
    async def test_refresh_access_token_http_error(self):
        """Test refresh token with HTTP error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.refresh_token = "test_refresh"

        mock_resp = AsyncMock()
        mock_resp.status = 401
        mock_resp.text = AsyncMock(return_value="Unauthorized")

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="Failed to refresh access token"):
                await auth.refresh_access_token()

    @pytest.mark.asyncio
    async def test_refresh_access_token_updates_platform(self):
        """Test refresh token updates authenticated_platform."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.refresh_token = "test_refresh"
        auth.base_url = "https://example.com"

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "access_token": "new_token",
                "refresh_token": "new_refresh",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            await auth.refresh_access_token()
            assert auth.authenticated_platform == "https://example.com"

    @pytest.mark.asyncio
    async def test_get_user_info_http_error(self):
        """Test get user info with HTTP error."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.access_token = "test_token"
        auth.refresh_token = "test_refresh"
        auth.token_expiry = time.time() + 3600

        mock_resp = AsyncMock()
        mock_resp.status = 401
        mock_resp.text = AsyncMock(return_value="Unauthorized")

        mock_get = AsyncMock()
        mock_get.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_get.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.get = MagicMock(return_value=mock_get)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ActronAirAuthError, match="Failed to get user info"):
                await auth.get_user_info()

    @pytest.mark.asyncio
    async def test_ensure_token_valid_when_expired(self):
        """Test ensure_token_valid refreshes expired token."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.access_token = "old_token"
        auth.refresh_token = "test_refresh"
        auth.token_expiry = time.time() - 100  # Expired

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "access_token": "new_token",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            token = await auth.ensure_token_valid()
            assert token == "new_token"
            assert auth.access_token == "new_token"

    @pytest.mark.asyncio
    async def test_ensure_token_valid_no_token_after_refresh(self):
        """Test ensure_token_valid when no token available after refresh."""
        auth = ActronAirOAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.access_token = None
        auth.refresh_token = "test_refresh"

        # Mock refresh to set access_token to None
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "token_type": "Bearer",
                "expires_in": 3600,
            }
        )

        mock_post = AsyncMock()
        mock_post.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_post.__aexit__ = AsyncMock(return_value=None)

        mock_session_instance = AsyncMock()
        mock_session_instance.post = MagicMock(return_value=mock_post)

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session_instance)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(
                ActronAirAuthError, match="Access token missing or invalid in response"
            ):
                await auth.ensure_token_valid()


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
        mock_device_code = ActronAirDeviceCode(
            device_code="test",
            user_code="test",
            verification_uri="test",
            verification_uri_complete="test",
            expires_in=300,
            interval=5,
        )
        mock_token = ActronAirToken(
            access_token="test",
            refresh_token="test",
            token_type="Bearer",
            expires_in=3600,
        )
        mock_user_info = ActronAirUserInfo(id="test", email="test@example.com")
        api.oauth2_auth.request_device_code = AsyncMock(return_value=mock_device_code)
        api.oauth2_auth.poll_for_token = AsyncMock(return_value=mock_token)
        api.oauth2_auth.get_user_info = AsyncMock(return_value=mock_user_info)

        # Test methods
        device_code = await api.request_device_code()
        token_data = await api.poll_for_token("test_device_code")
        user_info = await api.get_user_info()

        assert device_code.device_code == "test"
        assert token_data.access_token == "test"
        assert user_info.sub == "test"

    def test_token_properties(self):
        """Test token properties work correctly."""
        api = ActronAirAPI(refresh_token="test_refresh_token")
        api.oauth2_auth.access_token = "test_access_token"

        assert api.access_token == "test_access_token"
        assert api.refresh_token_value == "test_refresh_token"
