"""Tests for schema models module.

This tests the schema model re-exports for backward compatibility.
"""

from actron_neo_api.models import schemas


def test_actron_air_zone_export() -> None:
    """Test ActronAirZone is exported."""
    assert hasattr(schemas, "ActronAirZone")
    assert schemas.ActronAirZone.__name__ == "ActronAirZone"


def test_actron_air_zone_sensor_export() -> None:
    """Test ActronAirZoneSensor is exported."""
    assert hasattr(schemas, "ActronAirZoneSensor")
    assert schemas.ActronAirZoneSensor.__name__ == "ActronAirZoneSensor"


def test_actron_air_user_aircon_settings_export() -> None:
    """Test ActronAirUserAirconSettings is exported."""
    assert hasattr(schemas, "ActronAirUserAirconSettings")
    assert schemas.ActronAirUserAirconSettings.__name__ == "ActronAirUserAirconSettings"


def test_actron_air_live_aircon_export() -> None:
    """Test ActronAirLiveAircon is exported."""
    assert hasattr(schemas, "ActronAirLiveAircon")
    assert schemas.ActronAirLiveAircon.__name__ == "ActronAirLiveAircon"


def test_actron_air_master_info_export() -> None:
    """Test ActronAirMasterInfo is exported."""
    assert hasattr(schemas, "ActronAirMasterInfo")
    assert schemas.ActronAirMasterInfo.__name__ == "ActronAirMasterInfo"


def test_actron_air_ac_system_export() -> None:
    """Test ActronAirACSystem is exported."""
    assert hasattr(schemas, "ActronAirACSystem")
    assert schemas.ActronAirACSystem.__name__ == "ActronAirACSystem"


def test_actron_air_status_export() -> None:
    """Test ActronAirStatus is exported."""
    assert hasattr(schemas, "ActronAirStatus")
    assert schemas.ActronAirStatus.__name__ == "ActronAirStatus"


def test_all_exports_present() -> None:
    """Test that __all__ contains expected exports."""
    expected_exports = [
        "ActronAirZone",
        "ActronAirZoneSensor",
        "ActronAirUserAirconSettings",
        "ActronAirLiveAircon",
        "ActronAirMasterInfo",
        "ActronAirACSystem",
        "ActronAirStatus",
    ]

    assert hasattr(schemas, "__all__")
    for export in expected_exports:
        assert export in schemas.__all__
