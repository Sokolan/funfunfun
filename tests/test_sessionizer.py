from timetracker.sessionizer import rebuild_sessions
from timetracker.db import get_conn

from tests._util import BASE_TS, add_events, steady_block


def _sessions(config):
    conn = get_conn(config.db_path)
    try:
        return conn.execute(
            "SELECT * FROM sessions ORDER BY start_ts").fetchall()
    finally:
        conn.close()


def test_empty_events_no_sessions(config):
    assert rebuild_sessions(config) == 0
    assert _sessions(config) == []


def test_gap_splits_into_two_sessions(config):
    evs = steady_block(BASE_TS, "code", "main.py", 30)            # 0..290s
    evs += steady_block(BASE_TS + 5000, "winword", "thesis", 30)  # big gap
    add_events(config, evs)
    n = rebuild_sessions(config)
    assert n == 2
    s = _sessions(config)
    assert s[0]["mode"] == "coding-experiments"
    assert s[1]["mode"] == "writing"


def test_idle_splits_session(config):
    evs = steady_block(BASE_TS, "code", "main.py", 10)
    evs.append((BASE_TS + 100, "code", "main.py", 999))  # idle >= threshold
    evs += steady_block(BASE_TS + 110, "code", "main.py", 10)
    add_events(config, evs)
    n = rebuild_sessions(config)
    assert n >= 2


def test_quality_focused_beats_fragmented(config, tmp_path):
    # Focused: one app, long, no idle.
    add_events(config, steady_block(BASE_TS, "code", "main.py", 60))
    rebuild_sessions(config)
    focused_q = _sessions(config)[0]["quality_score"]

    # Fragmented: alternating apps, same length.
    from tests._util import make_config
    from timetracker.db import init_db
    cfg2 = make_config(tmp_path / "frag")
    init_db(cfg2.db_path)
    apps = ["code", "zoom", "slack", "winword"]
    evs = [(BASE_TS + i * 10, apps[i % len(apps)], "t", 0.0) for i in range(60)]
    add_events(cfg2, evs)
    rebuild_sessions(cfg2)
    frag = _sessions(cfg2)[0]

    assert focused_q > frag["quality_score"]
    assert frag["switch_count"] > 0
    assert bool(frag["fragmented"]) is True


def test_session_metrics_columns(config):
    add_events(config, steady_block(BASE_TS, "code", "main.py", 20))
    rebuild_sessions(config)
    s = _sessions(config)[0]
    assert s["dominant_app"] == "code"
    assert s["sample_count"] == 20
    assert 0.0 <= s["idle_ratio"] <= 1.0
