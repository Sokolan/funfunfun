from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from timetracker.db import get_conn
from timetracker.web import create_app

from tests._util import BASE_TS, add_events, add_session, steady_block


@pytest.fixture
def client(config):
    return TestClient(create_app(config))


def test_all_endpoints_empty_db(client):
    # The exact scenario a fresh user hits before any data exists.
    for path in ["/", "/api/config", "/api/insights?days=28",
                 "/api/sessions", "/api/digest?days=7"]:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text}"


def test_insights_with_data(client, config):
    now = datetime.now(tz=timezone.utc).timestamp()
    add_session(config, now - 3600, now, "coding-experiments", quality=20.0)
    r = client.get("/api/insights?days=28")
    assert r.status_code == 200
    assert r.json()["totals"]["session_count"] == 1


def test_config_endpoint_lists_modes(client):
    data = client.get("/api/config").json()
    assert "coding-experiments" in data["modes"]
    assert "unknown" in data["modes"]
    assert "timezone" in data


def test_feedback_updates_and_generalizes(client, config):
    # Two sessions of the same app; correcting one must relabel both on rebuild.
    add_events(config, steady_block(BASE_TS, "zoom", "standup", 30))
    add_events(config, steady_block(BASE_TS + 5000, "zoom", "1:1", 30))
    from timetracker.sessionizer import rebuild_sessions
    rebuild_sessions(config)

    sid = client.get("/api/sessions?limit=1").json()[0]["id"]
    r = client.post("/api/feedback", json={"session_id": sid, "mode": "reviewing"})
    assert r.status_code == 200 and r.json()["ok"] is True

    conn = get_conn(config.db_path)
    try:
        rows = conn.execute(
            "SELECT mode FROM sessions WHERE dominant_app='zoom'").fetchall()
    finally:
        conn.close()
    assert rows and all(row["mode"] == "reviewing" for row in rows)


def test_feedback_bad_session_id_404(client):
    r = client.post("/api/feedback", json={"session_id": 999999, "mode": "writing"})
    assert r.status_code == 404
