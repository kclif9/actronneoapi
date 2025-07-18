"""
Comprehensive example demonstrating the ActronNeoAPI library.

This example shows:
1. OAuth2 device code flow authentication
2. System information retrieval
3. Status monitoring with typed models
4. Object-oriented control methods (optional)

Usage:
    python example.py

Environment Variables:
    ACTRON_ACCESS_TOKEN     - Saved access token to skip authentication
    ACTRON_REFRESH_TOKEN    - Saved refresh token to skip authentication
    ACTRON_DEMO_CONTROLS    - Set to 'true' to enable control demonstrations

The example will guide you through authentication and then display your AC system
information. Control demonstrations are disabled by default to avoid accidentally
changing your AC settings.
"""

import asyncio
import logging
import os
from actron_neo_api import ActronNeoAPI, ActronNeoAuthError, ActronNeoAPIError

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def oauth2_authentication_example():
    """
    Example of OAuth2 device code flow authentication.
    This is the first step to get your tokens.
    """
    print("\n=== OAUTH2 AUTHENTICATION FLOW ===\n")

    async with ActronNeoAPI() as api:
        try:
            # Step 1: Request device code
            logger.info("Requesting device code...")
            device_code_response = await api.request_device_code()

            device_code = device_code_response["device_code"]
            user_code = device_code_response["user_code"]
            verification_uri = device_code_response["verification_uri"]
            verification_uri_complete = device_code_response["verification_uri_complete"]
            expires_in = device_code_response["expires_in"]
            interval = device_code_response["interval"]

            # Step 2: Display instructions to user
            print("\n" + "="*60)
            print("OAUTH2 DEVICE CODE FLOW")
            print("="*60)
            print("1. Open this URL in your browser: %s" % verification_uri)
            print("2. Enter this code: %s" % user_code)
            print("3. Or use the complete URL: %s" % verification_uri_complete)
            print("4. Complete authorization within %d minutes" % (expires_in // 60))
            print("="*60)
            print("Waiting for authorization...")

            # Step 3: Poll for token
            token_data = None
            max_attempts = expires_in // interval

            for attempt in range(max_attempts):
                try:
                    token_data = await api.poll_for_token(device_code)
                    if token_data:
                        logger.info("Authorization successful!")
                        break
                    else:
                        logger.info("Authorization pending... (attempt %d/%d)", attempt + 1, max_attempts)
                        await asyncio.sleep(interval)

                except Exception as e:
                    logger.error("Error during polling: %s", e)
                    break

            if not token_data:
                logger.error("Authorization timed out or failed")
                return None, None

            # Return tokens for use in the main example
            access_token = api.access_token
            refresh_token = api.refresh_token_value

            print("\n" + "="*60)
            print("AUTHENTICATION SUCCESSFUL!")
            print("="*60)
            print("Access Token: %s..." % access_token[:20])
            print("Refresh Token: %s..." % refresh_token[:20])
            print("Save these tokens for future use!")
            print("="*60)

            return access_token, refresh_token

        except Exception as e:
            logger.error("OAuth2 authentication failed: %s", e)
            return None, None

async def api_usage_example(refresh_token: str):
    """
    Example of using the ActronNeoAPI with saved OAuth2 tokens.
    This demonstrates the full API capabilities.
    """
    print("\n=== API USAGE EXAMPLE ===\n")

    try:
        async with ActronNeoAPI() as api:
            # Set OAuth2 tokens from previous authentication
            logger.info("Setting OAuth2 tokens...")
            await api.set_oauth2_tokens(refresh_token)

            # Get user information
            logger.info("Getting user information...")
            user_info = await api.get_user_info()
            logger.info("Authenticated as: %s", user_info.get('name', 'Unknown'))

            # Get AC systems
            logger.info("Fetching AC systems...")
            systems = await api.get_ac_systems()
            logger.info("Found %d AC systems", len(systems))

            if not systems:
                logger.warning("No AC systems found in your account")
                return

            # Store systems for status updates
            api.systems = systems

            # Update status to get the latest data
            logger.info("Updating system status...")
            await api.update_status()

            # Work with the first system
            system = systems[0]
            serial = system.get("serial")
            name = system.get("name", "Unknown System")

            logger.info("Working with system: %s (Serial: %s)", name, serial)

            # Get the typed status object
            status = api.state_manager.get_status(serial)

            if not status:
                logger.error("Could not retrieve status for system %s", serial)
                return

            # Display current system information
            print("\n" + "="*60)
            print("SYSTEM INFORMATION")
            print("="*60)

            if status.ac_system:
                print("System Name: %s" % status.ac_system.system_name)
                print("Model: %s" % status.ac_system.master_wc_model)
                print("Firmware: %s" % status.ac_system.master_wc_firmware_version)
                print("Serial: %s" % status.ac_system.master_serial)

            # Display current settings
            if status.user_aircon_settings:
                settings = status.user_aircon_settings
                print("\nCURRENT SETTINGS:")
                print("Power: %s" % ('ON' if settings.is_on else 'OFF'))
                print("Mode: %s" % settings.mode)
                print("Fan Mode: %s" % settings.fan_mode)
                print("Continuous Fan: %s" % ('Enabled' if settings.continuous_fan_enabled else 'Disabled'))
                print("Cool Setpoint: %s°C" % settings.temperature_setpoint_cool_c)
                print("Heat Setpoint: %s°C" % settings.temperature_setpoint_heat_c)

                # Get current temperature from zones
                current_temp = None
                if status.remote_zone_info:
                    for zone in status.remote_zone_info:
                        if zone.live_temp_c is not None and zone.live_temp_c > 0:
                            current_temp = zone.live_temp_c
                            break
                        elif zone.peripheral_temperature is not None:
                            current_temp = zone.peripheral_temperature
                            break

                if current_temp is not None:
                    print("Current Temperature: %s°C" % current_temp)
                else:
                    print("Current Temperature: Not available")

                print("Quiet Mode: %s" % ('Enabled' if settings.quiet_mode_enabled else 'Disabled'))
                print("Turbo Mode: %s" % ('Enabled' if settings.turbo_mode_enabled else 'Disabled'))
                print("Away Mode: %s" % ('Enabled' if settings.away_mode else 'Disabled'))

            # Display zone information
            if status.remote_zone_info:
                print("\nZONE INFORMATION:")
                for i, zone in enumerate(status.remote_zone_info):
                    print("Zone %d (%s): %s" % (
                        i + 1,
                        zone.title,
                        'Enabled' if zone.is_active else 'Disabled'
                    ))
                    print("  Set Temperature Cool: %s°C" % zone.temperature_setpoint_cool_c)
                    print("  Set Temperature Heat: %s°C" % zone.temperature_setpoint_heat_c)

                    # Display actual temperature from zone or peripheral
                    if zone.live_temp_c is not None and zone.live_temp_c > 0:
                        print("  Current Temperature: %s°C" % zone.live_temp_c)
                    elif zone.peripheral_temperature is not None:
                        print("  Current Temperature: %s°C (sensor)" % zone.peripheral_temperature)
                    else:
                        print("  Current Temperature: Not available")

                    # Display humidity
                    if zone.humidity is not None and zone.humidity > 0:
                        print("  Current Humidity: %s%%" % zone.humidity)
                    else:
                        print("  Current Humidity: Not available")

                    # Display battery level if available
                    if zone.battery_level is not None:
                        print("  Sensor Battery: %s%%" % zone.battery_level)
                    else:
                        print("  Sensor Battery: Not available")

                    print("  Zone Position: %s%%" % zone.zone_position)

            print("="*60)

            # Demonstrate control capabilities
            print("\n=== DEMONSTRATING CONTROL CAPABILITIES ===\n")

            # Check if user wants to run control examples
            if os.environ.get("ACTRON_DEMO_CONTROLS", "").lower() == "true":
                await demonstrate_controls(api, status, serial)
            else:
                print("Control demonstrations are disabled by default.")
                print("Set ACTRON_DEMO_CONTROLS=true environment variable to enable.")
                print("\nThe following controls would be available:")
                print("- AC System control (power, mode, temperature)")
                print("- Fan control (speed, continuous mode)")
                print("- Zone control (enable/disable, temperature)")
                print("- Special modes (quiet, turbo, away)")

            print("\n=== EXAMPLE COMPLETE ===")
            print("Successfully demonstrated:")
            print("1. OAuth2 token authentication")
            print("2. System information retrieval")
            print("3. Status monitoring with typed models")
            print("4. Object-oriented API access")

    except ActronNeoAuthError as e:
        logger.error("Authentication error: %s", e)
        print("Authentication failed. Your tokens may have expired.")
        print("Please run the OAuth2 flow again to get new tokens.")
    except ActronNeoAPIError as e:
        logger.error("API error: %s", e)
    except Exception as e:
        logger.error("Unexpected error: %s", e)

async def demonstrate_controls(api, status, serial):
    """
    Demonstrate actual control operations.
    Only runs if explicitly enabled via environment variable.
    """
    print("Running control demonstrations...")
    print("WARNING: This will change your AC system settings!")

    try:
        # AC System Control
        if status.ac_system:
            print("\n--- AC System Control ---")

            # Set system to COOL mode
            logger.info("Setting system to COOL mode...")
            await status.ac_system.set_system_mode(mode="COOL")
            print("✓ System mode set to COOL")

            # Wait a moment for the change to take effect
            await asyncio.sleep(2)

        # Settings Control
        if status.user_aircon_settings:
            print("\n--- Settings Control ---")
            settings = status.user_aircon_settings

            # Set temperature to 23°C
            logger.info("Setting temperature to 23°C...")
            await settings.set_temperature(23.0)
            print("✓ Temperature set to 23°C")

            # Set fan mode to AUTO
            logger.info("Setting fan mode to AUTO...")
            await settings.set_fan_mode("AUTO")
            print("✓ Fan mode set to AUTO")

            # Enable quiet mode
            logger.info("Enabling quiet mode...")
            await settings.set_quiet_mode(enabled=True)
            print("✓ Quiet mode enabled")

            await asyncio.sleep(2)

        # Zone Control
        if status.remote_zone_info and len(status.remote_zone_info) > 0:
            print("\n--- Zone Control ---")

            # Enable the first zone
            first_zone = status.remote_zone_info[0]
            logger.info("Enabling zone %d (%s)...", first_zone.zone_number, first_zone.zone_name)
            await first_zone.enable(is_enabled=True)
            print("✓ Zone %d enabled" % first_zone.zone_number)

            # Set zone temperature to 22°C
            logger.info("Setting zone temperature to 22°C...")
            await first_zone.set_temperature(22.0)
            print("✓ Zone temperature set to 22°C")

            await asyncio.sleep(2)

        # Update status to show changes
        print("\n--- Updating Status ---")
        logger.info("Refreshing status to show changes...")
        await api.update_status()

        updated_status = api.state_manager.get_status(serial)
        if updated_status and updated_status.user_aircon_settings:
            settings = updated_status.user_aircon_settings
            print("✓ Updated settings:")
            print("  Power: %s" % ('ON' if settings.is_on else 'OFF'))
            print("  Mode: %s" % settings.mode)
            print("  Temperature: %s°C" % settings.temperature_setpoint_cool_c)
            print("  Fan Mode: %s" % settings.fan_mode)
            print("  Quiet Mode: %s" % ('Enabled' if settings.quiet_mode_enabled else 'Disabled'))

        print("\n✓ Control demonstrations completed successfully!")

    except Exception as e:
        logger.error("Error during control demonstration: %s", e)
        print("✗ Some control operations may have failed")

async def main():
    """
    Main example function that demonstrates both authentication and API usage.
    """
    print("=== ACTRON NEO API EXAMPLE ===")
    print("This example demonstrates OAuth2 authentication and API usage.")

    # Check if we have saved tokens in environment variables
    saved_access_token = os.environ.get("ACTRON_ACCESS_TOKEN")
    saved_refresh_token = os.environ.get("ACTRON_REFRESH_TOKEN")

    if saved_access_token and saved_refresh_token:
        print("\nUsing saved tokens from environment variables...")
        access_token = saved_access_token
        refresh_token = saved_refresh_token
    else:
        print("\nNo saved tokens found. Starting OAuth2 authentication flow...")
        access_token, refresh_token = await oauth2_authentication_example()

        if not access_token or not refresh_token:
            print("Authentication failed. Cannot continue with API example.")
            return

        print("\nTo skip authentication in future runs, set these environment variables:")
        print("export ACTRON_ACCESS_TOKEN='%s'" % access_token)
        print("export ACTRON_REFRESH_TOKEN='%s'" % refresh_token)

    # Run the API usage example
    await api_usage_example(refresh_token)

if __name__ == "__main__":
    asyncio.run(main())
