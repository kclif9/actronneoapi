"""Actron Air API client module."""

import asyncio
import logging
from typing import Any, Dict, List, Literal, Optional

import aiohttp

from .const import BASE_URL_DEFAULT, BASE_URL_NIMBUS, BASE_URL_QUE, PLATFORM_NEO, PLATFORM_QUE
from .exceptions import ActronAirAPIError, ActronAirAuthError
from .oauth import ActronAirOAuth2DeviceCodeAuth
from .state import StateManager

_LOGGER = logging.getLogger(__name__)


class ActronAirAPI:
    """Client for the Actron Air API with improved architecture.

    This client provides a modern, structured approach to interacting with
    the Actron Air API while maintaining compatibility with the previous interface.
    """

    def __init__(
        self,
        oauth2_client_id: str = "home_assistant",
        refresh_token: Optional[str] = None,
        platform: Optional[Literal["neo", "que"]] = None,
    ):
        """Initialize the ActronAirAPI client with OAuth2 authentication.

        Args:
            oauth2_client_id: OAuth2 client ID for device code flow
            refresh_token: Optional refresh token for authentication
            platform: Platform to use ('neo', 'que', or None for auto-detect).
            If None, enables auto-detection with Neo as the initial platform.

        """
        # Determine base URL from platform parameter
        if platform == PLATFORM_QUE:
            resolved_base_url = BASE_URL_QUE
            self._auto_manage_base_url = False
        elif platform == PLATFORM_NEO:
            resolved_base_url = BASE_URL_NIMBUS
            self._auto_manage_base_url = False
        else:
            # Auto-detect with Neo as fallback (platform is None)
            resolved_base_url = BASE_URL_DEFAULT
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

        self.systems: List[Dict[str, Any]] = []
        self._initialized = False

        # Session management
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()

    @property
    def platform(self) -> str:
        """Get the current platform being used.

        Returns:
            'neo' if using Nimbus platform, 'que' if using Que platform

        """
        if self.base_url == BASE_URL_NIMBUS:
            return PLATFORM_NEO
        elif self.base_url == BASE_URL_QUE:
            return PLATFORM_QUE
        else:
            return "unknown"

    @property
    def authenticated_platform(self) -> Optional[str]:
        """Get the platform where tokens were originally obtained.

        Returns:
            Platform URL where tokens were authenticated, or None if not authenticated

        """
        return self.oauth2_auth.authenticated_platform

    def _get_system_link(self, serial_number: str, rel: str) -> Optional[str]:
        """Return a HAL link for a cached system if available.

        Args:
            serial_number: Serial number of the AC system
            rel: The relationship name of the link to retrieve

        Returns:
            The href URL string with leading slash removed, or None if not found

        """
        for system in self.systems:
            if system.get("serial") != serial_number:
                continue

            links = system.get("_links") or {}
            link_info = links.get(rel)

            if isinstance(link_info, dict):
                href = link_info.get("href")
            elif isinstance(link_info, list) and link_info:
                href = link_info[0].get("href") if isinstance(link_info[0], dict) else None
            else:
                href = None

            if href:
                return href.lstrip("/")

        return None

    @staticmethod
    def _is_nx_gen_system(system: Dict[str, Any]) -> bool:
        """Check if a system is an NX Gen type.

        Args:
            system: System dictionary containing type information

        Returns:
            True if the system is NX Gen type, False otherwise

        """
        system_type = str(system.get("type") or "").replace("-", "").lower()
        return system_type == "nxgen"

    def _set_base_url(self, base_url: str) -> None:
        """Update the base URL and preserve existing authentication tokens.

        Args:
            base_url: New base URL to switch to

        Note:
            This preserves tokens but they may not work if switching between
            incompatible platforms (Neo vs Que).

        """
        if self.base_url == base_url:
            return

        _LOGGER.info("Switching API base URL from %s to %s", self.base_url, base_url)

        # Preserve existing tokens
        old_access_token = self.oauth2_auth.access_token
        old_refresh_token = self.oauth2_auth.refresh_token
        old_token_expiry = self.oauth2_auth.token_expiry
        old_authenticated_platform = self.oauth2_auth.authenticated_platform

        # Update base URL and recreate OAuth2 handler to match new platform
        self.base_url = base_url
        self.oauth2_auth = ActronAirOAuth2DeviceCodeAuth(base_url, self._oauth2_client_id)

        # Restore tokens
        self.oauth2_auth.access_token = old_access_token
        self.oauth2_auth.refresh_token = old_refresh_token
        self.oauth2_auth.token_expiry = old_token_expiry
        self.oauth2_auth.authenticated_platform = old_authenticated_platform

        _LOGGER.warning(
            "Platform switched - tokens obtained from %s may not work with %s. "
            "Re-authentication may be required.",
            old_authenticated_platform or "unknown platform",
            base_url,
        )

    def _maybe_update_base_url_from_systems(self, systems: List[Dict[str, Any]]) -> None:
        """Automatically update base URL based on system types if auto-management is enabled.

        Args:
            systems: List of AC systems to analyze

        Note:
            Switches to QUE platform if any NX Gen systems are found,
            otherwise uses NIMBUS platform.

        """
        if not self._auto_manage_base_url or not systems:
            return

        has_nx_gen = any(self._is_nx_gen_system(system) for system in systems)
        target_base = BASE_URL_QUE if has_nx_gen else BASE_URL_NIMBUS
        self._set_base_url(target_base)

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
                session: aiohttp.ClientSession = aiohttp.ClientSession()
                self._session = session
                return session
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
    async def request_device_code(self) -> Dict[str, Any]:
        """Request a device code for OAuth2 device code flow."""
        return await self.oauth2_auth.request_device_code()

    async def poll_for_token(
        self, device_code: str, interval: int = 5, timeout: int = 600
    ) -> Optional[Dict[str, Any]]:
        """Poll for access token using device code with automatic polling loop.

        Args:
            device_code: The device code received from request_device_code
            interval: Polling interval in seconds (default: 5)
            timeout: Maximum time to wait in seconds (default: 600 = 10 minutes)

        Returns:
            Token data if successful, None if timeout occurs

        """
        return await self.oauth2_auth.poll_for_token(device_code, interval, timeout)

    async def get_user_info(self) -> Dict[str, Any]:
        """Get user information using the access token."""
        return await self.oauth2_auth.get_user_info()

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        _retry: bool = True,
    ) -> Dict[str, Any]:
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
                        _LOGGER.info("Received 401, attempting to refresh token and retry")
                        try:
                            await self.oauth2_auth.refresh_access_token()
                            # Retry the request once with the new token
                            return await self._make_request(
                                method, endpoint, params, json_data, data, headers, _retry=False
                            )
                        except ActronAirAuthError:
                            # Token refresh failed - re-raise as-is for proper handling
                            _LOGGER.error("Token refresh failed due to authentication error")
                            raise
                        except Exception as refresh_error:
                            # Unexpected error during refresh
                            _LOGGER.error("Token refresh failed: %s", refresh_error)
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

    async def get_ac_systems(self) -> List[Dict[str, Any]]:
        """Retrieve all AC systems in the customer account.

        Returns:
            List of AC systems

        """
        try:
            response = await self._make_request(
                "get", "api/v0/client/ac-systems", params={"includeNeo": "true"}
            )
            systems = response["_embedded"]["ac-system"]
            self.systems = systems  # Auto-populate for convenience
            self._maybe_update_base_url_from_systems(systems)
            return systems
        except Exception as e:
            _LOGGER.error("Error getting AC systems: %s", e)
            raise

    async def get_ac_status(self, serial_number: str) -> Dict[str, Any]:
        """Retrieve the current status for a specific AC system.

        This replaces the events API which was disabled by Actron in July 2025.

        Args:
            serial_number: Serial number of the AC system

        Returns:
            Current status of the AC system

        """
        try:
            endpoint = self._get_system_link(serial_number, "ac-status")
            if endpoint:
                return await self._make_request("get", endpoint)
            raise ActronAirAPIError(f"No ac-status link found for system {serial_number}")
        except Exception as e:
            _LOGGER.error("Error getting AC status for %s: %s", serial_number, e)
            raise

    async def send_command(self, serial_number: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command to the specified AC system.

        Args:
            serial_number: Serial number of the AC system
            command: Dictionary containing the command details

        Returns:
            Command response

        """
        try:
            endpoint = self._get_system_link(serial_number, "commands")
            if endpoint:
                serial_number = serial_number.lower()
                return await self._make_request(
                    "post",
                    endpoint,
                    json_data=command,
                    headers={"Content-Type": "application/json"},
                )
            raise ActronAirAPIError(f"No commands link found for system {serial_number}")
        except Exception as e:
            _LOGGER.error("Error sending command to %s: %s", serial_number, e)
            raise

    async def update_status(self, serial_number: Optional[str] = None) -> Dict[str, Any]:
        """Update the status of AC systems using event-based updates.

        Args:
            serial_number: Optional serial number to update specific system,
                          or None to update all systems

        Returns:
            Dictionary of updated status data by serial number

        """
        if serial_number:
            # Update specific system
            await self._update_system_status(serial_number)
            status = self.state_manager.get_status(serial_number)
            return {serial_number: status.dict() if status else None}

        # Update all systems
        if not self.systems:
            return {}

        results = {}
        for system in self.systems:
            serial = system.get("serial")
            if serial:
                await self._update_system_status(serial)
                status = self.state_manager.get_status(serial)
                if status:
                    results[serial] = status.dict()

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
        try:
            # Get current status using the status/latest endpoint
            status_data = await self.get_ac_status(serial_number)
            if status_data:
                # Process the status data through the state manager
                self.state_manager.process_status_update(serial_number, status_data)
        except (ActronAirAuthError, ActronAirAPIError):
            # Re-raise authentication and API errors for proper handling upstream
            raise
        except Exception as e:
            _LOGGER.error("Failed to update status for system %s: %s", serial_number, e)
            raise

    @property
    def access_token(self) -> Optional[str]:
        """Get the current OAuth2 access token."""
        return self.oauth2_auth.access_token

    @property
    def refresh_token_value(self) -> Optional[str]:
        """Get the current OAuth2 refresh token."""
        return self.oauth2_auth.refresh_token

    @property
    def latest_event_id(self) -> Dict[str, str]:
        """Get the latest event ID for each system."""
        return self.state_manager.latest_event_id.copy()
