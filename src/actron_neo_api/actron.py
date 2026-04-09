"""Actron Air API client module."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import aiohttp

from .const import (
    BASE_URL_DEFAULT,
    BASE_URL_NIMBUS,
    BASE_URL_QUE,
    COMMAND_DEBOUNCE_SECONDS,
    HTTP_CONNECT_TIMEOUT,
    HTTP_TOTAL_TIMEOUT,
    MAX_ERROR_RESPONSE_LENGTH,
    OAUTH_CLIENT_ID,
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

_LOGGER = logging.getLogger(__name__)


class _PendingBatch:
    """A batch of set-settings commands being coalesced for a single system."""

    __slots__ = ("merged_command", "baseline_zones", "zone_overrides", "futures", "timer")

    def __init__(self, baseline_zones: list[bool] | None) -> None:
        """Initialise a pending batch.

        Args:
            baseline_zones: Current enabled-zones snapshot (for element-wise merging),
                or None if unavailable.

        """
        self.merged_command: dict[str, Any] = {"type": "set-settings"}
        self.baseline_zones = baseline_zones
        self.zone_overrides: dict[int, bool] = {}
        self.futures: list[asyncio.Future[None]] = []
        self.timer: asyncio.TimerHandle | None = None


class CommandCoalescer:
    """Coalesces ``set-settings`` commands per system over a debounce window.

    When multiple zone-enable or other set-settings commands arrive within
    ``debounce_seconds``, they are deep-merged into a single API call.
    ``EnabledZones`` lists are merged element-wise against the current state
    so concurrent zone toggles don't overwrite each other.
    """

    def __init__(
        self,
        send_fn: Callable[[str, dict[str, Any]], Awaitable[None]],
        state_manager: StateManager,
        debounce_seconds: float = COMMAND_DEBOUNCE_SECONDS,
    ) -> None:
        """Initialise the command coalescer.

        Args:
            send_fn: Async callable ``(serial, command_dict) -> None`` that sends
                a command to the API.
            state_manager: State manager used to snapshot current zone state.
            debounce_seconds: How long to wait for additional commands before
                flushing the batch.

        """
        self._send_fn = send_fn
        self._state_manager = state_manager
        self._debounce = debounce_seconds
        self._batches: dict[str, _PendingBatch] = {}

    @property
    def debounce_seconds(self) -> float:
        """Return the debounce window in seconds."""
        return self._debounce

    # -- public -----------------------------------------------------------------

    @staticmethod
    def _flush_task_done(task: asyncio.Task[None]) -> None:
        """Log unhandled errors from background flush tasks."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            _LOGGER.error("Command flush failed: %s", exc, exc_info=exc)

    async def enqueue(self, serial_number: str, command: dict[str, Any]) -> None:
        """Enqueue a ``set-settings`` command for coalescing.

        The returned coroutine completes only after the merged batch is sent.

        Args:
            serial_number: Target system serial number.
            command: Full command dict (``{"command": {…}}``).

        Raises:
            ActronAirAuthError: If authentication fails while sending the merged
                command.
            ActronAirAPIError: If the eventual API call fails.

        """
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()

        batch = self._get_or_create_batch(serial_number)
        self._merge_into_batch(batch, command)
        batch.futures.append(future)

        # Reset the debounce timer
        if batch.timer is not None:
            batch.timer.cancel()

        def _schedule_flush(sn: str = serial_number) -> None:
            task = asyncio.ensure_future(self._flush(sn))
            task.add_done_callback(self._flush_task_done)

        batch.timer = loop.call_later(self._debounce, _schedule_flush)

        await future

    async def flush_all(self) -> None:
        """Flush every pending batch immediately, cancelling debounce timers."""
        serials = list(self._batches.keys())
        for serial in serials:
            batch = self._batches.get(serial)
            if batch and batch.timer:
                batch.timer.cancel()
            await self._flush(serial)

    # -- internals --------------------------------------------------------------

    def _get_or_create_batch(self, serial_number: str) -> _PendingBatch:
        """Return the pending batch for *serial_number*, creating one if needed."""
        if serial_number not in self._batches:
            baseline = self._get_baseline_zones(serial_number)
            self._batches[serial_number] = _PendingBatch(baseline)
        return self._batches[serial_number]

    def _get_baseline_zones(self, serial_number: str) -> list[bool] | None:
        """Snapshot the current ``EnabledZones`` from the state manager."""
        status = self._state_manager.get_status(serial_number)
        if status and status.user_aircon_settings:
            return list(status.user_aircon_settings.enabled_zones)
        return None

    def _merge_into_batch(self, batch: _PendingBatch, command: dict[str, Any]) -> None:
        """Merge a command's keys into the pending batch."""
        inner = command.get("command", {})
        for key, value in inner.items():
            if key == "type":
                continue

            if (
                key == "UserAirconSettings.EnabledZones"
                and isinstance(value, list)
                and batch.baseline_zones is not None
            ):
                # Element-wise merge: diff this command's list against the
                # baseline to discover which index(es) the caller changed,
                # then record those as overrides.  Indices that match baseline
                # are left alone — they represent stale reads from the same
                # snapshot, NOT intentional reverts.  (Each concurrent caller
                # reads the same stale baseline, mutates one index, and sends
                # the full array back.)
                for i, val in enumerate(value):
                    if i < len(batch.baseline_zones) and val != batch.baseline_zones[i]:
                        batch.zone_overrides[i] = val
            else:
                # Scalar / non-list keys: last-write-wins
                batch.merged_command[key] = value

    async def _flush(self, serial_number: str) -> None:
        """Send the merged batch and resolve all waiting futures."""
        batch = self._batches.pop(serial_number, None)
        if batch is None:
            return

        # Build the final command dict
        final_inner: dict[str, Any] = dict(batch.merged_command)

        # Apply per-index zone overrides
        if batch.zone_overrides and batch.baseline_zones is not None:
            final_zones = list(batch.baseline_zones)
            for idx, val in batch.zone_overrides.items():
                if idx < len(final_zones):
                    final_zones[idx] = val
            final_inner["UserAirconSettings.EnabledZones"] = final_zones

        merged_command: dict[str, Any] = {"command": final_inner}

        try:
            await self._send_fn(serial_number, merged_command)
        except Exception as exc:
            for future in batch.futures:
                if not future.done():
                    future.set_exception(exc)
            return

        for future in batch.futures:
            if not future.done():
                future.set_result(None)


class ActronAirAPI:
    """Client for the Actron Air API with improved architecture.

    This client provides a modern, structured approach to interacting with
    the Actron Air API while maintaining compatibility with the previous interface.
    """

    def __init__(
        self,
        oauth2_client_id: str = OAUTH_CLIENT_ID,
        refresh_token: str | None = None,
        platform: Literal["neo", "que"] | None = None,
        session: aiohttp.ClientSession | None = None,
        debounce_seconds: float = COMMAND_DEBOUNCE_SECONDS,
    ):
        """Initialize the ActronAirAPI client with OAuth2 authentication.

        Args:
            oauth2_client_id: OAuth2 client ID for device code flow
            refresh_token: Optional refresh token for authentication
            platform: Platform to use ('neo', 'que', or None for auto-detect).
                If None, enables auto-detection with Neo as the initial platform.
            session: Optional externally-managed aiohttp session. When provided,
                the session is reused for all HTTP requests (including OAuth) and
                will NOT be closed by :meth:`close`.
            debounce_seconds: Debounce window for coalescing ``set-settings``
                commands (default: 0.1 s).  Set to 0 to disable coalescing.

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
        else:
            # Auto-detect with Neo as fallback (platform is None)
            resolved_base_url = BASE_URL_DEFAULT
            self._platform = PLATFORM_NEO
            self._auto_manage_base_url = True

        self.base_url = resolved_base_url
        self._oauth2_client_id = oauth2_client_id

        # Initialize OAuth2 authentication
        self.oauth2_auth = ActronAirOAuth2DeviceCodeAuth(
            resolved_base_url, oauth2_client_id, session=session
        )

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
        self._session: aiohttp.ClientSession | None = session
        self._external_session = session is not None
        self._session_lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()

        # Command coalescing
        self._coalescer = CommandCoalescer(
            send_fn=self._send_command_direct,
            state_manager=self.state_manager,
            debounce_seconds=debounce_seconds,
        )

    @property
    def platform(self) -> str:
        """Get the current platform being used.

        Returns:
            'neo' if using Nimbus platform, 'que' if using Que platform,

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

    def _set_base_url(self, base_url: str, platform: str) -> None:
        """Update the base URL and platform, preserving existing authentication tokens.

        Args:
            base_url: New base URL to switch to
            platform: Platform identifier ('neo', 'que')

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
        self.oauth2_auth = ActronAirOAuth2DeviceCodeAuth(
            base_url, self._oauth2_client_id, session=self._session
        )

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

        has_nx_gen = any(self._is_nx_gen_system(system) for system in systems)

        if has_nx_gen:
            target_base = BASE_URL_QUE
            target_platform = PLATFORM_QUE
        else:
            target_base = BASE_URL_NIMBUS
            target_platform = PLATFORM_NEO

        self._set_base_url(target_base, target_platform)

    async def _ensure_initialized(self) -> None:
        """Ensure the API is initialized with valid tokens.

        Uses double-check locking so concurrent first calls only
        initialise once.
        """
        if self._initialized:
            return

        async with self._init_lock:
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
                timeout = aiohttp.ClientTimeout(
                    total=HTTP_TOTAL_TIMEOUT, connect=HTTP_CONNECT_TIMEOUT
                )
                self._session = aiohttp.ClientSession(timeout=timeout)
                self._external_session = False
                self.oauth2_auth.set_session(self._session)
                return self._session
            return self._session

    async def close(self) -> None:
        """Close the API client and release resources.

        Note:
            If an external session was provided at construction, it will NOT be
            closed — the caller retains ownership.

        """
        await self._coalescer.flush_all()
        async with self._session_lock:
            if self._session and not self._session.closed and not self._external_session:
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

        # Prepare the request — clone headers to avoid mutating caller's dict
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        request_headers = dict(headers) if headers else {}
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
                    safe_text = response_text[:MAX_ERROR_RESPONSE_LENGTH]

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
                                f"Authentication failed and token refresh failed: {safe_text}"
                            ) from refresh_error

                    raise ActronAirAuthError(f"Authentication failed: {safe_text}")

                if not 200 <= response.status < 300:
                    response_text = await response.text()
                    raise ActronAirAPIError(
                        f"API request failed. "
                        f"Status: {response.status}, "
                        f"Response: {response_text[:MAX_ERROR_RESPONSE_LENGTH]}"
                    )

                if response.status == 204:
                    return {}

                result: dict[str, Any] = await response.json()
                return result
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

        ``set-settings`` commands are routed through the :class:`CommandCoalescer`
        so that concurrent zone toggles are merged into a single API call.
        All other command types are sent immediately.

        Args:
            serial_number: Serial number of the AC system
            command: Dictionary containing the command details

        Raises:
            ActronAirAPIError: If command fails or system not found

        """
        serial_number = serial_number.lower()

        inner = command.get("command", {})
        if inner.get("type") == "set-settings" and self._coalescer.debounce_seconds > 0:
            await self._coalescer.enqueue(serial_number, command)
        else:
            await self._send_command_direct(serial_number, command)

    async def _send_command_direct(self, serial_number: str, command: dict[str, Any]) -> None:
        """Send a command directly to the API without coalescing.

        Args:
            serial_number: Serial number of the AC system
            command: Dictionary containing the command details

        Raises:
            ActronAirAPIError: If command fails or system not found

        """
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
        if status is not None:
            # Process and store the status via the state manager so observers are notified
            self.state_manager.process_status_update(serial_number, status)

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
        """Get the latest event ID for each system.

        .. deprecated:: Event-based updates were removed in v0.5.
        """
        return {}
