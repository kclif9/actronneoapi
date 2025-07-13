"""
Home Assistant Integration Guide for ActronNeoAPI OAuth2

This document shows how to integrate ActronNeoAPI with Home Assistant using OAuth2 device code flow.
The OAuth2 implementation in the library follows Home Assistant's requirements for proper OAuth2 flows.
"""

## Sample Home Assistant config_flow.py

```python
"""Config flow for ActronAir using OAuth2 device code flow."""

import asyncio
import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

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
        self.verification_uri: Optional[str] = None
        self.verification_uri_complete: Optional[str] = None
        self.expires_in: Optional[int] = None
        self.interval: Optional[int] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            # User has completed authorization, check for token
            return await self._async_check_authorization()

        # Start OAuth2 device code flow
        try:
            self.api = ActronNeoAPI(use_oauth2=True)
            
            # Request device code
            device_code_response = await self.api.request_device_code()
            
            self.device_code = device_code_response["device_code"]
            self.user_code = device_code_response["user_code"]
            self.verification_uri = device_code_response["verification_uri"]
            self.verification_uri_complete = device_code_response["verification_uri_complete"]
            self.expires_in = device_code_response["expires_in"]
            self.interval = device_code_response["interval"]
            
            # Generate QR code if available
            qr_code_data_url = None
            if is_qr_code_available():
                qr_code_data_url = generate_qr_code(self.verification_uri_complete)
            
            # Show authorization form
            return self.async_show_form(
                step_id="user",
                description_placeholders={
                    "user_code": self.user_code,
                    "verification_uri": self.verification_uri,
                    "verification_uri_complete": self.verification_uri_complete,
                    "qr_code": qr_code_data_url or "",
                    "expires_minutes": str(self.expires_in // 60),
                },
            )
            
        except ActronNeoAuthError as err:
            _LOGGER.error("Failed to start OAuth2 flow: %s", err)
            return self.async_abort(reason="oauth2_error")
        except Exception as err:
            _LOGGER.error("Unexpected error: %s", err)
            return self.async_abort(reason="unknown")

    async def _async_check_authorization(self) -> FlowResult:
        """Check if the user has completed authorization."""
        try:
            # Poll for token
            token_data = await self.api.poll_for_token(self.device_code)
            
            if token_data is None:
                # Still waiting for authorization
                return self.async_show_form(
                    step_id="user",
                    errors={"base": "authorization_pending"},
                    description_placeholders={
                        "user_code": self.user_code,
                        "verification_uri": self.verification_uri,
                        "verification_uri_complete": self.verification_uri_complete,
                        "expires_minutes": str(self.expires_in // 60),
                    },
                )
            
            # Authorization successful, get user info
            user_info = await self.api.get_user_info()
            user_id = user_info.get("id")
            
            if user_id:
                await self.async_set_unique_id(user_id)
                self._abort_if_unique_id_configured()
            
            # Create config entry
            return self.async_create_entry(
                title="ActronAir",
                data={
                    "access_token": self.api.access_token,
                    "refresh_token": self.api.refresh_token_value,
                    "token_type": "Bearer",
                    "user_id": user_id,
                },
            )
            
        except ActronNeoAuthError as err:
            _LOGGER.error("Authorization failed: %s", err)
            return self.async_abort(reason="authorization_failed")
        except Exception as err:
            _LOGGER.error("Unexpected error during authorization: %s", err)
            return self.async_abort(reason="unknown")

    async def async_step_reauth(self, entry_data: Dict[str, Any]) -> FlowResult:
        """Handle reauthorization."""
        return await self.async_step_user()
```

## Sample Home Assistant strings.json

```json
{
  "config": {
    "step": {
      "user": {
        "title": "ActronAir OAuth2 Authorization",
        "description": "To connect your ActronAir account:\n\n1. Go to: {verification_uri}\n2. Enter code: **{user_code}**\n3. Or scan the QR code below\n4. Complete authorization within {expires_minutes} minutes\n\n{qr_code}\n\nClick **Submit** after completing authorization.",
        "data": {}
      }
    },
    "error": {
      "authorization_pending": "Authorization is still pending. Please complete the authorization process and try again.",
      "authorization_failed": "Authorization failed. Please try again.",
      "oauth2_error": "Failed to start OAuth2 flow. Please try again later.",
      "unknown": "An unexpected error occurred. Please try again."
    },
    "abort": {
      "already_configured": "Account is already configured",
      "authorization_failed": "Authorization failed",
      "oauth2_error": "Failed to start OAuth2 flow",
      "unknown": "Unknown error occurred"
    }
  }
}
```

## Sample Home Assistant __init__.py

```python
"""The ActronAir integration."""

import logging
from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from actron_neo_api import ActronNeoAPI, ActronNeoAuthError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["climate", "sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ActronAir from a config entry."""
    
    # Initialize API with OAuth2 and restored tokens
    api = ActronNeoAPI(use_oauth2=True)
    
    # Restore saved tokens
    api.set_oauth2_tokens(
        access_token=entry.data["access_token"],
        refresh_token=entry.data["refresh_token"],
        expires_in=3600  # Will be automatically refreshed as needed
    )
    
    try:
        # Test the connection
        systems = await api.get_ac_systems()
        await api.update_status()
        
        # Store API instance
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {
            "api": api,
            "systems": systems,
        }
        
        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        return True
        
    except ActronNeoAuthError as err:
        _LOGGER.error("Authentication failed: %s", err)
        # Trigger reauth flow
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "reauth"},
                data=entry.data,
            )
        )
        return False
    except Exception as err:
        _LOGGER.error("Failed to set up ActronAir: %s", err)
        return False


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # Close API connection
        api_data = hass.data[DOMAIN].pop(entry.entry_id)
        await api_data["api"].close()
    
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    _LOGGER.debug("Migrating from version %s", config_entry.version)
    
    # Migration logic here if needed
    
    return True
```

## Key Benefits of This Approach

1. **Compliant with Home Assistant Rules**: The OAuth2 flow is handled entirely within the ActronNeoAPI library, not in the Home Assistant integration.

2. **Simplified Integration**: Home Assistant just needs to call the library methods - no complex OAuth2 logic in the integration.

3. **Automatic Token Management**: The library handles token refresh automatically.

4. **QR Code Support**: Built-in QR code generation for better user experience.

5. **Proper Error Handling**: Clear error messages and proper flow control.

6. **Reauth Support**: Built-in support for reauthorization when tokens expire.

## Installation

Make sure to install the library with QR code support:

```bash
pip install actron-neo-api[qrcode]
```

Or add to your requirements.txt:

```
actron-neo-api
qrcode[pil]
```
