import os

from timetracker.config import _deep_merge, load_config
from timetracker.db import get_conn, init_db


def test_init_db_idempotent_and_tables(tmp_path):
    db = tmp_path / "a.db"
    init_db(db)
    init_db(db)  # second call must not fail
    conn = get_conn(db)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert {"events", "sessions", "feedback", "meta"} <= names


def test_get_conn_creates_parent_dir(tmp_path):
    db = tmp_path / "nested" / "deep" / "a.db"
    conn = get_conn(db)
    conn.close()
    assert db.exists()


def test_deep_merge_nested():
    base = {"a": {"x": 1, "y": 2}, "b": 1}
    override = {"a": {"y": 9}, "c": 3}
    assert _deep_merge(base, override) == {"a": {"x": 1, "y": 9}, "b": 1, "c": 3}


def test_load_config_defaults_expand_home():
    cfg = load_config()
    assert os.path.isabs(str(cfg.db_path))
    assert "~" not in str(cfg.db_path)
    assert cfg.rules  # shipped rules parsed
    assert cfg.poll_seconds > 0


def test_load_config_override(tmp_path):
    override = tmp_path / "o.toml"
    override.write_text(
        '[collector]\npoll_seconds = 99\n[storage]\ndb_path = "/tmp/x.db"\n')
    cfg = load_config(override)
    assert cfg.poll_seconds == 99
    assert str(cfg.db_path) == "/tmp/x.db"
