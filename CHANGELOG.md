# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Inject websession** — `ActronAirAPI` and `ActronAirOAuth2DeviceCodeAuth` now accept
  an optional `session: aiohttp.ClientSession` parameter so callers (e.g. Home Assistant)
  can manage the HTTP session lifecycle externally.
- **Strict typing** — added `py.typed` marker (PEP 561) so downstream consumers get
  inline type information out of the box.
- **`_version.py`** — single-source version module (`actron_neo_api.__version__`).
- **CHANGELOG.md** — this file.
- **`ActronAirIndoorUnit` model** — new model with `nv_auto_fan_enabled`,
  `nv_supported_fan_modes` (bitmap), `nv_model_number`, and a
  `supported_fan_mode_list` property that decodes the bitmap into human-readable
  fan mode strings.
- **`ActronAirOutdoorUnit`** — 13 new fields: `capacity_kw`, `supply_voltage_vac`,
  `supply_current_rms_a`, `supply_power_rms_w`, `coil_temp`,
  `reverse_valve_position`, `defrost_mode`, `drm`, `err_code_1`–`err_code_5`.
- **`ActronAirLiveAircon`** — 4 new fields: `am_running_fan`, `fan_pwm`,
  `coil_inlet`, `err_code`.
- **`ActronAirACSystem`** — `indoor_unit` field referencing `ActronAirIndoorUnit`.
- **`ActronAirZone`** — 8 new fields: `nv_vav`, `nv_itc`, `temperature_setpoint_c`,
  `airflow_setpoint`, `airflow_control_enabled`, `airflow_control_locked`,
  `zone_max_position`, `zone_min_position`; plus a `has_temp_control` property
  (True when both `nv_vav` and `nv_itc` are enabled).
- **`ActronAirPeripheral`** — 4 new fields: `rssi`, `last_connection_time`,
  `connection_state`, `control_capabilities`.
- **`ActronAirStatus`** — 2 new fields: `last_status_update`, `time_since_last_contact`.

### Fixed

- **QuietMode alias** — changed alias from `QuietModeEnabled` to `QuietMode` and added
  a `model_validator` to accept both keys from the API, ensuring backward compatibility.

### Changed

- **Modernised build** — migrated from `setuptools`/`requirements.txt` to
  `hatchling` + `hatch-vcs` with a `uv`-compatible `pyproject.toml`.
  Removed legacy `setup.py`, `requirements.txt`, and `mypy.ini`.
- **Pydantic 2026 best practices** — replaced deprecated `class Config` with
  `model_config = ConfigDict(...)` across all models; use `ConfigDict` imports
  from `pydantic`.
- **mypy strict mode** — enabled `strict = true` with the `pydantic.mypy` plugin
  in `pyproject.toml`.
- **pytest-asyncio** — set `asyncio_mode = "auto"` so async tests no longer need
  the `@pytest.mark.asyncio` decorator.

### Removed

- `setup.py` — no longer needed with `hatchling`.
- `requirements.txt` — dependencies are declared in `pyproject.toml`.
- `mypy.ini` — configuration moved into `pyproject.toml`.
