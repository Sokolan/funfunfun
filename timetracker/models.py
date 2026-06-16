"""Plain data structures shared across the pipeline."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Sample:
    """One poll of the foreground window, produced by a collector backend."""

    ts: float            # unix epoch seconds, UTC
    app: str             # executable / application name (lowercased)
    title: str           # window title (may be empty if OS withholds it)
    idle_seconds: float  # seconds since last user input
    host: str            # machine hostname


@dataclass
class Session:
    """A contiguous span of activity derived from raw samples."""

    start_ts: float
    end_ts: float
    dominant_app: str
    mode: str
    quality_score: float
    switch_count: int
    idle_ratio: float
    fragmented: bool
    sample_count: int

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.end_ts - self.start_ts)

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60.0
