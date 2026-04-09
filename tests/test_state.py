"""Tests for state management module."""

from typing import Any, Dict

import pytest

from actron_neo_api.state import StateManager


@pytest.fixture
def state_manager() -> StateManager:
    """Create a state manager instance."""
    return StateManager()


@pytest.fixture
def sample_status_data() -> Dict[str, Any]:
    """Sample status data for testing."""
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

    def test_init(self, state_manager: StateManager) -> None:
        """Test StateManager initialization."""
        assert state_manager.status == {}
        assert state_manager._observers == []
        assert state_manager._api is None

    def test_set_api(self, state_manager: StateManager, sample_status_data: Dict[str, Any]) -> None:
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

    def test_add_observer(self, state_manager: StateManager) -> None:
        """Test adding observers."""

        def observer1(serial: str, data: Dict[str, Any]) -> None:
            pass

        def observer2(serial: str, data: Dict[str, Any]) -> None:
            pass

        state_manager.add_observer(observer1)
        assert len(state_manager._observers) == 1
        assert observer1 in state_manager._observers

        state_manager.add_observer(observer2)
        assert len(state_manager._observers) == 2
        assert observer2 in state_manager._observers

    def test_remove_observer(self, state_manager: StateManager) -> None:
        """Test removing a registered observer."""

        def observer(serial: str, data: Dict[str, Any]) -> None:
            pass

        state_manager.add_observer(observer)
        assert observer in state_manager._observers

        state_manager.remove_observer(observer)
        assert observer not in state_manager._observers

    def test_remove_observer_not_registered(self, state_manager: StateManager) -> None:
        """Test removing an unregistered observer is a no-op."""

        def observer(serial: str, data: Dict[str, Any]) -> None:
            pass

        # Should not raise
        state_manager.remove_observer(observer)
        assert state_manager._observers == []

    def test_get_status(
        self, state_manager: StateManager, sample_status_data: Dict[str, Any]
    ) -> None:
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

    def test_process_status_update(
        self, state_manager: StateManager, sample_status_data: Dict[str, Any]
    ) -> None:
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

    def test_process_status_update_with_api(
        self, state_manager: StateManager, sample_status_data: Dict[str, Any]
    ) -> None:
        """Test status update sets API reference."""

        class MockAPI:
            pass

        mock_api = MockAPI()
        state_manager.set_api(mock_api)

        status = state_manager.process_status_update("TEST123", sample_status_data)

        # Verify API reference was set
        assert status.api is mock_api

    def test_process_status_update_notifies_observers(
        self, state_manager: StateManager, sample_status_data: Dict[str, Any]
    ) -> None:
        """Test that observers are notified on status update."""
        called_with = []

        def observer(serial: str, data: Dict[str, Any]) -> None:
            called_with.append((serial, data))

        state_manager.add_observer(observer)

        # Process update
        state_manager.process_status_update("TEST123", sample_status_data)

        # Verify observer was called
        assert len(called_with) == 1
        assert called_with[0][0] == "test123"
        assert called_with[0][1] == sample_status_data

    def test_process_status_update_observer_error_handling(
        self, state_manager: StateManager, sample_status_data: Dict[str, Any]
    ) -> None:
        """Test that observer errors don't break status updates."""

        def failing_observer(serial: str, data: Dict[str, Any]) -> None:
            raise ValueError("Observer error")

        class WorkingObserver:
            called: bool = False

            def __call__(self, serial: str, data: Dict[str, Any]) -> None:
                self.called = True

        working_observer = WorkingObserver()

        state_manager.add_observer(failing_observer)
        state_manager.add_observer(working_observer)

        # Process update - should not raise despite failing observer
        status = state_manager.process_status_update("TEST123", sample_status_data)

        # Verify status was still processed
        assert status is not None
        assert status.is_online is True

        # Verify working observer was still called
        assert working_observer.called is True
