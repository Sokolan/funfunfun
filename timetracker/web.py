"""FastAPI app: serve the dashboard + a small JSON API.

Endpoints:
  GET  /                  -> dashboard (static/index.html)
  GET  /api/insights      -> aggregates + headlines
  GET  /api/sessions      -> recent sessions
  GET  /api/config        -> known modes + targets
  POST /api/feedback      -> correct a session's mode (learning loop)
  GET  /api/digest        -> rendered weekly digest (html)
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ._paths import bundle_root
from .config import Config, load_config
from .db import get_conn
from .digest import build_digest_html
from .insights import compute_insights
from .sessionizer import rebuild_sessions

_STATIC = bundle_root() / "static"


class Feedback(BaseModel):
    session_id: int
    mode: str


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="timetracker", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return FileResponse(str(_STATIC / "index.html"))

    @app.get("/api/insights")
    def api_insights(days: int = 28):
        return compute_insights(config, since_days=days)

    @app.get("/api/sessions")
    def api_sessions(limit: int = 100):
        conn = get_conn(config.db_path)
        try:
            rows = conn.execute(
                "SELECT id, start_ts, end_ts, dominant_app, mode, quality_score, "
                "switch_count, idle_ratio, fragmented, sample_count "
                "FROM sessions ORDER BY start_ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @app.get("/api/config")
    def api_config():
        modes = sorted(set(list(config.targets.keys()) +
                           [r.mode for r in config.rules] + ["unknown"]))
        return {"modes": modes, "targets": config.targets,
                "timezone": config.timezone}

    @app.post("/api/feedback")
    def api_feedback(fb: Feedback):
        import time
        conn = get_conn(config.db_path)
        try:
            row = conn.execute(
                "SELECT dominant_app FROM sessions WHERE id = ?", (fb.session_id,)
            ).fetchone()
            if row is None:
                raise HTTPException(404, "session not found")
            conn.execute(
                "INSERT INTO feedback(session_id, app, user_mode, created_ts) "
                "VALUES(?,?,?,?)",
                (fb.session_id, row["dominant_app"], fb.mode, time.time()),
            )
        finally:
            conn.close()
        # Re-apply the (now updated) learning to all sessions.
        rebuild_sessions(config)
        return {"ok": True}

    @app.get("/api/digest", response_class=HTMLResponse)
    def api_digest(days: int = 7):
        return build_digest_html(config, since_days=days)

    return app
