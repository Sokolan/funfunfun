# PLAN — Self-instructions (Claude only). User does not read this.

## What this project is
A local activity/time tracker that gets smarter with use. Daemon logs activity → SQLite → web UI for review/config → weekly digest with real insights. PhD-specific "modes" (writing / coding-experiments / reading-papers / reviewing). Calendar integration to protect focus blocks. Inference layer is the actual product: session quality, circadian patterns, deep-work vs shallow classification.

## ENVIRONMENT / PLATFORM (UPDATED 2026-06-16: must run on Windows, macOS, Linux)
- Repo developed in WSL (`/home/sokolan/repos/ShokoHadar`) but the app must be **cross-platform**.
- Collector active-window + idle detection is OS-specific → **backend abstraction**:
  - Windows: `pywin32` (`GetForegroundWindow`/`GetWindowText`) + `GetLastInputInfo` idle.
  - macOS: `pyobjc` (`NSWorkspace.frontmostApplication`, Quartz `CGWindowListCopyWindowInfo`) + `CGEventSourceSecondsSinceLastEventType` idle. (Needs Accessibility/Screen-Recording permission for titles.)
  - Linux/X11: `python-xlib` (active window + `_NET_WM_NAME`) + XScreenSaver idle. Wayland: degrade gracefully (app only, no title).
  - `fake`: synthetic data for dev/testing on any OS (incl. inside WSL).
- Backend chosen by `config.collector.backend = auto|windows|macos|linux|fake` (`auto` = pick by `sys.platform`).
- NOTE re WSL: a collector running *inside* WSL only sees WSL processes, not host GUI apps. That's fine — on each real machine the user runs the native collector. No shared `/mnt/c` DB anymore.
- DB is **per-machine**, in home dir: `~/.timetracker/activity.db` (expanduser, cross-platform). `host` column distinguishes machines if DBs are ever merged.

## Tech stack (decided on merits — do not re-litigate)
- Language: **Python** (3.10+; targets 3.11 stdlib `tomllib` with `tomli` fallback). Chosen because the riskiest component — cross-platform foreground-window + idle detection — has the most mature, battle-tested libraries in Python (`pywin32`, `pyobjc`, `python-xlib`, `psutil`). The rest is glue + an insight layer + a small web UI where dev velocity dominates and runtime perf is irrelevant (one poll per ~10s into tiny SQLite). NOT chosen for "user doesn't want to learn."
- Runner-up was Go (single-binary daemon distribution); rejected because its cross-OS active-window/idle support is patchy (esp. Linux/Wayland), forcing hand-written cgo bindings on exactly the risky part. Rust/C/C++: no perf need to justify the ceremony.
- Storage: **SQLite** (stdlib `sqlite3`).
- Web UI: **FastAPI** + a single static HTML/JS page (Chart.js via CDN). No build step, no node.
- Scheduling for digest: simplest thing that works (a `--digest` CLI run + Windows Task Scheduler / cron). Do NOT build a custom scheduler.
- Dependencies kept minimal: `fastapi`, `uvicorn`, `psutil`, `pywin32` (Windows collector only). Use a `requirements.txt`.

## Repo layout to create
```
timetracker/
  __init__.py
  db.py            # schema + connection helpers + migrations
  collector.py     # Windows-host: poll foreground window + idle, write events
  models.py        # dataclasses for Event, Session, Mode
  sessionizer.py   # raw events -> sessions (gap-based segmentation + quality score)
  classifier.py    # session -> mode (heuristics first, learning later)
  insights.py      # circadian patterns, best/worst day, neglected modes
  digest.py        # build weekly digest text/html
  web.py           # FastAPI app: serve API + static page
  cli.py           # entrypoints: collect / serve / digest / init-db
static/
  index.html       # dashboard (Chart.js from CDN)
config.toml         # user config: db path, modes, app->mode mapping, idle threshold
requirements.txt
README.md           # short user-facing run instructions (this is what the USER reads)
```

## Data model (SQLite)
- `events`: id, ts (unix, UTC), active_app (exe name), window_title, idle_seconds, host. Raw poll samples (~ every 5–15s).
- `sessions`: id, start_ts, end_ts, dominant_app, mode, quality_score, switch_count, idle_ratio, fragmented (bool). Derived.
- `mode_rules`: pattern (app/title regex) -> mode, weight. For classifier + manual overrides.
- `feedback`: session_id, user_mode (manual correction) — this is the data that makes classifier "learn".
- Store all timestamps UTC; convert to local (Europe/Berlin, RWTH) only at display/digest time.

## Build order (do these in sequence; each step must run before moving on)
1. **Scaffold**: create repo layout, `requirements.txt`, `config.toml` with sane defaults, empty modules. Commit nothing (repo is not git — `git init` only if user asks).
2. **db.py**: schema creation + `get_conn(path)` + idempotent `init_db()`. Make `cli.py init-db` work and verify the file/tables are created.
3. **collector.py**: Windows poll loop. Foreground window via `win32gui.GetForegroundWindow` + `GetWindowText`; exe via `psutil`; idle via `GetLastInputInfo`. Write one `events` row per tick. Make it survive errors (never crash the loop). Verify by running a few minutes and querying rows.
   - Provide a **WSL fallback collector mode** behind a flag for testing without Windows (logs active process / fakes data) so the rest of the pipeline is testable in WSL.
4. **sessionizer.py**: group events into sessions by inactivity gap (default 5 min idle/no-events ends a session). Compute: duration, switch_count (distinct app switches), idle_ratio, fragmented flag, quality_score (define formula: high focus = long, low switches, low idle; penalize fragmentation). Pure function over events → idempotent rebuild of `sessions`.
5. **classifier.py**: heuristic mapping app/title → mode using `mode_rules` (e.g. Word/LaTeX→writing, VSCode/terminal→coding-experiments, browser+PDF/arxiv→reading-papers, mail/Zoom/Teams→shallow/meeting). Apply manual `feedback` overrides on top. (Learning = later: weight rules by feedback frequency. Keep interface stable.)
6. **insights.py**: aggregate sessions → per-hour and per-weekday productivity (sum of quality-weighted deep-work minutes), identify peak hours, worst day, and which modes are under-served vs target. Return plain dicts.
7. **web.py + static/index.html**: FastAPI endpoints (`/api/sessions`, `/api/insights`, `/api/config`, POST `/api/feedback` to correct a session's mode). Single HTML page with charts (daily timeline, weekly heatmap, mode breakdown) + a way to relabel a session (feeds `feedback`). `cli.py serve` launches uvicorn.
8. **digest.py**: build a weekly summary (real insights, not just total hours): peak/worst times, deep-work hours, neglected modes, focus-block protection suggestions. Output as text + simple HTML. `cli.py digest` prints it / writes a file. Email/notification = optional later; do not block on SMTP.
9. **Calendar integration (LAST, optional)**: Google Calendar read-only via `google-api-python-client` to mark seminar/meeting blocks and auto-protect remaining focus time. Gate behind config flag; everything must work without it. RWTH cal is likely also Google/Exchange — confirm with user before building.

## Insight/scoring layer notes (this is the "interesting" part, per the idea)
- quality_score formula (start simple, document it): `q = duration_min * (1 - idle_ratio) / (1 + switch_penalty)` where switch_penalty grows with app switches per minute. Tune later with real data.
- "fragmented" = many short sessions of same intended mode broken by switches.
- Circadian: bucket quality-weighted minutes by local hour-of-day and weekday over trailing N weeks; surface top/bottom buckets.
- "Learning": the only real learning loop initially is `feedback` reweighting `mode_rules`. Don't oversell ML; heuristics + feedback first. Note this honestly.

## DECISIONS TO CONFIRM WITH USER BEFORE CODING (only ask what blocks progress)
- ~~Collector scope~~ **DECIDED 2026-06-16: track ALL Windows activity. Collector runs on Windows host (pywin32/psutil/GetLastInputInfo). WSL fake-data fallback is for testing only.**
- Windows username (for default DB path) — can defer until step 2/3.
- Everything else: pick the default above and proceed. Do not ask preference questions the user will find annoying.

## Rules for execution (per CLAUDE.md)
- User vibecodes, won't learn, wants blunt no-fluff communication. Don't explain concepts. Just build and report status.
- README.md is the ONLY user-facing doc: dead-simple run commands (`pip install -r requirements.txt`, `python -m timetracker.cli collect`, `... serve`, `... digest`). No theory.
- Make no assumptions about git; repo is currently not a git repo.
- Verify each step actually runs before claiming it's done.
```
