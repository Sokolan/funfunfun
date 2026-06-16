"""Path resolution that works both in dev and inside a PyInstaller exe.

When frozen, bundled data (static/, config.toml) lives under sys._MEIPASS, while
user-writable files (config.local.toml) live next to the .exe.
"""
from __future__ import annotations

import sys
from pathlib import Path


def bundle_root() -> Path:
    """Directory holding bundled read-only resources."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def app_dir() -> Path:
    """Writable directory for user overrides (next to the exe, or repo root)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent
