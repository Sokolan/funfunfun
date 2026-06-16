"""Command-line entrypoint.

Usage:
  python -m timetracker.cli init-db
  python -m timetracker.cli collect
  python -m timetracker.cli rebuild
  python -m timetracker.cli serve [--host H] [--port P]
  python -m timetracker.cli digest [--days N] [--html OUT.html]
  python -m timetracker.cli seed-fake [--minutes N]   # dev: generate test data

Global: --config PATH to layer an extra TOML file over the defaults.
"""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .db import init_db


def _add_config_arg(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", default=None, help="extra TOML config to layer on top")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="timetracker")
    sub = parser.add_subparsers(dest="cmd", required=True)

    for name in ("init-db", "collect", "rebuild"):
        sp = sub.add_parser(name)
        _add_config_arg(sp)

    sp_serve = sub.add_parser("serve")
    _add_config_arg(sp_serve)
    sp_serve.add_argument("--host", default="127.0.0.1")
    sp_serve.add_argument("--port", type=int, default=8765)

    sp_digest = sub.add_parser("digest")
    _add_config_arg(sp_digest)
    sp_digest.add_argument("--days", type=int, default=7)
    sp_digest.add_argument("--html", default=None, help="write HTML digest to this path")

    sp_seed = sub.add_parser("seed-fake")
    _add_config_arg(sp_seed)
    sp_seed.add_argument("--days", type=int, default=21,
                         help="how many past days of synthetic activity to generate")

    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.cmd == "init-db":
        init_db(config.db_path)
        print(f"initialised {config.db_path}")
        return 0

    if args.cmd == "collect":
        from .collector import run_collector
        run_collector(config)
        return 0

    if args.cmd == "rebuild":
        from .sessionizer import rebuild_sessions
        n = rebuild_sessions(config)
        print(f"rebuilt {n} sessions")
        return 0

    if args.cmd == "serve":
        import uvicorn
        from .web import create_app
        app = create_app(config)
        print(f"serving on http://{args.host}:{args.port}")
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return 0

    if args.cmd == "digest":
        from .digest import build_digest_html, build_digest_text
        if args.html:
            with open(args.html, "w", encoding="utf-8") as fh:
                fh.write(build_digest_html(config, since_days=args.days))
            print(f"wrote {args.html}")
        else:
            print(build_digest_text(config, since_days=args.days))
        return 0

    if args.cmd == "seed-fake":
        _seed_fake(config, args.days)
        return 0

    return 1


def _seed_fake(config, days: int) -> None:
    """Generate realistic synthetic events over the past `days`, then rebuild.

    Activity only happens on weekdays during working hours, with a morning and
    afternoon productivity peak, a slow midday dip, and one consistently weak
    weekday — so the circadian/weekday insights have a real signal to find.
    """
    import datetime as dt
    import random
    import time

    from .collector.backends import FakeBackend
    from .db import get_conn
    from .sessionizer import rebuild_sessions

    init_db(config.db_path)
    backend = FakeBackend()
    step = config.poll_seconds
    host = "seed"
    now = dt.datetime.now()

    # Probability that any given sample-slot is "active" (produces an event).
    def active_prob(hour: int, weekday: int) -> float:
        if weekday >= 5:          # weekends mostly off
            return 0.05
        if hour < 8 or hour >= 19:
            return 0.02
        peak = 0.9 if (9 <= hour <= 11 or 15 <= hour <= 17) else 0.45
        if 12 <= hour <= 13:      # lunch dip
            peak = 0.2
        if weekday == 2:          # Wednesday is this person's worst day
            peak *= 0.4
        return peak

    rows = []
    for d in range(days):
        day = now - dt.timedelta(days=d)
        for hour in range(24):
            slots = max(1, 3600 // step)
            for slot in range(slots):
                if random.random() > active_prob(hour, day.weekday()):
                    continue
                ts = day.replace(hour=hour, minute=0, second=0,
                                 microsecond=0).timestamp() + slot * step
                s = backend.sample(host)
                rows.append((ts, s.app, s.title, s.idle_seconds, host))

    conn = get_conn(config.db_path)
    try:
        conn.executemany(
            "INSERT INTO events(ts, app, title, idle_seconds, host) VALUES(?,?,?,?,?)",
            rows,
        )
    finally:
        conn.close()

    n = rebuild_sessions(config)
    print(f"seeded {len(rows)} events over {days} days -> {n} sessions")


if __name__ == "__main__":
    sys.exit(main())
