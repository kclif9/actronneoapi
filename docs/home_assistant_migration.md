# Home Assistant Integration Migration Guide

## Overview

This guide shows how to migrate from the complex OAuth2 implementation in your Home Assistant config flow to using the simplified ActronNeoAPI library with built-in OAuth2 support.

## Key Changes

### 1. Remove Complex OAuth2 Logic from Config Flow

**After (Simple):**
```python
# Simple library calls
from actron_neo_api import ActronNeoAPI, generate_qr_code, is_qr_code_available

# In your config flow:
async def async_step_user(self, user_input=None):
    if user_input is not None:
        return await self._check_authorization()

    # Start OAuth2 flow with library
    self.api = ActronNeoAPI(use_oauth2=True)
    device_code_response = await self.api.request_device_code()

    # Generate QR code with library
    qr_code = None
    if is_qr_code_available():
        qr_code = generate_qr_code(device_code_response["verification_uri_complete"])

    return self.async_show_form(step_id="user", ...)

async def _check_authorization(self):
    # Simple polling with library
    token_data = await self.api.poll_for_token(self.device_code)
    if token_data:
        user_info = await self.api.get_user_info()
        return self.async_create_entry(title="ActronAir", data=...)
    return self.async_show_form(step_id="user", errors={"base": "authorization_pending"})
```

### 2. Simplified Token Management

**After:**
```python
# Token refresh is handled automatically by the library
# Just initialize with saved tokens:
api = ActronNeoAPI(use_oauth2=True)
api.set_oauth2_tokens(
    access_token=entry.data["access_token"],
    refresh_token=entry.data["refresh_token"],
    expires_in=3600
)
# Library handles refresh automatically
```

### 3. Updated Dependencies

**requirements.txt:**
```
# Add to your Home Assistant integration requirements
actron-neo-api[qrcode]
```

### 4. Updated Config Flow

**config_flow.py:**
```python
"""Config flow for ActronAir using ActronNeoAPI OAuth2."""

import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from actron_neo_api import ActronNeoAPI, ActronNeoAuthError, generate_qr_code, is_qr_code_available

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ActronAirConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ActronAir."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.api: Optional[ActronNeoAPI] = None
        self.device_code: Optional[str] = None
        self.user_code: Optional[str] = None
        self.verification_uri_complete: Optional[str] = None

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return await self._async_check_authorization()

        try:
            # Initialize API with OAuth2
            self.api = ActronNeoAPI(use_oauth2=True)

            # Request device code
            device_code_response = await self.api.request_device_code()

            self.device_code = device_code_response["device_code"]
            self.user_code = device_code_response["user_code"]
            verification_uri = device_code_response["verification_uri"]
            self.verification_uri_complete = device_code_response["verification_uri_complete"]

            # Generate QR code
            qr_code_data_url = None
            if is_qr_code_available():
                qr_code_data_url = generate_qr_code(self.verification_uri_complete)

            return self.async_show_form(
                step_id="user",
                description_placeholders={
                    "user_code": self.user_code,
                    "verification_uri": verification_uri,
                    "verification_uri_complete": self.verification_uri_complete,
                    "qr_code": qr_code_data_url or "",
                },
            )

        except ActronNeoAuthError as err:
            _LOGGER.error("Failed to start OAuth2 flow: %s", err)
            return self.async_abort(reason="oauth2_error")

    async def _async_check_authorization(self) -> FlowResult:
        """Check if the user has completed authorization."""
        try:
            # Poll for token
            token_data = await self.api.poll_for_token(self.device_code)

            if token_data is None:
                return self.async_show_form(
                    step_id="user",
                    errors={"base": "authorization_pending"},
                )

            # Get user info and create entry
            user_info = await self.api.get_user_info()
            user_id = user_info.get("id")

            if user_id:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title="ActronAir",
                data={
                    "access_token": self.api.access_token,
                    "refresh_token": self.api.refresh_token_value,
                    "user_id": user_id,
                },
            )

        except ActronNeoAuthError as err:
            _LOGGER.error("Authorization failed: %s", err)
            return self.async_abort(reason="authorization_failed")
```

### 5. Updated Integration Setup

**__init__.py:**
```python
"""The ActronAir integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from actron_neo_api import ActronNeoAPI, ActronNeoAuthError

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ActronAir from a config entry."""

    # Initialize API with OAuth2 and restored tokens
    api = ActronNeoAPI(use_oauth2=True)
    api.set_oauth2_tokens(
        access_token=entry.data["access_token"],
        refresh_token=entry.data["refresh_token"],
        expires_in=3600  # Auto-refreshed as needed
    )

    try:
        # Test connection
        systems = await api.get_ac_systems()
        await api.update_status()

        # Store for use in platforms
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "systems": systems,
        }

        return True

    except ActronNeoAuthError:
        # Token expired, trigger reauth
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": "reauth"}, data=entry.data
            )
        )
        return False
```

## Testing

Test your integration with:

```python
# Test OAuth2 flow
async def test_oauth2():
    api = ActronNeoAPI(use_oauth2=True)
    device_code_response = await api.request_device_code()
    print(f"Go to: {device_code_response['verification_uri']}")
    print(f"Enter code: {device_code_response['user_code']}")

    # Poll for token (in real implementation, do this in a loop)
    token_data = await api.poll_for_token(device_code_response['device_code'])
    if token_data:
        user_info = await api.get_user_info()
        print(f"Success! User: {user_info}")
```
