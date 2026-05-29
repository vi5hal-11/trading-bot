"""
PPO-based position sizing agent.

The agent's ONLY job is to output a position size multiplier (0.5× … 2.0×)
given the current market state. All entry/exit logic stays in the existing
rule-based strategies — this is a pure sizing overlay.

State features fed to the agent
────────────────────────────────
  0  ensemble confidence (0–1)
  1  consensus score (normalised –1 to +1)
  2  RSI (normalised 0–1)
  3  ADX (normalised 0–100)
  4  ATR / price  (normalised vol proxy)
  5  vol_ratio (volume vs 20-bar avg, capped at 3)
  6  daily_pnl_pct (account health, –1 to +1)
  7  drawdown_from_peak (0–1, penalty signal)
  8  open_positions / max_positions (capacity signal)
  9  intraday_pnl_pct (–1 to +1)

Action space
────────────
  Continuous scalar in [0, 1] → mapped to [size_min, size_max]
  Default: 0.5× min, 2.0× max

Reward
──────
  At position close: pnl_pct × size_multiplier
  Penalty: –drawdown_from_peak (encourages conservative sizing in drawdown)
  Penalty: –0.1 × size² when in drawdown > 5%  (risk-aversion under stress)

The model is saved to ml/models/ppo_sizer/ and reloaded on restart.
If stable-baselines3 is not installed the agent falls back to size=1.0
(no-op), so the rest of the bot continues working.

Training
────────
Train from closed_trades history:
    python -m learning.ppo_sizer --train

Inference happens synchronously in main.py via get_size_multiplier().
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from loguru import logger

_MODEL_DIR  = os.path.join("ml", "models", "ppo_sizer")
_SIZE_MIN   = 0.5
_SIZE_MAX   = 2.0
_OBS_DIM    = 10

# ── Optional SB3 import ───────────────────────────────────────────────────────
try:
    import gymnasium as gym
    from stable_baselines3 import PPO
    from stable_baselines3.common.env_util import make_vec_env
    _SB3_AVAILABLE = True
except ImportError:
    _SB3_AVAILABLE = False
    logger.info("stable-baselines3 not installed — PPO sizer using fixed multiplier 1.0")


# ── Gymnasium environment ─────────────────────────────────────────────────────

if _SB3_AVAILABLE:
    class SizingEnv(gym.Env):
        """
        Single-step environment: one observation → one sizing decision → reward.
        Episodes correspond to individual trades from historical closed_trades.
        """

        metadata = {"render_modes": []}

        def __init__(self, episodes: list[dict]):
            super().__init__()
            self._episodes = episodes
            self._idx = 0
            self.observation_space = gym.spaces.Box(
                low=-1.0, high=3.0, shape=(_OBS_DIM,), dtype=np.float32
            )
            self.action_space = gym.spaces.Box(low=0.0, high=1.0, shape=(1,), dtype=np.float32)

        def reset(self, *, seed=None, options=None):
            super().reset(seed=seed)
            self._idx = self.np_random.integers(0, len(self._episodes))
            obs = self._make_obs(self._episodes[self._idx])
            return obs, {}

        def step(self, action):
            ep = self._episodes[self._idx]
            size_mult = _SIZE_MIN + float(action[0]) * (_SIZE_MAX - _SIZE_MIN)
            pnl_pct = ep.get("pnl_pct", 0.0)
            drawdown = ep.get("drawdown_at_entry", 0.0)

            reward = pnl_pct * size_mult
            # Penalise over-sizing during drawdown
            if drawdown > 0.05:
                reward -= 0.1 * size_mult ** 2
            # Clip reward for training stability
            reward = float(np.clip(reward, -1.0, 1.0))

            obs = self._make_obs(ep)
            return obs, reward, True, False, {}   # terminated=True: single-step

        @staticmethod
        def _make_obs(ep: dict) -> np.ndarray:
            return np.array([
                float(ep.get("confidence",          0.5)),
                float(ep.get("consensus_score",     0.0)),
                float(ep.get("rsi",                50.0)) / 100.0,
                float(ep.get("adx",                25.0)) / 100.0,
                float(ep.get("atr_pct",             0.01)),
                min(float(ep.get("vol_ratio",       1.0)), 3.0),
                float(np.clip(ep.get("daily_pnl_pct",   0.0), -1.0, 1.0)),
                float(ep.get("drawdown_at_entry",   0.0)),
                float(ep.get("open_pos_ratio",      0.0)),
                float(np.clip(ep.get("intraday_pnl_pct", 0.0), -1.0, 1.0)),
            ], dtype=np.float32)


# ── Public agent ─────────────────────────────────────────────────────────────

class PPOSizer:
    """
    Load-and-use wrapper. Call get_size_multiplier() before opening a position.
    Falls back to 1.0 if SB3 is unavailable or the model hasn't been trained yet.
    """

    def __init__(self):
        self._model = None
        self._available = _SB3_AVAILABLE
        self._load()

    def _load(self) -> None:
        if not _SB3_AVAILABLE:
            return
        path = os.path.join(_MODEL_DIR, "model.zip")
        if not os.path.exists(path):
            logger.info("[PPOSizer] No trained model found — using size multiplier 1.0. Run: python -m learning.ppo_sizer --train")
            return
        try:
            self._model = PPO.load(path)
            logger.info(f"[PPOSizer] Loaded from {path}")
        except Exception as e:
            logger.warning(f"[PPOSizer] Load failed: {e} — using 1.0")

    def get_size_multiplier(self, state: dict) -> float:
        """
        state dict keys match SizingEnv._make_obs() (all optional, safe defaults).
        Returns a multiplier in [SIZE_MIN, SIZE_MAX].
        """
        if not _SB3_AVAILABLE or self._model is None:
            return 1.0

        try:
            obs = np.array([
                float(state.get("confidence",          0.5)),
                float(state.get("consensus_score",     0.0)),
                float(state.get("rsi",                50.0)) / 100.0,
                float(state.get("adx",                25.0)) / 100.0,
                float(state.get("atr_pct",             0.01)),
                min(float(state.get("vol_ratio",       1.0)), 3.0),
                float(np.clip(state.get("daily_pnl_pct",   0.0), -1.0, 1.0)),
                float(state.get("drawdown_from_peak",  0.0)),
                float(state.get("open_pos_ratio",      0.0)),
                float(np.clip(state.get("intraday_pnl_pct", 0.0), -1.0, 1.0)),
            ], dtype=np.float32)
            action, _ = self._model.predict(obs, deterministic=True)
            multiplier = float(_SIZE_MIN + float(action[0]) * (_SIZE_MAX - _SIZE_MIN))
            return round(float(np.clip(multiplier, _SIZE_MIN, _SIZE_MAX)), 3)
        except Exception as e:
            logger.debug(f"[PPOSizer] predict failed: {e}")
            return 1.0

    def is_trained(self) -> bool:
        return self._model is not None

    def summary(self) -> dict:
        return {
            "available": self._available,
            "trained": self.is_trained(),
            "size_range": [_SIZE_MIN, _SIZE_MAX],
        }


# ── Training entry point ──────────────────────────────────────────────────────

def train(closed_trades: list[dict], timesteps: int = 50_000) -> str:
    """
    Train the PPO agent on historical closed trades.
    Returns path to saved model.
    """
    if not _SB3_AVAILABLE:
        return "stable-baselines3 not installed"

    if len(closed_trades) < 50:
        return f"Need at least 50 closed trades to train (have {len(closed_trades)})"

    logger.info(f"[PPOSizer] Training on {len(closed_trades)} trades for {timesteps} timesteps...")
    env = make_vec_env(lambda: SizingEnv(closed_trades), n_envs=4)
    model = PPO(
        "MlpPolicy",
        env,
        n_steps=512,
        batch_size=64,
        n_epochs=10,
        learning_rate=3e-4,
        verbose=0,
    )
    model.learn(total_timesteps=timesteps)

    os.makedirs(_MODEL_DIR, exist_ok=True)
    save_path = os.path.join(_MODEL_DIR, "model")
    model.save(save_path)
    meta = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_trades": len(closed_trades),
        "timesteps": timesteps,
    }
    with open(os.path.join(_MODEL_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"[PPOSizer] Saved to {save_path}.zip")
    return save_path + ".zip"


if __name__ == "__main__":
    import sys, asyncio
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    if "--train" in sys.argv:
        from data.storage import Storage
        from config.settings import Settings
        settings = Settings()
        storage = Storage(settings)
        trades = storage.get_trades(limit=10000)
        result = train(trades)
        print(result)
    else:
        print("Usage: python -m learning.ppo_sizer --train")
