"""Shared test helpers: build a Config and seed events/sessions directly."""
from __future__ import annotations

from pathlib import Path

from timetracker.config import Config, Rule
from timetracker.db import get_conn

BASE_TS = 1_700_000_000  # fixed epoch for deterministic tests


def make_config(tmp_path: Path, timezone: str = "Europe/Berlin",
                targets=None, rules=None) -> Config:
    return Config(
        db_path=tmp_path / "activity.db",
        backend="fake",
        poll_seconds=10,
        idle_threshold_seconds=300,
        timezone=timezone,
        targets=targets if targets is not None
        else {"writing": 8, "coding-experiments": 10, "reading-papers": 6,
              "reviewing": 3, "shallow": 0},
        rules=rules if rules is not None else [
            Rule(r"winword|\.tex|overleaf", "writing"),
            Rule(r"code|python|terminal|jupyter", "coding-experiments"),
            Rule(r"arxiv|\.pdf|zotero", "reading-papers"),
            Rule(r"github|review", "reviewing"),
            Rule(r"zoom|slack|mail|teams", "shallow"),
        ],
        raw={},
    )


def add_events(config: Config, samples) -> None:
    """samples: iterable of (ts, app, title, idle_seconds)."""
    conn = get_conn(config.db_path)
    try:
        conn.executemany(
            "INSERT INTO events(ts, app, title, idle_seconds, host) VALUES(?,?,?,?,?)",
            [(ts, app, title, idle, "test") for ts, app, title, idle in samples],
        )
    finally:
        conn.close()


def add_session(config: Config, start_ts, end_ts, mode, quality=10.0,
                dominant_app="code", switch_count=0, idle_ratio=0.0,
                fragmented=0, sample_count=10) -> None:
    conn = get_conn(config.db_path)
    try:
        conn.execute(
            "INSERT INTO sessions(start_ts, end_ts, dominant_app, mode, "
            "quality_score, switch_count, idle_ratio, fragmented, sample_count) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (start_ts, end_ts, dominant_app, mode, quality, switch_count,
             idle_ratio, fragmented, sample_count),
        )
    finally:
        conn.close()


def steady_block(start_ts, app, title, count, step=10, idle=0.0):
    """Generate `count` events for one app at `step` spacing."""
    return [(start_ts + i * step, app, title, idle) for i in range(count)]
