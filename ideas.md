The core idea is a tool that gets smarter the more you use it — not just a fancy timer, but something that learns your patterns and gives you genuinely useful feedback.

What makes it non-trivial
Most time trackers just record start/end. The interesting engineering is in the inference layer:

Detecting session quality, not just duration — did you get interrupted? Did you switch apps? Was it fragmented?
Learning your circadian productivity pattern from accumulated data (e.g. you peak 9–11am and 4–6pm, Tuesdays are your worst day)
Distinguishing "deep work" from meetings, email, shallow tasks — either via manual tagging or heuristics (idle detection, window titles, calendar integration)

Core components
A local background daemon that logs activity → a SQLite database → a lightweight web UI or TUI for review and config → a weekly digest (email or notification) with actual insights, not just "you worked 34 hours."
The PhD-specific angle
You could add research-specific modes: "writing", "coding experiments", "reading papers", "reviewing" — and track which modes you're neglecting. Pair it with your calendar (RWTH/Google) so it knows when you have seminars, and auto-protects your remaining focus blocks. Your dev friend could own the daemon + data pipeline while you design the insight/scoring layer.