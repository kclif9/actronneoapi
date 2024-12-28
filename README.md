# ActronNeoAPI

The `ActronNeoAPI` library provides an interface to communicate with Actron Air Neo systems, enabling integration with Home Assistant or other platforms. This Python library offers methods for authentication, token management, and interacting with AC systems, zones, and settings.

---

## Features

- **Authentication**:
  - Pairing token and bearer token support.
  - Automatic token refresh handling.
- **System Information**:
  - Retrieve system details, statuses, and events.
- **Control Features**:
  - Set system modes (e.g., COOL, HEAT, AUTO, FAN).
  - Enable/disable zones.
  - Adjust fan modes and temperatures.

---

## Installation

```bash
pip install actron-neo-api
```

---

## Usage

### 1. Initialization

You must provide either an access token or username/password combination for authentication.

```python
from actron_neo_api import ActronNeoAPI

# Initialize with username and password
api = ActronNeoAPI(username="your_username", password="your_password")

# Or initialize with an existing access token
api = ActronNeoAPI(access_token="your_access_token")
```

### 2. Authentication

#### Request Pairing Token

Pairing tokens are used to generate bearer tokens.

```python
await api.request_pairing_token(device_name="MyDevice", device_unique_id="123456789")
```

#### Request Bearer Token

Use the pairing token to request a bearer token.

```python
await api.request_bearer_token()
```

#### Refresh Token

Automatically refresh tokens when they expire.

```python
await api.refresh_token()
```

### 3. Retrieve System Information

#### Get AC Systems

```python
systems = await api.get_ac_systems()
```

#### Get System Status

```python
status = await api.get_ac_status(serial_number="AC_SERIAL")
```

#### Get Events

```python
events = await api.get_ac_events(serial_number="AC_SERIAL", event_type="latest")
```

### 4. Control the System

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

---

## Logging

This library uses Python's built-in `logging` module for debug and error messages. Configure logging in your application to capture these logs:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

---

## Error Handling

The library defines custom exceptions for better error management:

- `ActronNeoAuthError`: Raised for authentication-related issues.
- `ActronNeoAPIError`: Raised for general API errors.

Example:

```python
try:
    systems = await api.get_ac_systems()
except ActronNeoAuthError as e:
    print(f"Authentication failed: {e}")
except ActronNeoAPIError as e:
    print(f"API error: {e}")
```

---

## Advanced Features

### Handle Token Expiration

The library automatically refreshes expired tokens using `_handle_request`.

### Proactive Token Refresh

Tokens are refreshed before they expire if `expires_in` is provided by the API.

---

## Contributing

Contributions are welcome! Please submit issues and pull requests on [GitHub](https://github.com/your-repo/actronneoapi).

1. Fork the repository.
2. Create a feature branch.
3. Submit a pull request.

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Disclaimer

This library is not affiliated with or endorsed by Actron Air. Use it at your own risk.
