"""Comprehensive example demonstrating the ActronAirAPI library.

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
from typing import Optional, Tuple

from actron_neo_api import ActronAirAPI, ActronAirAPIError, ActronAirAuthError, ActronAirStatus

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def oauth2_authentication_example() -> Tuple[Optional[str], Optional[str]]:
    """Example of OAuth2 device code flow authentication."""
    print("\n=== OAUTH2 AUTHENTICATION FLOW ===\n")

    async with ActronAirAPI() as api:
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
            print("\n" + "=" * 60)
            print("OAUTH2 DEVICE CODE FLOW")
            print("=" * 60)
            print(f"1. Open this URL in your browser: {verification_uri}")
            print(f"2. Enter this code: {user_code}")
            print(f"3. Or use the complete URL: {verification_uri_complete}")
            print(f"4. Complete authorization within {expires_in // 60} minutes")
            print("=" * 60)
            print("Waiting for authorization...")

            # Step 3: Poll for token (with automatic polling)
            try:
                token_data = await api.poll_for_token(
                    device_code, interval=interval, timeout=expires_in
                )
                if token_data:
                    logger.info("Authorization successful!")
                else:
                    logger.error("Authorization timed out")
                    return None, None
            except Exception as e:
                logger.error("Error during authorization: %s", e)
                return None, None

            # Return tokens for use in the main example
            access_token = api.access_token
            refresh_token = api.refresh_token_value

            print("\n" + "=" * 60)
            print("AUTHENTICATION SUCCESSFUL!")
            print("=" * 60)
            if access_token:
                print(f"Access Token: {access_token[:20]}...")
            if refresh_token:
                print(f"Refresh Token: {refresh_token[:20]}...")
            print("Save these tokens for future use!")
            print("=" * 60)

            return access_token, refresh_token

        except Exception as e:
            logger.error("OAuth2 authentication failed: %s", e, exc_info=True)
            raise


async def api_usage_example(refresh_token: str) -> None:
    """Example of using the ActronAirAPI with saved OAuth2 tokens."""
    print("\n=== API USAGE EXAMPLE ===\n")

    try:
        # Initialize with refresh token - token will be refreshed on first API call
        logger.info("Initializing API with refresh token...")
        api = ActronAirAPI(refresh_token=refresh_token)

        # Get user information
        logger.info("Getting user information...")
        user_info = await api.get_user_info()
        logger.info("Authenticated as: %s", user_info.get("name", "Unknown"))

        # Get AC systems
        logger.info("Fetching AC systems...")
        systems = await api.get_ac_systems()
        logger.info("Found %d AC systems", len(systems))

        if not systems:
            logger.warning("No AC systems found in your account")
            return

        # Update status to get the latest data (may fail if events API is not accessible)
        logger.info("Updating system status...")
        await api.update_status()

        # Work with the first system
        system = systems[0]
        serial = system.get("serial")
        family = system.get("family")
        name = system.get("name", "Unknown System")

        logger.info("Working with system: %s (Serial: %s)", name, serial)

        # Get the typed status object
        if not serial:
            logger.warning("System has no serial number, skipping")
            return
        status = api.state_manager.get_status(serial)

        if not status:
            logger.warning(
                "Status data not available for system %s (events API may not be accessible)", serial
            )
            print("\n" + "=" * 60)
            print("SYSTEM INFORMATION")
            print("=" * 60)
            print(f"System Name: {name}")
            print(f"Serial: {serial}")
            print(f"Family: {family}")
            print("Status: Events API not accessible - limited information available")
            print("=" * 60)
        else:
            # Display current system information
            print("\n" + "=" * 60)
            print("SYSTEM INFORMATION")
            print("=" * 60)

            if status.ac_system:
                print(f"System Name: {status.ac_system.system_name}")
                print(f"Model: {status.ac_system.master_wc_model}")
                print(f"Firmware: {status.ac_system.master_wc_firmware_version}")
                print(f"Serial: {status.ac_system.master_serial}")

            # Display current settings
            if status.user_aircon_settings:
                settings = status.user_aircon_settings
                print("\nCURRENT SETTINGS:")
                print(f"Power: {'ON' if settings.is_on else 'OFF'}")
                print(f"Mode: {settings.mode}")
                print(f"Fan Mode: {'Enabled' if settings.continuous_fan_enabled else 'Disabled'}")
                print(f"Cool Setpoint: {settings.temperature_setpoint_cool_c}°C")
                print(f"Heat Setpoint: {settings.temperature_setpoint_heat_c}°C")

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
                    print(f"Current Temperature: {current_temp}°C")
                else:
                    print("Current Temperature: Not available")

                print(f"Quiet Mode: {'Enabled' if settings.quiet_mode_enabled else 'Disabled'}")
                print(f"Turbo Mode: {'Enabled' if settings.turbo_mode_enabled else 'Disabled'}")
                print(f"Away Mode: {'Enabled' if settings.away_mode else 'Disabled'}")

            # Display zone information
            if status.remote_zone_info:
                print("\nZONE INFORMATION:")
                for i, zone in enumerate(status.remote_zone_info):
                    print(
                        f"Zone {i + 1} ({zone.title}): "
                        f"{'Enabled' if zone.is_active else 'Disabled'}"
                    )
                    print(f"  Set Temperature Cool: {zone.temperature_setpoint_cool_c}°C")
                    print(f"  Set Temperature Heat: {zone.temperature_setpoint_heat_c}°C")

                    # Display actual temperature from zone or peripheral
                    if zone.live_temp_c is not None and zone.live_temp_c > 0:
                        print(f"  Current Temperature: {zone.live_temp_c}°C")
                    elif zone.peripheral_temperature is not None:
                        print(f"  Current Temperature: {zone.peripheral_temperature}°C (sensor)")
                    else:
                        print("  Current Temperature: Not available")

                    # Display humidity
                    if zone.humidity is not None and zone.humidity > 0:
                        print(f"  Current Humidity: {zone.humidity}%")
                    else:
                        print("  Current Humidity: Not available")

                    # Display battery level if available
                    if zone.battery_level is not None:
                        print(f"  Sensor Battery: {zone.battery_level}%")
                    else:
                        print("  Sensor Battery: Not available")

                    print(f"  Zone Position: {zone.zone_position}%")
            print("=" * 60)

            # Demonstrate control capabilities
            print("\n=== DEMONSTRATING CONTROL CAPABILITIES ===\n")

            # Check if user wants to run control examples
            # if os.environ.get("ACTRON_DEMO_CONTROLS", "").lower() == "true":
            await demonstrate_controls(api, status, serial)
            # else:
            #    print("Control demonstrations are disabled by default.")
            #    print("Set ACTRON_DEMO_CONTROLS=true environment variable to enable.")
            #    print("\nThe following controls would be available:")
            #    print("- AC System control (power, mode, temperature)")
            #    print("- Fan control (speed, continuous mode)")
            #    print("- Zone control (enable/disable, temperature)")
            #    print("- Special modes (quiet, turbo, away)")

        print("\n=== EXAMPLE COMPLETE ===")
        print("Successfully demonstrated:")
        print("1. OAuth2 token authentication")
        print("2. System information retrieval")
        print("3. Status monitoring with typed models")
        print("4. Object-oriented API access")

        # Close the API session properly
        await api.close()

    except ActronAirAuthError as e:
        logger.error("Authentication error: %s", e)
        print("Authentication failed. Your tokens may have expired.")
        print("Please run the OAuth2 flow again to get new tokens.")
    except ActronAirAPIError as e:
        logger.error("API error: %s", e)
        raise
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        raise


async def demonstrate_controls(api: ActronAirAPI, status: ActronAirStatus, serial: str) -> None:
    """Demonstrate actual control operations."""
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
            logger.info("Enabling zone %d (%s)...", first_zone.zone_id, first_zone.title)
            await first_zone.enable(is_enabled=True)
            print(f"✓ Zone {first_zone.zone_id} enabled")

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
            print(f"  Power: {'ON' if settings.is_on else 'OFF'}")
            print(f"  Mode: {settings.mode}")
            print(f"  Temperature: {settings.temperature_setpoint_cool_c}°C")
            print(f"  Fan Mode: {settings.fan_mode}")
            print(f"  Quiet Mode: {'Enabled' if settings.quiet_mode_enabled else 'Disabled'}")
        print("✓ Control demonstrations completed successfully!")

    except Exception as e:
        logger.error("Error during control demonstration: %s", e, exc_info=True)
        raise


async def main() -> None:
    """Main example function that demonstrates both authentication and API usage."""
    print("=== ACTRON AIR API EXAMPLE ===")
    print("This example demonstrates OAuth2 authentication and API usage.")

    # Check if we have saved tokens in environment variables
    saved_access_token = os.environ.get("ACTRON_ACCESS_TOKEN")
    saved_refresh_token = os.environ.get("ACTRON_REFRESH_TOKEN")

    if saved_access_token and saved_refresh_token:
        print("\nUsing saved tokens from environment variables...")
        access_token: Optional[str] = saved_access_token
        refresh_token: Optional[str] = saved_refresh_token
    else:
        print("\nNo saved tokens found. Starting OAuth2 authentication flow...")
        access_token, refresh_token = await oauth2_authentication_example()

        if not access_token or not refresh_token:
            print("Authentication failed. Cannot continue with API example.")
            return

        print("\nTo skip authentication in future runs, set these environment variables:")
        print(f"export ACTRON_ACCESS_TOKEN='{access_token}'")
        print(f"export ACTRON_REFRESH_TOKEN='{refresh_token}'")

    # Run the API usage example
    # At this point we know refresh_token is not None due to the check above
    assert refresh_token is not None
    await api_usage_example(refresh_token)


if __name__ == "__main__":
    asyncio.run(main())
