# ActronNeoAPI
ActronNeoAPI is a Python library for interacting with Actron Air Neo API. It allows you to manage and monitor your Actron Air systems programmatically, including retrieving AC system status, events, and more.

## Features
Authentication: Authenticate with the Actron Air API using your account credentials.
AC System Management:
List all AC systems in your account.
Retrieve detailed status for a specific AC system.
Fetch system events, including latest, newer, or older events.
Fully asynchronous, built using aiohttp.
Installation
Install the library via pip:
`pip install actron-neo-api`

## Usage
1. Authentication
To authenticate with the Actron Air API, you need your username, password, a device name, and a unique device identifier.

2. Fetch AC Systems
Retrieve the list of AC systems associated with your account.

3. Get AC System Status
Get the full status of a specific AC system by its serial number.

4. Get AC System Events
Retrieve events for a specific AC system, including the latest, newer, or older events based on an event ID.

## Example Code
    import asyncio
    from actronneoapi import ActronNeoAPI, ActronNeoAuthError, ActronNeoAPIError

    async def main():
        username = "your_email@example.com"
        password = "your_password"
        device_name = "my_device"
        device_unique_id = "unique_device_id"

        api = ActronNeoAPI(username, password)

        try:
            # Step 1: Authenticate
            await api.request_pairing_token(device_name, device_unique_id)
            await api.request_bearer_token()

            # Step 2: Fetch AC systems
            systems = await api.get_ac_systems()
            print("AC Systems:", systems)

            # Get the serial number of the first system
            if systems:
                serial = systems[0].get("serial")
                if serial:
                    # Fetch system status
                    status = await api.get_ac_status(serial)
                    print(f"Status for {serial}:", status)

                    # Fetch latest events
                    events = await api.get_ac_events(serial, event_type="latest")
                    print(f"Latest events for {serial}:", events)
        except ActronNeoAuthError as auth_error:
            print(f"Authentication failed: {auth_error}")
        except ActronNeoAPIError as api_error:
            print(f"API error: {api_error}")
        except Exception as e:
            print(f"Unexpected error: {e}")

    # Run the async example
    asyncio.run(main())

## API Methods
### Authentication
request_pairing_token(device_name: str, device_unique_id: str)
Requests a pairing token using your Actron Neo credentials and device details.

request_bearer_token()
Exchanges the pairing token for a bearer token required for subsequent API calls.

### AC Systems
get_ac_systems()
Retrieves a list of all AC systems associated with your account.

### AC System Status
get_ac_status(serial_number: str)
Retrieves the full status of a specific AC system, including temperature, humidity, zone details, and more.

### AC System Events
get_ac_events(serial_number: str, event_type: str, event_id: str = None)
Fetches events for a specific AC system:
latest: Retrieves the latest events.
newer: Retrieves events newer than the provided event ID.
older: Retrieves events older than the provided event ID.

## Requirements
Python 3.8 or higher
aiohttp

## Installation Notes
Ensure you have access to the Actron Neo API by using valid credentials from your Actron Air account.

## License
This project is licensed under the MIT License. See the LICENSE file for details.

## Disclaimer
This is an unofficial library for the Actron Air API. It is not affiliated, endorsed, or supported by Actron Air. Use at your own risk.