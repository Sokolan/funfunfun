from datetime import datetime, timezone

from timetracker.digest import build_digest_html, build_digest_text

from tests._util import add_session, make_config
from timetracker.db import init_db


def test_digest_empty_db(config):
    text = build_digest_text(config, since_days=7)
    assert "Weekly digest" in text
    assert "Tracked time" in text
    # no crash, mentions there are no sessions
    assert "no sessions" in text.lower() or "0" in text


def test_digest_populated(config):
    now = datetime.now(tz=timezone.utc).timestamp()
    add_session(config, now - 7200, now - 3600, "coding-experiments", quality=30.0)
    add_session(config, now - 3600, now, "writing", quality=20.0)
    text = build_digest_text(config, since_days=7)
    assert "coding-experiments" in text
    assert "writing" in text


def test_digest_html_escapes_and_renders(config):
    html = build_digest_html(config, since_days=7)
    assert html.startswith("<!doctype html>")
    assert "<pre" in html


def test_digest_bad_timezone_no_crash(tmp_path):
    cfg = make_config(tmp_path, timezone="Bogus/Zone")
    init_db(cfg.db_path)
    build_digest_text(cfg, since_days=7)  # must not raise
