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
        await api.request_bearer_token()

        # Step 2: Fetch AC systems
        systems = await api.get_ac_systems()
        print("AC Systems:", systems)

        # Parse systems data
        if '_embedded' in systems and 'ac-system' in systems['_embedded']:
            for system in systems['_embedded']['ac-system']:
                serial = system.get('serial')
                description = system.get('description')
                print(f"System Found: Serial={serial}, Description={description}")

                # Fetch system status
                if serial:
                    status = await api.get_ac_status(serial)
                    print(f"Status for {serial}:", status)

                    # Fetch latest events
                    events = await api.get_ac_events(serial, event_type="latest")
                    print(f"Latest events for {serial}:", events)
        else:
            print("No AC systems found in the response.")
    except ActronNeoAuthError as auth_error:
        print(f"Authentication failed: {auth_error}")
    except ActronNeoAPIError as api_error:
        print(f"API error: {api_error}")
    except Exception as e:
        print(f"Unexpected error: {e}")

# Run the async example
asyncio.run(main())