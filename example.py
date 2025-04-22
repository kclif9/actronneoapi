import asyncio
import json
from actron_neo_api import ActronNeoAPI, ActronNeoAuthError, ActronNeoAPIError

def truncate_json(data, level=1, max_level=2):
    if level > max_level:
        return "..."
    if isinstance(data, dict):
        return {k: truncate_json(v, level + 1, max_level) for k, v in data.items()}
    elif isinstance(data, list):
        return [truncate_json(item, level + 1, max_level) for item in data]
    else:
        return data

async def main():
    username = "example@example.com"
    password = "yourpassword"
    device_name = "actron-api"
    device_unique_id = "unique_device_id"

    api = ActronNeoAPI(username, password)

    try:
        # Step 1: Authenticate
        print("Authenticating")
        await api.request_pairing_token(device_name, device_unique_id)
        await api.refresh_token()

        # Step 2: Fetch AC systems
        cache = await api.get_user()
        truncated_cache = truncate_json(cache)
        json_formatted_str = json.dumps(truncated_cache, indent=2)
        print("User:", json_formatted_str)
        print("User ID:", cache["id"])
        #serial = "23c04269"

        # Step 3: Update the status cache
        #status = await api.update_status()
        #print("Status:", status)

        #print("Check status cache")
        #print("Current fan mode:", api.status[serial]["UserAirconSettings"]["FanMode"])

        # Update fan mode
        #print("Update fan mode to HIGH")
        #await api.set_fan_mode(serial, "HIGH")

        # Check status
        #print("Check status cache")
        #print("Current fan mode:", api.status[serial]["UserAirconSettings"]["FanMode"])

        # Refresh data
        #print("Refresh data")
        #await api.update_status()

        # Check status
        #print("Check status cache")
        #print("Current fan mode:", api.status[serial]["UserAirconSettings"]["FanMode"])

        #

        #await api.set_zone(unit['serial'], 5, True)

        #print("Local State:",api.status)

        #await api.get_updated_status(unit['serial'])

        #print("Local State:",api.status)
        #print("Latest event ID:",api.latest_event_id)

        #print("Running status update")
        #await api.get_updated_status(unit['serial'])
        #print("Latest event ID:",api.latest_event_id)

        # Parse systems data
        # print("Attempt to change temp")
        # await api.set_temperature(
        #    unit['serial'],
        #    mode="COOL",
        #    temperature=22,
        #    zone=1,
        # )
    except ActronNeoAuthError as auth_error:
        print(f"Authentication failed: {auth_error}")
    except ActronNeoAPIError as api_error:
        print(f"API error: {api_error}")
    except Exception as e:
        print(f"Unexpected error: {e}")

# Run the async example
asyncio.run(main())
