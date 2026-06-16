from datetime import datetime, timezone

from timetracker.insights import _tz, compute_insights

from tests._util import add_session, make_config
from timetracker.db import init_db


def test_tz_fallback_on_bad_name():
    # The Windows-crash path: bad/unknown zone must not raise.
    assert _tz("Not/AReal_Zone") is timezone.utc


def test_tz_valid_name():
    tz = _tz("Europe/Berlin")
    # Either real ZoneInfo (tzdata present) or UTC fallback — never a crash.
    assert tz is not None


def test_insights_empty_db_no_crash(config):
    ins = compute_insights(config, since_days=28)
    assert ins["totals"]["session_count"] == 0
    assert ins["totals"]["tracked_hours"] == 0.0
    assert ins["headlines"]["best_day"] is None
    assert ins["headlines"]["worst_day"] is None
    assert len(ins["by_hour"]) == 24
    assert len(ins["by_weekday"]) == 7


def test_insights_empty_db_bad_timezone_no_crash(tmp_path):
    cfg = make_config(tmp_path, timezone="Bogus/Zone")
    init_db(cfg.db_path)
    ins = compute_insights(cfg, since_days=28)  # must not raise
    assert ins["totals"]["session_count"] == 0


def test_insights_aggregates_and_peak(config):
    # Build a clear 10:00 local peak on a Tuesday-equivalent day.
    now = datetime.now(tz=timezone.utc).timestamp()
    day = now - 3 * 86400
    # Three sessions at the same hour, high quality.
    for i in range(3):
        add_session(config, day + i * 3600, day + i * 3600 + 1800,
                    "coding-experiments", quality=20.0)
    ins = compute_insights(config, since_days=28)
    assert ins["totals"]["session_count"] == 3
    assert ins["totals"]["deep_work_hours"] > 0
    assert ins["headlines"]["best_day"] is not None
    assert "coding-experiments" in ins["by_mode"]


def test_neglected_modes_flagged(config):
    # No writing logged at all -> below its target of 8h/wk.
    now = datetime.now(tz=timezone.utc).timestamp()
    add_session(config, now - 3600, now, "coding-experiments", quality=20.0)
    ins = compute_insights(config, since_days=7)
    neglected = {n["mode"] for n in ins["headlines"]["neglected_modes"]}
    assert "writing" in neglected
