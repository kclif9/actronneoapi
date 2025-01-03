import asyncio
from actron_neo_api import ActronNeoAPI, ActronNeoAuthError, ActronNeoAPIError


async def main():
    username = "example@example.com"
    password = "yourpassword"
    device_name = "actron-api"
    device_unique_id = "unique_device_id"

    api = ActronNeoAPI(username, password)

    try:
        # Step 1: Authenticate
        await api.request_pairing_token(device_name, device_unique_id)
        await api.refresh_token()

        # Step 2: Fetch AC systems
        systems = await api.get_ac_systems()
        unit = systems["_embedded"]["ac-system"][0]
        print("AC Systems:", systems)

        # Parse systems data
        print("Attempt to change temp")
        await api.set_temperature(
            unit['serial'],
            mode="COOL",
            temperature=22,
            zone=1,
        )
    except ActronNeoAuthError as auth_error:
        print(f"Authentication failed: {auth_error}")
    except ActronNeoAPIError as api_error:
        print(f"API error: {api_error}")
    except Exception as e:
        print(f"Unexpected error: {e}")

# Run the async example
asyncio.run(main())
