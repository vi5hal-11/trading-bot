"""
Thompson Sampling bandit for adaptive ensemble strategy weights.

Each strategy is treated as a "bandit arm". After every closed trade the bandit
updates the arm that voted for the trade. A Beta(α, β) distribution is
maintained per strategy:
  α = wins + 1   (prior = 1 so we never sample from a zero distribution)
  β = losses + 1

On each loop, weights are sampled from each arm's distribution. Strategies
performing well recently get higher weight — strategies on a losing streak get
lower weight. The ensemble still votes; this just changes how much each vote is
worth.

Regime awareness
────────────────
We maintain separate α/β counters per regime bucket:
  "trending"  — ADX > 25
  "ranging"   — ADX ≤ 25

This means a strategy that works in trending markets but not ranging markets
gets properly rewarded/penalised in each context rather than averaging out.

Persistence
───────────
State is saved to `ml/models/bandit_state.json` so it survives restarts.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from loguru import logger

_STATE_PATH = os.path.join("ml", "models", "bandit_state.json")
_REGIMES = ("trending", "ranging")
_ADX_THRESHOLD = 25.0


def _regime(adx: float) -> str:
    return "trending" if adx >= _ADX_THRESHOLD else "ranging"


class BanditEnsemble:
    """
    Wraps the existing EnsembleStrategy and replaces its fixed weights with
    Thompson-Sampling-derived weights that adapt after every closed trade.
    """

    def __init__(self, strategy_names: list[str]):
        self._names = strategy_names
        # alpha[regime][strategy], beta[regime][strategy]
        self._alpha: dict[str, dict[str, float]] = {r: defaultdict(lambda: 1.0) for r in _REGIMES}
        self._beta:  dict[str, dict[str, float]] = {r: defaultdict(lambda: 1.0) for r in _REGIMES}
        self._load()
        logger.info(f"BanditEnsemble ready — strategies: {strategy_names}")

    # ── Weight sampling ───────────────────────────────────────────────────────

    def sample_weights(self, adx: float = 0.0) -> dict[str, float]:
        """
        Sample one weight per strategy from Beta(α, β).
        Returns a normalised dict {strategy_name: weight}.
        """
        reg = _regime(adx)
        samples = {}
        for name in self._names:
            a = self._alpha[reg][name]
            b = self._beta[reg][name]
            samples[name] = float(np.random.beta(a, b))

        total = sum(samples.values()) or 1.0
        return {k: v / total for k, v in samples.items()}

    def current_weights(self, adx: float = 0.0) -> dict[str, float]:
        """Deterministic mean weights (α / (α+β)) — used for display only."""
        reg = _regime(adx)
        weights = {}
        for name in self._names:
            a = self._alpha[reg][name]
            b = self._beta[reg][name]
            weights[name] = a / (a + b)
        total = sum(weights.values()) or 1.0
        return {k: v / total for k, v in weights.items()}

    # ── Update after trade close ──────────────────────────────────────────────

    def update(
        self,
        component_signals: dict[str, str],
        trade_side: str,
        pnl: float,
        adx: float = 0.0,
    ) -> None:
        """
        After a trade closes, update every strategy that voted.

        A strategy is rewarded (alpha++) if:
          - it voted in the same direction as the trade AND the trade was profitable
          - it voted HOLD/against AND the trade was a loss (it was right to be cautious)

        A strategy is penalised (beta++) if:
          - it voted for the trade AND the trade was a loss
          - it voted HOLD/against AND the trade was profitable (missed a winner)
        """
        reg = _regime(adx)
        won = pnl > 0

        for strategy, vote in component_signals.items():
            voted_for = (vote == trade_side)

            if voted_for and won:
                self._alpha[reg][strategy] += 1
                outcome = "✓ reward (voted for winner)"
            elif voted_for and not won:
                self._beta[reg][strategy] += 1
                outcome = "✗ penalise (voted for loser)"
            elif not voted_for and not won:
                self._alpha[reg][strategy] += 0.5   # partial reward for caution
                outcome = "~ half-reward (correctly cautious)"
            else:
                self._beta[reg][strategy] += 0.5    # missed a winner
                outcome = "~ half-penalise (missed winner)"

            logger.debug(
                f"[Bandit/{reg}] {strategy}: {outcome} "
                f"α={self._alpha[reg][strategy]:.1f} β={self._beta[reg][strategy]:.1f}"
            )

        self._save()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
            state = {
                "alpha": {r: dict(self._alpha[r]) for r in _REGIMES},
                "beta":  {r: dict(self._beta[r])  for r in _REGIMES},
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(_STATE_PATH, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.debug(f"Bandit save failed: {e}")

    def _load(self) -> None:
        if not os.path.exists(_STATE_PATH):
            return
        try:
            with open(_STATE_PATH) as f:
                state = json.load(f)
            for reg in _REGIMES:
                for name, val in state.get("alpha", {}).get(reg, {}).items():
                    self._alpha[reg][name] = float(val)
                for name, val in state.get("beta", {}).get(reg, {}).items():
                    self._beta[reg][name] = float(val)
            logger.info(f"BanditEnsemble state loaded from {_STATE_PATH}")
        except Exception as e:
            logger.warning(f"Bandit load failed (using priors): {e}")

    def summary(self, adx: float = 0.0) -> dict:
        reg = _regime(adx)
        return {
            "regime": reg,
            "weights": self.current_weights(adx),
            "raw": {
                name: {"alpha": self._alpha[reg][name], "beta": self._beta[reg][name]}
                for name in self._names
            },
        }
