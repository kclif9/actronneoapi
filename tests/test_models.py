"""Simple focused tests for settings and zone models."""

from unittest.mock import MagicMock

import pytest

from actron_neo_api.models.settings import ActronAirUserAirconSettings
from actron_neo_api.models.zone import ActronAirPeripheral, ActronAirZone


class TestUserAirconSettings:
    """Test ActronAirUserAirconSettings properties and commands."""

    def test_turbo_supported_with_dict(self):
        """Test turbo_supported when turbo_mode is a dict with Supported key."""
        settings = ActronAirUserAirconSettings(TurboMode={"Supported": True, "Enabled": False})
        assert settings.turbo_supported is True

    def test_turbo_supported_dict_no_supported_key(self):
        """Test turbo_supported when dict doesn't have Supported key."""
        settings = ActronAirUserAirconSettings(turbo_mode_enabled={"Enabled": False})
        assert settings.turbo_supported is False

    def test_turbo_supported_with_bool(self):
        """Test turbo_supported when turbo_mode is a bool."""
        settings = ActronAirUserAirconSettings(turbo_mode_enabled=True)
        assert settings.turbo_supported is False

    def test_turbo_enabled_with_dict(self):
        """Test turbo_enabled when turbo_mode is a dict."""
        settings = ActronAirUserAirconSettings(TurboMode={"Enabled": True})
        assert settings.turbo_enabled is True

    def test_turbo_enabled_with_bool(self):
        """Test turbo_enabled when turbo_mode is a bool."""
        settings = ActronAirUserAirconSettings(TurboMode=True)
        assert settings.turbo_enabled is True

    def test_continuous_fan_enabled_with_plus(self):
        """Test continuous_fan_enabled with +CONT."""
        settings = ActronAirUserAirconSettings(FanMode="AUTO+CONT")
        assert settings.continuous_fan_enabled is True

    def test_continuous_fan_enabled_with_dash(self):
        """Test continuous_fan_enabled with -CONT."""
        settings = ActronAirUserAirconSettings(FanMode="LOW-CONT")
        assert settings.continuous_fan_enabled is True

    def test_continuous_fan_enabled_without_cont(self):
        """Test continuous_fan_enabled without CONT."""
        settings = ActronAirUserAirconSettings(FanMode="HIGH")
        assert settings.continuous_fan_enabled is False

    def test_base_fan_mode_with_plus_cont(self):
        """Test base_fan_mode extraction with +CONT."""
        settings = ActronAirUserAirconSettings(FanMode="AUTO+CONT")
        assert settings.base_fan_mode == "AUTO"

    def test_base_fan_mode_with_dash_cont(self):
        """Test base_fan_mode extraction with -CONT."""
        settings = ActronAirUserAirconSettings(FanMode="LOW-CONT")
        assert settings.base_fan_mode == "LOW"

    def test_base_fan_mode_without_cont(self):
        """Test base_fan_mode without CONT."""
        settings = ActronAirUserAirconSettings(FanMode="HIGH")
        assert settings.base_fan_mode == "HIGH"

    def test_set_system_mode_on(self):
        """Test set_system_mode_command for turning on."""
        settings = ActronAirUserAirconSettings()
        command = settings._set_system_mode_command("COOL")

        assert command["command"]["UserAirconSettings.isOn"] is True
        assert command["command"]["UserAirconSettings.Mode"] == "COOL"
        assert command["command"]["type"] == "set-settings"

    def test_set_system_mode_off(self):
        """Test set_system_mode_command for turning off."""
        settings = ActronAirUserAirconSettings(Mode="COOL")
        command = settings._set_system_mode_command("OFF")

        assert command["command"]["UserAirconSettings.isOn"] is False
        # Mode is preserved when turning off so it remembers what mode to use when turning back on
        assert command["command"]["UserAirconSettings.Mode"] == "COOL"

    def test_set_fan_mode_preserves_cont(self):
        """Test set_fan_mode_command preserves continuous mode."""
        settings = ActronAirUserAirconSettings(FanMode="AUTO+CONT")
        command = settings._set_fan_mode_command("LOW")

        assert command["command"]["UserAirconSettings.FanMode"] == "LOW+CONT"

    def test_set_fan_mode_without_cont(self):
        """Test set_fan_mode_command without continuous mode."""
        settings = ActronAirUserAirconSettings(FanMode="AUTO")
        command = settings._set_fan_mode_command("LOW")

        assert command["command"]["UserAirconSettings.FanMode"] == "LOW"

    def test_set_continuous_mode_enable(self):
        """Test set_continuous_mode_command to enable."""
        settings = ActronAirUserAirconSettings(FanMode="HIGH")
        command = settings._set_continuous_mode_command(True)

        assert command["command"]["UserAirconSettings.FanMode"] == "HIGH+CONT"

    def test_set_continuous_mode_disable(self):
        """Test set_continuous_mode_command to disable."""
        settings = ActronAirUserAirconSettings(FanMode="HIGH+CONT")
        command = settings._set_continuous_mode_command(False)

        assert command["command"]["UserAirconSettings.FanMode"] == "HIGH"

    def test_set_temperature_command_cool(self):
        """Test set_temperature_command in COOL mode."""
        settings = ActronAirUserAirconSettings(Mode="COOL")
        command = settings._set_temperature_command(22.0)

        assert command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] == 22.0

    def test_set_temperature_command_heat(self):
        """Test set_temperature_command in HEAT mode."""
        settings = ActronAirUserAirconSettings(Mode="HEAT")
        command = settings._set_temperature_command(20.0)

        assert command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] == 20.0

    def test_set_temperature_command_auto(self):
        """Test set_temperature_command in AUTO mode."""
        settings = ActronAirUserAirconSettings(
            Mode="AUTO", TemperatureSetpoint_Cool_oC=24.0, TemperatureSetpoint_Heat_oC=20.0
        )
        command = settings._set_temperature_command(25.0)

        assert command["command"]["UserAirconSettings.TemperatureSetpoint_Cool_oC"] == 25.0
        assert command["command"]["UserAirconSettings.TemperatureSetpoint_Heat_oC"] == 21.0

    def test_set_temperature_command_no_mode(self):
        """Test set_temperature_command with no mode raises error."""
        settings = ActronAirUserAirconSettings(Mode="")

        with pytest.raises(ValueError, match="No mode available"):
            settings._set_temperature_command(22.0)

    def test_set_away_mode_command(self):
        """Test set_away_mode_command."""
        settings = ActronAirUserAirconSettings()
        command = settings._set_away_mode_command(True)

        assert command["command"]["UserAirconSettings.AwayMode"] is True

    def test_set_quiet_mode_command(self):
        """Test set_quiet_mode_command."""
        settings = ActronAirUserAirconSettings()
        command = settings._set_quiet_mode_command(True)

        assert command["command"]["UserAirconSettings.QuietModeEnabled"] is True

    def test_set_turbo_mode_command(self):
        """Test set_turbo_mode_command."""
        settings = ActronAirUserAirconSettings()
        command = settings._set_turbo_mode_command(True)

        assert command["command"]["UserAirconSettings.TurboMode.Enabled"] is True


class TestZoneProperties:
    """Test ActronAirZone properties."""

    def test_is_active_without_parent(self):
        """Test is_active without parent status."""
        zone = ActronAirZone(CanOperate=True)
        assert zone.is_active is False

    def test_is_active_cannot_operate(self):
        """Test is_active when zone cannot operate."""
        zone = ActronAirZone(CanOperate=False)
        parent = MagicMock()
        parent.user_aircon_settings.enabled_zones = [True, True]
        zone.set_parent_status(parent, 0)

        assert zone.is_active is False

    def test_is_active_zone_disabled(self):
        """Test is_active when zone is disabled."""
        zone = ActronAirZone(CanOperate=True)
        parent = MagicMock()
        parent.user_aircon_settings.enabled_zones = [False, True]
        zone.set_parent_status(parent, 0)

        assert zone.is_active is False

    def test_is_active_zone_enabled(self):
        """Test is_active when zone is enabled and can operate."""
        zone = ActronAirZone(CanOperate=True)
        parent = MagicMock()
        parent.user_aircon_settings.enabled_zones = [True, True]
        zone.set_parent_status(parent, 0)

        assert zone.is_active is True

    def test_hvac_mode_without_parent(self):
        """Test hvac_mode without parent returns OFF."""
        zone = ActronAirZone()
        assert zone.hvac_mode == "OFF"

    def test_hvac_mode_system_off(self):
        """Test hvac_mode when system is off."""
        zone = ActronAirZone(can_operate=True)
        parent = MagicMock()
        parent.user_aircon_settings.is_on = False
        parent.user_aircon_settings.mode = "COOL"
        parent.user_aircon_settings.enabled_zones = [True]
        zone.set_parent_status(parent, 0)

        assert zone.hvac_mode == "OFF"

    def test_hvac_mode_zone_inactive(self):
        """Test hvac_mode when zone is inactive."""
        zone = ActronAirZone(CanOperate=True)
        parent = MagicMock()
        parent.user_aircon_settings.is_on = True
        parent.user_aircon_settings.mode = "COOL"
        parent.user_aircon_settings.enabled_zones = [False]
        zone.set_parent_status(parent, 0)

        assert zone.hvac_mode == "OFF"

    def test_hvac_mode_active(self):
        """Test hvac_mode when zone is active."""
        zone = ActronAirZone(CanOperate=True)
        parent = MagicMock()
        parent.user_aircon_settings.is_on = True
        parent.user_aircon_settings.mode = "COOL"
        parent.user_aircon_settings.enabled_zones = [True]
        zone.set_parent_status(parent, 0)

        assert zone.hvac_mode == "COOL"

    def test_humidity_with_actual(self):
        """Test humidity property uses actual_humidity_pc when available."""
        zone = ActronAirZone(LiveHumidity_pc=50.0, actual_humidity_pc=55.0)
        assert zone.humidity == 55.0

    def test_humidity_without_actual(self):
        """Test humidity property falls back to live_humidity_pc."""
        zone = ActronAirZone(LiveHumidity_pc=50.0, actual_humidity_pc=None)
        assert zone.humidity == 50.0

    def test_battery_level_without_parent(self):
        """Test battery_level without parent."""
        zone = ActronAirZone()
        assert zone.battery_level is None

    def test_battery_level_with_peripheral(self):
        """Test battery_level from peripheral."""
        zone = ActronAirZone()
        parent = MagicMock()
        peripheral = MagicMock()
        peripheral.battery_level = 85.0
        parent.get_peripheral_for_zone.return_value = peripheral
        zone.set_parent_status(parent, 0)

        assert zone.battery_level == 85.0

    def test_battery_level_no_peripheral(self):
        """Test battery_level when no peripheral assigned."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.get_peripheral_for_zone.return_value = None
        zone.set_parent_status(parent, 0)

        assert zone.battery_level is None

    def test_peripheral_temperature(self):
        """Test peripheral_temperature property."""
        zone = ActronAirZone()
        parent = MagicMock()
        peripheral = MagicMock()
        peripheral.temperature = 22.5
        parent.get_peripheral_for_zone.return_value = peripheral
        zone.set_parent_status(parent, 0)

        assert zone.peripheral_temperature == 22.5

    def test_peripheral_humidity(self):
        """Test peripheral_humidity property."""
        zone = ActronAirZone()
        parent = MagicMock()
        peripheral = MagicMock()
        peripheral.humidity = 55.0
        parent.get_peripheral_for_zone.return_value = peripheral
        zone.set_parent_status(parent, 0)

        assert zone.peripheral_humidity == 55.0

    def test_peripheral_property(self):
        """Test peripheral property returns the peripheral."""
        zone = ActronAirZone()
        parent = MagicMock()
        peripheral = MagicMock()
        parent.get_peripheral_for_zone.return_value = peripheral
        zone.set_parent_status(parent, 0)

        assert zone.peripheral is peripheral

    def test_max_temp_without_parent(self):
        """Test max_temp without parent returns default."""
        zone = ActronAirZone()
        assert zone.max_temp == 30.0

    def test_min_temp_without_parent(self):
        """Test min_temp without parent returns default."""
        zone = ActronAirZone()
        assert zone.min_temp == 16.0


class TestZoneCommands:
    """Test ActronAirZone command generation."""

    def test_set_temperature_command_cool(self):
        """Test set_temperature_command in COOL mode."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.mode = "COOL"
        zone.set_parent_status(parent, 0)

        command = zone.set_temperature_command(22.0)

        assert command["command"]["RemoteZoneInfo[0].TemperatureSetpoint_Cool_oC"] == 22.0

    def test_set_temperature_command_heat(self):
        """Test set_temperature_command in HEAT mode."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.mode = "HEAT"
        zone.set_parent_status(parent, 1)

        command = zone.set_temperature_command(20.0)

        assert command["command"]["RemoteZoneInfo[1].TemperatureSetpoint_Heat_oC"] == 20.0

    def test_set_temperature_command_auto(self):
        """Test set_temperature_command in AUTO mode."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.mode = "AUTO"
        parent.user_aircon_settings.temperature_setpoint_cool_c = 24.0
        parent.user_aircon_settings.temperature_setpoint_heat_c = 20.0
        zone.set_parent_status(parent, 0)

        command = zone.set_temperature_command(25.0)

        assert command["command"]["RemoteZoneInfo[0].TemperatureSetpoint_Cool_oC"] == 25.0
        assert command["command"]["RemoteZoneInfo[0].TemperatureSetpoint_Heat_oC"] == 21.0

    def test_set_temperature_command_no_zone_id(self):
        """Test set_temperature_command without zone_id raises error."""
        zone = ActronAirZone()

        with pytest.raises(ValueError, match="Zone index not set"):
            zone.set_temperature_command(22.0)

    def test_set_temperature_command_no_parent(self):
        """Test set_temperature_command without parent raises error."""
        zone = ActronAirZone()
        zone.zone_id = 0

        with pytest.raises(ValueError, match="No parent AC status"):
            zone.set_temperature_command(22.0)

    def test_set_enable_command_enable(self):
        """Test set_enable_command to enable zone."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.enabled_zones = [False, True, False]
        zone.set_parent_status(parent, 0)

        command = zone.set_enable_command(True)

        assert command["command"]["UserAirconSettings.EnabledZones"] == [True, True, False]

    def test_set_enable_command_disable(self):
        """Test set_enable_command to disable zone."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.enabled_zones = [True, True, False]
        zone.set_parent_status(parent, 1)

        command = zone.set_enable_command(False)

        assert command["command"]["UserAirconSettings.EnabledZones"] == [True, False, False]

    def test_set_enable_command_no_zone_id(self):
        """Test set_enable_command without zone_id raises error."""
        zone = ActronAirZone()

        with pytest.raises(ValueError, match="Zone index not set"):
            zone.set_enable_command(True)

    def test_set_enable_command_out_of_range(self):
        """Test set_enable_command with out of range zone_id."""
        zone = ActronAirZone()
        parent = MagicMock()
        parent.user_aircon_settings.enabled_zones = [True, False]
        zone.set_parent_status(parent, 5)

        with pytest.raises(ValueError, match="out of range"):
            zone.set_enable_command(True)


class TestPeripheral:
    """Test ActronAirPeripheral."""

    def test_zones_without_parent(self):
        """Test zones property without parent."""
        peripheral = ActronAirPeripheral(ZoneAssignment=[1, 2])
        assert peripheral.zones == []

    def test_zones_with_parent(self):
        """Test zones property with parent."""
        peripheral = ActronAirPeripheral(ZoneAssignment=[1, 2])

        zone1 = MagicMock()
        zone2 = MagicMock()
        zone3 = MagicMock()

        parent = MagicMock()
        parent.remote_zone_info = [zone1, zone2, zone3]
        peripheral.set_parent_status(parent)

        zones = peripheral.zones
        assert len(zones) == 2
        assert zones[0] is zone1
        assert zones[1] is zone2

    def test_zones_out_of_range(self):
        """Test zones property with out of range assignments."""
        peripheral = ActronAirPeripheral(ZoneAssignment=[1, 99])

        zone1 = MagicMock()

        parent = MagicMock()
        parent.remote_zone_info = [zone1]
        peripheral.set_parent_status(parent)

        zones = peripheral.zones
        assert len(zones) == 1
        assert zones[0] is zone1

    def test_from_peripheral_data_with_sensors(self):
        """Test from_peripheral_data with sensor data."""
        data = {
            "LogicalAddress": 3,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "ABC123",
            "SensorInputs": {"SHTC1": {"Temperature_oC": 22.5, "RelativeHumidity_pc": 55.0}},
        }

        peripheral = ActronAirPeripheral.from_peripheral_data(data)

        assert peripheral.temperature == 22.5
        assert peripheral.humidity == 55.0

    def test_from_peripheral_data_without_sensors(self):
        """Test from_peripheral_data without sensor data."""
        data = {
            "LogicalAddress": 3,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "ABC123",
        }

        peripheral = ActronAirPeripheral.from_peripheral_data(data)

        assert peripheral.temperature is None
        assert peripheral.humidity is None

    def test_from_peripheral_data_invalid_temp(self):
        """Test from_peripheral_data with invalid temperature."""
        data = {
            "LogicalAddress": 3,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "ABC123",
            "SensorInputs": {"SHTC1": {"Temperature_oC": "invalid"}},
        }

        peripheral = ActronAirPeripheral.from_peripheral_data(data)

        assert peripheral.temperature is None

    def test_from_peripheral_data_invalid_humidity(self):
        """Test from_peripheral_data with invalid humidity."""
        data = {
            "LogicalAddress": 3,
            "DeviceType": "ZoneController",
            "ZoneAssignment": [1],
            "SerialNumber": "ABC123",
            "SensorInputs": {"SHTC1": {"RelativeHumidity_pc": "invalid"}},
        }

        peripheral = ActronAirPeripheral.from_peripheral_data(data)

        assert peripheral.humidity is None
