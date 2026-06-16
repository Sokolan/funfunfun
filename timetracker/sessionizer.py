"""Turn raw event samples into scored sessions.

A session is a contiguous span of activity. It breaks when there is a long gap
between samples or when a sample reports idle >= the threshold. Quality scoring
rewards sustained focus and penalises app-switching and idleness.

``rebuild_sessions`` is idempotent: it wipes the ``sessions`` table and
recomputes everything from ``events`` (plus manual ``feedback`` overrides via the
classifier). Cheap enough for a single-user local DB.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Optional

from .classifier import Classifier
from .config import Config
from .db import get_conn
from .models import Session


def _score(duration_min: float, idle_ratio: float, switches: int) -> float:
    """Quality score for a session.

    q = active_minutes / (1 + switch_rate_penalty)
    where active_minutes discounts idle time and the penalty grows with the
    number of app switches per active minute. Long, focused, single-context
    spans score highest. Bounded below at 0.
    """
    active_min = max(0.0, duration_min * (1.0 - idle_ratio))
    switch_rate = switches / active_min if active_min > 0 else float(switches)
    penalty = switch_rate * 2.0
    return round(active_min / (1.0 + penalty), 3)


def _finalize(samples: list[sqlite3.Row], classifier: Classifier,
              idle_threshold: float) -> Optional[Session]:
    if len(samples) < 1:
        return None

    start_ts = samples[0]["ts"]
    end_ts = samples[-1]["ts"]
    duration_min = max(0.0, (end_ts - start_ts) / 60.0)

    apps = [s["app"] or "unknown" for s in samples]
    app_counts = Counter(apps)
    dominant_app = app_counts.most_common(1)[0][0]

    # App switches: count transitions between consecutive distinct apps.
    switches = sum(1 for a, b in zip(apps, apps[1:]) if a != b)

    # Idle ratio: fraction of samples reporting idle at/above threshold.
    idle_hits = sum(1 for s in samples if s["idle_seconds"] >= idle_threshold)
    idle_ratio = idle_hits / len(samples)

    quality = _score(duration_min, idle_ratio, switches)

    # Fragmented: lots of context switching relative to length.
    switch_rate = switches / duration_min if duration_min > 0 else 0.0
    fragmented = switch_rate > 1.0 or (len(app_counts) >= 4 and duration_min < 10)

    mode = classifier.classify(dominant_app, _dominant_title(samples, dominant_app))

    return Session(
        start_ts=start_ts,
        end_ts=end_ts,
        dominant_app=dominant_app,
        mode=mode,
        quality_score=quality,
        switch_count=switches,
        idle_ratio=round(idle_ratio, 3),
        fragmented=fragmented,
        sample_count=len(samples),
    )


def _dominant_title(samples: list[sqlite3.Row], app: str) -> str:
    titles = Counter(s["title"] for s in samples if s["app"] == app and s["title"])
    return titles.most_common(1)[0][0] if titles else ""


def sessionize(events: list[sqlite3.Row], classifier: Classifier,
               idle_threshold: float, max_gap_seconds: float) -> list[Session]:
    """Pure function: ordered events -> list of sessions."""
    sessions: list[Session] = []
    current: list[sqlite3.Row] = []

    for ev in events:
        if not current:
            current = [ev]
            continue

        gap = ev["ts"] - current[-1]["ts"]
        prev_idle = current[-1]["idle_seconds"] >= idle_threshold
        if gap > max_gap_seconds or prev_idle:
            done = _finalize(current, classifier, idle_threshold)
            if done:
                sessions.append(done)
            current = [ev]
        else:
            current.append(ev)

    done = _finalize(current, classifier, idle_threshold)
    if done:
        sessions.append(done)
    return sessions


def start_periodic_rebuild(config: Config, interval_seconds: int = 60):
    """Rebuild sessions now and every `interval_seconds` in a daemon thread.

    The collector only writes raw events; this keeps the `sessions` table (what
    the dashboard reads) current without the user running `rebuild` by hand.
    Returns the started thread.
    """
    import threading
    import time

    def _loop():
        while True:
            try:
                rebuild_sessions(config)
            except Exception as exc:  # never let the loop die
                print(f"[rebuild] error: {exc!r}", flush=True)
            time.sleep(interval_seconds)

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t


def rebuild_sessions(config: Config) -> int:
    """Recompute the sessions table from events. Returns session count."""
    conn = get_conn(config.db_path)
    try:
        classifier = Classifier.from_db(conn, config)
        events = conn.execute(
            "SELECT ts, app, title, idle_seconds FROM events ORDER BY ts ASC"
        ).fetchall()

        # A break also happens if no sample arrives for a few poll intervals.
        max_gap = max(config.idle_threshold_seconds, config.poll_seconds * 3)
        sessions = sessionize(events, classifier, config.idle_threshold_seconds, max_gap)

        # Atomic swap so concurrent dashboard reads never see an empty table.
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM sessions")
        conn.executemany(
            "INSERT INTO sessions(start_ts, end_ts, dominant_app, mode, "
            "quality_score, switch_count, idle_ratio, fragmented, sample_count) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            [
                (s.start_ts, s.end_ts, s.dominant_app, s.mode, s.quality_score,
                 s.switch_count, s.idle_ratio, int(s.fragmented), s.sample_count)
                for s in sessions
            ],
        )
        conn.execute("COMMIT")
        return len(sessions)
    finally:
        conn.close()
