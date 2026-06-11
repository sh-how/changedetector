"""Profile management: named sets of watched areas inside one config file.

A config either has a flat ``watchers:`` list (one implicit profile named
"default") or a ``profiles:`` mapping plus ``active_profile``. Global settings
(capture/detection/alert/runtime) are shared across profiles. These functions
are pure file operations so the CLI and tray share one implementation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

IMPLICIT_NAME = "default"


def _read(path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _write(path, data: dict) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def _is_flat(data: dict) -> bool:
    """A pre-profiles config: flat watchers/region, no profiles mapping."""
    return "profiles" not in data and ("watchers" in data or "region" in data)


def resolve_active(data: dict) -> Optional[str]:
    """The active profile name for a parsed config dict (None if no profiles)."""
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and profiles:
        active = data.get("active_profile")
        return active if active in profiles else next(iter(profiles))
    if _is_flat(data):
        return IMPLICIT_NAME
    return None


def read_profiles(config_path) -> tuple:
    """Return (profile names, active name). Flat configs read as (['default'], 'default')."""
    data = _read(config_path)
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and profiles:
        return list(profiles.keys()), resolve_active(data)
    if _is_flat(data):
        return [IMPLICIT_NAME], IMPLICIT_NAME
    return [], None


def _migrate_flat(data: dict) -> dict:
    """Move a flat watchers/region config under profiles[IMPLICIT_NAME]."""
    if not _is_flat(data):
        return data
    watchers = data.pop("watchers", None)
    region = data.pop("region", None)
    if watchers is None:
        watchers = [{"name": IMPLICIT_NAME, "region": region}] if region else []
    data["profiles"] = {IMPLICIT_NAME: {"watchers": watchers}}
    data["active_profile"] = IMPLICIT_NAME
    return data


def create_profile(config_path, name: str) -> str:
    """Create an empty profile and make it active. Returns "created" or "exists"."""
    data = _read(config_path)
    names, _ = read_profiles(config_path)
    if name in names:
        return "exists"
    data = _migrate_flat(data)
    data.setdefault("profiles", {})[name] = {"watchers": []}
    data["active_profile"] = name
    _write(config_path, data)
    return "created"


def switch_profile(config_path, name: str) -> str:
    """Make ``name`` the active profile. "switched" | "already_active" | "not_found"."""
    data = _read(config_path)
    names, active = read_profiles(config_path)
    if name not in names:
        return "not_found"
    if name == active:
        return "already_active"
    data = _migrate_flat(data)
    data["active_profile"] = name
    _write(config_path, data)
    return "switched"


def delete_profile(config_path, name: str) -> tuple:
    """Delete a profile. Returns (status, new_active):

    ("deleted", None)        - inactive profile removed
    ("deleted", new_active)  - active profile removed; switched to new_active
    ("last", None)           - refused: it's the only profile
    ("not_found", None)      - no such profile
    """
    data = _read(config_path)
    names, active = read_profiles(config_path)
    if name not in names:
        return ("not_found", None)
    if len(names) <= 1:
        return ("last", None)
    data = _migrate_flat(data)
    del data["profiles"][name]
    new_active = None
    if name == active:
        new_active = next(iter(data["profiles"]))
        data["active_profile"] = new_active
    _write(config_path, data)
    return ("deleted", new_active)
