"""Weekly digest: real insights, not just 'you worked 34 hours'."""
from __future__ import annotations

from datetime import datetime

from .config import Config
from .insights import compute_insights


def _format_hour(h: int) -> str:
    return f"{h:02d}:00–{(h + 1) % 24:02d}:00"


def build_digest_text(config: Config, since_days: int = 7) -> str:
    ins = compute_insights(config, since_days=since_days)
    t = ins["totals"]
    h = ins["headlines"]

    lines: list[str] = []
    lines.append(f"Weekly digest — last {since_days} days "
                 f"({datetime.now().strftime('%Y-%m-%d')})")
    lines.append("=" * 56)
    lines.append(f"Tracked time:    {t['tracked_hours']} h")
    lines.append(f"Deep-work time:  {t['deep_work_hours']} h "
                 f"(quality-weighted)")
    lines.append(f"Sessions:        {t['session_count']} "
                 f"({t['fragmented_sessions']} fragmented)")
    lines.append("")

    if h["peak_hours"]:
        peaks = ", ".join(_format_hour(p["hour"]) for p in h["peak_hours"])
        lines.append(f"Peak focus hours: {peaks}")
    if h["best_day"]:
        lines.append(f"Best day: {h['best_day']}   Worst day: {h['worst_day']}")
    lines.append("")

    lines.append("Time by mode:")
    if ins["by_mode"]:
        for mode, v in ins["by_mode"].items():
            lines.append(f"  - {mode:<20} {v['tracked_hours']:>5} h tracked, "
                         f"{v['deep_work_hours']:>5} h deep")
    else:
        lines.append("  (no sessions yet)")
    lines.append("")

    if h["neglected_modes"]:
        lines.append("Neglected — below target this period:")
        for n in h["neglected_modes"]:
            lines.append(f"  ! {n['mode']}: {n['actual_weekly_hours']} h/wk "
                         f"vs target {n['target_weekly_hours']} h/wk")
        lines.append("")
        lines.append("Suggestion: protect a focus block for the modes above "
                     "during your peak hours.")
    else:
        lines.append("All modes are at or near target. Nice.")

    return "\n".join(lines)


def build_digest_html(config: Config, since_days: int = 7) -> str:
    text = build_digest_text(config, since_days=since_days)
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<body style='font-family:ui-monospace,Menlo,Consolas,monospace;"
        "background:#0f1115;color:#e6e6e6;padding:24px'>"
        f"<pre style='font-size:14px;line-height:1.5'>{_escape(text)}</pre>"
        "</body>"
    )


def _escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
