"""The insight/scoring layer: aggregate sessions into actual feedback.

Everything works off quality-weighted minutes ("deep-work minutes") rather than
raw duration, so fragmented/idle time counts for less. Times are converted from
UTC to the configured local timezone before bucketing by hour/weekday.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo

from .config import Config
from .db import get_conn

_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _tz(name: str) -> tzinfo:
    # On Windows, zoneinfo has no tz database unless the `tzdata` package is
    # present; fall back to plain UTC (timezone.utc) which never needs data.
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _local(ts: float, tz: tzinfo) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(tz)


def compute_insights(config: Config, since_days: int = 28) -> dict:
    """Return a JSON-friendly dict of aggregates and headline insights."""
    tz = _tz(config.timezone)
    cutoff = datetime.now(tz=timezone.utc).timestamp() - since_days * 86400

    conn = get_conn(config.db_path)
    try:
        rows = conn.execute(
            "SELECT start_ts, end_ts, mode, quality_score, fragmented "
            "FROM sessions WHERE start_ts >= ? ORDER BY start_ts ASC",
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    by_hour = defaultdict(float)       # hour-of-day -> quality minutes
    by_weekday = defaultdict(float)    # 0..6 -> quality minutes
    by_mode_minutes = defaultdict(float)
    by_mode_quality = defaultdict(float)
    total_minutes = 0.0
    total_quality = 0.0
    fragmented_count = 0

    for r in rows:
        local_start = _local(r["start_ts"], tz)
        dur_min = max(0.0, (r["end_ts"] - r["start_ts"]) / 60.0)
        q = r["quality_score"]
        by_hour[local_start.hour] += q
        by_weekday[local_start.weekday()] += q
        by_mode_minutes[r["mode"]] += dur_min
        by_mode_quality[r["mode"]] += q
        total_minutes += dur_min
        total_quality += q
        if r["fragmented"]:
            fragmented_count += 1

    weeks = max(1.0, since_days / 7.0)

    # Headline insights ------------------------------------------------------
    peak_hours = sorted(by_hour.items(), key=lambda kv: kv[1], reverse=True)[:2]
    best_day = max(by_weekday.items(), key=lambda kv: kv[1], default=(None, 0))
    worst_day = min(by_weekday.items(), key=lambda kv: kv[1], default=(None, 0))

    # Neglected modes: actual weekly hours vs configured target.
    neglected = []
    for mode, target in config.targets.items():
        if target <= 0:
            continue
        actual_weekly = (by_mode_minutes.get(mode, 0.0) / 60.0) / weeks
        if actual_weekly < target * 0.6:  # >40% under target
            neglected.append({
                "mode": mode,
                "actual_weekly_hours": round(actual_weekly, 1),
                "target_weekly_hours": target,
            })

    return {
        "window_days": since_days,
        "totals": {
            "tracked_hours": round(total_minutes / 60.0, 1),
            "deep_work_hours": round(total_quality / 60.0, 1),
            "session_count": len(rows),
            "fragmented_sessions": fragmented_count,
        },
        "by_hour": {str(h): round(by_hour.get(h, 0.0), 1) for h in range(24)},
        "by_weekday": {
            _WEEKDAYS[d]: round(by_weekday.get(d, 0.0), 1) for d in range(7)
        },
        "by_mode": {
            m: {
                "tracked_hours": round(by_mode_minutes[m] / 60.0, 1),
                "deep_work_hours": round(by_mode_quality[m] / 60.0, 1),
            }
            for m in sorted(by_mode_minutes)
        },
        "headlines": {
            "peak_hours": [
                {"hour": h, "deep_work_minutes": round(v, 1)} for h, v in peak_hours
            ],
            "best_day": _WEEKDAYS[best_day[0]] if best_day[0] is not None else None,
            "worst_day": _WEEKDAYS[worst_day[0]] if worst_day[0] is not None else None,
            "neglected_modes": neglected,
        },
    }
