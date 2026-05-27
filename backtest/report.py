from __future__ import annotations

from pathlib import Path
import pandas as pd

RESULTS_DIR = Path(__file__).parent / "results"


def print_report(metrics: dict, label: str) -> None:
    w = 52
    print(f"\n{'=' * w}")
    print(f"  {label}")
    print(f"{'=' * w}")

    def row(name, val):
        print(f"  {name:<28} {val}")

    row("Initial Balance",    f"${metrics['initial_balance']:>10,.2f}")
    row("Final Balance",      f"${metrics['final_balance']:>10,.2f}")
    row("Total Return",       f"{metrics['total_return']:>+10.2%}")
    row("CAGR (annualized)",  f"{metrics['cagr']:>+10.2%}")
    print(f"  {'-' * (w - 4)}")
    row("Sharpe Ratio",       f"{metrics['sharpe']:>10.3f}")
    row("Sortino Ratio",      f"{metrics['sortino']:>10.3f}")
    row("Max Drawdown",
        f"{metrics['max_drawdown']:>+10.2%}  ({metrics['max_drawdown_bars']} bars)")
    print(f"  {'-' * (w - 4)}")
    row("Win Rate",           f"{metrics['win_rate']:>10.1%}")
    row("Profit Factor",
        f"{metrics['profit_factor']:>10.3f}" if metrics['profit_factor'] != float('inf') else "       inf (no losses)")
    row("Total Trades",       f"{metrics['total_trades']:>10}")
    row("Avg Duration",       f"{metrics['avg_duration_bars']:>9.1f}  bars")
    row("Avg Win",            f"{metrics['avg_win_pct']:>+10.2%}")
    row("Avg Loss",           f"{metrics['avg_loss_pct']:>+10.2%}")
    print(f"  {'-' * (w - 4)}")
    print(f"  Trading in the Zone  (Mark Douglas)")
    print(f"  {'-' * (w - 4)}")
    exp = metrics['expectancy']
    exp_verdict = "[+] Edge exists" if exp > 0 else "[-] No edge"
    row("Expectancy / trade",  f"{exp:>+10.3%}  {exp_verdict}")
    row("Avg R-Multiple",      f"{metrics['avg_r_multiple']:>+10.3f}R")
    row("R-Multiple Std Dev",  f"{metrics['std_r_multiple']:>10.3f}R")
    row("Max Win Streak",      f"{metrics['max_win_streak']:>10}")
    row("Max Loss Streak",     f"{metrics['max_loss_streak']:>10}")
    print(f"{'=' * w}\n")


def print_walkforward_summary(window_metrics: list[dict], labels: list[str]) -> None:
    from backtest.metrics import edge_consistency

    print(f"\n{'=' * 60}")
    print("  Walk-Forward Validation Summary")
    print(f"{'=' * 60}")
    header = f"  {'Window':<18} {'Return':>8} {'Sharpe':>8} {'WinRate':>8} {'Expect':>9}"
    print(header)
    print(f"  {'-' * 56}")
    for lbl, m in zip(labels, window_metrics):
        print(
            f"  {lbl:<18} "
            f"{m['total_return']:>+8.2%} "
            f"{m['sharpe']:>8.3f} "
            f"{m['win_rate']:>8.1%} "
            f"{m['expectancy']:>+9.3%}"
        )

    ec = edge_consistency(window_metrics)
    if ec:
        print(f"  {'-' * 56}")
        print(
            f"  {'Mean +/- Std':<18} "
            f"{ec['total_return_mean']:>+8.2%} "
            f"{ec['sharpe_mean']:>8.3f} "
            f"{ec['win_rate_mean']:>8.1%} "
            f"{ec['expectancy_mean']:>+9.3%}"
        )
        ret_s  = f"+/-{ec['total_return_std']:.2%}"
        shr_s  = f"+/-{ec['sharpe_std']:.3f}"
        wr_s   = f"+/-{ec['win_rate_std']:.1%}"
        exp_s  = f"+/-{ec['expectancy_std']:.3%}"
        print(
            f"  {'(std dev)':<18} "
            f"{ret_s:>8} "
            f"{shr_s:>8} "
            f"{wr_s:>8} "
            f"{exp_s:>9}"
        )
        consistency = "CONSISTENT" if ec["sharpe_std"] < ec["sharpe_mean"] * 0.5 else "INCONSISTENT"
        print(f"\n  Edge consistency verdict: {consistency}")
    print(f"{'=' * 60}\n")


def save_equity_curve(
    equity: pd.Series,
    label: str,
    out_dir: Path = RESULTS_DIR,
    combined: bool = False,
) -> Path:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print("  [report] matplotlib not installed — skipping equity curve PNG")
        return Path()

    out_dir.mkdir(parents=True, exist_ok=True)
    safe = label.replace("/", "_").replace(":", "_").replace(" ", "_").replace("|", "").replace("*", "").replace("?", "").replace("<", "").replace(">", "").replace('"', "")
    out_path = out_dir / f"{safe}_equity.png"

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(label, fontsize=13, fontweight="bold")

    # Equity curve
    ax1.plot(equity.index, equity.values, color="#2196F3", linewidth=1.2, label="Equity")
    ax1.axhline(equity.iloc[0], color="gray", linestyle="--", linewidth=0.8, alpha=0.6)
    ax1.fill_between(equity.index, equity.values, equity.iloc[0],
                     where=(equity.values >= equity.iloc[0]), alpha=0.15, color="green")
    ax1.fill_between(equity.index, equity.values, equity.iloc[0],
                     where=(equity.values < equity.iloc[0]), alpha=0.15, color="red")
    ax1.set_ylabel("Equity (USDT)", fontsize=10)
    ax1.grid(True, alpha=0.3)
    ax1.legend(fontsize=9)

    # Drawdown
    roll_max = equity.cummax()
    drawdown = (equity - roll_max) / roll_max * 100
    ax2.fill_between(drawdown.index, drawdown.values, 0, color="red", alpha=0.5)
    ax2.set_ylabel("Drawdown %", fontsize=10)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Equity curve saved -> {out_path}")
    return out_path


def save_trade_log(
    trades: list[dict],
    label: str,
    out_dir: Path = RESULTS_DIR,
) -> Path:
    if not trades:
        return Path()
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = label.replace("/", "_").replace(":", "_").replace(" ", "_").replace("|", "").replace("*", "").replace("?", "").replace("<", "").replace(">", "").replace('"', "")
    out_path = out_dir / f"{safe}_trades.csv"
    pd.DataFrame(trades).to_csv(out_path, index=False)
    print(f"  Trade log saved    -> {out_path}")
    return out_path
