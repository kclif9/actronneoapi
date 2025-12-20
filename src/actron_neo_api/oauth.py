"""OAuth2 Device Code Flow authentication for Actron Air API."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Final

import aiohttp

from .exceptions import ActronAirAuthError
from .models import ActronAirDeviceCode, ActronAirToken


class ActronAirOAuth2DeviceCodeAuth:
    """OAuth2 Device Code Flow authentication handler for Actron Air API.

    This class implements the OAuth2 device code flow which is suitable for
    devices with limited input capabilities or when QR code authentication
    is preferred.
    """

    def __init__(self, base_url: str, client_id: str = "home_assistant") -> None:
        """Initialize the OAuth2 Device Code Flow handler.

        Args:
            base_url: Base URL for the Actron Air API
            client_id: OAuth2 client ID

        Raises:
            ValueError: If base_url or client_id are empty

        """
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be empty")
        if not client_id or not client_id.strip():
            raise ValueError("client_id cannot be empty")

        self.base_url: Final[str] = base_url.rstrip("/")
        self.client_id: Final[str] = client_id
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_type: str = "Bearer"
        self.token_expiry: float | None = None
        self.authenticated_platform: str | None = None  # Track which platform issued tokens

        # OAuth2 endpoints
        self.token_url: Final[str] = f"{self.base_url}/api/v0/oauth/token"
        self.authorize_url: Final[str] = f"{self.base_url}/authorize"
        self.device_auth_url: Final[str] = f"{self.base_url}/connect"
        self.user_info_url: Final[str] = f"{self.base_url}/api/v0/client/account"

    @property
    def is_token_valid(self) -> bool:
        """Check if the access token is valid and not expired."""
        return (
            self.access_token is not None
            and self.token_expiry is not None
            and time.time() < self.token_expiry
        )

    @property
    def is_token_expiring_soon(self) -> bool:
        """Check if the token is expiring within the next 15 minutes."""
        return (
            self.token_expiry is not None and time.time() > (self.token_expiry - 900)  # 15 minutes
        )

    @property
    def authorization_header(self) -> dict[str, str]:
        """Get the authorization header using the current token."""
        if not self.access_token:
            raise ActronAirAuthError("No access token available")
        return {"Authorization": f"{self.token_type} {self.access_token}"}

    async def request_device_code(self) -> ActronAirDeviceCode:
        """Request a device code for OAuth2 device code flow.

        Returns:
            Device code response model

        Raises:
            ActronAirAuthError: If device code request fails

        """
        payload = {
            "client_id": self.client_id,
            "scope": "read write",  # Add appropriate scopes
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()

                    # Validate required fields
                    required_fields: Final[list[str]] = [
                        "device_code",
                        "user_code",
                        "verification_uri",
                        "expires_in",
                        "interval",
                    ]

                    missing_fields = [field for field in required_fields if field not in data]
                    if missing_fields:
                        raise ActronAirAuthError(
                            f"Missing required fields in response: {', '.join(missing_fields)}"
                        )

                    # Add verification_uri_complete if not present
                    if "verification_uri_complete" not in data:
                        data["verification_uri_complete"] = (
                            f"{data['verification_uri']}?user_code={data['user_code']}"
                        )

                    return ActronAirDeviceCode(**data)
                else:
                    response_text = await response.text()
                    raise ActronAirAuthError(
                        f"Failed to request device code. "
                        f"Status: {response.status}, "
                        f"Response: {response_text}"
                    )

    async def poll_for_token(
        self, device_code: str, interval: int = 5, timeout: int = 600
    ) -> ActronAirToken | None:
        """Poll for access token using device code with automatic polling loop.

        This method implements the full OAuth2 device code flow polling logic,
        automatically handling authorization_pending and slow_down responses
        according to the OAuth2 specification.

        Args:
            device_code: The device code received from request_device_code
            interval: Polling interval in seconds (default: 5, minimum: 1)
            timeout: Maximum time to wait in seconds (default: 600 = 10 minutes, minimum: 10)

        Returns:
            Token model if successful, None if timeout occurs

        Raises:
            ActronAirAuthError: If authorization is denied or other errors occur
            ValueError: If device_code is empty or interval/timeout are invalid

        """
        if not device_code or not device_code.strip():
            raise ValueError("device_code cannot be empty")
        if interval < 1:
            raise ValueError("interval must be at least 1 second")
        if timeout < 10:
            raise ValueError("timeout must be at least 10 seconds")

        payload = {
            "client_id": self.client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        start_time = time.time()
        current_interval = interval
        attempt = 0

        async with aiohttp.ClientSession() as session:
            while time.time() - start_time < timeout:
                attempt += 1

                try:
                    async with session.post(
                        self.token_url, data=payload, headers=headers
                    ) as response:
                        data = await response.json()

                        if response.status == 200 and "access_token" in data:
                            # Success - store tokens
                            self.access_token = data["access_token"]
                            self.refresh_token = data.get("refresh_token")
                            self.token_type = data.get("token_type", "Bearer")
                            self.authenticated_platform = (
                                self.base_url
                            )  # Record platform that issued tokens

                            expires_in = data.get("expires_in", 3600)
                            self.token_expiry = time.time() + expires_in

                            return ActronAirToken(**data)

                        elif response.status == 400:
                            error = data.get("error", "unknown_error")

                            if error == "authorization_pending":
                                # Still waiting for user authorization - continue polling
                                await asyncio.sleep(current_interval)
                                continue

                            elif error == "slow_down":
                                # Server requests slower polling - increase interval
                                current_interval += 5  # Add 5 seconds as per OAuth2 spec
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
                                f"Token polling failed. "
                                f"Status: {response.status}, "
                                f"Response: {response_text}."
                            )

                except aiohttp.ClientError:
                    await asyncio.sleep(current_interval)
                    continue
                except (ValueError, KeyError, TypeError) as e:
                    raise ActronAirAuthError(f"Polling failed: {str(e)}") from e

        # Timeout reached
        return None

    async def refresh_access_token(self) -> tuple[str, float]:
        """Refresh the access token using the refresh token.

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
            "client_id": self.client_id,
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()

                    access_token = data.get("access_token")
                    if not access_token or not isinstance(access_token, str):
                        raise ActronAirAuthError("Access token missing or invalid in response")
                    self.access_token = access_token

                    # Update refresh token if provided
                    refresh_token = data.get("refresh_token")
                    if refresh_token and isinstance(refresh_token, str):
                        self.refresh_token = refresh_token

                    token_type = data.get("token_type", "Bearer")
                    self.token_type = token_type if isinstance(token_type, str) else "Bearer"

                    expires_in_raw = data.get("expires_in", 3600)
                    try:
                        expires_in = int(expires_in_raw) if expires_in_raw else 3600
                    except (ValueError, TypeError):
                        expires_in = 3600

                    # Update authenticated platform since refresh succeeded on this endpoint
                    self.authenticated_platform = self.base_url

                    # Store expiry time as Unix timestamp
                    self.token_expiry = time.time() + expires_in

                    if self.access_token is None or self.token_expiry is None:
                        raise ActronAirAuthError("Access token or expiry missing after refresh")
                    return self.access_token, self.token_expiry
                else:
                    response_text = await response.text()
                    raise ActronAirAuthError(
                        f"Failed to refresh access token. "
                        f"Status: {response.status}, "
                        f"Response: {response_text}."
                    )

    async def get_user_info(self) -> dict[str, Any]:
        """Get user information using the access token.

        Returns:
            Dictionary containing user information

        Raises:
            ActronAirAuthError: If user info request fails

        """
        # Ensure we have a valid access token
        await self.ensure_token_valid()

        headers = self.authorization_header

        async with aiohttp.ClientSession() as session:
            async with session.get(self.user_info_url, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    response_text = await response.text()
                    raise ActronAirAuthError(
                        f"Failed to get user info. "
                        f"Status: {response.status}, "
                        f"Response: {response_text}."
                    )

    async def ensure_token_valid(self) -> str:
        """Ensure the token is valid, refreshing it if necessary.

        Returns:
            The current valid access token

        Raises:
            ActronAirAuthError: If token validation fails

        """
        if not self.is_token_valid:
            await self.refresh_access_token()

        if not self.access_token:
            raise ActronAirAuthError("Access token is not available")
        return self.access_token

    def set_tokens(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_in: int | None = None,
        token_type: str = "Bearer",
    ) -> None:
        """Set tokens manually (useful for restoring saved tokens).

        Args:
            access_token: The access token
            refresh_token: The refresh token (optional)
            expires_in: Token expiration time in seconds from now (optional)
            token_type: Token type (default: "Bearer")

        Raises:
            ValueError: If access_token is empty or expires_in is negative

        """
        if not access_token or not access_token.strip():
            raise ValueError("access_token cannot be empty")
        if expires_in is not None and expires_in < 0:
            raise ValueError("expires_in cannot be negative")

        self.access_token = access_token
        self.refresh_token = refresh_token if refresh_token else None
        self.token_type = token_type if token_type else "Bearer"

        if expires_in is not None:
            self.token_expiry = time.time() + expires_in
        else:
            # Default to 1 hour if not specified
            self.token_expiry = time.time() + 3600
