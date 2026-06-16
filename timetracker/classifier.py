"""Map a session's app/title to a research mode.

Priority:
  1. Learned overrides from user feedback (per app) — this is the "gets smarter"
     loop: correct a session once and every session dominated by that app
     follows.
  2. Regex rules from config (first match wins).
  3. Fallback "unknown".
"""
from __future__ import annotations

import re
import sqlite3

from .config import Config

UNKNOWN = "unknown"


class Classifier:
    def __init__(self, rules, learned: dict[str, str]):
        # Pre-compile rules once.
        self._rules = [(re.compile(r.pattern, re.IGNORECASE), r.mode) for r in rules]
        self._learned = learned

    @classmethod
    def from_db(cls, conn: sqlite3.Connection, config: Config) -> "Classifier":
        """Build a classifier from config rules + latest feedback per app."""
        learned: dict[str, str] = {}
        rows = conn.execute(
            "SELECT app, user_mode FROM feedback "
            "WHERE id IN (SELECT MAX(id) FROM feedback GROUP BY app)"
        ).fetchall()
        for row in rows:
            learned[(row["app"] or "").lower()] = row["user_mode"]
        return cls(config.rules, learned)

    def classify(self, app: str, title: str) -> str:
        app = (app or "").lower()
        if app in self._learned:
            return self._learned[app]

        haystack = f"{app} {title}".lower()
        for pattern, mode in self._rules:
            if pattern.search(haystack):
                return mode
        return UNKNOWN
