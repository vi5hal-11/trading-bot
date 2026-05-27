import math
import numpy as np
import pandas as pd

BARS_PER_YEAR = 4 * 24 * 365  # 35,040 fifteen-minute bars per year


def _returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def sharpe(equity: pd.Series) -> float:
    r = _returns(equity)
    if r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * math.sqrt(BARS_PER_YEAR))


def sortino(equity: pd.Series) -> float:
    r = _returns(equity)
    downside = r[r < 0]
    if len(downside) == 0 or downside.std() == 0:
        return 0.0
    return float((r.mean() / downside.std()) * math.sqrt(BARS_PER_YEAR))


def max_drawdown(equity: pd.Series) -> tuple[float, int]:
    """Returns (max_drawdown_pct, max_drawdown_duration_bars)."""
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max

    max_dd = float(drawdown.min())

    # Duration of longest drawdown
    in_dd = drawdown < 0
    max_dur = 0
    cur_dur = 0
    for v in in_dd:
        if v:
            cur_dur += 1
            max_dur = max(max_dur, cur_dur)
        else:
            cur_dur = 0

    return max_dd, max_dur


def cagr(equity: pd.Series) -> float:
    if len(equity) < 2 or equity.iloc[0] == 0:
        return 0.0
    years = len(equity) / BARS_PER_YEAR
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def profit_factor(trades: list[dict]) -> float:
    wins = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    losses = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    return float(wins / losses) if losses > 0 else float("inf")


def win_rate(trades: list[dict]) -> float:
    if not trades:
        return 0.0
    winners = sum(1 for t in trades if t["pnl"] > 0)
    return winners / len(trades)


# ── Trading in the Zone metrics (Mark Douglas) ────────────────────────────────

def expectancy(trades: list[dict]) -> float:
    """
    Mathematical expectancy per trade as a fraction of risk.
    E = (win_rate × avg_R_win) - (loss_rate × avg_R_loss)
    Positive expectancy = edge exists. >0.2R per trade is solid.
    """
    if not trades:
        return 0.0
    winners = [t for t in trades if t["pnl"] > 0]
    losers = [t for t in trades if t["pnl"] <= 0]
    wr = len(winners) / len(trades)
    lr = 1 - wr
    avg_win = np.mean([t["pnl_pct"] for t in winners]) if winners else 0.0
    avg_loss = abs(np.mean([t["pnl_pct"] for t in losers])) if losers else 0.0
    return float(wr * avg_win - lr * avg_loss)


def r_multiple(trades: list[dict]) -> tuple[float, float]:
    """
    R-multiple: each trade's P&L expressed as multiples of initial risk.
    Returns (avg_R, std_R). Consistent positive avg_R = reliable edge.
    """
    r_values = []
    for t in trades:
        entry = t["entry_price"]
        sl = t.get("stop_loss", entry * 0.98)
        risk_per_unit = abs(entry - sl) if sl else entry * 0.01
        risk_dollars = risk_per_unit * t["quantity"]
        if risk_dollars > 0:
            r_values.append(t["pnl"] / risk_dollars)
    if not r_values:
        return 0.0, 0.0
    return float(np.mean(r_values)), float(np.std(r_values))


def streak_analysis(trades: list[dict]) -> dict:
    """
    Douglas emphasizes thinking in probabilities across a distribution of trades,
    not fixating on individual wins/losses. Streak analysis shows the realistic
    worst-case runs a trader must endure while the edge plays out.
    """
    max_win_streak = max_loss_streak = 0
    cur_win = cur_loss = 0
    for t in trades:
        if t["pnl"] > 0:
            cur_win += 1
            cur_loss = 0
        else:
            cur_loss += 1
            cur_win = 0
        max_win_streak = max(max_win_streak, cur_win)
        max_loss_streak = max(max_loss_streak, cur_loss)
    return {"max_win_streak": max_win_streak, "max_loss_streak": max_loss_streak}


def edge_consistency(window_metrics: list[dict]) -> dict:
    """
    Douglas: an edge only matters if it's consistent across many market conditions.
    Measures mean ± std of key metrics across walk-forward windows.
    """
    if not window_metrics:
        return {}
    keys = ["total_return", "sharpe", "win_rate", "expectancy"]
    result = {}
    for k in keys:
        vals = [m.get(k, 0) for m in window_metrics]
        result[f"{k}_mean"] = float(np.mean(vals))
        result[f"{k}_std"] = float(np.std(vals))
        result[f"{k}_min"] = float(np.min(vals))
    return result


def compile_metrics(
    equity_curve: pd.Series,
    trades: list[dict],
    initial_balance: float,
) -> dict:
    final_balance = float(equity_curve.iloc[-1]) if len(equity_curve) else initial_balance
    total_return = (final_balance - initial_balance) / initial_balance

    max_dd, max_dd_dur = max_drawdown(equity_curve) if len(equity_curve) > 1 else (0.0, 0)

    avg_duration = (
        sum(t["duration_bars"] for t in trades) / len(trades) if trades else 0.0
    )
    avg_win = (
        np.mean([t["pnl_pct"] for t in trades if t["pnl"] > 0]) if any(t["pnl"] > 0 for t in trades) else 0.0
    )
    avg_loss = (
        np.mean([t["pnl_pct"] for t in trades if t["pnl"] < 0]) if any(t["pnl"] < 0 for t in trades) else 0.0
    )

    avg_r, std_r = r_multiple(trades)
    streaks = streak_analysis(trades)
    exp = expectancy(trades)

    return {
        "initial_balance": initial_balance,
        "final_balance": final_balance,
        "total_return": total_return,
        "cagr": cagr(equity_curve),
        "sharpe": sharpe(equity_curve),
        "sortino": sortino(equity_curve),
        "max_drawdown": max_dd,
        "max_drawdown_bars": max_dd_dur,
        "win_rate": win_rate(trades),
        "profit_factor": profit_factor(trades),
        "total_trades": len(trades),
        "avg_duration_bars": avg_duration,
        "avg_win_pct": float(avg_win),
        "avg_loss_pct": float(avg_loss),
        # Trading in the Zone metrics
        "expectancy": exp,
        "avg_r_multiple": avg_r,
        "std_r_multiple": std_r,
        "max_win_streak": streaks["max_win_streak"],
        "max_loss_streak": streaks["max_loss_streak"],
    }
