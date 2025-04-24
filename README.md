# ActronNeoAPI

The `ActronNeoAPI` library provides an interface to communicate with Actron Air Neo systems, enabling integration with Home Assistant or other platforms. This Python library offers methods for authentication, token management, and interacting with AC systems, zones, and settings.

---

## Features

- **Authentication**:
  - Pairing token and bearer token support.
  - Automatic and proactive token refresh.
  - Token expiration tracking.
- **System Information**:
  - Retrieve system details, statuses, and events.
  - Strongly-typed data models with Pydantic.
- **Control Features**:
  - Set system modes (e.g., COOL, HEAT, AUTO, FAN).
  - Enable/disable zones.
  - Adjust fan modes and temperatures.
- **Object-Oriented API**:
  - Call control methods directly on model objects.
  - Intuitive interface for settings and zone management.
  - More natural integration with object-oriented code.
- **Advanced State Management**:
  - Efficient incremental state updates.
  - Event-based state tracking.
  - Type-safe access to device properties.

---

## Installation

```bash
pip install actron-neo-api
```

---

## Quick Start

```python
import asyncio
from actron_neo_api import ActronNeoAPI

async def main():
    async with ActronNeoAPI(username="your_username", password="your_password") as api:
        # Authenticate
        await api.request_pairing_token(device_name="MyDevice", device_unique_id="123456789")
        await api.refresh_token()

        # Get systems and update status
        systems = await api.get_ac_systems()
        await api.update_status()

        # Get the status object
        serial = systems[0].get("serial")
        status = api.state_manager.get_status(serial)

        # Control your AC using object-oriented methods
        await status.user_aircon_settings.set_system_mode(is_on=True, mode="COOL")
        await status.user_aircon_settings.set_temperature(mode="COOL", temperature=23.0)

        # Control zones directly
        zone = status.remote_zone_info[0]
        await zone.enable(is_enabled=True)
        await zone.set_temperature(mode="COOL", temperature=22.0)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Authentication

```python
# Initialize the API
api = ActronNeoAPI(username="your_username", password="your_password")

# Request a pairing token (only needed once)
await api.request_pairing_token(device_name="MyDevice", device_unique_id="123456789")
print(f"Save this pairing token for future use: {api.pairing_token}")

# Or initialize with an existing pairing token
api = ActronNeoAPI(pairing_token="your_saved_pairing_token")

# Refresh the access token (needed for each session)
await api.refresh_token()
```

## System Information

```python
# Get all AC systems
systems = await api.get_ac_systems()
for system in systems:
    print(f"System: {system.get('name')} (Serial: {system.get('serial')})")

# Update status to get the latest data
await api.update_status()

# Access typed status for a system
serial = systems[0].get("serial")
status = api.state_manager.get_status(serial)

# Access system properties
if status and status.user_aircon_settings:
    print(f"Power: {'ON' if status.user_aircon_settings.is_on else 'OFF'}")
    print(f"Mode: {status.user_aircon_settings.mode}")
    print(f"Cool Setpoint: {status.user_aircon_settings.temperature_setpoint_cool_c}°C")
```

## Object-Oriented Control API (Recommended)

The object-oriented API allows you to call methods directly on the model objects for a more intuitive developer experience:

### System Settings Control

```python
# Get the status object
status = api.state_manager.get_status("AC_SERIAL")

# Turn the system on/off and set mode
await status.user_aircon_settings.set_system_mode(is_on=True, mode="COOL")

# Set temperature
await status.user_aircon_settings.set_temperature(mode="COOL", temperature=23.0)

# Set fan mode
await status.user_aircon_settings.set_fan_mode(fan_mode="HIGH", continuous=False)

# Enable/disable features
await status.user_aircon_settings.set_quiet_mode(enabled=True)
await status.user_aircon_settings.set_turbo_mode(enabled=False)
await status.user_aircon_settings.set_away_mode(enabled=False)
```

### Zone Control

```python
# Get the status object
status = api.state_manager.get_status("AC_SERIAL")

# Enable/disable a zone directly
zone = status.remote_zone_info[0]  # First zone
await zone.enable(is_enabled=True)

# Check zone temperature limits
print(f"Zone min temp: {zone.min_temp}°C")
print(f"Zone max temp: {zone.max_temp}°C")

# Enable/disable multiple zones
zones = status.remote_zone_info
for i, zone in enumerate(zones):
    if i == 0 or i == 2:  # Enable zones 0 and 2
        await zone.enable(is_enabled=True)
    else:  # Disable other zones
        await zone.enable(is_enabled=False)
```

## Alternative Control Method

While the object-oriented approach is recommended, you can also use these methods:

```python
# Set system mode
await api.set_system_mode(serial_number="AC_SERIAL", is_on=True, mode="COOL")

# Set temperature
await api.set_temperature(serial_number="AC_SERIAL", mode="COOL", temperature=24.0)

# Set fan mode
await api.set_fan_mode(serial_number="AC_SERIAL", fan_mode="HIGH", continuous=False)

# Enable/disable a zone
await api.set_zone(serial_number="AC_SERIAL", zone_number=0, is_enabled=True)

# Enable/disable multiple zones
zone_settings = {0: True, 1: False}
await api.set_multiple_zones(serial_number="AC_SERIAL", zone_settings=zone_settings)
```

---

## Error Handling

```python
from actron_neo_api import ActronNeoAPI, ActronNeoAuthError, ActronNeoAPIError

try:
    async with ActronNeoAPI(username="user", password="pass") as api:
        await api.refresh_token()
        # API operations...
except ActronNeoAuthError as e:
    print(f"Authentication error: {e}")
except ActronNeoAPIError as e:
    print(f"API error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

---

## Logging

```python
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("actron_neo_api").setLevel(logging.DEBUG)  # For more detailed logging
```

---

## Contributing

Contributions are welcome! Please submit issues and pull requests on [GitHub](https://github.com/kclif9/actronneoapi).

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Disclaimer

This library is not affiliated with or endorsed by Actron Air. Use it at your own risk.
