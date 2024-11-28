from typing import List

from .actron import Auth
from .const import Switch


class ActronNeoAPI:
    """Class to communicate with the ExampleHub API."""

    def __init__(self, auth: Auth):
        """Initialize the API and store the auth so we can make requests."""
        self.auth = auth
        
    async def async_get_switches(self) -> List[Switch]:
        """Return the switches."""
        resp = await self.auth.request("get", "switches")
        resp.raise_for_status()
        return [Switch(switch_data, self.auth) for switch_data in await resp.json()]

    async def async_get_switche(self, switch_id) -> Switch:
        """Return the switches."""
        resp = await self.auth.request("get", f"switch/{switch_id}")
        resp.raise_for_status()
        return Switch(await resp.json(), self.auth)