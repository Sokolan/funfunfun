"""Activity collector: a poll loop that writes raw samples to SQLite.

The OS-specific work (reading the foreground window + idle time) lives in
``backends``. This module owns the loop, error handling and persistence so the
backends stay tiny.
"""
from __future__ import annotations

import signal
import socket
import sys
import time

from ..config import Config
from ..db import get_conn, init_db
from .backends import get_backend

__all__ = ["run_collector", "get_backend"]


def run_collector(config: Config) -> None:
    """Run the sampling loop until interrupted (Ctrl-C / SIGTERM)."""
    init_db(config.db_path)
    backend = get_backend(config.backend)
    host = socket.gethostname()
    conn = get_conn(config.db_path)

    running = {"on": True}

    def _stop(*_a):
        running["on"] = False

    signal.signal(signal.SIGINT, _stop)
    try:
        signal.signal(signal.SIGTERM, _stop)
    except (ValueError, AttributeError):
        pass  # SIGTERM not available on some platforms/threads

    print(
        f"[collector] backend={backend.name} host={host} "
        f"poll={config.poll_seconds}s db={config.db_path}",
        flush=True,
    )

    try:
        while running["on"]:
            tick_start = time.time()
            try:
                sample = backend.sample(host)
                if sample is not None:
                    conn.execute(
                        "INSERT INTO events(ts, app, title, idle_seconds, host) "
                        "VALUES(?,?,?,?,?)",
                        (sample.ts, sample.app, sample.title,
                         sample.idle_seconds, sample.host),
                    )
            except Exception as exc:  # never let one bad poll kill the loop
                print(f"[collector] sample error: {exc!r}", file=sys.stderr, flush=True)

            # Sleep the remainder of the interval, staying responsive to stop.
            elapsed = time.time() - tick_start
            remaining = max(0.0, config.poll_seconds - elapsed)
            slept = 0.0
            while slept < remaining and running["on"]:
                step = min(0.5, remaining - slept)
                time.sleep(step)
                slept += step
    finally:
        conn.close()
        print("[collector] stopped", flush=True)
