"""SQLite schema and connection helpers.

All timestamps are stored as unix epoch seconds in UTC. Conversion to local
time happens only at display/digest time.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    app          TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    idle_seconds REAL NOT NULL DEFAULT 0,
    host         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    start_ts      REAL NOT NULL,
    end_ts        REAL NOT NULL,
    dominant_app  TEXT NOT NULL,
    mode          TEXT NOT NULL,
    quality_score REAL NOT NULL,
    switch_count  INTEGER NOT NULL,
    idle_ratio    REAL NOT NULL,
    fragmented    INTEGER NOT NULL,
    sample_count  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_ts);

-- Manual corrections. Keyed by the session's dominant app so the correction
-- generalises and survives session rebuilds (session ids are regenerated each
-- rebuild). The latest correction per app wins and overrides the regex rules.
CREATE TABLE IF NOT EXISTS feedback (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    app        TEXT NOT NULL,
    user_mode  TEXT NOT NULL,
    created_ts REAL NOT NULL
);
"""


def get_conn(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection, ensuring the parent directory exists."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: str | Path) -> None:
    """Create tables if missing. Idempotent."""
    conn = get_conn(db_path)
    try:
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(SCHEMA_VERSION),),
        )
    finally:
        conn.close()
