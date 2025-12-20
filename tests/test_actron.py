"""Tests for ActronAirAPI core client functionality."""

from typing import Any
from unittest.mock import AsyncMock

import pytest

from actron_neo_api import ActronAirAPI
from actron_neo_api.exceptions import ActronAirAPIError, ActronAirAuthError
from actron_neo_api.models import ActronAirDeviceCode, ActronAirToken, ActronAirUserInfo
from actron_neo_api.models.system import ActronAirSystemInfo


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
        """Test latest_event_id property."""
        api = ActronAirAPI()
        api.state_manager.latest_event_id = {"abc123": "event_1"}
        assert api.latest_event_id == {"abc123": "event_1"}


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
