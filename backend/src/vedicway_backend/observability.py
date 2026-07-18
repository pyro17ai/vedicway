from __future__ import annotations

import threading
import time
from collections import Counter, defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass


def _labels(values: dict[str, str] | None = None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((values or {}).items()))


def _format_labels(values: tuple[tuple[str, str], ...]) -> str:
    if not values:
        return ""
    return "{" + ",".join(f'{key}="{value.replace(chr(34), chr(39))}"' for key, value in values) + "}"


@dataclass(slots=True)
class Timer:
    metrics: Metrics
    metric: str
    labels: dict[str, str]
    started: float

    def finish(self) -> None:
        self.metrics.observe(self.metric, time.perf_counter() - self.started, self.labels)


class Metrics:
    """Small Prometheus-compatible registry without PII-bearing labels."""

    def __init__(self) -> None:
        self._counters: Counter[tuple[str, tuple[tuple[str, str], ...]]] = Counter()
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def increment(self, metric: str, labels: dict[str, str] | None = None, amount: int = 1) -> None:
        with self._lock:
            self._counters[(metric, _labels(labels))] += amount

    def observe(self, metric: str, seconds: float, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._histograms[(metric, _labels(labels))].append(max(0.0, seconds))

    @contextmanager
    def time(self, metric: str, labels: dict[str, str] | None = None) -> Iterator[Timer]:
        timer = Timer(self, metric, labels or {}, time.perf_counter())
        try:
            yield timer
        finally:
            timer.finish()

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (metric, labels), value in sorted(self._counters.items()):
                lines.append(f"vedicway_{metric}{_format_labels(labels)} {value}")
            for (metric, labels), samples in sorted(self._histograms.items()):
                ordered = sorted(samples)
                total = sum(ordered)
                p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
                label_suffix = _format_labels(labels)
                lines.extend(
                    [
                        f"vedicway_{metric}_count{label_suffix} {len(ordered)}",
                        f"vedicway_{metric}_sum{label_suffix} {total:.6f}",
                        f"vedicway_{metric}_p95{label_suffix} {p95:.6f}",
                    ]
                )
        return "\n".join(lines) + "\n"
