"""Tests for status model properties and methods."""

import pytest

from actron_neo_api.models import ActronAirStatus


@pytest.fixture
def minimal_status():
    """Minimal status data."""
    return ActronAirStatus(
        isOnline=True,
        lastKnownState={},
    )


@pytest.fixture
def full_status_data():
    """Full status data with all components."""
    return {
        "isOnline": True,
        "lastKnownState": {
            "AirconSystem": {
                "MasterSerial": "TEST123",
                "CanOperate": True,
                "Peripherals": [
                    {
                        "ZoneAssignment": [0, 1],
                        "SensorInputs": {
                            "SHTC1": {
                                "Temperature_oC": 22.5,
                                "RelativeHumidity_pc": 55.0,
                            }
                        },
                    },
                    {
                        "ZoneAssignment": [2],
                        "SensorInputs": {
                            "SHTC1": {
                                "Temperature_oC": 23.0,
                                "RelativeHumidity_pc": 60.0,
                            }
                        },
                    },
                ],
            },
            "UserAirconSettings": {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "SetPoint": 22.0,
            },
            "MasterInfo": {
                "LiveOutdoorTemp_oC": 28.5,
                "LiveHumidity_pc": 65.0,
            },
            "LiveAircon": {
                "SystemOn": True,
                "CompressorMode": "COOL",
                "CompressorChasingTemperature": 21.0,
                "CompressorLiveTemperature": 22.0,
                "OutdoorUnit": {
                    "CompSpeed": 75.5,
                    "CompPower": 1500,
                },
            },
            "Alerts": {
                "CleanFilter": True,
                "Defrosting": False,
            },
            "RemoteZoneInfo": [
                {
                    "ZoneNumber": 0,
                    "LiveTemp_oC": 22.0,
                    "EnabledZone": True,
                    "CanOperate": True,
                },
                {
                    "ZoneNumber": 1,
                    "LiveTemp_oC": 23.0,
                    "EnabledZone": True,
                    "CanOperate": True,
                },
                {
                    "ZoneNumber": 2,
                    "LiveTemp_oC": 24.0,
                    "EnabledZone": False,
                    "CanOperate": True,
                },
            ],
            "NV_Limits": {
                "UserSetpoint_oC": {
                    "setCool_Min": 18.0,
                    "setCool_Max": 30.0,
                }
            },
            "NV_SystemSettings": {"SystemName": "Home AC"},
        },
    }


class TestStatusProperties:
    """Test ActronAirStatus property accessors."""

    def test_zones_property(self, full_status_data):
        """Test zones property returns dict with integer keys."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        zones = status.zones
        assert isinstance(zones, dict)
        assert len(zones) == 3
        assert 0 in zones
        assert 1 in zones
        assert 2 in zones

    def test_clean_filter_with_alerts(self, full_status_data):
        """Test clean_filter property when alerts exist."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.clean_filter is True

    def test_clean_filter_without_alerts(self, minimal_status):
        """Test clean_filter property when alerts don't exist."""
        assert minimal_status.clean_filter is False

    def test_defrost_mode_with_alerts(self, full_status_data):
        """Test defrost_mode property when alerts exist."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.defrost_mode is False

    def test_defrost_mode_without_alerts(self, minimal_status):
        """Test defrost_mode property when alerts don't exist."""
        assert minimal_status.defrost_mode is False

    def test_compressor_chasing_temperature_with_live_aircon(self, full_status_data):
        """Test compressor_chasing_temperature with live aircon data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.compressor_chasing_temperature == 21.0

    def test_compressor_chasing_temperature_without_live_aircon(self, minimal_status):
        """Test compressor_chasing_temperature without live aircon data."""
        assert minimal_status.compressor_chasing_temperature is None

    def test_compressor_live_temperature_with_live_aircon(self, full_status_data):
        """Test compressor_live_temperature with live aircon data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.compressor_live_temperature == 22.0

    def test_compressor_live_temperature_without_live_aircon(self, minimal_status):
        """Test compressor_live_temperature without live aircon data."""
        assert minimal_status.compressor_live_temperature is None

    def test_compressor_mode_with_live_aircon(self, full_status_data):
        """Test compressor_mode with live aircon data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.compressor_mode == "COOL"

    def test_compressor_mode_without_live_aircon(self, minimal_status):
        """Test compressor_mode without live aircon data."""
        assert minimal_status.compressor_mode is None

    def test_system_on_with_live_aircon(self, full_status_data):
        """Test system_on with live aircon data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # The system_on property checks live_aircon.is_on
        assert status.live_aircon is not None
        assert status.system_on is True

    def test_system_on_without_live_aircon(self, minimal_status):
        """Test system_on without live aircon data."""
        assert minimal_status.system_on is False

    def test_outdoor_temperature_with_master_info(self, full_status_data):
        """Test outdoor_temperature with master info data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.outdoor_temperature == 28.5

    def test_outdoor_temperature_without_master_info(self, minimal_status):
        """Test outdoor_temperature without master info data."""
        assert minimal_status.outdoor_temperature is None

    def test_humidity_with_master_info(self, full_status_data):
        """Test humidity with master info data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.humidity == 65.0

    def test_humidity_without_master_info(self, minimal_status):
        """Test humidity without master info data."""
        assert minimal_status.humidity is None

    def test_compressor_speed_with_outdoor_unit(self, full_status_data):
        """Test compressor_speed with outdoor unit data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.compressor_speed == 75.5

    def test_compressor_speed_without_outdoor_unit(self, minimal_status):
        """Test compressor_speed without outdoor unit data."""
        assert minimal_status.compressor_speed == 0.0

    def test_compressor_power_with_outdoor_unit(self, full_status_data):
        """Test compressor_power with outdoor unit data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.compressor_power == 1500

    def test_compressor_power_without_outdoor_unit(self, minimal_status):
        """Test compressor_power without outdoor unit data."""
        assert minimal_status.compressor_power == 0

    def test_min_temp_with_limits(self, full_status_data):
        """Test min_temp property with NV_Limits."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.min_temp == 18.0

    def test_min_temp_without_limits(self, minimal_status):
        """Test min_temp property with default value."""
        assert minimal_status.min_temp == 16.0

    def test_max_temp_with_limits(self, full_status_data):
        """Test max_temp property with NV_Limits."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.max_temp == 30.0

    def test_max_temp_without_limits(self, minimal_status):
        """Test max_temp property with default value."""
        assert minimal_status.max_temp == 32.0


class TestStatusAPIMethods:
    """Test API-related methods on ActronAirStatus."""

    def test_set_api(self, minimal_status):
        """Test setting API reference."""

        class MockAPI:
            pass

        mock_api = MockAPI()
        minimal_status.set_api(mock_api)

        assert minimal_status._api is mock_api
        assert minimal_status.api is mock_api

    def test_api_property_when_not_set(self, minimal_status):
        """Test api property when not set."""
        assert minimal_status.api is None


class TestStatusPeripheralMethods:
    """Test peripheral processing methods."""

    def test_process_peripherals_with_valid_data(self, full_status_data):
        """Test peripheral processing with valid data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # Should have processed 2 peripherals
        assert len(status.peripherals) == 2

        # Verify peripherals have parent reference
        for peripheral in status.peripherals:
            assert peripheral._parent_status is status

    def test_process_peripherals_without_data(self, minimal_status):
        """Test peripheral processing without peripheral data."""
        minimal_status.parse_nested_components()

        assert minimal_status.peripherals == []

    def test_process_peripherals_with_invalid_data(self):
        """Test peripheral processing gracefully handles invalid data."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {
                    "MasterSerial": "TEST123",
                    "Peripherals": [
                        None,  # Invalid peripheral
                        {},  # Empty peripheral
                        {"InvalidKey": "value"},  # Missing required fields
                    ],
                },
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Should handle errors gracefully and continue
        assert isinstance(status.peripherals, list)

    def test_map_peripheral_data_to_zones(self, full_status_data):
        """Test mapping peripheral data to zones."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # Verify zones can access peripheral data through the peripheral objects
        assert len(status.peripherals) == 2
        # Zone 0 and 1 should be mapped to first peripheral
        peripheral0 = status.get_peripheral_for_zone(0)
        assert peripheral0 is not None
        assert peripheral0.humidity == 55.0

    def test_map_peripheral_data_without_zones(self):
        """Test mapping peripheral data when no zones exist."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {
                    "Peripherals": [
                        {
                            "ZoneAssignment": [0],
                            "SensorInputs": {
                                "SHTC1": {
                                    "Temperature_oC": 22.5,
                                    "RelativeHumidity_pc": 55.0,
                                }
                            },
                        }
                    ],
                },
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Should not crash
        assert len(status.peripherals) == 1

    def test_get_peripheral_for_zone(self, full_status_data):
        """Test getting peripheral for specific zone."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # Zone 0 should have first peripheral
        peripheral0 = status.get_peripheral_for_zone(0)
        assert peripheral0 is not None
        assert 0 in peripheral0.zone_assignments

        # Zone 2 should have second peripheral
        peripheral2 = status.get_peripheral_for_zone(2)
        assert peripheral2 is not None
        assert 2 in peripheral2.zone_assignments

        # Zone 99 shouldn't have any peripheral
        peripheral_none = status.get_peripheral_for_zone(99)
        assert peripheral_none is None

    def test_get_peripheral_for_zone_without_peripherals(self, minimal_status):
        """Test getting peripheral when no peripherals exist."""
        peripheral = minimal_status.get_peripheral_for_zone(0)
        assert peripheral is None


class TestStatusParseNestedComponents:
    """Test parse_nested_components method."""

    def test_parse_all_components(self, full_status_data):
        """Test parsing all nested components."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # Verify all components were parsed
        assert status.ac_system is not None
        assert status.user_aircon_settings is not None
        assert status.master_info is not None
        assert status.live_aircon is not None
        assert status.alerts is not None
        assert len(status.remote_zone_info) == 3
        assert len(status.peripherals) == 2

        # Verify system name was set
        assert status.ac_system.system_name == "Home AC"

        # Verify serial number was extracted
        assert status.serial_number == "TEST123"

    def test_parse_sets_parent_references(self, full_status_data):
        """Test that parsing sets parent references correctly."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # Verify parent references
        assert status.ac_system._parent_status is status
        assert status.user_aircon_settings._parent_status is status

        for i, zone in enumerate(status.remote_zone_info):
            assert zone._parent_status is status
            assert zone.zone_id == i

    def test_parse_with_partial_data(self):
        """Test parsing with only some components present."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {
                    "isOn": True,
                    "Mode": "COOL",
                    "FanMode": "AUTO",
                    "SetPoint": 22.0,
                },
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Only UserAirconSettings should be parsed
        assert status.user_aircon_settings is not None
        assert status.ac_system is None
        assert status.master_info is None
        assert status.live_aircon is None
        assert status.alerts is None
