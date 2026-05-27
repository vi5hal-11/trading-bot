"use client";
import { useLive } from "@/lib/live-context";
import MetricCard from "./MetricCard";

export default function MetricGrid() {
  const { summary } = useLive();

  const dd = summary?.drawdown_from_peak ?? 0;
  const ddColor = dd > 0.1 ? "loss" : dd > 0.05 ? "warn" : "neutral";
  const pnlColor = (summary?.total_pnl ?? 0) >= 0 ? "gain" : "loss";
  const dayColor = (summary?.daily_pnl_pct ?? 0) >= 0 ? "gain" : "loss";
  const isLoading = !summary;

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
      <MetricCard label="Balance" value={summary ? `${summary.balance.toFixed(2)} USDT` : "—"} isLoading={isLoading} />
      <MetricCard
        label="Total PnL"
        value={summary ? `${summary.total_pnl >= 0 ? "+" : ""}${summary.total_pnl.toFixed(2)}` : "—"}
        color={pnlColor}
        isLoading={isLoading}
      />
      <MetricCard
        label="Daily PnL"
        value={summary ? `${(summary.daily_pnl_pct * 100).toFixed(2)}%` : "—"}
        color={dayColor}
        isLoading={isLoading}
      />
      <MetricCard
        label="Drawdown"
        value={summary ? `${(dd * 100).toFixed(2)}%` : "—"}
        color={ddColor}
        isLoading={isLoading}
      />
      <MetricCard
        label="Win Rate"
        value={summary ? `${(summary.win_rate * 100).toFixed(1)}%` : "—"}
        color={(summary?.win_rate ?? 0) >= 0.5 ? "gain" : "loss"}
        delta={undefined}
        deltaLabel={summary ? `${summary.total_trades} trades` : undefined}
        isLoading={isLoading}
      />
      <MetricCard label="Open Positions" value={summary ? String(summary.open_positions) : "—"} isLoading={isLoading} />
    </div>
  );
}
