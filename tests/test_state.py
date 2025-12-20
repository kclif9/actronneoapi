"""Tests for state management module."""

import pytest

from actron_neo_api.state import StateManager


@pytest.fixture
def state_manager():
    """Create a state manager instance."""
    return StateManager()


@pytest.fixture
def sample_status_data():
    """Sample status data for testing."""
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
                    }
                ],
            },
            "UserAirconSettings": {
                "isOn": True,
                "Mode": "COOL",
                "FanMode": "AUTO",
                "SetPoint": 22.0,
            },
            "MasterInfo": {
                "LiveOutdoorTemp_oC": 25.0,
                "LiveHumidity_pc": 60.0,
            },
            "LiveAircon": {
                "isOn": True,
                "CompressorMode": "COOL",
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
            ],
        },
    }


class TestStateManager:
    """Tests for StateManager class."""

    def test_init(self, state_manager):
        """Test StateManager initialization."""
        assert state_manager.status == {}
        assert state_manager.latest_event_id == {}
        assert state_manager._observers == []
        assert state_manager._api is None

    def test_set_api(self, state_manager, sample_status_data):
        """Test setting API reference."""

        # Create a mock API object
        class MockAPI:
            pass

        mock_api = MockAPI()

        # Add a status first
        status = state_manager.process_status_update("TEST123", sample_status_data)

        # Set API
        state_manager.set_api(mock_api)

        # Verify API is set on manager
        assert state_manager._api is mock_api

        # Verify API is set on existing status
        assert status.api is mock_api

    def test_add_observer(self, state_manager):
        """Test adding observers."""

        def observer1(serial, data):
            pass

        def observer2(serial, data):
            pass

        state_manager.add_observer(observer1)
        assert len(state_manager._observers) == 1
        assert observer1 in state_manager._observers

        state_manager.add_observer(observer2)
        assert len(state_manager._observers) == 2
        assert observer2 in state_manager._observers

    def test_get_status(self, state_manager, sample_status_data):
        """Test getting status by serial number."""
        # Process status update
        state_manager.process_status_update("TEST123", sample_status_data)

        # Test retrieval with exact case
        status = state_manager.get_status("test123")
        assert status is not None
        assert status.is_online is True

        # Test case insensitivity
        status_upper = state_manager.get_status("TEST123")
        assert status_upper is status

        # Test non-existent system
        missing = state_manager.get_status("NONEXISTENT")
        assert missing is None

    def test_process_status_update(self, state_manager, sample_status_data):
        """Test processing a status update."""
        status = state_manager.process_status_update("TEST123", sample_status_data)

        # Verify status was created and stored
        assert status is not None
        assert status.is_online is True
        assert status.serial_number == "test123"  # Normalized to lowercase

        # Verify nested components were parsed
        assert status.ac_system is not None
        assert status.user_aircon_settings is not None
        assert status.master_info is not None
        assert status.live_aircon is not None
        assert len(status.remote_zone_info) == 2

    def test_process_status_update_with_api(self, state_manager, sample_status_data):
        """Test status update sets API reference."""

        class MockAPI:
            pass

        mock_api = MockAPI()
        state_manager.set_api(mock_api)

        status = state_manager.process_status_update("TEST123", sample_status_data)

        # Verify API reference was set
        assert status.api is mock_api

    def test_process_status_update_notifies_observers(self, state_manager, sample_status_data):
        """Test that observers are notified on status update."""
        called_with = []

        def observer(serial, data):
            called_with.append((serial, data))

        state_manager.add_observer(observer)

        # Process update
        state_manager.process_status_update("TEST123", sample_status_data)

        # Verify observer was called
        assert len(called_with) == 1
        assert called_with[0][0] == "test123"
        assert called_with[0][1] == sample_status_data

    def test_process_status_update_observer_error_handling(self, state_manager, sample_status_data):
        """Test that observer errors don't break status updates."""

        def failing_observer(serial, data):
            raise ValueError("Observer error")

        def working_observer(serial, data):
            working_observer.called = True

        working_observer.called = False

        state_manager.add_observer(failing_observer)
        state_manager.add_observer(working_observer)

        # Process update - should not raise despite failing observer
        status = state_manager.process_status_update("TEST123", sample_status_data)

        # Verify status was still processed
        assert status is not None
        assert status.is_online is True

        # Verify working observer was still called
        assert working_observer.called is True

    def test_map_peripheral_humidity_to_zones(self, state_manager, sample_status_data):
        """Test peripheral humidity mapping to zones."""
        status = state_manager.process_status_update("TEST123", sample_status_data)

        # Verify peripheral data was mapped to zones
        assert len(status.remote_zone_info) == 2

        # Both zones should have peripheral humidity data
        zone0 = status.remote_zone_info[0]
        zone1 = status.remote_zone_info[1]

        assert zone0.actual_humidity_pc == 55.0
        assert zone1.actual_humidity_pc == 55.0

    def test_extract_peripheral_humidity_valid(self, state_manager):
        """Test extracting valid peripheral humidity."""
        peripheral = {
            "SensorInputs": {
                "SHTC1": {
                    "RelativeHumidity_pc": 65.5,
                }
            }
        }

        humidity = state_manager._extract_peripheral_humidity(peripheral)
        assert humidity == 65.5

    def test_extract_peripheral_humidity_no_sensor(self, state_manager):
        """Test extracting humidity from peripheral without sensor."""
        peripheral = {"SensorInputs": {}}

        humidity = state_manager._extract_peripheral_humidity(peripheral)
        assert humidity is None

    def test_extract_peripheral_humidity_invalid_range(self, state_manager):
        """Test extracting humidity with invalid range."""
        peripheral = {
            "SensorInputs": {
                "SHTC1": {
                    "RelativeHumidity_pc": 150.0,  # Invalid: > 100
                }
            }
        }

        humidity = state_manager._extract_peripheral_humidity(peripheral)
        assert humidity is None

    def test_extract_peripheral_humidity_negative(self, state_manager):
        """Test extracting negative humidity value."""
        peripheral = {
            "SensorInputs": {
                "SHTC1": {
                    "RelativeHumidity_pc": -10.0,  # Invalid: < 0
                }
            }
        }

        humidity = state_manager._extract_peripheral_humidity(peripheral)
        assert humidity is None

    def test_extract_peripheral_humidity_missing_data(self, state_manager):
        """Test extracting humidity when data is missing."""
        peripheral = {}

        humidity = state_manager._extract_peripheral_humidity(peripheral)
        assert humidity is None

    def test_map_peripheral_humidity_no_status(self, state_manager):
        """Test peripheral mapping with None status."""
        # Should not raise, just return early
        state_manager._map_peripheral_humidity_to_zones(None)

    def test_map_peripheral_humidity_no_peripherals(self, state_manager):
        """Test peripheral mapping without peripherals."""
        status_data = {
            "isOnline": True,
            "lastKnownState": {
                "AirconSystem": {},  # No Peripherals key
                "RemoteZoneInfo": [
                    {
                        "ZoneNumber": 0,
                        "LiveTemp_oC": 22.0,
                        "EnabledZone": True,
                        "CanOperate": True,
                    }
                ],
            },
        }

        status = state_manager.process_status_update("TEST123", status_data)

        # Should not crash, zones just won't have peripheral humidity
        assert len(status.remote_zone_info) == 1
