# PyInstaller spec — builds a single timetracker.exe.
# Build on Windows:  pyinstaller timetracker.spec --noconfirm
# (PyInstaller is not a cross-compiler: run it on the OS you want a binary for.)
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# uvicorn/fastapi/starlette load many pieces by string at runtime — pull them all.
hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("fastapi")
    + collect_submodules("starlette")
    + ["win32timezone", "tzdata"]  # pywin32 + zoneinfo's tz database on Windows
)

# Bundle the dashboard, the default config, and the IANA tz database (tzdata is
# a data-only package, so its files must be collected explicitly).
datas = [("static", "static"), ("config.toml", ".")] + collect_data_files("tzdata")

a = Analysis(
    ["run_timetracker.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    # macOS/Linux-only backends won't resolve on a Windows build; that's fine.
    excludes=["AppKit", "Quartz", "Xlib"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="timetracker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,            # it's a CLI: collect / serve / digest
    disable_windowed_traceback=False,
)
# Note: passing a.binaries + a.datas into EXE (and no COLLECT) => single-file exe.
