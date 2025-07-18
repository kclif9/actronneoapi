import logging
import asyncio
from typing import Dict, List, Optional, Any

import aiohttp

from .oauth import OAuth2DeviceCodeAuth
from .state import StateManager
from .exceptions import ActronNeoAPIError, ActronNeoAuthError
from .models.system import ActronAirNeoSystemInfo

_LOGGER = logging.getLogger(__name__)

class ActronNeoAPI:
    """
    Client for the Actron Neo API with improved architecture.

    This client provides a modern, structured approach to interacting with
    the Actron Neo API while maintaining compatibility with the previous interface.
    """

    def __init__(
        self,
        base_url: str = "https://nimbus.actronair.com.au",
        oauth2_client_id: str = "home_assistant",
        refresh_token: Optional[str] = None,
    ):
        """
        Initialize the ActronNeoAPI client with OAuth2 authentication.

        Args:
            base_url: Base URL for the Actron Neo API
            oauth2_client_id: OAuth2 client ID for device code flow
            refresh_token: Optional refresh token for authentication
        """
        self.base_url = base_url

        # Initialize OAuth2 authentication
        self.oauth2_auth = OAuth2DeviceCodeAuth(base_url, oauth2_client_id)

        # Set refresh token if provided
        if refresh_token:
            self.oauth2_auth.refresh_token = refresh_token

        self.state_manager = StateManager()
        # Set the API reference in the state manager for command execution
        self.state_manager.set_api(self)

        self.systems = []

        # Session management
        self._session = None
        self._session_lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp ClientSession."""
        async with self._session_lock:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession()
            return self._session

    async def close(self) -> None:
        """Close the API client and release resources."""
        async with self._session_lock:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

    async def __aenter__(self):
        """Support for async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Support for async context manager."""
        await self.close()

    # OAuth2 Device Code Flow methods

    async def request_device_code(self) -> Dict[str, Any]:
        """
        Request a device code for OAuth2 device code flow.

        Returns:
            Dictionary containing device code, user code, verification URI, etc.

        Raises:
            ActronNeoAuthError: If device code request fails
        """
        return await self.oauth2_auth.request_device_code()

    async def poll_for_token(self, device_code: str) -> Optional[Dict[str, Any]]:
        """
        Poll for access token using device code.

        Args:
            device_code: The device code received from request_device_code

        Returns:
            Token data if successful, None if still pending

        Raises:
            ActronNeoAuthError: If polling fails
        """
        return await self.oauth2_auth.poll_for_token(device_code)

    async def get_user_info(self) -> Dict[str, Any]:
        """
        Get user information using the access token.

        Returns:
            Dictionary containing user information

        Raises:
            ActronNeoAuthError: If user info request fails
        """
        return await self.oauth2_auth.get_user_info()

    async def _handle_request(self, request_func, *args, **kwargs):
        """
        Handle API requests, retrying once if the token is expired.
        """
        # Ensure the token is valid before making the request
        if self.oauth2_auth.is_token_expiring_soon:
            _LOGGER.info("Access token is about to expire. Proactively refreshing.")
            await self.oauth2_auth.refresh_access_token()

        try:
            return await request_func(*args, **kwargs)
        except Exception as e:
            _LOGGER.error("Error occurred: %s", e)
            raise

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Make an API request with proper error handling.

        Args:
            method: HTTP method ("get", "post", etc.)
            endpoint: API endpoint (without base URL)
            params: URL parameters
            json_data: JSON body data
            data: Form data
            headers: HTTP headers

        Returns:
            API response as JSON

        Raises:
            ActronNeoAuthError: For authentication errors
            ActronNeoAPIError: For API errors
        """
        # If we have a refresh token but no access token, get one
        if self.oauth2_auth.refresh_token and not self.oauth2_auth.access_token:
            await self.oauth2_auth.refresh_access_token()

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
                method,
                url,
                params=params,
                json=json_data,
                data=data,
                headers=request_headers
            ) as response:
                if response.status == 401:
                    response_text = await response.text()
                    raise ActronNeoAuthError(f"Authentication failed: {response_text}")

                if response.status != 200:
                    response_text = await response.text()
                    raise ActronNeoAPIError(
                        f"API request failed. Status: {response.status}, Response: {response_text}"
                    )

                return await response.json()
        except aiohttp.ClientError as e:
            raise ActronNeoAPIError(f"Request failed: {str(e)}") from e

    # API Methods

    async def get_ac_systems(self) -> List[ActronAirNeoSystemInfo]:
        """
        Retrieve all AC systems in the customer account.

        Returns:
            List of typed AC system info objects
        """
        raw_systems = await self._handle_request(self._get_ac_systems)
        # Convert raw dicts to typed objects
        systems = [ActronAirNeoSystemInfo.model_validate(system) for system in raw_systems]
        self.systems = systems  # Store typed objects
        return systems

    async def _get_ac_systems(self) -> List[Dict[str, Any]]:
        """Internal method to perform the actual API call."""
        response = await self._make_request(
            "get",
            "api/v0/client/ac-systems",
            params={"includeNeo": "true"}
        )
        return response["_embedded"]["ac-system"]



    async def get_ac_events(
        self, serial_number: str, event_type: str = "latest", event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve events for a specific AC system.

        Args:
            serial_number: Serial number of the AC system
            event_type: 'latest', 'newer', or 'older' for the event query type
            event_id: The event ID for 'newer' or 'older' event queries

        Returns:
            Events of the AC system
        """
        return await self._handle_request(
            self._get_ac_events, serial_number, event_type, event_id
        )

    async def _get_ac_events(
        self, serial_number: str, event_type: str = "latest", event_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Internal method to perform the actual API call."""
        params = {"serial": serial_number}

        if event_type == "latest":
            endpoint = "api/v0/client/ac-systems/events/latest"
        elif event_type == "newer" and event_id:
            endpoint = "api/v0/client/ac-systems/events/newer"
            params["newerThanEventId"] = event_id
        elif event_type == "older" and event_id:
            endpoint = "api/v0/client/ac-systems/events/older"
            params["olderThanEventId"] = event_id
        else:
            raise ValueError(
                "Invalid event_type or missing event_id for 'newer'/'older' event queries."
            )

        return await self._make_request("get", endpoint, params=params)

    async def send_command(self, serial_number: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a command to the specified AC system.

        Args:
            serial_number: Serial number of the AC system
            command: Dictionary containing the command details

        Returns:
            Command response
        """
        return await self._handle_request(self._send_command, serial_number, command)

    async def _send_command(self, serial_number: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """Internal method to perform the actual API call."""
        serial_number = serial_number.lower()
        return await self._make_request(
            "post",
            "api/v0/client/ac-systems/cmds/send",
            params={"serial": serial_number},
            json_data=command,
            headers={"Content-Type": "application/json"}
        )

    async def update_status(self, serial_number: Optional[str] = None) -> Dict[str, Any]:
        """
        Update the status of AC systems using event-based updates.

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
            serial = system.serial  # Now using typed object property
            if serial:
                await self._update_system_status(serial)
                status = self.state_manager.get_status(serial)
                if status:
                    results[serial] = status.dict()

        return results

    async def _update_system_status(self, serial_number: str) -> None:
        """
        Update status for a single system using event-based updates.

        Args:
            serial_number: Serial number of the system to update
        """
        try:
            # Check if we need a full update or incremental update
            if serial_number not in self.state_manager.latest_event_id:
                # First time - fetch full status
                events = await self.get_ac_events(serial_number, event_type="latest")
                if events:
                    self.state_manager.process_events(serial_number, events)
            else:
                # Incremental update
                latest_event_id = self.state_manager.latest_event_id.get(serial_number)
                events = await self.get_ac_events(
                    serial_number,
                    event_type="newer",
                    event_id=latest_event_id
                )
                if events:
                    self.state_manager.process_events(serial_number, events)
        except Exception as e:
            _LOGGER.error("Failed to update status for system %s: %s", serial_number, e)

    # Property accessors

    @property
    def access_token(self) -> Optional[str]:
        """Get the current access token."""
        return self.oauth2_auth.access_token

    @property
    def refresh_token_value(self) -> Optional[str]:
        """Get the current refresh token."""
        return self.oauth2_auth.refresh_token

    @property
    def latest_event_id(self) -> Dict[str, str]:
        """Get the latest event ID for each system."""
        return self.state_manager.latest_event_id.copy()
