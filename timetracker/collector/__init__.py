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


def run_collector(config: Config, install_signal_handlers: bool = True) -> None:
    """Run the sampling loop until interrupted (Ctrl-C / SIGTERM).

    When run in a background thread (e.g. the all-in-one `start` mode) pass
    install_signal_handlers=False: signal.signal() only works on the main thread.
    """
    init_db(config.db_path)
    backend = get_backend(config.backend)
    host = socket.gethostname()
    conn = get_conn(config.db_path)

    running = {"on": True}

    def _stop(*_a):
        running["on"] = False

    if install_signal_handlers:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _stop)
            except (ValueError, AttributeError, OSError):
                pass  # not available on this platform/thread

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
