"""Tests for ActronAirAPI core client functionality."""

import asyncio
import logging
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    async def test_start_push_selects_mqtt_for_neo(self) -> None:
        """Neo platform should use the MQTT transport."""

        class FakeMQTTClient:
            def __init__(self, details: RealtimeConnectionDetails, token: str) -> None:
                self.details = details
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

        with caplog.at_level(logging.INFO, logger="actron_neo_api.actron"):
            started = await api.start_push()

        assert started is False
        assert "Realtime connection details unavailable; push not started" in caplog.text
        assert not any(
            record.name == "actron_neo_api.actron" and record.levelno >= logging.WARNING
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_start_push_uses_explicit_serial_numbers(self) -> None:
        """start_push should honor provided serial_numbers and ignore blanks."""

        class FakeMQTTClient:
            def __init__(self, details: RealtimeConnectionDetails, token: str) -> None:
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
    async def test_start_push_handles_missing_token_and_cleanup_error(self) -> None:
        """start_push should handle auth failure and cleanup failures gracefully."""

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
        started = await api.start_push(connection_details=details)

        assert started is False
        assert api._rt_client is None

    @pytest.mark.asyncio
    async def test_start_push_cleans_up_local_client_on_subscribe_failure(self) -> None:
        """start_push should disconnect newly-created client when subscribe fails."""

        class FakeMQTTClient:
            instances: list["FakeMQTTClient"] = []

            def __init__(self, details: RealtimeConnectionDetails, token: str) -> None:
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
    async def test_start_push_event_callback_creates_background_task(
        self, sample_status_full: dict[str, Any]
    ) -> None:
        """Registered transport callback should schedule event handling task."""

        class FakeMQTTClient:
            def __init__(self, details: RealtimeConnectionDetails, token: str) -> None:
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
        """Neo discovery should try endpoint variants when links are absent."""
        api = ActronAirAPI(platform="neo")
        api._get_system_link = lambda *_: None  # type: ignore[method-assign]
        seen_endpoints: list[str] = []

        async def _req(method: str, endpoint: str) -> dict[str, Any]:
            assert method == "get"
            seen_endpoints.append(endpoint)
            if endpoint == "api/v0/messaging/connection/details":
                raise RuntimeError("404")
            assert endpoint == "messaging/connection/details"
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
        assert seen_endpoints == [
            "api/v0/messaging/connection/details",
            "messaging/connection/details",
        ]

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
        assert seen_endpoints == [
            "api/v0/messaging/connection/details",
            "messaging/connection/details",
        ]

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
