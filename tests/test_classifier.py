import time

from timetracker.classifier import UNKNOWN, Classifier
from timetracker.db import get_conn


def test_rule_match_and_unknown(config):
    conn = get_conn(config.db_path)
    try:
        clf = Classifier.from_db(conn, config)
    finally:
        conn.close()
    assert clf.classify("code", "main.py") == "coding-experiments"
    assert clf.classify("winword", "thesis.docx") == "writing"
    assert clf.classify("zoom", "standup") == "shallow"
    assert clf.classify("somethingweird", "") == UNKNOWN


def test_title_used_when_app_generic(config):
    conn = get_conn(config.db_path)
    try:
        clf = Classifier.from_db(conn, config)
    finally:
        conn.close()
    # app doesn't match any rule, but the title does (arxiv -> reading-papers)
    assert clf.classify("firefox", "arxiv.org 2406.0001") == "reading-papers"


def test_learned_feedback_overrides_rules(config):
    conn = get_conn(config.db_path)
    try:
        conn.execute(
            "INSERT INTO feedback(session_id, app, user_mode, created_ts) "
            "VALUES(?,?,?,?)", (1, "zoom", "reviewing", time.time()))
        clf = Classifier.from_db(conn, config)
    finally:
        conn.close()
    # zoom normally -> shallow, but feedback says reviewing and wins.
    assert clf.classify("zoom", "standup") == "reviewing"


def test_latest_feedback_per_app_wins(config):
    conn = get_conn(config.db_path)
    try:
        conn.execute("INSERT INTO feedback(session_id, app, user_mode, created_ts)"
                     " VALUES(?,?,?,?)", (1, "code", "writing", 1.0))
        conn.execute("INSERT INTO feedback(session_id, app, user_mode, created_ts)"
                     " VALUES(?,?,?,?)", (2, "code", "reviewing", 2.0))
        clf = Classifier.from_db(conn, config)
    finally:
        conn.close()
    assert clf.classify("code", "main.py") == "reviewing"
