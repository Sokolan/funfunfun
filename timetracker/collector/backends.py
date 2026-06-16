"""OS-specific foreground-window + idle backends.

Each backend exposes ``name`` and ``sample(host) -> Sample | None``. Heavy OS
modules are imported lazily inside each backend so importing this file never
fails on the "wrong" platform. ``get_backend("auto")`` picks by ``sys.platform``.
"""
from __future__ import annotations

import random
import sys
import time
from typing import Optional

from ..models import Sample


class Backend:
    name = "base"

    def sample(self, host: str) -> Optional[Sample]:  # pragma: no cover - interface
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Windows
# --------------------------------------------------------------------------- #
class WindowsBackend(Backend):
    name = "windows"

    def __init__(self) -> None:
        import win32gui  # noqa: F401  (validate availability early)
        import win32process  # noqa: F401
        import psutil  # noqa: F401

    def sample(self, host: str) -> Optional[Sample]:
        import ctypes
        from ctypes import wintypes

        import psutil
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(hwnd) if hwnd else ""
        app = ""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid:
                app = psutil.Process(pid).name()
        except Exception:
            app = ""

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
        millis = ctypes.windll.kernel32.GetTickCount() - info.dwTime
        idle = max(0.0, millis / 1000.0)

        return Sample(time.time(), app.lower(), title, idle, host)


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #
class MacBackend(Backend):
    name = "macos"

    def __init__(self) -> None:
        from AppKit import NSWorkspace  # noqa: F401
        import Quartz  # noqa: F401

    def sample(self, host: str) -> Optional[Sample]:
        from AppKit import NSWorkspace
        import Quartz

        ws = NSWorkspace.sharedWorkspace()
        active = ws.frontmostApplication()
        app = (active.localizedName() or "") if active else ""
        pid = active.processIdentifier() if active else -1

        # Window title of the frontmost app's frontmost window (best effort;
        # requires Screen Recording permission on recent macOS, else stays "").
        title = ""
        try:
            opts = (Quartz.kCGWindowListOptionOnScreenOnly
                    | Quartz.kCGWindowListExcludeDesktopElements)
            for win in Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID):
                if win.get("kCGWindowOwnerPID") == pid:
                    name = win.get("kCGWindowName") or ""
                    if name:
                        title = name
                        break
        except Exception:
            title = ""

        # Idle = seconds since last input across all HID event types.
        idle = Quartz.CGEventSourceSecondsSinceLastEventType(
            Quartz.kCGEventSourceStateCombinedSessionState,
            Quartz.kCGAnyInputEventType,
        )
        return Sample(time.time(), app.lower(), title, float(idle), host)


# --------------------------------------------------------------------------- #
# Linux / X11
# --------------------------------------------------------------------------- #
class LinuxBackend(Backend):
    name = "linux"

    def __init__(self) -> None:
        from Xlib import display  # noqa: F401
        self._disp = None

    def _display(self):
        from Xlib import display
        if self._disp is None:
            self._disp = display.Display()
        return self._disp

    def sample(self, host: str) -> Optional[Sample]:
        from Xlib import X

        disp = self._display()
        root = disp.screen().root

        net_active = disp.intern_atom("_NET_ACTIVE_WINDOW")
        net_name = disp.intern_atom("_NET_WM_NAME")
        utf8 = disp.intern_atom("UTF8_STRING")
        wm_class = disp.intern_atom("WM_CLASS")

        app, title = "", ""
        try:
            active = root.get_full_property(net_active, X.AnyPropertyType)
            if active and active.value:
                win = disp.create_resource_object("window", active.value[0])
                name_prop = win.get_full_property(net_name, utf8)
                if name_prop:
                    title = _decode(name_prop.value)
                cls_prop = win.get_full_property(wm_class, X.AnyPropertyType)
                if cls_prop:
                    parts = _decode(cls_prop.value).split("\x00")
                    app = next((p for p in parts if p), "")
        except Exception:
            pass

        idle = self._idle_seconds(disp)
        return Sample(time.time(), app.lower(), title, idle, host)

    @staticmethod
    def _idle_seconds(disp) -> float:
        # MIT-SCREEN-SAVER reports ms since last input. Auto-loaded by python-xlib
        # when present; absent under Wayland/headless, where we degrade to 0.
        try:
            si = disp.screen().root.xss_query_info()
            return max(0.0, si.idle / 1000.0)
        except Exception:
            return 0.0


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# --------------------------------------------------------------------------- #
# Fake (dev/testing on any OS, incl. inside WSL)
# --------------------------------------------------------------------------- #
class FakeBackend(Backend):
    name = "fake"

    _APPS = [
        ("code", "main.py - timetracker - VSCode"),
        ("python", "experiment_run.py"),
        ("firefox", "arxiv.org 2406.12345 attention.pdf"),
        ("zoom", "Weekly sync - Zoom Meeting"),
        ("winword", "thesis_chapter3.docx - Word"),
        ("slack", "lab-channel - Slack"),
    ]

    def __init__(self) -> None:
        self._i = 0

    def sample(self, host: str) -> Optional[Sample]:
        # Stay on one app for a while (sticky), switch rarely, idle rarely.
        if random.random() < 0.04:
            self._i = random.randrange(len(self._APPS))
        app, title = self._APPS[self._i]
        idle = random.uniform(350, 600) if random.random() < 0.03 else 0.0
        return Sample(time.time(), app, title, idle, host)


def get_backend(name: str) -> Backend:
    """Resolve and instantiate a backend. ``auto`` picks by platform."""
    name = (name or "auto").lower()
    if name == "auto":
        if sys.platform.startswith("win"):
            name = "windows"
        elif sys.platform == "darwin":
            name = "macos"
        elif sys.platform.startswith("linux"):
            name = "linux"
        else:
            name = "fake"

    table = {
        "windows": WindowsBackend,
        "macos": MacBackend,
        "linux": LinuxBackend,
        "fake": FakeBackend,
    }
    if name not in table:
        raise ValueError(f"unknown collector backend: {name!r}")

    try:
        return table[name]()
    except Exception as exc:
        raise RuntimeError(
            f"collector backend {name!r} failed to initialise ({exc!r}). "
            f"Install its dependencies (see requirements.txt) or set "
            f"collector.backend = \"fake\" in config.local.toml for testing."
        ) from exc
