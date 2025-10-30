"""OAuth2 Device Code Flow authentication for Actron Neo API."""

import logging
import time
from typing import Dict, Optional, Any, Tuple
import aiohttp

from .exceptions import ActronAirAuthError

_LOGGER = logging.getLogger(__name__)


class ActronAirOAuth2DeviceCodeAuth:
    """
    OAuth2 Device Code Flow authentication handler for Actron Neo API.

    This class implements the OAuth2 device code flow which is suitable for
    devices with limited input capabilities or when QR code authentication
    is preferred.
    """

    def __init__(self, base_url: str, client_id: str = "home_assistant"):
        """
        Initialize the OAuth2 Device Code Flow handler.

        Args:
            base_url: Base URL for the Actron Neo API
            client_id: OAuth2 client ID
        """
        self.base_url = base_url
        self.client_id = client_id
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_type: str = "Bearer"
        self.token_expiry: Optional[float] = None

        # OAuth2 endpoints
        self.token_url = f"{base_url}/api/v0/oauth/token"
        self.authorize_url = f"{base_url}/authorize"
        self.device_auth_url = f"{base_url}/connect"
        self.user_info_url = f"{base_url}/api/v0/client/account"

    @property
    def is_token_valid(self) -> bool:
        """Check if the access token is valid and not expired."""
        return (
            self.access_token is not None and
            self.token_expiry is not None and
            time.time() < self.token_expiry
        )

    @property
    def is_token_expiring_soon(self) -> bool:
        """Check if the token is expiring within the next 15 minutes."""
        return (
            self.token_expiry is not None and
            time.time() > (self.token_expiry - 900)  # 15 minutes
        )

    @property
    def authorization_header(self) -> Dict[str, str]:
        """Get the authorization header using the current token."""
        if not self.access_token:
            raise ActronAirAuthError("No access token available")
        return {"Authorization": f"{self.token_type} {self.access_token}"}

    async def request_device_code(self) -> Dict[str, Any]:
        """
        Request a device code for OAuth2 device code flow.

        Returns:
            Dictionary containing device code, user code, verification URI, etc.

        Raises:
            ActronAirAuthError: If device code request fails
        """
        payload = {
            "client_id": self.client_id,
            "scope": "read write"  # Add appropriate scopes
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.token_url,
                data=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    # Validate required fields
                    required_fields = [
                        "device_code", "user_code", "verification_uri",
                        "expires_in", "interval"
                    ]

                    for field in required_fields:
                        if field not in data:
                            raise ActronAirAuthError(f"Missing required field: {field}")

                    # Add verification_uri_complete if not present
                    if "verification_uri_complete" not in data:
                        data["verification_uri_complete"] = (
                            f"{data['verification_uri']}?user_code={data['user_code']}"
                        )

                    return data
                else:
                    response_text = await response.text()
                    raise ActronAirAuthError(
                        f"Failed to request device code. Status: {response.status}, Response: {response_text}"
                    )

    async def poll_for_token(self, device_code: str, interval: int = 5, timeout: int = 600) -> Optional[Dict[str, Any]]:
        """
        Poll for access token using device code with automatic polling loop.

        This method implements the full OAuth2 device code flow polling logic,
        automatically handling authorization_pending and slow_down responses
        according to the OAuth2 specification.

        Args:
            device_code: The device code received from request_device_code
            interval: Polling interval in seconds (default: 5)
            timeout: Maximum time to wait in seconds (default: 600 = 10 minutes)

        Returns:
            Token data if successful, None if timeout occurs

        Raises:
            ActronAirAuthError: If authorization is denied or other errors occur
        """
        import asyncio

        payload = {
            "client_id": self.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        start_time = time.time()
        current_interval = interval
        attempt = 0

        _LOGGER.info("Starting token polling (interval=%ds, timeout=%ds)", interval, timeout)

        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < timeout:
                attempt += 1

                try:
                    async with session.post(
                        self.token_url,
                        data=payload,
                        headers=headers
                    ) as response:
                        data = await response.json()

                        if response.status == 200 and "access_token" in data:
                            # Success - store tokens
                            self.access_token = data["access_token"]
                            self.refresh_token = data.get("refresh_token")
                            self.token_type = data.get("token_type", "Bearer")

                            expires_in = data.get("expires_in", 3600)
                            self.token_expiry = time.time() + expires_in

                            _LOGGER.info(
                                "OAuth2 token obtained successfully after %d attempts. "
                                "Expires in %s seconds", attempt, expires_in
                            )

                            return data

                        elif response.status == 400:
                            error = data.get("error", "unknown_error")

                            if error == "authorization_pending":
                                # Still waiting for user authorization - continue polling
                                _LOGGER.debug(
                                    "Authorization pending (attempt %d) - continuing to poll in %ds",
                                    attempt, current_interval
                                )
                                await asyncio.sleep(current_interval)
                                continue

                            elif error == "slow_down":
                                # Server requests slower polling - increase interval
                                current_interval += 5  # Add 5 seconds as per OAuth2 spec
                                _LOGGER.warning(
                                    "Server requested slow down - increasing interval to %ds",
                                    current_interval
                                )
                                await asyncio.sleep(current_interval)
                                continue

                            elif error == "expired_token":
                                raise ActronAirAuthError("Device code has expired")
                            elif error == "access_denied":
                                raise ActronAirAuthError("User denied authorization")
                            else:
                                raise ActronAirAuthError(f"Authorization error: {error}")
                        else:
                            response_text = await response.text()
                            raise ActronAirAuthError(
                                f"Token polling failed. Status: {response.status}, Response: {response_text}"
                            )

                except aiohttp.ClientError as e:
                    _LOGGER.warning("Network error during polling attempt %d: %s", attempt, e)
                    await asyncio.sleep(current_interval)
                    continue
                except Exception as e:
                    _LOGGER.error("Unexpected error during polling: %s", e)
                    raise ActronAirAuthError(f"Polling failed: {str(e)}") from e

        # Timeout reached
        _LOGGER.error("Token polling timed out after %d seconds (%d attempts)", timeout, attempt)
        return None

    async def refresh_access_token(self) -> Tuple[str, float]:
        """
        Refresh the access token using the refresh token.

        Returns:
            Tuple of (access_token, expiry_timestamp)

        Raises:
            ActronAirAuthError: If token refresh fails
        """
        if not self.refresh_token:
            raise ActronAirAuthError("Refresh token is required to refresh the access token")

        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.token_url,
                data=payload,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    self.access_token = data.get("access_token")
                    if not self.access_token:
                        raise ActronAirAuthError("Access token missing in response")

                    # Update refresh token if provided
                    if "refresh_token" in data:
                        self.refresh_token = data["refresh_token"]

                    self.token_type = data.get("token_type", "Bearer")
                    expires_in = data.get("expires_in", 3600)

                    # Store expiry time as Unix timestamp
                    self.token_expiry = time.time() + expires_in

                    _LOGGER.info(
                        "OAuth2 token refreshed successfully. "
                        "Expires in %s seconds", expires_in
                    )

                    return self.access_token, self.token_expiry
                else:
                    response_text = await response.text()
                    raise ActronAirAuthError(
                        f"Failed to refresh access token. Status: {response.status}, Response: {response_text}"
                    )

    async def get_user_info(self) -> Dict[str, Any]:
        """
        Get user information using the access token.

        Returns:
            Dictionary containing user information

        Raises:
            ActronAirAuthError: If user info request fails
        """
        # Ensure we have a valid access token
        await self.ensure_token_valid()

        headers = self.authorization_header

        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.user_info_url,
                headers=headers
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    response_text = await response.text()
                    raise ActronAirAuthError(
                        f"Failed to get user info. Status: {response.status}, Response: {response_text}"
                    )

    async def ensure_token_valid(self) -> str:
        """
        Ensure the token is valid, refreshing it if necessary.

        Returns:
            The current valid access token

        Raises:
            ActronAirAuthError: If token validation fails
        """
        if not self.is_token_valid:
            if self.is_token_expiring_soon:
                _LOGGER.info("OAuth2 access token is expiring soon. Refreshing...")
            else:
                _LOGGER.info("OAuth2 access token is invalid or missing. Refreshing...")

            await self.refresh_access_token()

        return self.access_token

    def set_tokens(self, access_token: str, refresh_token: Optional[str] = None,
                   expires_in: Optional[int] = None, token_type: str = "Bearer") -> None:
        """
        Set tokens manually (useful for restoring saved tokens).

        Args:
            access_token: The access token
            refresh_token: The refresh token (optional)
            expires_in: Token expiration time in seconds from now (optional)
            token_type: Token type (default: "Bearer")
        """
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_type = token_type

        if expires_in is not None:
            self.token_expiry = time.time() + expires_in
        else:
            # Default to 1 hour if not specified
            self.token_expiry = time.time() + 3600

        _LOGGER.info("OAuth2 tokens set manually")
