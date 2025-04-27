from typing import Dict, List, Optional, Union, Any

class CommandBuilder:
    """
    Builder class for Actron Neo API commands.
    Provides a clear, consistent interface for creating command payloads.
    """

    @staticmethod
    def set_system_mode(is_on: bool, mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a command to set the AC system mode.

        Args:
            is_on: Boolean to turn the system on or off
            mode: Mode to set when the system is on ('AUTO', 'COOL', 'FAN', 'HEAT')

        Returns:
            Command dictionary
        """
        command = {
            "command": {
                "UserAirconSettings.isOn": is_on,
                "type": "set-settings"
            }
        }

        if is_on and mode:
            command["command"]["UserAirconSettings.Mode"] = mode

        return command

    @staticmethod
    def set_fan_mode(fan_mode: str, continuous: bool = False) -> Dict[str, Any]:
        """
        Create a command to set the fan mode.

        Args:
            fan_mode: The fan mode (e.g., "AUTO", "LOW", "MEDIUM", "HIGH")
            continuous: Whether to enable continuous fan mode

        Returns:
            Command dictionary
        """
        mode = fan_mode
        if continuous:
            mode = f"{fan_mode}+CONT"

        return {
            "command": {
                "UserAirconSettings.FanMode": mode,
                "type": "set-settings",
            }
        }

    @staticmethod
    def set_zone(zone_number: int, is_enabled: bool, current_zones: List[bool]) -> Dict[str, Any]:
        """
        Create a command to set a specific zone.

        Args:
            zone_number: Zone number to control (starting from 0)
            is_enabled: True to turn ON, False to turn OFF
            current_zones: Current state of all zones

        Returns:
            Command dictionary
        """
        # Create a copy of the current zones
        updated_zones = current_zones.copy()

        # Update the specific zone
        if zone_number < len(updated_zones):
            updated_zones[zone_number] = is_enabled

        return {
            "command": {
                "UserAirconSettings.EnabledZones": updated_zones,
                "type": "set-settings",
            }
        }

    @staticmethod
    def set_multiple_zones(zone_settings: Dict[int, bool]) -> Dict[str, Any]:
        """
        Create a command to set multiple zones at once.

        Args:
            zone_settings: Dictionary where keys are zone numbers and values are True/False

        Returns:
            Command dictionary
        """
        return {
            "command": {
                **{f"UserAirconSettings.EnabledZones[{zone}]": state
                   for zone, state in zone_settings.items()},
                "type": "set-settings",
            }
        }

    @staticmethod
    def set_temperature(mode: str, temperature: Union[float, Dict[str, float]],
                        zone: Optional[int] = None) -> Dict[str, Any]:
        """
        Create a command to set temperature.

        Args:
            mode: The mode ('COOL', 'HEAT', 'AUTO')
            temperature: The temperature to set (float or dict with 'cool' and 'heat' keys)
            zone: Zone number for zone-specific temperature, or None for common zone

        Returns:
            Command dictionary
        """
        command = {"command": {"type": "set-settings"}}

        if zone is None:  # Common zone
            if mode.upper() == "COOL":
                command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = temperature
            elif mode.upper() == "HEAT":
                command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = temperature
            elif mode.upper() == "AUTO":
                if isinstance(temperature, dict) and "cool" in temperature and "heat" in temperature:
                    command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] = temperature["cool"]
                    command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] = temperature["heat"]
        else:  # Specific zone
            if mode.upper() == "COOL":
                command["command"][f"RemoteZoneInfo[{zone}].TemperatureSetpoint_Cool_oC"] = temperature
            elif mode.upper() == "HEAT":
                command["command"][f"RemoteZoneInfo[{zone}].TemperatureSetpoint_Heat_oC"] = temperature
            elif mode.upper() == "AUTO":
                if isinstance(temperature, dict) and "cool" in temperature and "heat" in temperature:
                    command["command"][f"RemoteZoneInfo[{zone}].TemperatureSetpoint_Cool_oC"] = temperature["cool"]
                    command["command"][f"RemoteZoneInfo[{zone}].TemperatureSetpoint_Heat_oC"] = temperature["heat"]

        return command

    @staticmethod
    def set_feature_mode(feature: str, enabled: bool = False) -> Dict[str, Any]:
        """
        Create a command to enable/disable a feature mode.

        Args:
            feature: Feature name (e.g., "AwayMode", "QuietModeEnabled", "TurboMode.Enabled")
            enabled: True to enable, False to disable

        Returns:
            Command dictionary
        """
        return {
            "command": {
                f"UserAirconSettings.{feature}": enabled,
                "type": "set-settings",
            }
        }
