"""Shared pydantic field normalizers for Actron Air models."""

from __future__ import annotations

from typing import Any


def coerce_identifier_str(value: Any) -> Any:
    """Coerce numeric identifier payloads to strings.

    The cloud sometimes sends identification fields such as ``ModelNumber``
    as numbers (for example ``561``). ``None`` becomes ``""`` and numbers are
    stringified; any other type is returned unchanged so pydantic still
    rejects genuinely malformed values such as lists or dicts.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


def coerce_optional_float(value: Any) -> float | None:
    """Coerce an optional numeric reading to ``float``, or ``None``.

    Diagnostic readings (pressures, temperatures, power) are optional and their
    presence varies by unit family. A missing value, a boolean or anything that
    is not a number becomes ``None`` instead of failing validation, so one odd
    reading never discards the whole live status.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def coerce_optional_bool(value: Any) -> bool | None:
    """Coerce an optional flag to ``bool``, or ``None`` when it is not a flag."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def coerce_optional_str(value: Any) -> str | None:
    """Coerce an optional label to ``str``, or ``None`` when it is not a scalar."""
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value)
