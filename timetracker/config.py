"""Configuration loading.

Loads TOML config with sane shipped defaults, merges an optional override file,
and exposes a small typed accessor. Works on Python 3.10 (tomli) and 3.11+
(stdlib tomllib).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib as _toml
except ModuleNotFoundError:  # Python 3.10 and earlier
    import tomli as _toml  # type: ignore

from ._paths import app_dir, bundle_root

# Shipped defaults travel with the package/exe; the local override lives next to
# the exe (or repo root in dev) so users can edit it.
DEFAULT_CONFIG_PATH = bundle_root() / "config.toml"
LOCAL_CONFIG_PATH = app_dir() / "config.local.toml"


@dataclass
class Rule:
    pattern: str
    mode: str


@dataclass
class Config:
    db_path: Path
    backend: str
    poll_seconds: int
    idle_threshold_seconds: int
    timezone: str
    targets: dict[str, float]
    rules: list[Rule] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def _read_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return _toml.load(fh)


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load defaults, then layer config.local.toml, then an explicit --config path."""
    data = _read_toml(DEFAULT_CONFIG_PATH)
    if LOCAL_CONFIG_PATH.exists():
        data = _deep_merge(data, _read_toml(LOCAL_CONFIG_PATH))
    if path:
        data = _deep_merge(data, _read_toml(Path(path)))

    storage = data.get("storage", {})
    collector = data.get("collector", {})
    display = data.get("display", {})

    db_path = Path(os.path.expanduser(storage.get("db_path", "~/.timetracker/activity.db")))

    rules = [Rule(pattern=r["pattern"], mode=r["mode"]) for r in data.get("rules", [])]

    return Config(
        db_path=db_path,
        backend=collector.get("backend", "auto"),
        poll_seconds=int(collector.get("poll_seconds", 10)),
        idle_threshold_seconds=int(collector.get("idle_threshold_seconds", 300)),
        timezone=display.get("timezone", "UTC"),
        targets={str(k): float(v) for k, v in data.get("targets", {}).items()},
        rules=rules,
        raw=data,
    )
