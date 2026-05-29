"""
ADWIN-based concept drift detector for the XGBoost model.

ADWIN (ADaptive WINdowing) maintains a variable-length sliding window over a
stream of binary outcomes (1 = correct prediction, 0 = incorrect). It detects
when the error rate has shifted significantly, indicating that the market regime
has changed and the current model is stale.

When drift is detected:
  1. A `drift_detected` flag is set to True
  2. A Telegram alert is sent (via the callback)
  3. The ML retrain scheduler is triggered immediately instead of waiting for Sunday

The ADWIN algorithm is implemented without the `river` library so there are no
extra dependencies. It is a simplified O(log n) version using exponential
bucket merging.

Usage
─────
    detector = DriftDetector(on_drift=lambda: logger.warning("Drift!"))
    # Every loop, after the ML model makes a prediction:
    detector.add_element(correct=True)   # model was right
    detector.add_element(correct=False)  # model was wrong
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Callable, Optional

from loguru import logger


# ── Minimal ADWIN implementation ──────────────────────────────────────────────

class _Bucket:
    __slots__ = ("total", "variance", "size")

    def __init__(self, total: float = 0.0, variance: float = 0.0, size: int = 1):
        self.total = total
        self.variance = variance
        self.size = size


class _ADWIN:
    """
    Simplified ADWIN algorithm (Bifet & Gavalda, 2007).
    Detects when the mean of a binary stream has shifted.
    """

    def __init__(self, delta: float = 0.002):
        self.delta = delta
        self._buckets: list[_Bucket] = []
        self.total = 0.0
        self.variance = 0.0
        self.n = 0
        self.width = 0

    def add_element(self, value: float) -> bool:
        """Add a new observation. Returns True if drift detected."""
        self.n += 1
        self.width += 1
        self._insert_element(value)
        return self._detect_change()

    def _insert_element(self, value: float) -> None:
        self._buckets.insert(0, _Bucket(total=value, variance=0.0, size=1))
        self.total += value
        # Compress: merge buckets of equal size when count > log2(n)
        i = 0
        max_buckets = max(1, int(math.log2(self.n + 1)) + 1)
        while i < len(self._buckets) - 1:
            if self._buckets[i].size == self._buckets[i + 1].size:
                if self._bucket_count_at_size(self._buckets[i].size) > max_buckets:
                    b0, b1 = self._buckets.pop(i + 1), self._buckets.pop(i)
                    merged_total = b0.total + b1.total
                    n0, n1 = b0.size, b1.size
                    merged_var = (
                        b0.variance + b1.variance
                        + (n0 * n1 / (n0 + n1)) * ((b0.total / n0) - (b1.total / n1)) ** 2
                    )
                    self._buckets.insert(i, _Bucket(merged_total, merged_var, n0 + n1))
                    continue
            i += 1

    def _bucket_count_at_size(self, size: int) -> int:
        return sum(1 for b in self._buckets if b.size == size)

    def _detect_change(self) -> bool:
        n0 = 0
        mu0_total = 0.0
        n1 = self.n
        mu1_total = self.total

        for bucket in self._buckets:
            n0 += bucket.size
            n1 -= bucket.size
            mu0_total += bucket.total
            mu1_total -= bucket.total

            if n0 == 0 or n1 == 0:
                continue

            mu0 = mu0_total / n0
            mu1 = mu1_total / n1
            m = 1.0 / n0 + 1.0 / n1
            epsilon = math.sqrt(m / 2.0 * math.log(4 * self.n / self.delta))

            if abs(mu0 - mu1) >= epsilon:
                # Drift detected — cut the window at this point
                self.total = mu0_total
                self.n = n0
                self._buckets = self._buckets[:self._buckets.index(bucket) + 1]
                return True

        return False


# ── Public interface ──────────────────────────────────────────────────────────

class DriftDetector:
    """
    Wraps ADWIN and exposes a simple add_element() interface.
    Calls on_drift() when a regime change is detected.
    """

    def __init__(
        self,
        delta: float = 0.002,
        min_samples: int = 30,
        on_drift: Optional[Callable] = None,
    ):
        self._adwin = _ADWIN(delta=delta)
        self._min_samples = min_samples
        self._on_drift = on_drift
        self._samples = 0
        self._drifts = 0
        self.drift_detected = False
        self.last_drift_at: Optional[datetime] = None
        self._error_window: list[int] = []    # recent binary errors for display

    def add_element(self, correct: bool) -> bool:
        """
        Feed one ML prediction outcome.
        Returns True if drift was detected on this step.
        """
        self._samples += 1
        value = 1.0 if correct else 0.0
        self._error_window.append(int(not correct))
        if len(self._error_window) > 50:
            self._error_window.pop(0)

        if self._samples < self._min_samples:
            return False

        drift = self._adwin.add_element(value)
        if drift:
            self._drifts += 1
            self.drift_detected = True
            self.last_drift_at = datetime.now(timezone.utc)
            logger.warning(
                f"[DriftDetector] Concept drift detected after {self._samples} samples "
                f"(drift #{self._drifts}). ML model may be stale — retrain triggered."
            )
            if self._on_drift:
                try:
                    self._on_drift()
                except Exception as e:
                    logger.debug(f"Drift callback error: {e}")
            return True
        return False

    def acknowledge(self) -> None:
        """Call after retraining to clear the drift flag."""
        self.drift_detected = False

    @property
    def recent_error_rate(self) -> float:
        if not self._error_window:
            return 0.0
        return sum(self._error_window) / len(self._error_window)

    def summary(self) -> dict:
        return {
            "samples": self._samples,
            "drifts_detected": self._drifts,
            "drift_detected": self.drift_detected,
            "recent_error_rate": round(self.recent_error_rate, 4),
            "last_drift_at": self.last_drift_at.isoformat() if self.last_drift_at else None,
            "adwin_window_size": self._adwin.n,
        }
