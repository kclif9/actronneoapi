import aiohttp
from .exceptions import ActronNeoAuthError, ActronNeoAPIError

class ActronNeoAPI:
    def __init__(self, username: str, password: str, base_url: str = "https://nimbus.actronair.com.au"):
        """
        Initialize the ActronNeoAPI client.
        """
        self.username = username
        self.password = password
        self.base_url = base_url
        self.pairing_token = None
        self.access_token = None
        
    async def request_pairing_token(self, device_name: str, device_unique_id: str, client: str = "ios"):
        """
        Request a pairing token using the user's credentials and device details.
        """
        url = f"{self.base_url}/api/v0/client/user-devices"
        payload = {
            "username": self.username,
            "password": self.password,
            "client": client,
            "deviceName": device_name,
            "deviceUniqueIdentifier": device_unique_id,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.pairing_token = data.get("pairingToken")
                    if not self.pairing_token:
                        raise ActronNeoAuthError("Pairing token missing in response.")
                else:
                    raise ActronNeoAuthError(
                        f"Failed to request pairing token. Status: {response.status}, Response: {await response.text()}"
                    )

    async def request_bearer_token(self):
        """
        Use the pairing token to request a bearer token.
        """
        if not self.pairing_token:
            raise ActronNeoAuthError("Pairing token is required to request a bearer token.")

        url = f"{self.base_url}/api/v0/oauth/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.pairing_token,
            "client_id": "app",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=payload, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data.get("access_token")
                    if not self.access_token:
                        raise ActronNeoAuthError("Access token missing in response.")
                else:
                    raise ActronNeoAuthError(
                        f"Failed to request bearer token. Status: {response.status}, Response: {await response.text()}"
                    )


    async def get_ac_systems(self):
        """
        Retrieve all AC systems in the customer account.
        """
        if not self.access_token:
            raise ActronNeoAuthError("Authentication required before fetching AC systems.")

        url = f"{self.base_url}/api/v0/client/ac-systems?includeNeo=true"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    systems = await response.json()
                    return systems  # List of AC systems
                else:
                    raise ActronNeoAPIError(
                        f"Failed to fetch AC systems. Status: {response.status}, Response: {await response.text()}"
                    )

    async def get_ac_status(self, serial_number: str):
        """
        Retrieve the full status of a specific AC system by serial number.
        """
        if not self.access_token:
            raise ActronNeoAuthError("Authentication required before fetching AC system status.")

        url = f"{self.base_url}/api/v0/client/ac-systems/status/latest?serial={serial_number}"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    status = await response.json()
                    return status  # Full status of the AC system
                else:
                    raise ActronNeoAPIError(
                        f"Failed to fetch status for AC system {serial_number}. Status: {response.status}, Response: {await response.text()}"
                    )

    async def get_ac_events(self, serial_number: str, event_type: str = "latest", event_id: str = None):
        """
        Retrieve events for a specific AC system.
        
        :param serial_number: Serial number of the AC system.
        :param event_type: 'latest', 'newer', or 'older' for the event query type.
        :param event_id: The event ID for 'newer' or 'older' event queries.
        """
        if not self.access_token:
            raise ActronNeoAuthError("Authentication required before fetching AC system events.")

        if event_type == "latest":
            url = f"{self.base_url}/api/v0/client/ac-systems/events/latest?serial={serial_number}"
        elif event_type == "newer" and event_id:
            url = f"{self.base_url}/api/v0/client/ac-systems/events/newer?serial={serial_number}&newerThanEventId={event_id}"
        elif event_type == "older" and event_id:
            url = f"{self.base_url}/api/v0/client/ac-systems/events/older?serial={serial_number}&olderThanEventId={event_id}"
        else:
            raise ValueError("Invalid event_type or missing event_id for 'newer'/'older' event queries.")

        headers = {"Authorization": f"Bearer {self.access_token}"}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    events = await response.json()
                    return events  # Events of the AC system
                else:
                    raise ActronNeoAPIError(
                        f"Failed to fetch events for AC system {serial_number}. Status: {response.status}, Response: {await response.text()}"
                    )


    async def send_command(self, serial_number: str, command: dict):
        """
        Send a command to the specified AC system.

        :param serial_number: Serial number of the AC system.
        :param command: Dictionary containing the command details.
        """
        if not self.access_token:
            raise ActronNeoAuthError("Authentication required before sending commands.")

        url = f"{self.base_url}/api/v0/client/ac-systems/cmds/send?serial={serial_number}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=command, headers=headers) as response:
                if response.status == 200:
                    return await response.json()  # Success response
                else:
                    raise ActronNeoAPIError(
                        f"Failed to send command. Status: {response.status}, Response: {await response.text()}"
                    )

    async def set_system_mode(self, serial_number: str, is_on: bool, mode: str = None):
        """
        Convenience method to set the AC system mode.

        :param serial_number: Serial number of the AC system.
        :param is_on: Boolean to turn the system on or off.
        :param mode: Mode to set when the system is on. Options are: 'AUTO', 'COOL', 'FAN', 'HEAT'. Default is None.
        """
        command = {
            "command": {
                "UserAirconSettings.isOn": is_on,
                "type": "set-settings"
            }
        }

        if is_on and mode:
            command["command"]["UserAirconSettings.Mode"] = mode

        return await self.send_command(serial_number, command)