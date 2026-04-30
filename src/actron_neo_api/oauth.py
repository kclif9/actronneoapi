"""OAuth2 Device Code Flow authentication for Actron Air API."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import AsyncIterator, Final

import aiohttp

from .const import (
    HTTP_CONNECT_TIMEOUT,
    HTTP_TOTAL_TIMEOUT,
    MAX_ERROR_RESPONSE_LENGTH,
    OAUTH_CLIENT_ID,
    OAUTH_DEFAULT_EXPIRY,
    OAUTH_TOKEN_REFRESH_MARGIN,
)
from .exceptions import ActronAirAuthError
from .models import ActronAirDeviceCode, ActronAirToken, ActronAirUserInfo

_LOGGER = logging.getLogger(__name__)


class ActronAirOAuth2DeviceCodeAuth:
    """OAuth2 Device Code Flow authentication handler for Actron Air API.

    This class implements the OAuth2 device code flow which is suitable for
    devices with limited input capabilities or when QR code authentication
    is preferred.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str = OAUTH_CLIENT_ID,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the OAuth2 Device Code Flow handler.

        Args:
            base_url: Base URL for the Actron Air API
            client_id: OAuth2 client ID
            session: Optional externally-managed aiohttp session to reuse

        Raises:
            ValueError: If base_url or client_id are empty

        """
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be empty")
        if not client_id or not client_id.strip():
            raise ValueError("client_id cannot be empty")

        base_url = base_url.strip().rstrip("/")
        self.base_url: str = base_url
        self.client_id: Final[str] = client_id
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.token_type: str = "Bearer"
        self.token_expiry: float | None = None
        self.authenticated_platform: str | None = None  # Track which platform issued tokens
        self._session: aiohttp.ClientSession | None = session
        self._token_lock: asyncio.Lock = asyncio.Lock()

        # OAuth2 endpoints
        self.token_url: str = f"{self.base_url}/api/v0/oauth/token"
        self.authorize_url: str = f"{self.base_url}/authorize"
        self.device_auth_url: str = f"{self.base_url}/connect"
        self.user_info_url: str = f"{self.base_url}/api/v0/client/account"

    @property
    def is_token_valid(self) -> bool:
        """Check if the access token is valid and not expired."""
        return (
            self.access_token is not None
            and self.token_expiry is not None
            and time.monotonic() < self.token_expiry
        )

    @property
    def is_token_expiring_soon(self) -> bool:
        """Check if the token is expiring within the next 15 minutes."""
        return self.token_expiry is not None and time.monotonic() > (
            self.token_expiry - OAUTH_TOKEN_REFRESH_MARGIN
        )

    @property
    def authorization_header(self) -> dict[str, str]:
        """Get the authorization header using the current token."""
        if not self.access_token:
            raise ActronAirAuthError("No access token available")
        return {"Authorization": f"{self.token_type} {self.access_token}"}

    def set_session(self, session: aiohttp.ClientSession | None) -> None:
        """Set or replace the shared HTTP session.

        Args:
            session: aiohttp session to use, or None to revert to per-call sessions

        """
        self._session = session

    def update_base_url(self, base_url: str) -> None:
        """Update the base URL and derived endpoints in-place.

        Mutates the existing handler rather than requiring object
        replacement, so coroutines that hold a reference to this instance
        continue to see the updated endpoints.

        Args:
            base_url: New base URL for the Actron Air API

        Raises:
            ValueError: If base_url is empty

        """
        if not base_url or not base_url.strip():
            raise ValueError("base_url cannot be empty")

        base_url = base_url.strip().rstrip("/")
        self.base_url = base_url
        self.token_url = f"{self.base_url}/api/v0/oauth/token"
        self.authorize_url = f"{self.base_url}/authorize"
        self.device_auth_url = f"{self.base_url}/connect"
        self.user_info_url = f"{self.base_url}/api/v0/client/account"

    @contextlib.asynccontextmanager
    async def _get_session(self) -> AsyncIterator[aiohttp.ClientSession]:
        """Get an HTTP session, creating a temporary one if needed.

        Yields:
            An aiohttp.ClientSession to use for requests.

        """
        timeout = aiohttp.ClientTimeout(total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT)
        if self._session is not None and not self._session.closed:
            yield self._session
        else:
            session = aiohttp.ClientSession(timeout=timeout)
            try:
                yield session
            finally:
                await session.close()

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

        async with self._get_session() as session:
            try:
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
                            f"Response: {response_text[:MAX_ERROR_RESPONSE_LENGTH]}"
                        )
            except aiohttp.ClientError as e:
                raise ActronAirAuthError(f"Device code request failed: {e}") from e

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

        start_time = time.monotonic()
        current_interval = interval

        async with self._get_session() as session:
            while time.monotonic() - start_time < timeout:
                try:
                    async with session.post(
                        self.token_url, data=payload, headers=headers
                    ) as response:
                        data = await response.json()

                        if response.status == 200 and "access_token" in data:
                            # Success - store tokens under lock
                            async with self._token_lock:
                                self.access_token = data["access_token"]
                                self.refresh_token = data.get("refresh_token")
                                self.token_type = data.get("token_type", "Bearer")
                                self.authenticated_platform = self.base_url

                                raw_expires_in = data.get("expires_in", OAUTH_DEFAULT_EXPIRY)
                                try:
                                    expires_in = int(raw_expires_in)
                                except (TypeError, ValueError):
                                    expires_in = OAUTH_DEFAULT_EXPIRY
                                self.token_expiry = time.monotonic() + expires_in

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
                                f"Response: {response_text[:MAX_ERROR_RESPONSE_LENGTH]}."
                            )

                except aiohttp.ClientError as poll_err:
                    _LOGGER.debug("Poll request failed: %s", poll_err)
                    await asyncio.sleep(current_interval)
                    continue
                except (ValueError, KeyError, TypeError) as e:
                    raise ActronAirAuthError(f"Polling failed: {str(e)}") from e

        # Timeout reached
        return None

    async def refresh_access_token(self) -> tuple[str, float]:
        """Refresh the access token using the refresh token.

        Acquires ``_token_lock`` to serialise concurrent refresh attempts.
        Internal callers that already hold the lock should use
        :meth:`_refresh_access_token_unlocked` instead.

        Returns:
            Tuple of (access_token, monotonic_expiry_deadline) where the
            deadline is a :func:`time.monotonic` value. It is only valid
            within the current process and must not be persisted or
            converted to a wall-clock timestamp.

        Raises:
            ActronAirAuthError: If token refresh fails

        """
        async with self._token_lock:
            return await self._refresh_access_token_unlocked()

    async def _refresh_access_token_unlocked(self) -> tuple[str, float]:
        """Refresh the access token without acquiring ``_token_lock``.

        This is the real implementation; callers that already hold the lock
        (e.g. :meth:`ensure_token_valid`) call this directly to avoid
        deadlocking on the non-reentrant :class:`asyncio.Lock`.

        Returns:
            Tuple of (access_token, monotonic_expiry_deadline) where the
            deadline is a :func:`time.monotonic` value. It is only valid
            within the current process and must not be persisted or
            converted to a wall-clock timestamp.

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

        async with self._get_session() as session:
            try:
                async with session.post(self.token_url, data=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()

                        access_token = data.get("access_token")
                        if not access_token or not isinstance(access_token, str):
                            raise ActronAirAuthError("Access token missing or invalid in response")

                        # Update refresh token if provided
                        refresh_token = data.get("refresh_token")
                        token_type = data.get("token_type", "Bearer")
                        token_type = token_type if isinstance(token_type, str) else "Bearer"

                        expires_in_raw = data.get("expires_in", OAUTH_DEFAULT_EXPIRY)
                        try:
                            expires_in = (
                                int(expires_in_raw) if expires_in_raw else OAUTH_DEFAULT_EXPIRY
                            )
                        except (ValueError, TypeError):
                            expires_in = OAUTH_DEFAULT_EXPIRY

                        token_expiry = time.monotonic() + expires_in

                        self.access_token = access_token
                        if refresh_token and isinstance(refresh_token, str):
                            self.refresh_token = refresh_token
                        self.token_type = token_type
                        self.authenticated_platform = self.base_url
                        self.token_expiry = token_expiry

                        return access_token, token_expiry
                    else:
                        response_text = await response.text()
                        raise ActronAirAuthError(
                            f"Failed to refresh access token. "
                            f"Status: {response.status}, "
                            f"Response: {response_text[:MAX_ERROR_RESPONSE_LENGTH]}."
                        )
            except aiohttp.ClientError as e:
                raise ActronAirAuthError(f"Token refresh request failed: {e}") from e

    async def get_user_info(self) -> ActronAirUserInfo:
        """Get user information using the access token.

        Returns:
            User information model

        Raises:
            ActronAirAuthError: If user info request fails

        """
        # Ensure we have a valid access token
        await self.ensure_token_valid()

        headers = self.authorization_header

        async with self._get_session() as session:
            try:
                async with session.get(self.user_info_url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return ActronAirUserInfo.model_validate(data)
                    else:
                        response_text = await response.text()
                        raise ActronAirAuthError(
                            f"Failed to get user info. "
                            f"Status: {response.status}, "
                            f"Response: {response_text[:MAX_ERROR_RESPONSE_LENGTH]}."
                        )
            except aiohttp.ClientError as e:
                raise ActronAirAuthError(f"User info request failed: {e}") from e

    async def ensure_token_valid(self) -> str:
        """Ensure the token is valid, refreshing proactively if expiring soon.

        Uses double-check locking so that concurrent callers only trigger a
        single refresh.  When the token is still valid but a proactive refresh
        fails, the existing token is returned instead of raising.

        Returns:
            The current valid access token

        Raises:
            ActronAirAuthError: If token is expired and refresh fails

        """
        if self.is_token_valid and not self.is_token_expiring_soon:
            # is_token_valid guarantees access_token is not None
            assert self.access_token is not None
            return self.access_token

        async with self._token_lock:
            # Double-check after acquiring lock
            if not self.is_token_valid or self.is_token_expiring_soon:
                try:
                    await self._refresh_access_token_unlocked()
                except ActronAirAuthError:
                    if self.is_token_valid:
                        _LOGGER.warning(
                            "Proactive token refresh failed; using existing token (expires in %ds)",
                            int((self.token_expiry or 0) - time.monotonic()),
                        )
                    else:
                        raise

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

        This method is synchronous and performs all writes without yielding,
        so it is safe within a single-threaded asyncio event loop.  For
        thread-safe usage (e.g. from an executor), use :meth:`async_set_tokens`
        which acquires ``_token_lock``.

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
            self.token_expiry = time.monotonic() + expires_in
        else:
            # No expiry known — force a refresh on next use
            self.token_expiry = None

    async def async_set_tokens(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_in: int | None = None,
        token_type: str = "Bearer",
    ) -> None:
        """Set tokens under ``_token_lock`` for thread-safe usage.

        Acquires the token lock before delegating to :meth:`set_tokens`.
        Prefer this method when calling from a concurrent context or
        off the event-loop thread.

        Args:
            access_token: The access token
            refresh_token: The refresh token (optional)
            expires_in: Token expiration time in seconds from now (optional)
            token_type: Token type (default: "Bearer")

        Raises:
            ValueError: If access_token is empty or expires_in is negative

        """
        async with self._token_lock:
            self.set_tokens(access_token, refresh_token, expires_in, token_type)
