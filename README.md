# timetracker

A local time tracker that gets smarter the more you use it. A background
collector logs which app/window you're in and how long you've been idle, scores
your sessions for focus quality, classifies them into research modes, and gives
you a weekly digest with actual insights (peak hours, worst day, neglected
modes) — not just "you worked 34 hours."

Everything runs locally. Data lives in one SQLite file in your home dir
(`~/.timetracker/activity.db`). Runs on **Windows, macOS, and Linux**.

## Windows .exe (no Python needed)

A single `timetracker.exe` is built automatically on every push by GitHub
Actions (Windows runner). Get it from:

- **Actions tab** → latest `build-windows` run → **Artifacts** → `timetracker-windows`, or
- a tagged **Release** (push a `v*` tag to attach the exe to a release).

**Just double-click `timetracker.exe`.** With no arguments it sets up the
database, starts the background collector, serves the dashboard, and opens it in
your browser. A console window stays open — leave it open to keep tracking,
close it to stop.

Or run individual commands from a terminal:

```bat
timetracker.exe start          :: same as double-click (collector + dashboard)
timetracker.exe collect        :: collector only
timetracker.exe serve          :: dashboard only
timetracker.exe digest         :: print weekly digest
```

To edit settings next to the exe, drop a `config.local.toml` beside it.

To build it yourself on a Windows machine:

```bat
pip install -r requirements.txt pyinstaller
pyinstaller timetracker.spec --noconfirm
:: result: dist\timetracker.exe
```

(PyInstaller is not a cross-compiler — a Windows exe must be built on Windows.)

## Install (from source)

```bash
python3 -m venv .venv
# Windows:  .venv\Scripts\activate
# mac/linux: source .venv/bin/activate
pip install -r requirements.txt
```

The right OS backend installs automatically:
- macOS may ask for **Accessibility / Screen Recording** permission (needed to
  read window titles). Grant it to your terminal/Python.
- Linux uses X11. Under Wayland it still tracks the app, just not window titles.

## Run

```bash
python -m timetracker.cli init-db      # create the database (once)
python -m timetracker.cli collect      # the background collector — leave it running
```

In another terminal, view your dashboard:

```bash
python -m timetracker.cli serve        # then open http://127.0.0.1:8765
```

Weekly digest:

```bash
python -m timetracker.cli digest               # prints to terminal
python -m timetracker.cli digest --html out.html
```

## Try it without waiting (fake data)

```bash
python -m timetracker.cli seed-fake --minutes 480
python -m timetracker.cli serve
```

## Make it smarter

In the dashboard's "Recent sessions" table, change a session's mode in the
dropdown. The classifier remembers that correction for that app and re-labels
every matching session from then on.

## Configure

Edit `config.toml`, or (better) copy it to `config.local.toml` and change that —
it's gitignored. You can set the poll interval, idle threshold, your timezone,
weekly hour targets per mode, and the app→mode matching rules. Or pass any TOML
file with `--config path.toml`.

## Run it automatically at login (optional)

- **macOS**: a `launchd` plist running `collect`.
- **Linux**: a `systemd --user` service running `collect`.
- **Windows**: Task Scheduler, "at log on", running `collect`.

(Just point it at the venv's Python and `-m timetracker.cli collect`.)
