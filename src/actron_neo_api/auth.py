import logging
import time
from typing import Dict, Optional, Any, Tuple
import aiohttp

from .exceptions import ActronNeoAuthError

_LOGGER = logging.getLogger(__name__)

class TokenManager:
    """
    Manages authentication tokens for the Actron Neo API.
    Handles token acquisition, refreshing, and expiration tracking.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.pairing_token: Optional[str] = None
        self.access_token: Optional[str] = None
        self.token_type: str = "bearer"
        self.token_expiry: Optional[float] = None

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
            raise ActronNeoAuthError("No access token available")
        return {"Authorization": f"{self.token_type} {self.access_token}"}

    async def request_pairing_token(self, username: str, password: str,
                                    device_name: str, device_unique_id: str,
                                    client: str = "ios") -> str:
        """
        Request a pairing token using credentials and device details.

        Args:
            username: Username for Actron Neo account
            password: Password for Actron Neo account
            device_name: Name of the device
            device_unique_id: Unique identifier for the device
            client: Client type (default: "ios")

        Returns:
            The pairing token

        Raises:
            ActronNeoAuthError: If authentication fails
        """
        url = f"{self.base_url}/api/v0/client/user-devices"
        payload = {
            "username": username,
            "password": password,
            "client": client,
            "deviceName": device_name,
            "deviceUniqueIdentifier": device_unique_id,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    pairing_token = data.get("pairingToken")
                    if not pairing_token:
                        raise ActronNeoAuthError("Pairing token missing in response")

                    self.pairing_token = pairing_token
                    return pairing_token
                else:
                    response_text = await response.text()
                    raise ActronNeoAuthError(
                        f"Failed to request pairing token. Status: {response.status}, Response: {response_text}"
                    )

    async def refresh_token(self) -> Tuple[str, float]:
        """
        Refresh the access token using the pairing token.

        Returns:
            Tuple of (access_token, expiry_timestamp)

        Raises:
            ActronNeoAuthError: If token refresh fails
        """
        if not self.pairing_token:
            raise ActronNeoAuthError("Pairing token is required to refresh the access token")

        url = f"{self.base_url}/api/v0/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.pairing_token,
            "client_id": "app",
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()

                    self.access_token = data.get("access_token")
                    if not self.access_token:
                        raise ActronNeoAuthError("Access token missing in response")

                    self.token_type = data.get("token_type", "bearer")
                    expires_in = data.get("expires_in", 259199)  # Default to ~3 days

                    # Store expiry time as Unix timestamp
                    self.token_expiry = time.time() + expires_in

                    _LOGGER.info(
                        f"Token refreshed successfully. "
                        f"Expires in {expires_in} seconds ({expires_in/86400:.1f} days)"
                    )

                    return self.access_token, self.token_expiry
                else:
                    response_text = await response.text()
                    raise ActronNeoAuthError(
                        f"Failed to refresh access token. Status: {response.status}, Response: {response_text}"
                    )

    async def ensure_token_valid(self) -> str:
        """
        Ensure the token is valid, refreshing it if necessary.

        Returns:
            The current valid access token

        Raises:
            ActronNeoAuthError: If token validation fails
        """
        if not self.is_token_valid:
            if self.is_token_expiring_soon:
                _LOGGER.info("Access token is expiring soon. Refreshing...")
            else:
                _LOGGER.info("Access token is invalid or missing. Refreshing...")

            await self.refresh_token()

        return self.access_token
