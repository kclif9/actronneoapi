import asyncio
import json
import logging
import os
from datetime import datetime

from actron_neo_api import ActronNeoAPI, ActronNeoAuthError, ActronNeoAPIError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def example_modern_approach():
    """
    Example of using the ActronNeoAPI with the recommended object-oriented approach.

    This demonstrates:
    - Async context manager for proper resource management
    - Strongly-typed data access
    - Object-oriented command methods for intuitive control
    - Leveraging the new architectural improvements
    """
    print("\n=== RECOMMENDED API USAGE ===\n")

    # Replace with your actual credentials
    username = os.environ.get("ACTRON_USERNAME")
    password = os.environ.get("ACTRON_PASSWORD")
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

                # Get system information using the AC system object
                print("\nGetting system information:")
                print(f"Model: {status.ac_system.master_wc_model}")
                print(f"Firmware: {status.ac_system.master_wc_firmware_version}")

                try:
                    outdoor_unit_model = await status.ac_system.get_outdoor_unit_model()
                    print(f"Outdoor unit model: {outdoor_unit_model}")
                except Exception as e:
                    print(f"Could not get outdoor unit model: {e}")
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
                print(f"Continuous fan mode: {'Enabled' if settings.continuous_fan_enabled else 'Disabled'}")
                print(f"Base fan mode: {settings.base_fan_mode}")
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
                        print(f"  Min Temp: {zone.min_temp}°C")
                        print(f"  Max Temp: {zone.max_temp}°C")

            # Object-oriented approach using commands directly on models
            print("\nDemonstrating the object-oriented API:")

            # Turn on the system and set mode using AC system object
            print("Setting the system to COOL mode via AC system object...")
            try:
                await status.ac_system.set_system_mode("COOL")
                print("System mode set successfully")
            except Exception as e:
                print(f"Could not set system mode: {e}")

            # Setting temperature directly from the settings object
            print("\nSettings Object Control:")
            print("Setting temperature to 23°C...")
            await status.user_aircon_settings.set_temperature(23.0)

            # Setting fan mode directly (preserves continuous mode setting)
            print("Setting fan mode to HIGH...")
            await status.user_aircon_settings.set_fan_mode("HIGH")

            # Toggling continuous fan mode
            print("Enabling continuous fan mode...")
            await status.user_aircon_settings.set_continuous_mode(enabled=True)

            print("Disabling continuous fan mode...")
            await status.user_aircon_settings.set_continuous_mode(enabled=False)

            # Enable/disable features
            print("Enabling quiet mode...")
            await status.user_aircon_settings.set_quiet_mode(enabled=True)

            print("Disabling turbo mode...")
            await status.user_aircon_settings.set_turbo_mode(enabled=False)

            # Working with zones directly
            print("\nZone Object Control:")
            if status and status.remote_zone_info:
                # Enable all zones
                print("Managing zones:")
                for i, zone in enumerate(status.remote_zone_info):
                    if zone.exists:
                        print(f"Enabling zone '{zone.title}'...")
                        await zone.enable(is_enabled=True)

                # Set temperature for first zone
                if status.remote_zone_info[0].exists:
                    zone = status.remote_zone_info[0]
                    print(f"Setting temperature for zone '{zone.title}' to 22°C...")
                    await zone.set_temperature(22.0)

            # Update status using the AC system object
            print("\nUpdating status for this specific AC system...")
            try:
                updated_status = await status.ac_system.update_status()
                if updated_status:
                    print("Status updated successfully")
                else:
                    print("Could not update status")
            except Exception as e:
                print(f"Error updating status: {e}")

                # Fall back to regular update
                print("Falling back to regular update...")
                await api.update_status()

            # Demonstrate turning the system off with the new "OFF" mode
            print("\nTurning off the system using OFF mode...")
            try:
                await status.ac_system.set_system_mode("OFF")
                print("System turned off successfully")
            except Exception as e:
                print(f"Could not turn off system: {e}")

            # Display updated status
            print("\nFinal system state:")
            updated_status = api.state_manager.get_status(serial)
            if updated_status and updated_status.user_aircon_settings:
                settings = updated_status.user_aircon_settings
                print(f"System power: {'ON' if settings.is_on else 'OFF'}")
                print(f"Mode: {settings.mode}")
                print(f"Fan mode: {settings.fan_mode}")
                print(f"Continuous fan mode: {'Enabled' if settings.continuous_fan_enabled else 'Disabled'}")
                print(f"Base fan mode: {settings.base_fan_mode}")
                print(f"Cool setpoint: {settings.temperature_setpoint_cool_c}°C")
                print(f"Quiet mode: {'Enabled' if settings.quiet_mode_enabled else 'Disabled'}")
                print(f"Turbo mode: {'Enabled' if settings.turbo_enabled else 'Disabled'}")

                # Show zone information after updates
                print("\nFinal zone information:")
                for i, zone in enumerate(updated_status.remote_zone_info):
                    if zone.exists:
                        is_active = "ACTIVE" if zone.is_active(settings.enabled_zones, i) else "INACTIVE"
                        print(f"Zone {i}: {zone.title} - {is_active}")
                        print(f"  Temperature: {zone.live_temp_c}°C")
                        print(f"  Cool setpoint: {zone.temperature_setpoint_cool_c}°C")

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

    print("This example demonstrates the recommended object-oriented way to use the ActronNeoAPI.")
    print("To run the example with your credentials, update the username and password in the code.")

    await example_modern_approach()

if __name__ == "__main__":
    asyncio.run(main())
