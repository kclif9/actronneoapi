"""
Home Assistant Integration Guide for ActronNeoAPI OAuth2

This document shows how to integrate ActronNeoAPI with Home Assistant using OAuth2 device code flow.
The OAuth2 implementation in the library follows Home Assistant's requirements for proper OAuth2 flows.
"""

## Sample Home Assistant config_flow.py

```python
"""Config flow for ActronAir using OAuth2 device code flow."""

import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from actron_neo_api import ActronNeoAPI, ActronNeoAuthError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class ActronAirConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ActronAir."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self.api: Optional[ActronNeoAPI] = None
        self.device_code: Optional[str] = None

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            # User clicked Submit, check for token
            token_data = await self.api.poll_for_token(self.device_code)

            if token_data is None:
                # Still waiting - show same form with error
                return self.async_show_form(
                    step_id="user",
                    errors={"base": "authorization_pending"},
                )

            # Success! Create the config entry
            return self.async_create_entry(
                title="ActronAir",
                data={
                    "refresh_token": self.api.refresh_token_value,
                },
            )

        # First time - start OAuth2 flow
        try:
            self.api = ActronNeoAPI()
            device_code_response = await self.api.request_device_code()
            self.device_code = device_code_response["device_code"]

            return self.async_show_form(
                step_id="user",
                description_placeholders={
                    "user_code": device_code_response["user_code"],
                    "verification_uri": device_code_response["verification_uri"],
                    "expires_minutes": str(device_code_response["expires_in"] // 60),
                },
            )

        except Exception as err:
            _LOGGER.error("OAuth2 flow failed: %s", err)
            return self.async_abort(reason="oauth2_error")

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
        "description": "1. Go to: {verification_uri}\n2. Enter code: **{user_code}**\n3. Complete authorization within {expires_minutes} minutes\n\nClick **Submit** after completing authorization.",
        "data": {}
      }
    },
    "error": {
      "authorization_pending": "Authorization is still pending. Please complete the authorization process and try again.",
      "oauth2_error": "Failed to start OAuth2 flow. Please try again later."
    },
    "abort": {
      "oauth2_error": "Failed to start OAuth2 flow"
    }
  }
}
```

## Sample Home Assistant __init__.py

```python
"""The ActronAir integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from actron_neo_api import ActronNeoAPI

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["climate"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ActronAir from a config entry."""

    # Initialize API and set refresh token
    api = ActronNeoAPI()
    api.set_oauth2_tokens(refresh_token=entry.data["refresh_token"])

    # Get systems and store API
    systems = await api.get_ac_systems()
    await api.update_status()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"api": api, "systems": systems}

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        api_data = hass.data[DOMAIN].pop(entry.entry_id)
        await api_data["api"].close()

    return unload_ok
```

## Key Benefits of This Approach

1. **Compliant with Home Assistant Rules**: The OAuth2 flow is handled entirely within the ActronNeoAPI library, not in the Home Assistant integration.

2. **Simplified Integration**: Home Assistant just needs to call the library methods - no complex OAuth2 logic in the integration.

3. **Automatic Token Management**: The library handles token refresh automatically.

4. **Proper Error Handling**: Clear error messages and proper flow control.

5. **Reauth Support**: Built-in support for reauthorization when tokens expire.

## Installation

Install the library:

```bash
pip install actron-neo-api
```

Or add to your requirements.txt:

```
actron-neo-api
```
