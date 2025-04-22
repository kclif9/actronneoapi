import asyncio
import json
import logging
import os
from datetime import datetime

from actron_neo_api import ActronNeoAPI, ActronNeoAuthError, ActronNeoAPIError
from actron_neo_api.commands import CommandBuilder

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def example_modern_approach():
    """
    Example of using the ActronNeoAPI with the recommended approach.

    This demonstrates:
    - Async context manager for proper resource management
    - Strongly-typed data access
    - Command builder pattern
    - Leveraging the new architectural improvements
    """
    print("\n=== RECOMMENDED API USAGE ===\n")

    # Replace with your actual credentials
    username = ""
    password = ""
    device_name = "neo-example"
    device_unique_id = f"example-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    try:
        # Use async context manager for proper resource management
        async with ActronNeoAPI(username=username, password=password) as api:
            # Authentication
            print("Authenticating...")
            await api.request_pairing_token(device_name, device_unique_id)
            await api.refresh_token()
            print(f"Authentication successful!")
            print(f"Pairing token: {api.pairing_token[:10]}... (save this for future use)")

            # Get AC systems
            print("\nFetching AC systems...")
            systems = await api.get_ac_systems()

            if not systems:
                print("No AC systems found")
                return

            system = systems[0]
            serial = system.get("serial")
            print(f"Found system with serial: {serial}")

            # Update status to get system information through the state manager
            print("\nUpdating status cache...")
            await api.update_status()

            # Access the typed status model with proper system name
            status = api.state_manager.get_status(serial)

            if status and status.ac_system:
                system_name = status.ac_system.system_name
                print(f"System name: {system_name}")
            else:
                print("Could not retrieve system name from the typed model")

            # Access the typed status model
            print("\nAccessing the typed status model:")
            status = api.state_manager.get_status(serial)

            if status and status.user_aircon_settings:
                settings = status.user_aircon_settings
                print(f"System power: {'ON' if settings.is_on else 'OFF'}")
                print(f"Mode: {settings.mode}")
                print(f"Fan mode: {settings.fan_mode}")
                print(f"Cool setpoint: {settings.temperature_setpoint_cool_c}°C")
                print(f"Heat setpoint: {settings.temperature_setpoint_heat_c}°C")

                # Display master humidity value
                if status.master_info:
                    print(f"\nMaster controller humidity: {status.master_info.live_humidity_pc}%")

                # Zone information with typed access and accurate humidity
                print("\nZone information:")
                for i, zone in enumerate(status.remote_zone_info):
                    if zone.exists:
                        is_active = "ACTIVE" if zone.is_active(settings.enabled_zones, i) else "INACTIVE"
                        print(f"Zone {i}: {zone.title} - {is_active}")
                        print(f"  Temperature: {zone.live_temp_c}°C")
                        print(f"  Humidity: {zone.humidity}%")

            # Using the command builder directly
            print("\nDemonstrating the command builder:")

            # Example 1: Building a temperature command
            print("Setting temperature to 23°C in COOL mode...")
            temp_command = CommandBuilder.set_temperature(
                mode="COOL",
                temperature=23.0
            )
            await api.send_command(serial, temp_command)

            # Example 2: Enabling quiet mode
            print("Enabling quiet mode...")
            quiet_command = CommandBuilder.set_feature_mode("QuietModeEnabled", True)
            await api.send_command(serial, quiet_command)

            # Using convenience methods (which use the command builder internally)
            print("\nUsing convenience methods:")

            # Set system mode
            print("Setting system to HEAT mode...")
            await api.set_system_mode(serial, is_on=True, mode="HEAT")

            # Set fan mode
            print("Setting fan to LOW mode with continuous operation...")
            await api.set_fan_mode(serial, fan_mode="LOW", continuous=True)

            # Set zone
            if status and status.remote_zone_info:
                print("Enabling all zones...")
                for i, zone in enumerate(status.remote_zone_info):
                    if zone.exists:
                        await api.set_zone(serial, zone_number=i, is_enabled=True)

            # Get events (only if needed)
            print("\nFetching recent events...")
            events = await api.get_ac_events(serial, event_type="latest")

            # Update status again to see our changes
            print("\nUpdating status to see changes...")
            await api.update_status()

            # Display updated status
            print("Final system state:")
            updated_status = api.state_manager.get_status(serial)
            if updated_status and updated_status.user_aircon_settings:
                settings = updated_status.user_aircon_settings
                print(f"System power: {'ON' if settings.is_on else 'OFF'}")
                print(f"Mode: {settings.mode}")
                print(f"Fan mode: {settings.fan_mode}")

    except ActronNeoAuthError as auth_error:
        print(f"Authentication failed: {auth_error}")
    except ActronNeoAPIError as api_error:
        print(f"API error: {api_error}")
    except Exception as e:
        print(f"Unexpected error: {e}")

async def main():
    """Main function running the examples."""
    print("\nACTRON NEO API USAGE EXAMPLES")
    print("===========================\n")

    print("This example demonstrates the recommended way to use the ActronNeoAPI.")
    print("To run the example with your credentials, update the username and password in the code.")
    print("Then uncomment the example_modern_approach() call in the main() function.")

    await example_modern_approach()

if __name__ == "__main__":
    asyncio.run(main())
