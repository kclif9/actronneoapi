"""Actron Air API client module."""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import aiohttp

from .const import (
    BASE_URL_ACONNECT,
    BASE_URL_DEFAULT,
    BASE_URL_NIMBUS,
    BASE_URL_QUE,
    PLATFORM_ACONNECT,
    PLATFORM_NEO,
    PLATFORM_QUE,
)
from .exceptions import ActronAirAPIError, ActronAirAuthError
from .models import (
    ActronAirDeviceCode,
    ActronAirStatus,
    ActronAirSystemInfo,
    ActronAirToken,
    ActronAirUserInfo,
)
from .oauth import ActronAirOAuth2DeviceCodeAuth
from .state import StateManager


class ActronAirAPI:
    """Client for the Actron Air API with improved architecture.

    This client provides a modern, structured approach to interacting with
    the Actron Air API while maintaining compatibility with the previous interface.
    """

    def __init__(
        self,
        oauth2_client_id: str = "home_assistant",
        refresh_token: str | None = None,
        platform: Literal["neo", "que", "aconnect"] | None = None,
    ):
        """Initialize the ActronAirAPI client with OAuth2 authentication.

        Args:
            oauth2_client_id: OAuth2 client ID for device code flow
            refresh_token: Optional refresh token for authentication
            platform: Platform to use ('neo', 'que', 'aconnect', or None for auto-detect).
            If None, enables auto-detection with Neo as the initial platform.

        """
        # Determine base URL from platform parameter
        if platform == PLATFORM_QUE:
            resolved_base_url = BASE_URL_QUE
            self._platform = PLATFORM_QUE
            self._auto_manage_base_url = False
        elif platform == PLATFORM_NEO:
            resolved_base_url = BASE_URL_NIMBUS
            self._platform = PLATFORM_NEO
            self._auto_manage_base_url = False
        elif platform == PLATFORM_ACONNECT:
            resolved_base_url = BASE_URL_ACONNECT
            self._platform = PLATFORM_ACONNECT
            self._auto_manage_base_url = False
        else:
            # Auto-detect with Neo as fallback (platform is None)
            resolved_base_url = BASE_URL_DEFAULT
            self._platform = PLATFORM_NEO
            self._auto_manage_base_url = True

        self.base_url = resolved_base_url
        self._oauth2_client_id = oauth2_client_id

        # Initialize OAuth2 authentication
        self.oauth2_auth = ActronAirOAuth2DeviceCodeAuth(resolved_base_url, oauth2_client_id)

        # Set refresh token if provided
        if refresh_token:
            self.oauth2_auth.refresh_token = refresh_token

        self.state_manager = StateManager()
        # Set the API reference in the state manager for command execution
        self.state_manager.set_api(self)

        # Internal cache of system info models for link resolution
        self.systems: list[ActronAirSystemInfo] = []
        self._initialized = False

        # Session management
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    @property
    def platform(self) -> str:
        """Get the current platform being used.

        Returns:
            'neo' if using Nimbus platform, 'que' if using Que platform,
            'aconnect' if using Actron Connect platform

        """
        return self._platform

    @property
    def authenticated_platform(self) -> str | None:
        """Get the platform where tokens were originally obtained.

        Returns:
            Platform URL where tokens were authenticated, or None if not authenticated

        """
        return self.oauth2_auth.authenticated_platform

    def _get_system_link(self, serial_number: str, rel: str) -> str | None:
        """Return a HAL link for a cached system if available.

        Args:
            serial_number: Serial number of the AC system
            rel: The relationship name of the link to retrieve

        Returns:
            The href URL string with leading slash removed, or None if not found

        """
        # Normalize serial number comparison (case-insensitive)
        serial_lower = serial_number.lower()

        for system in self.systems:
            if system.serial.lower() != serial_lower:
                continue

            links = system.links
            if not links:
                continue

            link_info = links.get(rel)
            href: str | None = None

            if isinstance(link_info, dict):
                href_value = link_info.get("href")
                href = href_value if isinstance(href_value, str) else None
            elif isinstance(link_info, list) and link_info:
                first_item = link_info[0]
                if isinstance(first_item, dict):
                    href_value = first_item.get("href")
                    href = href_value if isinstance(href_value, str) else None

            if href:
                return href.lstrip("/")

        return None

    @staticmethod
    def _is_nx_gen_system(system: ActronAirSystemInfo) -> bool:
        """Check if a system is an NX Gen type.

        Args:
            system: System info model

        Returns:
            True if the system is NX Gen type, False otherwise

        """
        if not system.type:
            return False
        system_type = str(system.type).replace("-", "").lower()
        return system_type == "nxgen"

    @staticmethod
    def _is_aconnect_system(system: ActronAirSystemInfo) -> bool:
        """Check if a system is an Actron Connect (ACM-2) type.

        Args:
            system: System info model

        Returns:
            True if the system is Actron Connect type, False otherwise

        """
        if not system.type:
            return False
        system_type = str(system.type).replace("-", "").lower()
        return system_type == "aconnect"

    def _set_base_url(self, base_url: str, platform: str) -> None:
        """Update the base URL and platform, preserving existing authentication tokens.

        Args:
            base_url: New base URL to switch to
            platform: Platform identifier ('neo', 'que', 'aconnect')

        Note:
            This preserves tokens but they may not work if switching between
            incompatible platforms (Neo vs Que).

        """
        if self.base_url == base_url and self._platform == platform:
            return

        # Preserve existing tokens
        old_access_token = self.oauth2_auth.access_token
        old_refresh_token = self.oauth2_auth.refresh_token
        old_token_expiry = self.oauth2_auth.token_expiry
        old_authenticated_platform = self.oauth2_auth.authenticated_platform

        # Update base URL and platform, recreate OAuth2 handler to match new platform
        self.base_url = base_url
        self._platform = platform
        self.oauth2_auth = ActronAirOAuth2DeviceCodeAuth(base_url, self._oauth2_client_id)

        # Restore tokens
        self.oauth2_auth.access_token = old_access_token
        self.oauth2_auth.refresh_token = old_refresh_token
        self.oauth2_auth.token_expiry = old_token_expiry
        self.oauth2_auth.authenticated_platform = old_authenticated_platform

    def _maybe_update_base_url_from_systems(self, systems: list[ActronAirSystemInfo]) -> None:
        """Automatically update base URL based on system types if auto-management is enabled.

        Args:
            systems: List of AC systems to analyze

        Note:
            Platform priority: Actron Connect > QUE (NX Gen) > NIMBUS (Neo).
            Switches to the highest priority platform found in the systems list.

        """
        if not self._auto_manage_base_url or not systems:
            return

        has_aconnect = any(self._is_aconnect_system(system) for system in systems)
        has_nx_gen = any(self._is_nx_gen_system(system) for system in systems)

        if has_aconnect:
            target_base = BASE_URL_ACONNECT
            target_platform = PLATFORM_ACONNECT
        elif has_nx_gen:
            target_base = BASE_URL_QUE
            target_platform = PLATFORM_QUE
        else:
            target_base = BASE_URL_NIMBUS
            target_platform = PLATFORM_NEO

        self._set_base_url(target_base, target_platform)

    async def _ensure_initialized(self) -> None:
        """Ensure the API is initialized with valid tokens."""
        if self._initialized:
            return

        if self.oauth2_auth.refresh_token and not self.oauth2_auth.access_token:
            try:
                await self.oauth2_auth.refresh_access_token()
            except (ActronAirAuthError, aiohttp.ClientError) as e:
                raise ActronAirAuthError(f"Failed to initialize API: {e}") from e

        self._initialized = True

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession."""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
                return self._session
            return self._session

    async def close(self) -> None:
        """Close the API client and release resources."""
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

    async def __aenter__(self) -> "ActronAirAPI":
        """Support for async context manager."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Support for async context manager."""
        await self.close()

    # OAuth2 Device Code Flow methods - simple proxies
    async def request_device_code(self) -> ActronAirDeviceCode:
        """Request a device code for OAuth2 device code flow."""
        return await self.oauth2_auth.request_device_code()

    async def poll_for_token(
        self, device_code: str, interval: int = 5, timeout: int = 600
    ) -> ActronAirToken | None:
        """Poll for access token using device code with automatic polling loop.

        Args:
            device_code: The device code received from request_device_code
            interval: Polling interval in seconds (default: 5)
            timeout: Maximum time to wait in seconds (default: 600 = 10 minutes)

        Returns:
            Token model if successful, None if timeout occurs

        """
        return await self.oauth2_auth.poll_for_token(device_code, interval, timeout)

    async def get_user_info(self) -> ActronAirUserInfo:
        """Get user information using the access token."""
        return await self.oauth2_auth.get_user_info()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        _retry: bool = True,
    ) -> dict[str, Any]:
        """Make an API request with proper error handling.

        Args:
            method: HTTP method ("get", "post", etc.)
            endpoint: API endpoint (without base URL)
            params: URL parameters
            json_data: JSON body data
            data: Form data
            headers: HTTP headers
            _retry: Internal flag to prevent infinite retry loops

        Returns:
            API response as JSON

        Raises:
            ActronAirAuthError: For authentication errors
            ActronAirAPIError: For API errors

        """
        # Ensure API is initialized with valid tokens
        await self._ensure_initialized()

        # Ensure we have a valid token
        await self.oauth2_auth.ensure_token_valid()

        auth_header = self.oauth2_auth.authorization_header

        # Prepare the request
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_headers = headers or {}
        request_headers.update(auth_header)

        # Get a session
        session = await self._get_session()

        # Make the request
        try:
            async with session.request(
                method, url, params=params, json=json_data, data=data, headers=request_headers
            ) as response:
                if response.status == 401:
                    response_text = await response.text()

                    # If we have a refresh token and haven't retried yet, attempt refresh
                    if _retry and self.oauth2_auth.refresh_token:
                        try:
                            await self.oauth2_auth.refresh_access_token()
                            return await self._make_request(
                                method, endpoint, params, json_data, data, headers, _retry=False
                            )
                        except ActronAirAuthError:
                            raise
                        except (
                            aiohttp.ClientError,
                            ValueError,
                            TypeError,
                            KeyError,
                        ) as refresh_error:
                            raise ActronAirAuthError(
                                f"Authentication failed and token refresh failed: {response_text}"
                            ) from refresh_error

                    raise ActronAirAuthError(f"Authentication failed: {response_text}")

                if response.status != 200:
                    response_text = await response.text()
                    raise ActronAirAPIError(
                        f"API request failed. Status: {response.status}, Response: {response_text}"
                    )

                return await response.json()
        except aiohttp.ClientError as e:
            raise ActronAirAPIError(f"Request failed: {str(e)}") from e

    # API Methods

    async def get_ac_systems(self) -> list[ActronAirSystemInfo]:
        """Retrieve all AC systems in the customer account.

        Returns:
            List of AC system information models

        Raises:
            ActronAirAPIError: If response is missing required data

        """
        response = await self._make_request(
            "get", "api/v0/client/ac-systems", params={"includeNeo": "true"}
        )

        # Validate response structure
        if "_embedded" not in response:
            raise ActronAirAPIError("Invalid response: missing '_embedded' key")

        embedded = response["_embedded"]
        if not isinstance(embedded, dict) or "ac-system" not in embedded:
            raise ActronAirAPIError("Invalid response: missing 'ac-system' in '_embedded'")

        systems_data = embedded["ac-system"]
        if not isinstance(systems_data, list):
            raise ActronAirAPIError("Invalid response: 'ac-system' is not a list")

        # Convert to Pydantic models
        systems = [ActronAirSystemInfo(**system_data) for system_data in systems_data]

        # Store system info models for link resolution
        self.systems = systems
        self._maybe_update_base_url_from_systems(systems)

        return systems

    async def get_ac_status(self, serial_number: str) -> ActronAirStatus:
        """Retrieve the current status for a specific AC system.

        This replaces the events API which was disabled by Actron in July 2025.

        Args:
            serial_number: Serial number of the AC system

        Returns:
            Typed status model for the AC system

        Raises:
            ActronAirAPIError: If system not found or request fails

        """
        # Normalize serial number to lowercase for consistent lookup
        serial_number = serial_number.lower()

        endpoint = self._get_system_link(serial_number, "ac-status")
        if not endpoint:
            raise ActronAirAPIError(f"No ac-status link found for system {serial_number}")

        status_data = await self._make_request("get", endpoint)
        status = ActronAirStatus(serial_number=serial_number, **status_data)
        status._api = self  # Set API reference for command execution
        return status

    async def send_command(self, serial_number: str, command: dict[str, Any]) -> None:
        """Send a command to the specified AC system.

        Args:
            serial_number: Serial number of the AC system
            command: Dictionary containing the command details

        Raises:
            ActronAirAPIError: If command fails or system not found

        """
        # Normalize serial number to lowercase for consistent lookup
        serial_number = serial_number.lower()

        endpoint = self._get_system_link(serial_number, "commands")
        if not endpoint:
            raise ActronAirAPIError(f"No commands link found for system {serial_number}")

        await self._make_request(
            "post",
            endpoint,
            json_data=command,
            headers={"Content-Type": "application/json"},
        )

    async def update_status(
        self, serial_number: str | None = None
    ) -> dict[str, ActronAirStatus | None]:
        """Update the status of AC systems using event-based updates.

        Args:
            serial_number: Optional serial number to update specific system,
                          or None to update all systems

        Returns:
            Dictionary mapping serial numbers to status models

        """
        if serial_number:
            # Update specific system
            await self._update_system_status(serial_number)
            status = self.state_manager.get_status(serial_number)
            return {serial_number: status}

        # Update all systems
        if not self.systems:
            return {}

        results: dict[str, ActronAirStatus | None] = {}
        for system in self.systems:
            if system.serial:
                await self._update_system_status(system.serial)
                status = self.state_manager.get_status(system.serial)
                results[system.serial] = status

        return results

    async def _update_system_status(self, serial_number: str) -> None:
        """Update status for a single system using status polling.

        Note: Switched from event-based updates to status polling due to
        Actron disabling the events API in July 2025.

        Args:
            serial_number: Serial number of the system to update

        Raises:
            ActronAirAuthError: If authentication fails
            ActronAirAPIError: If API request fails

        """
        # Get current status using the status/latest endpoint
        status = await self.get_ac_status(serial_number)
        if status:
            # Store the status object in the state manager
            self.state_manager.status[serial_number] = status

    @property
    def access_token(self) -> str | None:
        """Get the current OAuth2 access token."""
        return self.oauth2_auth.access_token

    @property
    def refresh_token_value(self) -> str | None:
        """Get the current OAuth2 refresh token."""
        return self.oauth2_auth.refresh_token

    @property
    def latest_event_id(self) -> dict[str, str]:
        """Get the latest event ID for each system."""
        return self.state_manager.latest_event_id.copy()
