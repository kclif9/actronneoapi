"""Tests for ActronAirAPI core client functionality."""

import asyncio
import logging
import time
from copy import deepcopy
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiomqtt import MqttError

from actron_neo_api import ActronAirAPI
from actron_neo_api.exceptions import ActronAirAPIError, ActronAirAuthError
from actron_neo_api.models import (
    ActronAirDeviceCode,
    ActronAirStatus,
    ActronAirToken,
    ActronAirUserInfo,
)
from actron_neo_api.models.system import ActronAirSystemInfo
from actron_neo_api.rt.base import (
    RealtimeConnectionDetails,
    RealtimeConnectionEvent,
    RealtimeConnectionState,
    RealtimeEvent,
    RealtimeEventKind,
    RealtimeMessage,
    RealtimeTransportType,
)


class TestActronAirAPIInitialization:
    """Test ActronAirAPI initialization and configuration."""

    def test_init_default(self) -> None:
        """Test default initialization uses Neo platform."""
        api = ActronAirAPI()
        assert api.base_url == "https://nimbus.actronair.com.au"
        assert api.platform == "neo"
        assert api._auto_manage_base_url is True
        assert api.oauth2_auth is not None
        assert api.systems == []
        assert not api._initialized

    def test_init_with_refresh_token(self) -> None:
        """Test initialization with refresh token."""
        api = ActronAirAPI(refresh_token="test_refresh_token")
        assert api.oauth2_auth.refresh_token == "test_refresh_token"

    def test_init_neo_platform_explicit(self) -> None:
        """Test explicit Neo platform selection."""
        api = ActronAirAPI(platform="neo")
        assert api.base_url == "https://nimbus.actronair.com.au"
        assert api.platform == "neo"
        assert api._auto_manage_base_url is False

    def test_init_que_platform_explicit(self) -> None:
        """Test explicit Que platform selection."""
        api = ActronAirAPI(platform="que")
        assert api.base_url == "https://que.actronair.com.au"
        assert api.platform == "que"
        assert api._auto_manage_base_url is False

    def test_init_custom_client_id(self):
        """Test initialization with custom OAuth2 client ID."""
        api = ActronAirAPI(oauth2_client_id="custom_client")
        assert api.oauth2_auth.client_id == "custom_client"

    def test_authenticated_platform_property(self) -> None:
        """Test authenticated_platform property."""
        api = ActronAirAPI()
        api.oauth2_auth.authenticated_platform = "https://nimbus.actronair.com.au"
        assert api.authenticated_platform == "https://nimbus.actronair.com.au"


class TestActronAirAPIPlatformManagement:
    """Test platform detection and switching."""

    def test_is_nx_gen_system_true(self) -> None:
        """Test NX Gen system detection."""
        api = ActronAirAPI()
        assert api._is_nx_gen_system(ActronAirSystemInfo(serial="1", type="NX-Gen"))
        assert api._is_nx_gen_system(ActronAirSystemInfo(serial="1", type="nx-gen"))
        assert api._is_nx_gen_system(ActronAirSystemInfo(serial="1", type="nxgen"))

    def test_is_nx_gen_system_false(self) -> None:
        """Test non-NX Gen system detection."""
        api = ActronAirAPI()
        assert not api._is_nx_gen_system(ActronAirSystemInfo(serial="1", type="standard"))
        assert not api._is_nx_gen_system(ActronAirSystemInfo(serial="1", type="other"))
        assert not api._is_nx_gen_system(ActronAirSystemInfo(serial="1", type=None))

    def test_set_base_url_changes_platform(self):
        """Test platform URL change."""
        api = ActronAirAPI(platform="neo")
        api._set_base_url("https://que.actronair.com.au", "que")
        assert api.base_url == "https://que.actronair.com.au"
        assert api.platform == "que"

    def test_set_base_url_preserves_tokens(self) -> None:
        """Test token preservation during platform switch."""
        api = ActronAirAPI()
        api.oauth2_auth.access_token = "old_token"
        api.oauth2_auth.refresh_token = "old_refresh"
        api.oauth2_auth.token_expiry = 1234567890.0

        api._set_base_url("https://que.actronair.com.au", "que")

        assert api.oauth2_auth.access_token == "old_token"
        assert api.oauth2_auth.refresh_token == "old_refresh"
        assert api.oauth2_auth.token_expiry == 1234567890.0

    def test_set_base_url_preserves_handler_identity(self) -> None:
        """Test that _set_base_url mutates in-place, not replaces."""
        api = ActronAirAPI(platform="neo")
        original_oauth = api.oauth2_auth

        api._set_base_url("https://que.actronair.com.au", "que")

        assert api.oauth2_auth is original_oauth
        assert api.oauth2_auth.base_url == "https://que.actronair.com.au"

    def test_set_base_url_no_change(self) -> None:
        """Test no-op when setting same URL."""
        api = ActronAirAPI(platform="neo")
        original_oauth = api.oauth2_auth

        api._set_base_url("https://nimbus.actronair.com.au", "neo")

        # Should not recreate OAuth handler
        assert api.oauth2_auth is original_oauth

    def test_maybe_update_base_url_with_nx_gen(
        self, sample_system_que_nxgen: dict[str, Any]
    ) -> None:
        """Test auto-switch to Que platform for NX Gen systems."""
        api = ActronAirAPI()  # Auto-detect enabled
        api._maybe_update_base_url_from_systems([ActronAirSystemInfo(**sample_system_que_nxgen)])
        assert api.base_url == "https://que.actronair.com.au"
        assert api.platform == "que"

    def test_maybe_update_base_url_without_nx_gen(self, sample_system_neo: dict[str, Any]) -> None:
        """Test stays on Neo platform for standard systems."""
        api = ActronAirAPI()  # Auto-detect enabled
        api._maybe_update_base_url_from_systems([ActronAirSystemInfo(**sample_system_neo)])
        assert api.base_url == "https://nimbus.actronair.com.au"
        assert api.platform == "neo"

    def test_maybe_update_base_url_priority_que_over_neo(
        self, sample_system_neo: dict[str, Any], sample_system_que_nxgen: dict[str, Any]
    ) -> None:
        """Test que takes priority over neo when both present."""
        api = ActronAirAPI()  # Auto-detect enabled
        api._maybe_update_base_url_from_systems(
            [
                ActronAirSystemInfo(**sample_system_neo),
                ActronAirSystemInfo(**sample_system_que_nxgen),
            ]
        )
        assert api.base_url == "https://que.actronair.com.au"
        assert api.platform == "que"

    def test_maybe_update_base_url_disabled(self, sample_system_que_nxgen: dict[str, Any]) -> None:
        """Test no auto-switch when platform explicitly set."""
        api = ActronAirAPI(platform="neo")  # Explicit, no auto-detect
        api._maybe_update_base_url_from_systems([ActronAirSystemInfo(**sample_system_que_nxgen)])
        assert api.base_url == "https://nimbus.actronair.com.au"  # Should not change

    def test_maybe_update_base_url_empty_systems(self) -> None:
        """Test no-op with empty systems list."""
        api = ActronAirAPI()
        original_url = api.base_url
        api._maybe_update_base_url_from_systems([])
        assert api.base_url == original_url


class TestActronAirAPISessionManagement:
    """Test aiohttp session lifecycle management."""

    @pytest.mark.asyncio
    async def test_get_session_creates_new(self) -> None:
        """Test session creation on first access."""
        api = ActronAirAPI()
        assert api._session is None

        session = await api._get_session()

        assert session is not None
        assert api._session is session

    @pytest.mark.asyncio
    async def test_get_session_reuses_existing(self) -> None:
        """Test session reuse."""
        api = ActronAirAPI()

        session1 = await api._get_session()
        session2 = await api._get_session()

        assert session1 is session2

    @pytest.mark.asyncio
    async def test_get_session_recreates_if_closed(self) -> None:
        """Test session recreation if closed."""
        from unittest.mock import PropertyMock

        api = ActronAirAPI()

        session1 = await api._get_session()
        # Mock the closed property to return True
        type(session1).closed = PropertyMock(return_value=True)

        session2 = await api._get_session()

        assert session2 is not session1

    @pytest.mark.asyncio
    async def test_close_handles_no_session(self) -> None:
        """Test close() with no active session."""
        api = ActronAirAPI()
        await api.close()  # Should not raise
        assert api._session is None

    @pytest.mark.asyncio
    async def test_context_manager_entry(self) -> None:
        """Test async context manager entry returns API instance."""
        api = ActronAirAPI()

        async with api as context_api:
            assert context_api is api
            session = await api._get_session()
            assert session is not None


class TestActronAirAPISystemLinkResolution:
    """Test HAL link resolution for systems."""

    def test_get_system_link_success(self, sample_system_neo: dict[str, Any]) -> None:
        """Test successful link resolution."""
        api = ActronAirAPI()
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        link = api._get_system_link("abc123", "ac-status")

        assert link == "api/v0/client/ac-systems/abc123/status"

    def test_get_system_link_case_insensitive(self, sample_system_neo: dict[str, Any]) -> None:
        """Test case-insensitive serial number matching."""
        api = ActronAirAPI()
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        link = api._get_system_link("ABC123", "ac-status")  # Uppercase

        assert link is not None
        assert "abc123" in link

    def test_get_system_link_not_found(self) -> None:
        """Test link not found returns None."""
        api = ActronAirAPI()
        api.systems = [ActronAirSystemInfo(serial="abc123", links={})]

        link = api._get_system_link("abc123", "missing-link")

        assert link is None

    def test_get_system_link_system_not_found(self) -> None:
        """Test system not found returns None."""
        api = ActronAirAPI()
        api.systems = [ActronAirSystemInfo(serial="abc123")]

        link = api._get_system_link("xyz789", "ac-status")

        assert link is None

    def test_get_system_link_strips_leading_slash(self) -> None:
        """Test leading slash is stripped from href."""
        api = ActronAirAPI()
        api.systems = [
            ActronAirSystemInfo(
                serial="abc123",
                links={"test": {"href": "/api/v0/test"}},
            )
        ]

        link = api._get_system_link("abc123", "test")

        assert link == "api/v0/test"

    def test_get_system_link_list_format(self) -> None:
        """Test link resolution with list format."""
        api = ActronAirAPI()
        api.systems = [
            ActronAirSystemInfo(
                serial="abc123",
                links={"test": [{"href": "/api/v0/test"}]},
            )
        ]

        link = api._get_system_link("abc123", "test")

        assert link == "api/v0/test"


class TestActronAirAPIGetSystems:
    """Test get_ac_systems method."""

    @pytest.mark.asyncio
    async def test_get_ac_systems_success(
        self,
        mock_session: AsyncMock,
        sample_systems_response_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test successful systems retrieval."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_systems_response_neo
        )

        systems = await api.get_ac_systems()

        assert len(systems) == 1
        assert systems[0].serial == "abc123"
        assert api.systems == systems

    @pytest.mark.asyncio
    async def test_get_ac_systems_triggers_platform_detection(
        self,
        mock_session: AsyncMock,
        sample_systems_response_que: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test platform auto-detection on systems retrieval."""
        api = ActronAirAPI(refresh_token="test_token")  # Auto-detect enabled
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_systems_response_que
        )

        await api.get_ac_systems()

        assert api.platform == "que"

    @pytest.mark.asyncio
    async def test_get_ac_systems_includes_neo_param(
        self,
        mock_session: AsyncMock,
        sample_systems_response_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test includeNeo parameter is sent."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_systems_response_neo
        )

        await api.get_ac_systems()

        # Verify request was made with correct params
        call_args = mock_session.request.call_args
        assert call_args[1]["params"]["includeNeo"] == "true"


class TestActronAirAPIGetStatus:
    """Test get_ac_status method."""

    @pytest.mark.asyncio
    async def test_get_ac_status_success(
        self,
        mock_session: AsyncMock,
        sample_status_full: dict[str, Any],
        sample_system_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test successful status retrieval."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_status_full
        )

        status = await api.get_ac_status("abc123")

        assert status.is_online is True
        assert status.serial_number.lower() == "abc123"
        assert status.ac_system.master_serial == "ABC123"

    @pytest.mark.asyncio
    async def test_get_ac_status_normalizes_serial(
        self,
        mock_session: AsyncMock,
        sample_status_full: dict[str, Any],
        sample_system_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test serial number normalization."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_status_full
        )

        status = await api.get_ac_status("ABC123")  # Uppercase

        assert status is not None

    @pytest.mark.asyncio
    async def test_get_ac_status_missing_link_raises(self) -> None:
        """Test error when status link is missing."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api.systems = [ActronAirSystemInfo(serial="abc123", links={})]

        with pytest.raises(ActronAirAPIError, match="No ac-status link found"):
            await api.get_ac_status("abc123")


class TestActronAirAPISendCommand:
    """Test send_command method."""

    @pytest.mark.asyncio
    async def test_send_command_success(
        self,
        mock_session: AsyncMock,
        sample_command_response: dict[str, Any],
        sample_system_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test successful command sending."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_command_response
        )

        command = {"command": {"type": "set-settings", "UserAirconSettings.isOn": True}}
        await api.send_command("abc123", command)

        # Verify the command was sent (response is None for successful commands)
        mock_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_command_normalizes_serial(
        self,
        mock_session: AsyncMock,
        sample_command_response: dict[str, Any],
        sample_system_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test serial number normalization in send_command."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_command_response
        )

        command = {"command": {"type": "set-settings"}}
        await api.send_command("ABC123", command)  # Uppercase

        # Verify command was sent successfully (returns None)
        mock_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_command_missing_link_raises(self) -> None:
        """Test error when commands link is missing."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api.systems = [ActronAirSystemInfo(serial="abc123", links={})]

        with pytest.raises(ActronAirAPIError, match="No commands link found"):
            await api.send_command("abc123", {})

    @pytest.mark.asyncio
    async def test_send_command_sets_content_type(
        self,
        mock_session: AsyncMock,
        sample_command_response: dict[str, Any],
        sample_system_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test Content-Type header is set."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_command_response
        )

        await api.send_command("abc123", {})

        # Verify Content-Type was set
        call_args = mock_session.request.call_args
        assert call_args[1]["headers"]["Content-Type"] == "application/json"


class TestActronAirAPIErrorHandling:
    """Test error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_make_request_401_triggers_refresh_and_retry(
        self, mock_session: AsyncMock, mock_aiohttp_response: Any, mock_oauth: AsyncMock
    ) -> None:
        """Test 401 response triggers token refresh and retry."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.oauth2_auth.refresh_access_token = AsyncMock()

        # First call returns 401, second call succeeds
        mock_session.request.return_value.__aenter__.side_effect = [
            mock_aiohttp_response(status=401, text="Unauthorized"),
            mock_aiohttp_response(status=200, json_data={"success": True}),
        ]

        result = await api._make_request("get", "test/endpoint")

        assert result["success"] is True
        api.oauth2_auth.refresh_access_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_401_without_refresh_token_raises(
        self, mock_session: AsyncMock, mock_aiohttp_response: Any
    ) -> None:
        """Test 401 without refresh token raises immediately."""
        api = ActronAirAPI()  # No refresh token
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth.refresh_token = None

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=401, text="Unauthorized"
        )

        with pytest.raises(ActronAirAuthError, match="Refresh token is required"):
            await api._make_request("get", "test/endpoint")

    @pytest.mark.asyncio
    async def test_make_request_401_refresh_fails_raises(
        self, mock_session: AsyncMock, mock_aiohttp_response: Any
    ) -> None:
        """Test 401 with failed refresh raises ActronAirAuthError."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        # Set valid token so ensure_token_valid passes through
        api.oauth2_auth.access_token = "valid_token"
        api.oauth2_auth.token_expiry = time.monotonic() + 3600
        api.oauth2_auth.refresh_access_token = AsyncMock(
            side_effect=ActronAirAuthError("Refresh failed")
        )

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=401, text="Unauthorized"
        )

        with pytest.raises(ActronAirAuthError, match="Refresh failed"):
            await api._make_request("get", "test/endpoint")

    @pytest.mark.asyncio
    async def test_make_request_non_200_raises(
        self, mock_session: AsyncMock, mock_aiohttp_response: Any, mock_oauth: AsyncMock
    ) -> None:
        """Test non-200 response raises ActronAirAPIError."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=500, text="Internal Server Error"
        )

        with pytest.raises(ActronAirAPIError, match="API request failed"):
            await api._make_request("get", "test/endpoint")

    @pytest.mark.asyncio
    async def test_make_request_network_error_raises(
        self, mock_session: AsyncMock, mock_oauth: AsyncMock
    ) -> None:
        """Test network error raises ActronAirAPIError."""
        import aiohttp

        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth

        mock_session.request.side_effect = aiohttp.ClientError("Network error")

        with pytest.raises(ActronAirAPIError, match="Request failed"):
            await api._make_request("get", "test/endpoint")


class TestActronAirAPITokenProperties:
    """Test token property accessors."""

    def test_access_token_property(self) -> None:
        """Test access_token property."""
        api = ActronAirAPI()
        api.oauth2_auth.access_token = "test_token"
        assert api.access_token == "test_token"

    def test_refresh_token_value_property(self) -> None:
        """Test refresh_token_value property."""
        api = ActronAirAPI()
        api.oauth2_auth.refresh_token = "test_refresh"
        assert api.refresh_token_value == "test_refresh"

    def test_latest_event_id_property(self) -> None:
        """Test latest_event_id property returns empty dict (deprecated)."""
        api = ActronAirAPI()
        assert api.latest_event_id == {}


class TestActronAirAPIUpdateStatus:
    """Test status update methods."""

    @pytest.mark.asyncio
    async def test_update_status_single_system(
        self,
        mock_session: AsyncMock,
        sample_status_full: dict[str, Any],
        sample_system_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test updating single system status."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_status_full
        )

        result = await api.update_status("abc123")

        assert "abc123" in result
        assert result["abc123"] is not None

    @pytest.mark.asyncio
    async def test_update_status_all_systems(
        self,
        mock_session: AsyncMock,
        sample_status_full: dict[str, Any],
        sample_system_neo: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test updating all systems."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data=sample_status_full
        )

        result = await api.update_status()

        assert len(result) == 1
        assert "abc123" in result

    @pytest.mark.asyncio
    async def test_update_status_empty_systems(self) -> None:
        """Test update_status with no systems returns empty dict."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api.systems = []

        result = await api.update_status()

        assert result == {}

    @pytest.mark.asyncio
    async def test_ensure_initialized_with_refresh_token(self) -> None:
        """Test initialization triggers token refresh."""
        api = ActronAirAPI(refresh_token="test_token")
        api.oauth2_auth.access_token = None
        api.oauth2_auth.refresh_access_token = AsyncMock()

        await api._ensure_initialized()

        api.oauth2_auth.refresh_access_token.assert_called_once()
        assert api._initialized is True

    @pytest.mark.asyncio
    async def test_ensure_initialized_already_initialized(self) -> None:
        """Test ensure_initialized is idempotent."""
        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api.oauth2_auth.refresh_access_token = AsyncMock()

        await api._ensure_initialized()

        api.oauth2_auth.refresh_access_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_initialized_failure_raises(self) -> None:
        """Test initialization failure raises ActronAirAuthError."""
        import aiohttp

        api = ActronAirAPI(refresh_token="test_token")
        api.oauth2_auth.access_token = None
        api.oauth2_auth.refresh_access_token = AsyncMock(
            side_effect=aiohttp.ClientError("Network error")
        )

        with pytest.raises(ActronAirAuthError, match="Failed to initialize API"):
            await api._ensure_initialized()

    @pytest.mark.asyncio
    async def test_ensure_initialized_concurrent_single_init(self) -> None:
        """Concurrent first calls only trigger one initialization."""
        import asyncio

        api = ActronAirAPI(refresh_token="test_token")
        api.oauth2_auth.access_token = None

        call_count = 0

        async def mock_refresh() -> tuple[str, float]:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.05)
            api.oauth2_auth.access_token = "new_token"
            return "new_token", 0.0

        api.oauth2_auth.refresh_access_token = mock_refresh  # type: ignore[assignment]

        await asyncio.gather(
            api._ensure_initialized(),
            api._ensure_initialized(),
        )

        assert call_count == 1
        assert api._initialized is True


class TestActronAirAPIOAuth2Methods:
    """Test OAuth2 method proxies."""

    @pytest.mark.asyncio
    async def test_request_device_code_proxy(self) -> None:
        """Test request_device_code proxies to OAuth2 handler."""
        api = ActronAirAPI()
        mock_response = ActronAirDeviceCode(
            device_code="test",
            user_code="TEST",
            verification_uri="http://test",
            verification_uri_complete="http://test?user_code=TEST",
            expires_in=600,
            interval=5,
        )
        api.oauth2_auth.request_device_code = AsyncMock(return_value=mock_response)

        result = await api.request_device_code()

        assert result.device_code == "test"
        api.oauth2_auth.request_device_code.assert_called_once()

    @pytest.mark.asyncio
    async def test_poll_for_token_proxy(self) -> None:
        """Test poll_for_token proxies to OAuth2 handler."""
        api = ActronAirAPI()
        mock_response = ActronAirToken(
            access_token="test",
            token_type="Bearer",
            expires_in=3600,
            scope="read",
        )
        api.oauth2_auth.poll_for_token = AsyncMock(return_value=mock_response)

        result = await api.poll_for_token("device_code")

        assert result is not None
        assert result.access_token == "test"
        api.oauth2_auth.poll_for_token.assert_called_once_with("device_code", 5, 600)

    @pytest.mark.asyncio
    async def test_get_user_info_proxy(self) -> None:
        """Test get_user_info proxies to OAuth2 handler."""
        api = ActronAirAPI()
        mock_user = ActronAirUserInfo(id="test_user", email="test@example.com")
        api.oauth2_auth.get_user_info = AsyncMock(return_value=mock_user)

        result = await api.get_user_info()

        assert result.sub == "test_user"
        api.oauth2_auth.get_user_info.assert_called_once()


class TestActronAirAPIInjectableSession:
    """Test injectable websession support."""

    def test_init_with_external_session(self) -> None:
        """Test initialization with an externally-provided session."""
        from unittest.mock import MagicMock

        external_session = MagicMock()
        api = ActronAirAPI(session=external_session)

        assert api._session is external_session
        assert api._external_session is True
        # OAuth handler should also receive the session
        assert api.oauth2_auth._session is external_session

    def test_init_without_session(self) -> None:
        """Test initialization without session uses default behavior."""
        api = ActronAirAPI()
        assert api._session is None
        assert api._external_session is False
        assert api.oauth2_auth._session is None

    @pytest.mark.asyncio
    async def test_close_does_not_close_external_session(self) -> None:
        """Test close() does NOT close an externally-provided session."""
        from unittest.mock import MagicMock

        external_session = MagicMock()
        external_session.closed = False
        external_session.close = AsyncMock()

        api = ActronAirAPI(session=external_session)
        await api.close()

        external_session.close.assert_not_called()
        # Session reference is kept (caller owns it)
        assert api._session is external_session

    @pytest.mark.asyncio
    async def test_close_closes_internal_session(self) -> None:
        """Test close() closes an internally-created session."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()

        api = ActronAirAPI()
        # Simulate an internally-created session
        api._session = mock_session
        api._external_session = False

        await api.close()

        mock_session.close.assert_called_once()
        assert api._session is None

    @pytest.mark.asyncio
    async def test_get_session_returns_external_session(self) -> None:
        """Test _get_session returns the external session."""
        from unittest.mock import MagicMock

        external_session = MagicMock()
        external_session.closed = False

        api = ActronAirAPI(session=external_session)
        session = await api._get_session()

        assert session is external_session

    @pytest.mark.asyncio
    async def test_get_session_creates_new_if_external_closed(self) -> None:
        """Test _get_session creates a new session if external one is closed."""
        from unittest.mock import PropertyMock

        external_session = MagicMock()
        type(external_session).closed = PropertyMock(return_value=True)

        api = ActronAirAPI(session=external_session)
        session = await api._get_session()

        assert session is not external_session
        assert api._external_session is False
        assert api.oauth2_auth._session is session

    @pytest.mark.asyncio
    async def test_external_session_used_for_api_requests(
        self,
        sample_system_neo: dict[str, Any],
        sample_command_response: dict[str, Any],
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """Test external session is used for API requests."""
        from unittest.mock import MagicMock

        external_session = MagicMock()
        external_session.closed = False

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(
            return_value=mock_aiohttp_response(status=200, json_data=sample_command_response)
        )
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        external_session.request = MagicMock(return_value=mock_ctx)

        api = ActronAirAPI(session=external_session, refresh_token="test_token")
        api._initialized = True
        api.oauth2_auth = mock_oauth
        api.systems = [ActronAirSystemInfo(**sample_system_neo)]

        command = {"command": {"type": "set-settings", "UserAirconSettings.isOn": True}}
        await api.send_command("abc123", command)

        # Verify the external session was used
        external_session.request.assert_called_once()

    def test_set_base_url_preserves_session(self) -> None:
        """Test _set_base_url preserves session on in-place mutation."""
        from unittest.mock import MagicMock

        external_session = MagicMock()
        api = ActronAirAPI(session=external_session)

        api._set_base_url("https://que.actronair.com.au", "que")

        assert api.oauth2_auth._session is external_session


class TestActronAirAPIRealtimeIntegration:
    """Test issue #77 realtime public API integration."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("user_info", "expected_username"),
        [
            pytest.param(
                ActronAirUserInfo(email="user@example.test"), "user@example.test", id="normal"
            ),
            pytest.param(
                ActronAirUserInfo(email="  user@example.test  "),
                "user@example.test",
                id="whitespace",
            ),
            pytest.param(ActronAirUserInfo(email=""), "", id="empty"),
            pytest.param(ActronAirUserInfo(email="   "), "", id="blank"),
            pytest.param(None, "", id="no_user_info"),
        ],
    )
    async def test_start_push_selects_mqtt_for_neo(
        self, user_info: ActronAirUserInfo | None, expected_username: str
    ) -> None:
        """Neo platform should use the MQTT transport with a normalized username.

        An unusable email is passed through as an empty string; MQTTRTClient
        owns the fallback to "unknown".
        """

        class FakeMQTTClient:
            def __init__(
                self, details: RealtimeConnectionDetails, user_email: str, token: str
            ) -> None:
                self.details = details
                self.user_email = user_email
                self.token = token
                self.callbacks: list[Any] = []
                self.subscribed: list[str] = []

            def register_callback(self, callback: Any) -> None:
                self.callbacks.append(callback)

            async def connect(self) -> None:
                return None

            async def subscribe_system(self, serial: str) -> None:
                self.subscribed.append(serial)

            async def disconnect(self) -> None:
                return None

            async def update_access_token(self, token: str) -> None:
                self.token = token

        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.oauth2_auth.get_user_info = AsyncMock(return_value=user_info)
        api.systems = [ActronAirSystemInfo(serial="ABC123")]

        async def _discover(_: str) -> RealtimeConnectionDetails:
            return RealtimeConnectionDetails(
                endpoint="mqtt.example.test",
                port=8883,
                protocol="ssl",
                user_id="u",
            )

        api._discover_realtime_connection_details = _discover  # type: ignore[method-assign]

        from actron_neo_api import actron as actron_module

        original_mqtt = actron_module.MQTTRTClient
        try:
            actron_module.MQTTRTClient = FakeMQTTClient  # type: ignore[assignment]
            started = await api.start_push()
        finally:
            actron_module.MQTTRTClient = original_mqtt  # type: ignore[assignment]

        assert started is True
        assert isinstance(api._rt_client, FakeMQTTClient)
        assert api._rt_client.subscribed == ["abc123"]
        assert api._rt_client.user_email == expected_username

    @pytest.mark.asyncio
    async def test_start_push_survives_user_info_failure(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A user-info lookup failure must not stop push or trigger reauth.

        The email is only a broker-side label, so its lookup is best-effort even
        though get_user_info() reports every failure as an auth error.
        """

        class FakeMQTTClient:
            def __init__(
                self, details: RealtimeConnectionDetails, user_email: str, token: str
            ) -> None:
                self.user_email = user_email

            def register_callback(self, callback: Any) -> None:
                self.callback = callback

            async def connect(self) -> None:
                return None

            async def subscribe_system(self, serial: str) -> None:
                return None

            async def disconnect(self) -> None:
                return None

        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.oauth2_auth.get_user_info = AsyncMock(
            side_effect=ActronAirAuthError("user info unavailable")
        )
        api.systems = [ActronAirSystemInfo(serial="abc123")]

        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.test",
            port=8883,
            protocol="ssl",
            user_id="u",
        )

        from actron_neo_api import actron as actron_module

        original_mqtt = actron_module.MQTTRTClient
        try:
            actron_module.MQTTRTClient = FakeMQTTClient  # type: ignore[assignment]
            with caplog.at_level(logging.DEBUG, logger="actron_neo_api.actron"):
                started = await api.start_push(connection_details=details)
        finally:
            actron_module.MQTTRTClient = original_mqtt  # type: ignore[assignment]

        assert started is True
        assert isinstance(api._rt_client, FakeMQTTClient)
        assert api._rt_client.user_email == ""
        assert "Could not resolve account email for MQTT username" in caplog.text

    @pytest.mark.asyncio
    async def test_start_push_selects_signalr_for_que(self) -> None:
        """Que platform should use the SignalR transport."""

        class FakeSignalRClient:
            def __init__(self, details: RealtimeConnectionDetails, token: str) -> None:
                self.details = details
                self.token = token
                self.subscribed: list[str] = []

            def register_callback(self, callback: Any) -> None:
                self.callback = callback

            async def connect(self) -> None:
                return None

            async def subscribe(self, serial: str) -> None:
                self.subscribed.append(serial)

            async def disconnect(self) -> None:
                return None

            async def update_access_token(self, token: str) -> None:
                self.token = token

        api = ActronAirAPI(platform="que")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.oauth2_auth.get_user_info = AsyncMock(
            side_effect=AssertionError("should not be called")
        )
        api.systems = [ActronAirSystemInfo(serial="xyz789")]

        async def _discover(_: str) -> RealtimeConnectionDetails:
            return RealtimeConnectionDetails(
                endpoint="https://que.example.test/api/v0/messaging/app",
                port=443,
                protocol="https",
                user_id="u",
            )

        api._discover_realtime_connection_details = _discover  # type: ignore[method-assign]

        from actron_neo_api import actron as actron_module

        original_signalr = actron_module.SignalRRTClient
        try:
            actron_module.SignalRRTClient = FakeSignalRClient  # type: ignore[assignment]
            started = await api.start_push()
        finally:
            actron_module.SignalRRTClient = original_signalr  # type: ignore[assignment]

        assert started is True
        assert isinstance(api._rt_client, FakeSignalRClient)
        assert api._rt_client.subscribed == ["xyz789"]

    @pytest.mark.asyncio
    async def test_start_push_returns_false_without_systems(self) -> None:
        """start_push should fail gracefully when no systems are available."""
        api = ActronAirAPI()
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.get_ac_systems = AsyncMock(return_value=[])

        started = await api.start_push()

        assert started is False

    @pytest.mark.asyncio
    async def test_stop_push_disconnects_transport(self) -> None:
        """stop_push should disconnect and clear active transport."""

        class FakeClient:
            def __init__(self) -> None:
                self.disconnect = AsyncMock(return_value=None)

        api = ActronAirAPI()
        client = FakeClient()
        api._rt_client = client  # type: ignore[assignment]
        api._push_running = True

        await api.stop_push()

        client.disconnect.assert_called_once()
        assert api._rt_client is None
        assert api._push_running is False

    @pytest.mark.asyncio
    async def test_subscribe_and_stream_system_updates(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Callbacks and stream should receive parsed ActronAirStatus updates."""
        api = ActronAirAPI()
        api._push_running = True
        seen: list[str] = []

        def _cb(status: ActronAirStatus) -> None:
            if status.serial_number:
                seen.append(status.serial_number)

        api.subscribe_system_updates("ABC123", _cb)

        status = ActronAirStatus.model_validate(sample_status_full)
        status.serial_number = "abc123"
        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/full-status",
            payload={},
            raw_payload=None,
            domain_model=status,
        )

        async def _collect() -> list[ActronAirStatus]:
            return [item async for item in api.stream_system_updates("abc123")]

        collector = asyncio.create_task(_collect())
        await asyncio.sleep(0)
        await api._handle_realtime_event(event)
        await api.stop_push()
        streamed = await collector

        assert len(streamed) == 1
        assert streamed[0].serial_number == "abc123"
        assert seen == ["abc123"]

    @pytest.mark.asyncio
    async def test_handle_realtime_event_merges_mqtt_status_change_delta(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """MQTT status-change payloads should merge into the current baseline state."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.state_manager.process_status_update("abc123", sample_status_full)

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={
                "UserAirconSettings": {
                    "QuietModeEnabled": True,
                    "TurboMode": {"Enabled": True, "Supported": True},
                }
            },
            raw_payload=None,
            domain_model=None,
        )

        await api._handle_realtime_event(event)

        status = api.state_manager.get_status("abc123")
        assert status is not None
        assert status.user_aircon_settings.quiet_mode_enabled is True
        assert status.user_aircon_settings.turbo_enabled is True
        assert status.user_aircon_settings.mode == "COOL"
        assert status.user_aircon_settings.temperature_setpoint_cool_c == 24.0

    @pytest.mark.asyncio
    async def test_handle_realtime_event_hydrates_baseline_for_mqtt_status_change(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """MQTT deltas should fetch a baseline status when none is cached yet."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True

        async def _update_status(serial_number: str | None = None) -> dict[str, Any]:
            assert serial_number == "abc123"
            status = api.state_manager.process_status_update("abc123", sample_status_full)
            return {"abc123": status}

        api.update_status = AsyncMock(side_effect=_update_status)

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={"UserAirconSettings": {"QuietModeEnabled": True}},
            raw_payload=None,
            domain_model=None,
        )

        await api._handle_realtime_event(event)

        api.update_status.assert_awaited_once_with("abc123")
        status = api.state_manager.get_status("abc123")
        assert status is not None
        assert status.user_aircon_settings.quiet_mode_enabled is True

    @pytest.mark.asyncio
    async def test_handle_realtime_event_mqtt_status_change_with_nested_last_known_state(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Nested lastKnownState deltas should merge into the cached baseline."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.state_manager.process_status_update("abc123", sample_status_full)

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={
                "lastKnownState": {
                    "UserAirconSettings": {
                        "QuietModeEnabled": True,
                    }
                }
            },
            raw_payload=None,
            domain_model=None,
        )

        await api._handle_realtime_event(event)

        status = api.state_manager.get_status("abc123")
        assert status is not None
        assert status.user_aircon_settings.quiet_mode_enabled is True

    @pytest.mark.asyncio
    async def test_handle_realtime_event_refreshes_status_for_metadata_only_mqtt_signal(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Metadata-only MQTT status-change signals should force a fresh API refresh."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.state_manager.process_status_update("abc123", sample_status_full)

        refreshed_payload = deepcopy(sample_status_full)
        refreshed_settings = refreshed_payload["lastKnownState"]["UserAirconSettings"]
        refreshed_settings["QuietModeEnabled"] = True
        refreshed_settings["TurboMode"] = {"Enabled": True, "Supported": True}

        async def _update_status(serial_number: str | None = None) -> dict[str, Any]:
            assert serial_number == "abc123"
            status = api.state_manager.process_status_update("abc123", refreshed_payload)
            return {"abc123": status}

        api.update_status = AsyncMock(side_effect=_update_status)

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={"event": "statusChange", "wcFirmware": "1.2.3"},
            raw_payload=None,
            domain_model=None,
        )

        await api._handle_realtime_event(event)

        api.update_status.assert_awaited_once_with("abc123")
        status = api.state_manager.get_status("abc123")
        assert status is not None
        assert status.user_aircon_settings.quiet_mode_enabled is True
        assert status.user_aircon_settings.turbo_enabled is True

    @pytest.mark.asyncio
    async def test_handle_realtime_event_drops_mqtt_status_change_when_baseline_fails(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """MQTT deltas should be dropped when the baseline status cannot be fetched."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.update_status = AsyncMock(side_effect=RuntimeError("boom"))

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={"UserAirconSettings": {"QuietModeEnabled": True}},
            raw_payload=None,
            domain_model=None,
        )

        with caplog.at_level(logging.WARNING):
            await api._handle_realtime_event(event)

        assert api.state_manager.get_status("abc123") is None
        assert "Failed to hydrate baseline status for realtime delta abc123" in caplog.text

    @pytest.mark.asyncio
    async def test_handle_realtime_event_drops_mqtt_status_change_without_hydrated_baseline(
        self,
    ) -> None:
        """MQTT deltas should be ignored if baseline hydration returns no cached status."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.update_status = AsyncMock(return_value={})

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={"UserAirconSettings": {"QuietModeEnabled": True}},
            raw_payload=None,
            domain_model=None,
        )

        await api._handle_realtime_event(event)

        api.update_status.assert_awaited_once_with("abc123")
        assert api.state_manager.get_status("abc123") is None

    @pytest.mark.asyncio
    async def test_handle_realtime_event_metadata_only_mqtt_signal_without_refresh_result(
        self,
    ) -> None:
        """Metadata-only MQTT signals should be ignored if refresh yields no status."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.state_manager.status["abc123"] = ActronAirStatus.model_validate(
            {"isOnline": True, "lastKnownState": {}}
        )
        api.update_status = AsyncMock(return_value={})

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={"event": "statusChange", "wcFirmware": "1.2.3"},
            raw_payload=None,
            domain_model=None,
        )

        await api._handle_realtime_event(event)

        api.update_status.assert_awaited_once_with("abc123")

    @pytest.mark.asyncio
    async def test_refresh_status_from_realtime_signal_deduplicates_concurrent_calls(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Concurrent metadata refreshes for one serial should share one API request."""
        api = ActronAirAPI(platform="neo")

        async def _update_status(serial_number: str | None = None) -> dict[str, Any]:
            assert serial_number == "abc123"
            api.state_manager.process_status_update("abc123", sample_status_full)
            await asyncio.sleep(0)
            return {}

        api.update_status = AsyncMock(side_effect=_update_status)

        first, second = await asyncio.gather(
            api._refresh_status_from_realtime_signal("abc123"),
            api._refresh_status_from_realtime_signal("abc123"),
        )

        assert first is not None
        assert second is not None
        api.update_status.assert_awaited_once_with("abc123")

    def test_mqtt_status_change_contains_state_ignores_metadata_only_fields(self) -> None:
        """Metadata-only MQTT status-change payloads should not be treated as state deltas."""
        assert (
            ActronAirAPI._mqtt_status_change_contains_state(
                {
                    "event": "statusChange",
                    "wcFirmware": "1.2.3",
                    "isOnline": True,
                    "serialNumber": "ABC123",
                }
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_handle_realtime_event_drops_mqtt_status_change_when_merge_invalid(
        self,
        sample_status_full: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Invalid merged MQTT deltas should be logged and skipped."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.state_manager.process_status_update("abc123", sample_status_full)

        def _raise_validate(_: Any) -> ActronAirStatus:
            raise ValueError("merge boom")

        monkeypatch.setattr(
            ActronAirStatus,
            "model_validate",
            classmethod(lambda cls, payload: _raise_validate(payload)),
        )

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={"UserAirconSettings": {"QuietModeEnabled": True}},
            raw_payload=None,
            domain_model=None,
        )

        with caplog.at_level(logging.WARNING):
            await api._handle_realtime_event(event)

        assert "Failed to merge MQTT status-change for abc123" in caplog.text

    @pytest.mark.asyncio
    async def test_make_request_syncs_realtime_token(
        self,
        mock_session: AsyncMock,
        mock_aiohttp_response: Any,
        mock_oauth: AsyncMock,
    ) -> None:
        """_make_request should push refreshed/access token to realtime transport."""

        class FakeClient:
            def __init__(self) -> None:
                self.update_access_token = AsyncMock(return_value=None)

        api = ActronAirAPI(refresh_token="test_token")
        api._initialized = True
        api._session = mock_session
        api.oauth2_auth = mock_oauth
        api._rt_client = FakeClient()  # type: ignore[assignment]

        mock_session.request.return_value.__aenter__.return_value = mock_aiohttp_response(
            status=200, json_data={"ok": True}
        )

        result = await api._make_request("get", "test/endpoint")

        assert result["ok"] is True
        api._rt_client.update_access_token.assert_called_once_with("test_access_token")

    @pytest.mark.asyncio
    async def test_start_push_returns_true_when_already_running(self) -> None:
        """start_push should no-op when push is already active."""
        api = ActronAirAPI()
        api._push_running = True
        api._rt_client = object()  # type: ignore[assignment]

        started = await api.start_push()

        assert started is True

    @pytest.mark.asyncio
    async def test_start_push_returns_false_when_details_unavailable(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """start_push should fallback when realtime details cannot be resolved."""
        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.systems = [ActronAirSystemInfo(serial="abc123")]

        async def _discover(_: str) -> None:
            return None

        api._discover_realtime_connection_details = _discover  # type: ignore[method-assign]

        with caplog.at_level(logging.DEBUG, logger="actron_neo_api.actron"):
            started = await api.start_push()

        assert started is False
        assert "Realtime connection details unavailable; push not started" in caplog.text
        # Unavailable realtime is an expected fallback, not an operator-facing problem.
        assert not any(
            record.name == "actron_neo_api.actron" and record.levelno > logging.DEBUG
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_start_push_uses_explicit_serial_numbers(self) -> None:
        """start_push should honor provided serial_numbers and ignore blanks."""

        class FakeMQTTClient:
            def __init__(
                self, details: RealtimeConnectionDetails, user_email: str, token: str
            ) -> None:
                self.subscribed: list[str] = []

            def register_callback(self, callback: Any) -> None:
                self.callback = callback

            async def connect(self) -> None:
                return None

            async def subscribe_system(self, serial: str) -> None:
                self.subscribed.append(serial)

            async def disconnect(self) -> None:
                return None

            async def update_access_token(self, token: str) -> None:
                return None

        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.oauth2_auth.get_user_info = AsyncMock(
            return_value=ActronAirUserInfo(email="user@example.test")
        )

        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.test",
            port=8883,
            protocol="ssl",
            user_id="u",
        )

        from actron_neo_api import actron as actron_module

        original_mqtt = actron_module.MQTTRTClient
        try:
            actron_module.MQTTRTClient = FakeMQTTClient  # type: ignore[assignment]
            started = await api.start_push(
                serial_numbers=["ABC123", "", "  "], connection_details=details
            )
        finally:
            actron_module.MQTTRTClient = original_mqtt  # type: ignore[assignment]

        assert started is True
        assert isinstance(api._rt_client, FakeMQTTClient)
        assert api._rt_client.subscribed == ["abc123"]

    @pytest.mark.asyncio
    async def test_start_push_handles_missing_transport_instance(self) -> None:
        """start_push should fail gracefully when transport creation returns None."""
        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.systems = [ActronAirSystemInfo(serial="abc123")]

        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.test",
            port=8883,
            protocol="ssl",
            user_id="u",
        )

        from actron_neo_api import actron as actron_module

        original_mqtt = actron_module.MQTTRTClient
        try:
            actron_module.MQTTRTClient = lambda *_args, **_kwargs: None  # type: ignore[assignment]
            started = await api.start_push(connection_details=details)
        finally:
            actron_module.MQTTRTClient = original_mqtt  # type: ignore[assignment]

        assert started is False
        assert api._rt_client is None

    @pytest.mark.asyncio
    async def test_start_push_raises_auth_error_and_survives_cleanup_error(self) -> None:
        """start_push should re-raise auth failures after tolerating cleanup errors."""

        class _OldClient:
            async def disconnect(self) -> None:
                raise RuntimeError("cleanup failed")

        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = None
        api.systems = [ActronAirSystemInfo(serial="abc123")]
        api._rt_client = _OldClient()  # type: ignore[assignment]

        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.test",
            port=8883,
            protocol="ssl",
            user_id="u",
        )
        with pytest.raises(ActronAirAuthError):
            await api.start_push(connection_details=details)

        assert api._rt_client is None
        assert api._push_running is False

    @pytest.mark.asyncio
    async def test_start_push_cleans_up_local_client_on_subscribe_failure(self) -> None:
        """start_push should disconnect newly-created client when subscribe fails."""

        class FakeMQTTClient:
            instances: list["FakeMQTTClient"] = []

            def __init__(
                self, details: RealtimeConnectionDetails, user_email: str, token: str
            ) -> None:
                self.disconnect = AsyncMock(return_value=None)
                FakeMQTTClient.instances.append(self)

            def register_callback(self, callback: Any) -> None:
                self.callback = callback

            async def connect(self) -> None:
                return None

            async def subscribe_system(self, serial: str) -> None:
                raise RuntimeError("subscribe failed")

            async def update_access_token(self, token: str) -> None:
                return None

        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.oauth2_auth.get_user_info = AsyncMock(
            return_value=ActronAirUserInfo(email="user@example.test")
        )
        api.systems = [ActronAirSystemInfo(serial="abc123")]

        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.test",
            port=8883,
            protocol="ssl",
            user_id="u",
        )

        from actron_neo_api import actron as actron_module

        original_mqtt = actron_module.MQTTRTClient
        try:
            actron_module.MQTTRTClient = FakeMQTTClient  # type: ignore[assignment]
            started = await api.start_push(connection_details=details)
        finally:
            actron_module.MQTTRTClient = original_mqtt  # type: ignore[assignment]

        assert started is False
        assert api._rt_client is None
        assert len(FakeMQTTClient.instances) == 1
        FakeMQTTClient.instances[0].disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_push_transport_failure_logs_debug_without_traceback(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A broker failure is an expected fallback: debug level, no traceback."""

        class FakeMQTTClient:
            def __init__(
                self, details: RealtimeConnectionDetails, user_email: str, token: str
            ) -> None:
                self.disconnect = AsyncMock(return_value=None)

            def register_callback(self, callback: Any) -> None:
                self.callback = callback

            async def connect(self) -> None:
                raise MqttError("broker unreachable")

            async def update_access_token(self, token: str) -> None:
                return None

        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.oauth2_auth.get_user_info = AsyncMock(
            return_value=ActronAirUserInfo(email="user@example.test")
        )
        api.systems = [ActronAirSystemInfo(serial="abc123")]

        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.test",
            port=8883,
            protocol="ssl",
            user_id="u",
        )

        from actron_neo_api import actron as actron_module

        original_mqtt = actron_module.MQTTRTClient
        try:
            actron_module.MQTTRTClient = FakeMQTTClient  # type: ignore[assignment]
            with caplog.at_level(logging.DEBUG, logger="actron_neo_api.actron"):
                started = await api.start_push(connection_details=details)
        finally:
            actron_module.MQTTRTClient = original_mqtt  # type: ignore[assignment]

        assert started is False
        assert api._rt_client is None
        assert api._push_running is False
        records = [record for record in caplog.records if record.name == "actron_neo_api.actron"]
        assert records
        assert all(record.levelno == logging.DEBUG for record in records)
        assert all(record.exc_info is None for record in records)
        assert "Realtime push unavailable (broker unreachable)" in caplog.text

    @pytest.mark.asyncio
    async def test_start_push_event_callback_creates_background_task(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Registered transport callback should schedule event handling task."""

        class FakeMQTTClient:
            def __init__(
                self, details: RealtimeConnectionDetails, user_email: str, token: str
            ) -> None:
                self.callback: Any = None

            def register_callback(self, callback: Any) -> None:
                self.callback = callback

            async def connect(self) -> None:
                status = ActronAirStatus.model_validate(sample_status_full)
                status.serial_number = "abc123"
                event = RealtimeMessage(
                    transport=RealtimeTransportType.MQTT,
                    kind=RealtimeEventKind.MESSAGE,
                    topic="actron-cloud/u/neo/abc123/mwc/full-status",
                    payload={},
                    domain_model=status,
                )
                if self.callback is not None:
                    self.callback(event)

            async def subscribe_system(self, serial: str) -> None:
                return None

            async def disconnect(self) -> None:
                return None

            async def update_access_token(self, token: str) -> None:
                return None

        api = ActronAirAPI(platform="neo")
        api.oauth2_auth.ensure_token_valid = AsyncMock(return_value=None)
        api.oauth2_auth.access_token = "token"
        api.oauth2_auth.get_user_info = AsyncMock(
            return_value=ActronAirUserInfo(email="user@example.test")
        )
        api.systems = [ActronAirSystemInfo(serial="abc123")]

        details = RealtimeConnectionDetails(
            endpoint="mqtt.example.test",
            port=8883,
            protocol="ssl",
            user_id="u",
        )

        from actron_neo_api import actron as actron_module

        original_mqtt = actron_module.MQTTRTClient
        try:
            actron_module.MQTTRTClient = FakeMQTTClient  # type: ignore[assignment]
            started = await api.start_push(connection_details=details)
            await asyncio.sleep(0)
        finally:
            actron_module.MQTTRTClient = original_mqtt  # type: ignore[assignment]

        assert started is True
        assert api.state_manager.get_status("abc123") is not None

    def test_subscribe_system_updates_empty_serial_raises(self) -> None:
        """subscribe_system_updates should validate serial."""
        api = ActronAirAPI()
        with pytest.raises(ValueError, match="serial_number cannot be empty"):
            api.subscribe_system_updates("", lambda _: None)

    @pytest.mark.asyncio
    async def test_subscribe_system_updates_unsubscribe_stops_callback(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """The returned callable should remove only its own registration."""
        api = ActronAirAPI()
        api._push_running = True
        first: list[str] = []
        second: list[str] = []

        unsubscribe = api.subscribe_system_updates("ABC123", lambda status: first.append("a"))
        api.subscribe_system_updates("ABC123", lambda status: second.append("b"))

        status = ActronAirStatus.model_validate(sample_status_full)
        status.serial_number = "abc123"
        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/full-status",
            payload={},
            domain_model=status,
        )

        await api._handle_realtime_event(event)
        unsubscribe()
        await api._handle_realtime_event(event)

        assert first == ["a"]
        assert second == ["b", "b"]

    def test_subscribe_system_updates_unsubscribe_is_idempotent(self) -> None:
        """Calling the remove-callback twice should not raise."""
        api = ActronAirAPI()

        def _cb(_status: ActronAirStatus) -> None:
            return None

        unsubscribe = api.subscribe_system_updates("ABC123", _cb)
        unsubscribe()
        unsubscribe()

        assert "abc123" not in api._push_callbacks

        # Repeat with a sibling subscription keeping the serial's list alive.
        other_unsubscribe = api.subscribe_system_updates("ABC123", _cb)
        unsubscribe = api.subscribe_system_updates("ABC123", lambda _status: None)
        unsubscribe()
        unsubscribe()

        assert len(api._push_callbacks["abc123"]) == 1
        other_unsubscribe()
        assert "abc123" not in api._push_callbacks

    @pytest.mark.asyncio
    async def test_subscribe_connection_state_receives_events(self) -> None:
        """Connection events should reach sync and async subscribers."""
        api = ActronAirAPI()
        sync_seen: list[RealtimeConnectionState] = []
        async_seen: list[RealtimeConnectionState] = []

        async def _async_cb(event: RealtimeConnectionEvent) -> None:
            async_seen.append(event.state)

        api.subscribe_connection_state(lambda event: sync_seen.append(event.state))
        api.subscribe_connection_state(_async_cb)

        event = RealtimeConnectionEvent(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.CONNECTION,
            state=RealtimeConnectionState.CONNECTED,
            previous_state=RealtimeConnectionState.CONNECTING,
        )
        await api._handle_realtime_event(event)

        assert sync_seen == [RealtimeConnectionState.CONNECTED]
        assert async_seen == [RealtimeConnectionState.CONNECTED]

    @pytest.mark.asyncio
    async def test_subscribe_connection_state_unsubscribe_and_error_handling(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A failing callback should be logged, and unsubscribe should detach it."""
        api = ActronAirAPI()

        def _boom(_event: RealtimeConnectionEvent) -> None:
            raise RuntimeError("callback exploded")

        unsubscribe = api.subscribe_connection_state(_boom)

        event = RealtimeConnectionEvent(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.CONNECTION,
            state=RealtimeConnectionState.ERROR,
            reason="broker gone",
        )

        with caplog.at_level(logging.WARNING, logger="actron_neo_api.actron"):
            await api._handle_realtime_event(event)

        assert "Realtime connection callback failed for error" in caplog.text

        caplog.clear()
        unsubscribe()
        unsubscribe()
        with caplog.at_level(logging.WARNING, logger="actron_neo_api.actron"):
            await api._handle_realtime_event(event)

        assert caplog.text == ""
        assert api._push_connection_callbacks == []

    @pytest.mark.asyncio
    async def test_stream_system_updates_skips_non_matching_serial(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """stream_system_updates should filter by serial when requested."""
        api = ActronAirAPI()
        api._push_running = True
        status1 = ActronAirStatus.model_validate(sample_status_full)
        status1.serial_number = "abc123"
        status2 = ActronAirStatus.model_validate(sample_status_full)
        status2.serial_number = "xyz789"

        async def _collect() -> list[ActronAirStatus]:
            return [item async for item in api.stream_system_updates("abc123")]

        collector = asyncio.create_task(_collect())
        await asyncio.sleep(0)

        await api._handle_realtime_event(
            RealtimeMessage(
                transport=RealtimeTransportType.MQTT,
                kind=RealtimeEventKind.MESSAGE,
                topic="actron-cloud/u/neo/xyz789/mwc/full-status",
                payload={},
                domain_model=status2,
            )
        )
        await api._handle_realtime_event(
            RealtimeMessage(
                transport=RealtimeTransportType.MQTT,
                kind=RealtimeEventKind.MESSAGE,
                topic="actron-cloud/u/neo/abc123/mwc/full-status",
                payload={},
                domain_model=status1,
            )
        )

        await api.stop_push()
        streamed = await collector

        assert len(streamed) == 1
        assert streamed[0].serial_number == "abc123"

    @pytest.mark.asyncio
    async def test_stream_system_updates_unblocks_on_stop_push(self) -> None:
        """stream_system_updates should exit when stop_push is called while waiting."""
        api = ActronAirAPI()

        async def _collect() -> list[ActronAirStatus]:
            return [item async for item in api.stream_system_updates("abc123")]

        collector = asyncio.create_task(_collect())
        await asyncio.sleep(0)
        await api.stop_push()
        streamed = await collector

        assert streamed == []

    @pytest.mark.asyncio
    async def test_discover_realtime_details_success_and_fallback(self) -> None:
        """Discovery should parse link payloads and Que fallback endpoint."""
        api = ActronAirAPI(platform="neo")

        def _link(_: str, rel: str) -> str | None:
            return "api/v0/rtc" if rel == "rtc" else None

        async def _req(_: str, endpoint: str) -> dict[str, Any]:
            assert endpoint == "api/v0/rtc"
            return {
                "RTCDetails": {
                    "endPoint": "broker.test",
                    "port": 8883,
                    "protocol": "ssl",
                    "userId": "u",
                }
            }

        api._get_system_link = _link  # type: ignore[method-assign]
        api._make_request = _req  # type: ignore[method-assign]

        details = await api._discover_realtime_connection_details("abc123")
        assert details is not None
        assert details.endpoint == "broker.test"

        api_q = ActronAirAPI(platform="que")
        api_q._get_system_link = lambda *_: None  # type: ignore[method-assign]
        fallback = await api_q._discover_realtime_connection_details("xyz789")
        assert fallback is not None
        assert fallback.endpoint.endswith("/api/v0/messaging/app")

    @pytest.mark.asyncio
    async def test_discover_realtime_details_handles_lookup_exceptions(self) -> None:
        """Discovery should continue when a link request fails."""
        api = ActronAirAPI(platform="que")
        api._get_system_link = lambda *_: "api/v0/rtc"  # type: ignore[method-assign]

        async def _boom(_: str, __: str) -> dict[str, Any]:
            raise RuntimeError("boom")

        api._make_request = _boom  # type: ignore[method-assign]

        details = await api._discover_realtime_connection_details("xyz789")
        assert details is not None

    def test_parse_realtime_details_payload_variants(self) -> None:
        """Realtime details payload parsing should support multiple key variants."""
        api = ActronAirAPI()

        parsed = api._parse_realtime_details_payload(
            {
                "rtcDetails": {
                    "endpoint": "broker.test",
                    "port": "1883",
                    "scheme": "tcp",
                    "username": "u",
                }
            }
        )
        assert parsed is not None
        assert parsed.port == 1883
        assert parsed.protocol == "tcp"
        assert parsed.user_id == "u"

        parsed_upper = api._parse_realtime_details_payload(
            {
                "Endpoint": "broker.upper.test",
                "Port": 8883,
                "Protocol": "ssl",
                "UserId": "upper-user",
            }
        )
        assert parsed_upper is not None
        assert parsed_upper.endpoint == "broker.upper.test"
        assert parsed_upper.port == 8883
        assert parsed_upper.protocol == "ssl"
        assert parsed_upper.user_id == "upper-user"

        parsed_port_fallback = api._parse_realtime_details_payload(
            {
                "endpoint": "broker.fallback.test",
                "port": None,
                "Port": 1883,
                "protocol": "tcp",
                "userId": "fallback-user",
            }
        )
        assert parsed_port_fallback is not None
        assert parsed_port_fallback.port == 1883

        assert api._parse_realtime_details_payload({"RTCDetails": {"port": "bad"}}) is None
        assert api._pick_str({"a": "", "b": " value "}, "a", "b") == "value"
        assert api._pick_str({"a": ""}, "a") is None

    @pytest.mark.asyncio
    async def test_discover_realtime_details_uses_direct_endpoint_for_neo(self) -> None:
        """Neo discovery should use the canonical API-v0 details endpoint."""
        api = ActronAirAPI(platform="neo")
        api._get_system_link = lambda *_: None  # type: ignore[method-assign]
        seen_endpoints: list[str] = []

        async def _req(method: str, endpoint: str) -> dict[str, Any]:
            assert method == "get"
            seen_endpoints.append(endpoint)
            assert endpoint == "api/v0/messaging/connection/details"
            return {
                "Endpoint": "broker.direct.test",
                "Port": 8883,
                "Protocol": "ssl",
                "UserId": "u-direct",
            }

        api._make_request = _req  # type: ignore[method-assign]

        details = await api._discover_realtime_connection_details("abc123")

        assert details is not None
        assert details.endpoint == "broker.direct.test"
        assert details.user_id == "u-direct"
        assert seen_endpoints == ["api/v0/messaging/connection/details"]

    @pytest.mark.asyncio
    async def test_discover_realtime_details_returns_none_for_neo_without_links(self) -> None:
        """Neo discovery should return None if links and direct endpoint are unavailable."""
        api = ActronAirAPI(platform="neo")
        api._get_system_link = lambda *_: None  # type: ignore[method-assign]
        seen_endpoints: list[str] = []

        async def _req(_: str, endpoint: str) -> dict[str, Any]:
            seen_endpoints.append(endpoint)
            raise RuntimeError("boom")

        api._make_request = _req  # type: ignore[method-assign]

        details = await api._discover_realtime_connection_details("abc123")

        assert details is None
        assert seen_endpoints == ["api/v0/messaging/connection/details"]

    @pytest.mark.asyncio
    async def test_handle_realtime_event_branch_coverage(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Handle event should ignore unsupported shapes and await async callbacks."""
        api = ActronAirAPI()

        await api._handle_realtime_event(
            RealtimeEvent(transport=RealtimeTransportType.MQTT, kind=RealtimeEventKind.CONNECTION)
        )

        msg_no_status = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="x",
            payload={},
            domain_model={"not": "status"},
        )
        await api._handle_realtime_event(msg_no_status)

        status = ActronAirStatus.model_validate(sample_status_full)
        status.serial_number = None
        msg_no_serial = RealtimeMessage(
            transport=RealtimeTransportType.SIGNALR,
            kind=RealtimeEventKind.MESSAGE,
            topic="signalr",
            payload={},
            domain_model=status,
        )
        await api._handle_realtime_event(msg_no_serial)

        seen: list[str] = []

        async def _cb(s: ActronAirStatus) -> None:
            if s.serial_number:
                seen.append(s.serial_number)

        def _bad_cb(_: ActronAirStatus) -> None:
            raise RuntimeError("callback boom")

        api.subscribe_system_updates("abc123", _bad_cb)
        api.subscribe_system_updates("abc123", _cb)
        status_ok = ActronAirStatus.model_validate(sample_status_full)
        event_ok = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/full-status",
            payload={"serial": "abc123"},
            domain_model=status_ok,
        )
        await api._handle_realtime_event(event_ok)

        assert seen == ["abc123"]

    def test_extract_realtime_serial_from_topic_branch(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Serial extraction should parse MQTT topic structure when status has no serial."""
        status = ActronAirStatus.model_validate(sample_status_full)
        status.serial_number = None
        msg = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/full-status",
            payload={},
            domain_model=status,
        )

        assert ActronAirAPI._extract_realtime_serial(msg, status) == "abc123"

    @pytest.mark.asyncio
    async def test_log_background_task_error_branches(self) -> None:
        """Background task logger should handle both cancelled and failed tasks."""
        cancelled = asyncio.create_task(asyncio.sleep(0.1))
        cancelled.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled
        ActronAirAPI._log_background_task_error(cancelled)

        async def _boom() -> None:
            raise RuntimeError("boom")

        failed = asyncio.create_task(_boom())
        with pytest.raises(RuntimeError, match="boom"):
            await failed
        ActronAirAPI._log_background_task_error(failed)

    @pytest.mark.asyncio
    async def test_sync_realtime_access_token_branches(self) -> None:
        """Token sync should handle no-token and transport update failures."""

        class _Client:
            async def update_access_token(self, _: str) -> None:
                raise RuntimeError("boom")

        api = ActronAirAPI()
        await api._sync_realtime_access_token()  # no client branch

        api._rt_client = _Client()  # type: ignore[assignment]
        api.oauth2_auth.access_token = None
        await api._sync_realtime_access_token()  # no token branch

        api.oauth2_auth.access_token = "token"
        await api._sync_realtime_access_token()  # exception branch

    def test_extract_realtime_serial_from_payload_and_none(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Serial extraction should support payload keys and missing values."""
        status = ActronAirStatus.model_validate(sample_status_full)
        status.serial_number = None

        msg_payload = RealtimeMessage(
            transport=RealtimeTransportType.SIGNALR,
            kind=RealtimeEventKind.MESSAGE,
            topic="signalr",
            payload={"serialNumber": "ABC123"},
            domain_model=status,
        )
        assert ActronAirAPI._extract_realtime_serial(msg_payload, status) == "abc123"

        msg_none = RealtimeMessage(
            transport=RealtimeTransportType.SIGNALR,
            kind=RealtimeEventKind.MESSAGE,
            topic="signalr",
            payload={},
            domain_model=status,
        )
        assert ActronAirAPI._extract_realtime_serial(msg_none, status) is None


class TestNeoBroadcastPayloads:
    """Test Neo status-change-broadcast and full-status-broadcast handling."""

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("UserAirconSettings.EnabledZones[6]", ["UserAirconSettings", "EnabledZones", 6]),
            ("RemoteZoneInfo[1].ZonePosition", ["RemoteZoneInfo", 1, "ZonePosition"]),
            ("MasterInfo.LiveTemp_oC", ["MasterInfo", "LiveTemp_oC"]),
            ("isOn", ["isOn"]),
            # Peripheral identifiers carry dots that belong to the identifier.
            ("<28.8f.4d.a4.e2.6a>", ["<28.8f.4d.a4.e2.6a>"]),
            ("", []),
        ],
    )
    def test_parse_flat_key_path(self, key: str, expected: list[str | int]) -> None:
        """Flat broadcast keys should parse into dict keys and list indices."""
        assert ActronAirAPI._parse_flat_key_path(key) == expected

    @pytest.mark.parametrize(
        ("state", "key", "value", "applied", "expected"),
        [
            pytest.param(
                {"UserAirconSettings": {"EnabledZones": [False, False]}},
                "UserAirconSettings.EnabledZones[1]",
                True,
                True,
                {"UserAirconSettings": {"EnabledZones": [False, True]}},
                id="zone_toggle",
            ),
            pytest.param(
                {},
                "RemoteZoneInfo[1].ZonePosition",
                42,
                True,
                {"RemoteZoneInfo": [None, {"ZonePosition": 42}]},
                id="creates_missing_containers",
            ),
            pytest.param(
                {"RemoteZoneInfo": {}},
                "RemoteZoneInfo[0].ZonePosition",
                5,
                True,
                {"RemoteZoneInfo": [{"ZonePosition": 5}]},
                id="empty_container_is_coerced",
            ),
            pytest.param(
                {"RemoteZoneInfo": [{"ZonePosition": 1}]},
                "RemoteZoneInfo.Bogus",
                9,
                False,
                {"RemoteZoneInfo": [{"ZonePosition": 1}]},
                id="populated_list_is_never_discarded",
            ),
            pytest.param(
                {"UserAirconSettings": {"Mode": "COOL"}},
                "UserAirconSettings[0]",
                9,
                False,
                {"UserAirconSettings": {"Mode": "COOL"}},
                id="populated_dict_is_never_discarded",
            ),
            pytest.param(
                {"MasterInfo": {"LiveTemp_oC": 1.0}},
                "MasterInfo.LiveTemp_oC",
                23.5,
                True,
                {"MasterInfo": {"LiveTemp_oC": 23.5}},
                id="scalar_leaf",
            ),
            pytest.param(
                {"MasterInfo": 5},
                "MasterInfo.LiveTemp_oC",
                23.5,
                True,
                {"MasterInfo": {"LiveTemp_oC": 23.5}},
                id="scalar_container_is_replaced",
            ),
            pytest.param(
                {"UserAirconSettings": {"EnabledZones": [False, False]}},
                "UserAirconSettings.EnabledZones[3]",
                True,
                True,
                {"UserAirconSettings": {"EnabledZones": [False, False, None, True]}},
                id="leaf_index_past_end_is_padded",
            ),
            pytest.param({}, "", 1, False, {}, id="empty_path"),
        ],
    )
    def test_apply_flat_path_to_dict(
        self,
        state: dict[str, Any],
        key: str,
        value: Any,
        applied: bool,
        expected: dict[str, Any],
    ) -> None:
        """Broadcast deltas should write into state without discarding it."""
        path = ActronAirAPI._parse_flat_key_path(key)

        assert ActronAirAPI._apply_flat_path_to_dict(state, path, value) is applied
        assert state == expected

    def test_apply_flat_path_rejects_index_into_dict_root(self) -> None:
        """An indexed first segment cannot address the lastKnownState dict."""
        state: dict[str, Any] = {}

        assert ActronAirAPI._apply_flat_path_to_dict(state, [0, "Nested"], 1) is False
        assert ActronAirAPI._apply_flat_path_to_dict(state, [0], 1) is False
        assert state == {}

    @pytest.mark.parametrize(
        ("payload", "expected"),
        [
            pytest.param({}, None, id="no_event"),
            pytest.param({"event": "text"}, None, id="event_not_a_dict"),
            pytest.param(
                {"event": {"type": "full-status-broadcast"}}, None, id="wrong_broadcast_type"
            ),
            pytest.param({"event": {"type": "status-change-broadcast"}}, None, id="type_only_body"),
            pytest.param(
                {"event": {"type": "status-change-broadcast", "isOn": True}},
                {"isOn": True},
                id="state_bearing",
            ),
        ],
    )
    def test_status_change_broadcast_detection(
        self, payload: dict[str, Any], expected: dict[str, Any] | None
    ) -> None:
        """Only state-bearing status-change broadcasts should be recognised."""
        assert ActronAirAPI._status_change_broadcast(payload) == expected

    def test_broadcast_payload_counts_as_state(self) -> None:
        """A broadcast must not be treated as metadata-only.

        "event" is a metadata key, so without this the whole delta falls
        through to an HTTP refresh of the stale cloud snapshot.
        """
        payload = {
            "event": {
                "type": "status-change-broadcast",
                "UserAirconSettings.EnabledZones[6]": True,
            },
            "serial": "abc123",
            "isOnline": True,
        }

        assert ActronAirAPI._mqtt_status_change_contains_state(payload) is True

    @pytest.mark.asyncio
    async def test_status_change_broadcast_merges_without_http_refresh(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Zone deltas from the device should be applied to the cached state."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.state_manager.process_status_update("abc123", sample_status_full)
        api.update_status = AsyncMock(side_effect=AssertionError("must not refresh over HTTP"))

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={
                "event": {
                    "type": "status-change-broadcast",
                    "UserAirconSettings.EnabledZones[1]": True,
                    "RemoteZoneInfo[0].ZonePosition": 50.0,
                    "MasterInfo.LiveTemp_oC": 26.5,
                },
                "serial": "abc123",
            },
            domain_model=None,
        )

        await api._handle_realtime_event(event)

        status = api.state_manager.get_status("abc123")
        assert status is not None
        assert status.user_aircon_settings.enabled_zones[1] is True
        assert status.remote_zone_info[0].zone_position == 50.0
        assert status.master_info.live_temp_c == 26.5
        # Untouched fields must survive the delta.
        assert status.user_aircon_settings.mode == "COOL"

    @pytest.mark.asyncio
    async def test_status_change_broadcast_logs_unmappable_keys(
        self,
        sample_status_full: dict[str, Any],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A key that cannot be mapped is skipped rather than corrupting state."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        api.state_manager.process_status_update("abc123", sample_status_full)

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/status-change",
            payload={
                "event": {
                    "type": "status-change-broadcast",
                    "RemoteZoneInfo.Bogus": 1,
                }
            },
            domain_model=None,
        )

        with caplog.at_level(logging.DEBUG, logger="actron_neo_api.actron"):
            await api._handle_realtime_event(event)

        assert "Skipped unmappable status-change key" in caplog.text
        status = api.state_manager.get_status("abc123")
        assert status is not None
        assert status.remote_zone_info[0].zone_position == 100.0

    @pytest.mark.asyncio
    async def test_full_status_broadcast_replaces_zeroed_domain_model(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """A broadcast wrapper must win over the transport's all-defaults model.

        ActronAirStatus validates the wrapper successfully but with every field
        defaulted, so without this the push would overwrite good state with
        zeroes.
        """
        api = ActronAirAPI(platform="neo")
        api._push_running = True

        zeroed = ActronAirStatus.model_validate(
            {"event": {"type": "full-status-broadcast", **sample_status_full["lastKnownState"]}}
        )
        assert zeroed.user_aircon_settings.mode == ""

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/full-status",
            payload={
                "event": {
                    "type": "full-status-broadcast",
                    **sample_status_full["lastKnownState"],
                }
            },
            domain_model=zeroed,
        )

        await api._handle_realtime_event(event)

        status = api.state_manager.get_status("abc123")
        assert status is not None
        assert status.user_aircon_settings.mode == "COOL"
        assert status.master_info.live_temp_c == 22.5
        assert status.is_online is True

    @pytest.mark.parametrize(
        "payload",
        [
            pytest.param({}, id="no_event"),
            pytest.param({"event": ["not", "a", "dict"]}, id="event_not_a_dict"),
            pytest.param({"event": {"type": "status-change-broadcast"}}, id="wrong_type"),
            pytest.param({"event": {"type": "full-status-broadcast"}}, id="empty_body"),
        ],
    )
    def test_parse_full_status_broadcast_rejects(self, payload: dict[str, Any]) -> None:
        """Payloads that are not full-status broadcasts should not be parsed."""
        assert ActronAirAPI._parse_full_status_broadcast("abc123", payload) is None

    def test_parse_full_status_broadcast_handles_invalid_state(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A body that cannot be validated should warn instead of raising."""

        def _raise_validate(_: Any) -> ActronAirStatus:
            raise ValueError("broadcast boom")

        monkeypatch.setattr(
            ActronAirStatus,
            "model_validate",
            classmethod(lambda cls, payload: _raise_validate(payload)),
        )

        payload = {"event": {"type": "full-status-broadcast", "UserAirconSettings": {}}}

        with caplog.at_level(logging.WARNING, logger="actron_neo_api.actron"):
            result = ActronAirAPI._parse_full_status_broadcast("abc123", payload)

        assert result is None
        assert "Failed to parse full-status broadcast for abc123" in caplog.text

    @pytest.mark.asyncio
    async def test_non_broadcast_full_status_still_uses_domain_model(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """The original full-status shape must keep working."""
        api = ActronAirAPI(platform="neo")
        api._push_running = True
        status = ActronAirStatus.model_validate(sample_status_full)

        event = RealtimeMessage(
            transport=RealtimeTransportType.MQTT,
            kind=RealtimeEventKind.MESSAGE,
            topic="actron-cloud/u/neo/abc123/mwc/full-status",
            payload=sample_status_full,
            domain_model=status,
        )

        assert await api._coerce_realtime_status(event) is status

    def test_is_mqtt_full_status_topic(self) -> None:
        """Only the full-status channel should match."""
        assert ActronAirAPI._is_mqtt_full_status_topic("a/b/mwc/full-status") is True
        assert ActronAirAPI._is_mqtt_full_status_topic("a/b/mwc/status-change") is False
