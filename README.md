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

## Usage

### Recommended Approach: Using Context Manager

For proper resource management and to leverage the full power of the API, use the async context manager pattern:

```python
from actron_neo_api import ActronNeoAPI

async with ActronNeoAPI(username="your_username", password="your_password") as api:
    # Authenticate
    await api.request_pairing_token(device_name="MyDevice", device_unique_id="123456789")
    await api.refresh_token()

    # API operations
    systems = await api.get_ac_systems()
    # Resources automatically cleaned up when leaving this block
```

### Authentication

#### Request Pairing Token

Pairing tokens are used to generate access tokens. Store this token for future sessions.

```python
await api.request_pairing_token(device_name="MyDevice", device_unique_id="123456789")
print(f"Save this pairing token for future use: {api.pairing_token}")
```

#### Refresh Token

The library handles token management automatically, but you can manually refresh when needed:

```python
await api.refresh_token()
```

### System Information

#### Get AC Systems

```python
systems = await api.get_ac_systems()
for system in systems:
    print(f"System: {system.get('name')} (Serial: {system.get('serial')})")
```

#### Update Status

Update the local state cache for all systems:

```python
await api.update_status()
```

#### Access System Status

```python
serial_number = "AC_SERIAL"

# Retrieve updated status
status = api.state_manager.get_status(serial_number)

# Access typed properties
if status and status.user_aircon_settings:
    print(f"Power: {'ON' if status.user_aircon_settings.is_on else 'OFF'}")
    print(f"Mode: {status.user_aircon_settings.mode}")
    print(f"Fan Mode: {status.user_aircon_settings.fan_mode}")
    print(f"Cool Setpoint: {status.user_aircon_settings.temperature_setpoint_cool_c}°C")
```

### Control Systems

#### Set System Mode

```python
await api.set_system_mode(serial_number="AC_SERIAL", is_on=True, mode="COOL")
```

#### Set Fan Mode

```python
await api.set_fan_mode(serial_number="AC_SERIAL", fan_mode="HIGH", continuous=False)
```

#### Adjust Temperature

```python
await api.set_temperature(serial_number="AC_SERIAL", mode="COOL", temperature=24.0)
```

#### Manage Zones

Enable or disable specific zones:

```python
await api.set_zone(serial_number="AC_SERIAL", zone_number=0, is_enabled=True)
```

Enable or disable multiple zones:

```python
zone_settings = {
    0: True,  # Enable zone 0
    1: False, # Disable zone 1
}
await api.set_multiple_zones(serial_number="AC_SERIAL", zone_settings=zone_settings)
```

### Advanced: Working with Typed Models

```python
# Update status to get the latest data
await api.update_status()

# Access typed status for a system
serial = "AC_SERIAL"
status = api.state_manager.get_status(serial)

if status:
    # Access user settings with type information
    if status.user_aircon_settings:
        cool_temp = status.user_aircon_settings.temperature_setpoint_cool_c
        print(f"Cooling setpoint: {cool_temp}°C")

    # Iterate through zones with typed access
    for i, zone in enumerate(status.remote_zone_info):
        if zone.exists:
            print(f"Zone {i}: {zone.title}")
            print(f"  Temperature: {zone.live_temp_c}°C")
            print(f"  Humidity: {zone.live_humidity_pc}%")
```

### Advanced: Command Building

For more control, you can build commands directly:

```python
from actron_neo_api.commands import CommandBuilder

# Create a temperature command
command = CommandBuilder.set_temperature(
    mode="COOL",
    temperature=23.5,
    zone=1  # For a specific zone
)

# Send the command manually
await api.send_command(serial_number, command)
```

---

## Logging

Configure logging to monitor the API operations:

```python
import logging
logging.basicConfig(level=logging.INFO)

# For more detailed logging during development
logging.getLogger("actron_neo_api").setLevel(logging.DEBUG)
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

## Legacy Code Support

> **Note**: While the library maintains backward compatibility with the original API design, we recommend using the updated approach shown above. The legacy patterns are deprecated and may be removed in future versions.

---

## Contributing

Contributions are welcome! Please submit issues and pull requests on [GitHub](https://github.com/kclif9/actronneoapi).

1. Fork the repository.
2. Create a feature branch.
3. Submit a pull request.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Disclaimer

This library is not affiliated with or endorsed by Actron Air. Use it at your own risk.
