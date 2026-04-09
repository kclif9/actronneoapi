"""Tests for status model properties and methods."""

import pytest

from actron_neo_api.models import ActronAirStatus


@pytest.fixture
def minimal_status():
    """Minimal status data with always-present API sections."""
    return ActronAirStatus(
        isOnline=True,
        lastKnownState={
            "LiveAircon": {},
            "MasterInfo": {},
            "Alerts": {},
        },
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
                        "ZoneAssignment": [1, 2],
                        "SensorInputs": {
                            "SHTC1": {
                                "Temperature_oC": 22.5,
                                "RelativeHumidity_pc": 55.0,
                            }
                        },
                    },
                    {
                        "ZoneAssignment": [3],
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
        assert minimal_status.compressor_chasing_temperature == 0.0

    def test_compressor_live_temperature_with_live_aircon(self, full_status_data):
        """Test compressor_live_temperature with live aircon data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.compressor_live_temperature == 22.0

    def test_compressor_live_temperature_without_live_aircon(self, minimal_status):
        """Test compressor_live_temperature without live aircon data."""
        assert minimal_status.compressor_live_temperature == 0.0

    def test_compressor_mode_with_live_aircon(self, full_status_data):
        """Test compressor_mode with live aircon data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.compressor_mode == "COOL"

    def test_compressor_mode_without_live_aircon(self, minimal_status):
        """Test compressor_mode without live aircon data."""
        assert minimal_status.compressor_mode == ""

    def test_system_on_with_live_aircon(self, full_status_data):
        """Test system_on with live aircon data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # The system_on property checks live_aircon.is_on
        assert status.live_aircon.is_on is True
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
        assert minimal_status.outdoor_temperature == 0.0

    def test_humidity_with_master_info(self, full_status_data):
        """Test humidity with master info data."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        assert status.humidity == 65.0

    def test_humidity_without_master_info(self, minimal_status):
        """Test humidity without master info data."""
        assert minimal_status.humidity == 0.0

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
        assert minimal_status.max_temp == 30.0

    def test_min_temp_heat_mode(self):
        """Test min_temp returns heat limits when mode is HEAT."""
        status = ActronAirStatus.model_validate(
            {
                "isOnline": True,
                "lastKnownState": {
                    "UserAirconSettings": {"isOn": True, "Mode": "HEAT"},
                    "NV_Limits": {
                        "UserSetpoint_oC": {
                            "setCool_Min": 18.0,
                            "setCool_Max": 30.0,
                            "setHeat_Min": 14.0,
                            "setHeat_Max": 26.0,
                        }
                    },
                },
            }
        )
        assert status.min_temp == 14.0

    def test_max_temp_heat_mode(self):
        """Test max_temp returns heat limits when mode is HEAT."""
        status = ActronAirStatus.model_validate(
            {
                "isOnline": True,
                "lastKnownState": {
                    "UserAirconSettings": {"isOn": True, "Mode": "HEAT"},
                    "NV_Limits": {
                        "UserSetpoint_oC": {
                            "setCool_Min": 18.0,
                            "setCool_Max": 30.0,
                            "setHeat_Min": 14.0,
                            "setHeat_Max": 26.0,
                        }
                    },
                },
            }
        )
        assert status.max_temp == 26.0

    def test_min_temp_heat_mode_default(self):
        """Test min_temp heat mode default when limits missing."""
        status = ActronAirStatus.model_validate(
            {
                "isOnline": True,
                "lastKnownState": {
                    "UserAirconSettings": {"isOn": True, "Mode": "HEAT"},
                },
            }
        )
        assert status.min_temp == 16.0

    def test_max_temp_heat_mode_default(self):
        """Test max_temp heat mode default when limits missing."""
        status = ActronAirStatus.model_validate(
            {
                "isOnline": True,
                "lastKnownState": {
                    "UserAirconSettings": {"isOn": True, "Mode": "HEAT"},
                },
            }
        )
        assert status.max_temp == 30.0

    def test_cool_mode_uses_cool_limits(self, full_status_data):
        """Test that COOL mode still uses cool limits (regression)."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # full_status_data has Mode=COOL, setCool_Min=18, setCool_Max=30
        assert status.min_temp == 18.0
        assert status.max_temp == 30.0


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
                            "ZoneAssignment": [1],
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

        # Zone 0 should have first peripheral (ZoneAssignment [1, 2] → zones 0, 1)
        peripheral0 = status.get_peripheral_for_zone(0)
        assert peripheral0 is not None
        assert 1 in peripheral0.zone_assignments

        # Zone 2 should have second peripheral (ZoneAssignment [3] → zone 2)
        peripheral2 = status.get_peripheral_for_zone(2)
        assert peripheral2 is not None
        assert 3 in peripheral2.zone_assignments

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

        # Verify all components were parsed with real data
        assert status.ac_system.master_serial == "TEST123"
        assert status.user_aircon_settings.mode == "COOL"
        assert status.master_info.live_humidity_pc == 65.0
        assert status.live_aircon.is_on is True
        assert status.alerts.clean_filter is True
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

        # Only UserAirconSettings should be parsed with real data
        assert status.user_aircon_settings.mode == "COOL"
        assert status.ac_system.master_serial == ""
        assert status.master_info.live_temp_c == 0.0
        assert status.live_aircon.is_on is False
        assert status.alerts.clean_filter is False

    def test_remote_zone_info_with_non_dict_entry_skips_all_zones(self):
        """RemoteZoneInfo with non-dict entries is skipped entirely to preserve indices."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True},
                    None,
                    {"ZoneNumber": 2, "LiveTemp_oC": 24.0, "EnabledZone": True, "CanOperate": True},
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # Non-dict entry means entire list is skipped to avoid index misalignment
        assert len(status.remote_zone_info) == 0

    def test_remote_zone_info_with_string_entry_skips_all_zones(self):
        """RemoteZoneInfo with a string entry is skipped entirely."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True},
                    "bad_entry",
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        assert len(status.remote_zone_info) == 0

    def test_remote_zone_info_all_valid_dicts_parses_normally(self):
        """RemoteZoneInfo with all valid dict entries parses normally."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True},
                    {
                        "ZoneNumber": 1,
                        "LiveTemp_oC": 23.0,
                        "EnabledZone": False,
                        "CanOperate": True,
                    },
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        assert len(status.remote_zone_info) == 2
        assert status.remote_zone_info[0].zone_id == 0
        assert status.remote_zone_info[1].zone_id == 1

    def test_malformed_aircon_system_graceful(self):
        """Malformed AirconSystem is skipped; peripherals and other components still parse."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {
                    "MasterSerial": [1, 2, 3],  # wrong type
                    "Peripherals": [
                        {
                            "ZoneAssignment": [1],
                            "SensorInputs": {
                                "SHTC1": {
                                    "Temperature_oC": 22.5,
                                    "RelativeHumidity_pc": 55.0,
                                }
                            },
                        }
                    ],
                },
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

        assert status.ac_system.master_serial == ""
        assert status.user_aircon_settings.mode == "COOL"
        # Peripherals survive even when ACSystem model validation fails
        assert len(status.peripherals) == 1

    def test_malformed_user_aircon_settings_graceful(self):
        """Malformed UserAirconSettings is skipped; other components still parse."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "UserAirconSettings": {"Mode": {"nested": "wrong"}},
                "MasterInfo": {
                    "LiveOutdoorTemp_oC": 28.5,
                    "LiveHumidity_pc": 65.0,
                },
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        assert status.user_aircon_settings.mode == ""
        assert status.master_info.live_humidity_pc == 65.0

    def test_malformed_master_info_graceful(self):
        """Malformed MasterInfo is skipped; other components still parse."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "MasterInfo": {"LiveOutdoorTemp_oC": "not_a_number"},
                "LiveAircon": {"SystemOn": True, "CompressorMode": "COOL"},
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # MasterInfo may or may not fail depending on Pydantic coercion;
        # either way, LiveAircon should parse
        assert status.live_aircon.compressor_mode == "COOL"

    def test_malformed_live_aircon_graceful(self):
        """Malformed LiveAircon is skipped; other components still parse."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "LiveAircon": {"OutdoorUnit": {"CompSpeed": ["not", "valid"]}},
                "Alerts": {"CleanFilter": True, "Defrosting": False},
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        # LiveAircon should be reset to default on validation failure
        assert status.live_aircon.is_on is False
        # Alerts should still parse regardless
        assert status.alerts.clean_filter is True

    def test_malformed_alerts_graceful(self):
        """Malformed Alerts is skipped; other components still parse."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "Alerts": {"CleanFilter": {"nested": "wrong"}},
                "RemoteZoneInfo": [
                    {"ZoneNumber": 0, "LiveTemp_oC": 22.0, "EnabledZone": True, "CanOperate": True},
                ],
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        assert status.alerts.clean_filter is False
        assert len(status.remote_zone_info) == 1

    def test_malformed_remote_zone_info_graceful(self):
        """Malformed RemoteZoneInfo resets to empty; other components still parse."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "RemoteZoneInfo": [
                    {"ZoneNumber": "not_a_number", "LiveTemp_oC": "bad", "CanOperate": 999},
                ],
                "Alerts": {"CleanFilter": False, "Defrosting": False},
            },
        }

        status = ActronAirStatus.model_validate(status_data)
        status.parse_nested_components()

        assert len(status.remote_zone_info) == 0
        assert status.alerts.clean_filter is False

    def test_reparse_clears_stale_state(self, full_status_data):
        """Re-parsing after last_known_state changes clears stale objects."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # First parse should populate everything
        assert status.ac_system.master_serial == "TEST123"
        assert status.user_aircon_settings.mode == "COOL"
        assert status.live_aircon.is_on is True
        assert len(status.remote_zone_info) == 3
        assert status.serial_number == "TEST123"

        # Replace with empty state and re-parse
        status.last_known_state = {}
        status.parse_nested_components()

        assert status.ac_system.master_serial == ""
        assert status.user_aircon_settings.mode == ""
        assert status.master_info.live_temp_c == 0.0
        assert status.live_aircon.is_on is False
        assert status.alerts.clean_filter is False
        assert len(status.remote_zone_info) == 0
        assert len(status.peripherals) == 0
        # serial_number is preserved (may have been set externally);
        # it is only overwritten when AirconSystem data is present.
        assert status.serial_number == "TEST123"


class TestZoneAssignmentMapping:
    """Test that peripheral zone assignments use 1-based API convention."""

    def test_peripheral_humidity_maps_to_correct_zone(self, full_status_data):
        """Peripheral with ZoneAssignment [1, 2] maps humidity to zones 0 and 1."""
        status = ActronAirStatus.model_validate(full_status_data)
        status.parse_nested_components()

        # First peripheral has ZoneAssignment [1, 2] → zones 0, 1
        zone0 = status.remote_zone_info[0]
        zone1 = status.remote_zone_info[1]
        assert zone0.actual_humidity_pc == 55.0
        assert zone1.actual_humidity_pc == 55.0

        # Second peripheral has ZoneAssignment [3] → zone 2
        zone2 = status.remote_zone_info[2]
        assert zone2.actual_humidity_pc == 60.0

    def test_get_peripheral_for_zone_uses_1_based_lookup(self):
        """get_peripheral_for_zone converts 0-based zone_index to 1-based assignment."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "AirconSystem": {
                    "MasterSerial": "TEST",
                    "Peripherals": [
                        {
                            "ZoneAssignment": [2],
                            "SerialNumber": "P1",
                            "SensorInputs": {
                                "SHTC1": {
                                    "Temperature_oC": 22.0,
                                    "RelativeHumidity_pc": 50.0,
                                }
                            },
                        }
                    ],
                },
                "RemoteZoneInfo": [
                    {"CanOperate": True, "LiveTemp_oC": 22.0},
                    {"CanOperate": True, "LiveTemp_oC": 23.0},
                ],
            },
        )
        status.parse_nested_components()

        # Zone index 1 (0-based) should find peripheral with ZoneAssignment [2]
        result = status.get_peripheral_for_zone(1)
        assert result is not None
        assert result.serial_number == "P1"

        # Zone index 0 should not find this peripheral
        assert status.get_peripheral_for_zone(0) is None

    def test_non_int_zone_assignment_skipped_in_mapping(self):
        """Non-int entries in ZoneAssignment are skipped without raising."""
        status = ActronAirStatus(
            isOnline=True,
            lastKnownState={
                "AirconSystem": {
                    "MasterSerial": "TEST",
                    "Peripherals": [
                        {
                            "ZoneAssignment": [1],
                            "SerialNumber": "P1",
                            "SensorInputs": {
                                "SHTC1": {
                                    "Temperature_oC": 22.0,
                                    "RelativeHumidity_pc": 50.0,
                                }
                            },
                        }
                    ],
                },
                "RemoteZoneInfo": [
                    {"CanOperate": True, "LiveTemp_oC": 22.0},
                ],
            },
        )
        status.parse_nested_components()

        # Inject a non-int assignment after Pydantic validation
        status.peripherals[0].zone_assignments = ["bad", None, 1]
        status._map_peripheral_data_to_zones()

        # Zone 0 should still get humidity from the valid assignment (1 → index 0)
        assert status.remote_zone_info[0].actual_humidity_pc == 50.0
