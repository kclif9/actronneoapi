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
