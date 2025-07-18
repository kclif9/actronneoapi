"""Test OAuth2 device code flow implementation."""

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from actron_neo_api import ActronNeoAPI, OAuth2DeviceCodeAuth, ActronNeoAuthError


class TestOAuth2DeviceCodeAuth:
    """Test OAuth2 device code flow authentication."""

    def test_init(self):
        """Test OAuth2DeviceCodeAuth initialization."""
        auth = OAuth2DeviceCodeAuth("https://example.com", "test_client")
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
        auth = OAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_response = {
            "device_code": "test_device_code",
            "user_code": "TEST123",
            "verification_uri": "https://example.com/device",
            "expires_in": 600,
            "interval": 5
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
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
        auth = OAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_response = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.poll_for_token("test_device_code")

            assert result["access_token"] == "test_access_token"
            assert auth.access_token == "test_access_token"
            assert auth.refresh_token == "test_refresh_token"
            assert auth.is_token_valid

    @pytest.mark.asyncio
    async def test_poll_for_token_pending(self):
        """Test token polling when authorization is pending."""
        auth = OAuth2DeviceCodeAuth("https://example.com", "test_client")

        mock_response = {
            "error": "authorization_pending"
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 400
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.poll_for_token("test_device_code")

            assert result is None

    @pytest.mark.asyncio
    async def test_refresh_access_token(self):
        """Test access token refresh."""
        auth = OAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.refresh_token = "test_refresh_token"

        mock_response = {
            "access_token": "new_access_token",
            "refresh_token": "new_refresh_token",
            "token_type": "Bearer",
            "expires_in": 3600
        }

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json.return_value = mock_response

            token, expiry = await auth.refresh_access_token()

            assert token == "new_access_token"
            assert auth.access_token == "new_access_token"
            assert auth.refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_get_user_info(self):
        """Test getting user information."""
        auth = OAuth2DeviceCodeAuth("https://example.com", "test_client")
        auth.access_token = "test_access_token"

        mock_response = {
            "id": "test_user_id",
            "email": "test@example.com",
            "name": "Test User"
        }

        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_get.return_value.__aenter__.return_value.status = 200
            mock_get.return_value.__aenter__.return_value.json.return_value = mock_response

            result = await auth.get_user_info()

            assert result["id"] == "test_user_id"
            assert result["email"] == "test@example.com"

    def test_set_tokens(self):
        """Test manually setting tokens."""
        auth = OAuth2DeviceCodeAuth("https://example.com", "test_client")

        auth.set_tokens(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_in=3600,
            token_type="Bearer"
        )

        assert auth.access_token == "test_access_token"
        assert auth.refresh_token == "test_refresh_token"
        assert auth.token_type == "Bearer"
        assert auth.is_token_valid


class TestActronNeoAPIWithOAuth2:
    """Test ActronNeoAPI with OAuth2 integration."""

    def test_init_with_oauth2(self):
        """Test ActronNeoAPI initialization with OAuth2."""
        api = ActronNeoAPI(use_oauth2=True)
        assert api.use_oauth2 is True
        assert api.oauth2_auth is not None
        assert api.token_manager is None

    def test_init_without_oauth2(self):
        """Test ActronNeoAPI initialization without OAuth2."""
        api = ActronNeoAPI(username="test", password="test")
        assert api.use_oauth2 is False
        assert api.oauth2_auth is None
        assert api.token_manager is not None

    @pytest.mark.asyncio
    async def test_oauth2_methods_enabled(self):
        """Test OAuth2 methods are available when enabled."""
        api = ActronNeoAPI(use_oauth2=True)

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

    @pytest.mark.asyncio
    async def test_oauth2_methods_disabled(self):
        """Test OAuth2 methods raise error when disabled."""
        api = ActronNeoAPI(username="test", password="test")

        with pytest.raises(ActronNeoAuthError):
            await api.request_device_code()

        with pytest.raises(ActronNeoAuthError):
            await api.poll_for_token("test_device_code")

        with pytest.raises(ActronNeoAuthError):
            await api.get_user_info()

        with pytest.raises(ActronNeoAuthError):
            await api.set_oauth2_tokens("test")

    def test_token_properties(self):
        """Test token properties work with both authentication types."""
        # Test with OAuth2
        oauth2_api = ActronNeoAPI(use_oauth2=True)
        oauth2_api.oauth2_auth.access_token = "oauth2_access_token"
        oauth2_api.oauth2_auth.refresh_token = "oauth2_refresh_token"

        assert oauth2_api.access_token == "oauth2_access_token"
        assert oauth2_api.refresh_token_value == "oauth2_refresh_token"
        assert oauth2_api.pairing_token == "oauth2_refresh_token"

        # Test with traditional auth
        traditional_api = ActronNeoAPI(username="test", password="test")
        traditional_api.token_manager.access_token = "traditional_access_token"
        traditional_api.token_manager.pairing_token = "traditional_pairing_token"

        assert traditional_api.access_token == "traditional_access_token"
        assert traditional_api.refresh_token_value == "traditional_pairing_token"
        assert traditional_api.pairing_token == "traditional_pairing_token"


if __name__ == "__main__":
    pytest.main([__file__])
