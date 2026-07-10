"""Metrics — minimal in-process observability.

All state lives on the instance; no module-level globals.
Swap `emit` for StatsD / Prometheus / OTel in production by
subclassing or monkey-patching `emit`.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class Metrics:
    """Tracks per-strategy latency, success, and failure counts."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._latencies: dict[str, list[float]] = {}

    # ── emission ──────────────────────────────────────────────────────────────

    def emit(self, name: str, value: float = 1.0, kind: str = "counter") -> None:
        if kind == "counter":
            self._counters[name] = self._counters.get(name, 0) + int(value)
        elif kind == "latency":
            self._latencies.setdefault(name, []).append(value)
        logger.debug("metric name=%s value=%s kind=%s", name, value, kind)

    # ── context manager ───────────────────────────────────────────────────────

    @asynccontextmanager
    async def timed(self, strategy: str):
        """Async context manager that records latency + success/failure counts.

        Usage::

            async with self._metrics.timed("similarity"):
                ...
        """
        start = time.perf_counter()
        try:
            yield
            self.emit(f"rag.{strategy}.success")
        except Exception:
            self.emit(f"rag.{strategy}.failure")
            raise
        finally:
            self.emit(f"rag.{strategy}.latency", time.perf_counter() - start, kind="latency")

    # ── snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "counters": dict(self._counters),
            "latency_avg_ms": {
                k: round(sum(v) / len(v) * 1000, 2)
                for k, v in self._latencies.items()
                if v
            },
        }
