"use client";
import { useMemo } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { useTrades } from "@/lib/hooks/useTrades";

const STRATEGY_LABELS: Record<string, string> = {
  momentum: "Momentum",
  mean_reversion: "Mean Rev",
  trend_following: "Trend",
  sentiment: "Sentiment",
  ml_xgboost: "ML XGB",
  ensemble: "Ensemble",
};

export default function StrategyPnLChart() {
  const { trades, isLoading } = useTrades({ limit: 500 });

  const data = useMemo(() => {
    const map: Record<string, { pnl: number; wins: number; total: number }> = {};
    for (const t of trades) {
      const s = t.strategy || "ensemble";
      if (!map[s]) map[s] = { pnl: 0, wins: 0, total: 0 };
      map[s].pnl += t.pnl ?? 0;
      map[s].total++;
      if ((t.pnl ?? 0) > 0) map[s].wins++;
    }
    return Object.entries(map).map(([strategy, v]) => ({
      strategy: STRATEGY_LABELS[strategy] || strategy,
      "Total PnL": parseFloat(v.pnl.toFixed(2)),
      "Win Rate %": parseFloat((v.total > 0 ? (v.wins / v.total) * 100 : 0).toFixed(1)),
      trades: v.total,
    }));
  }, [trades]);

  if (isLoading) {
    return <div className="h-64 rounded-xl animate-pulse" style={{ background: "rgba(255,255,255,0.04)" }} />;
  }

  if (!data.length) {
    return (
      <div className="glass-card p-12 text-center text-subtle text-sm">
        No closed trades yet to analyze
      </div>
    );
  }

  return (
    <div className="glass-card p-5">
      <div className="text-xs text-subtle uppercase tracking-wider mb-4">PnL by Strategy</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,102,241,0.1)" />
          <XAxis dataKey="strategy" tick={{ fill: "#6b7280", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="pnl" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} width={50} />
          <YAxis yAxisId="wr" orientation="right" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} width={40} unit="%" />
          <Tooltip
            contentStyle={{ background: "#0d1428", border: "1px solid rgba(99,102,241,0.3)", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#9ca3af" }}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: "#6b7280" }} />
          <Bar yAxisId="pnl" dataKey="Total PnL" radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry["Total PnL"] >= 0 ? "#06b6d4" : "#ef4444"} />
            ))}
          </Bar>
          <Bar yAxisId="wr" dataKey="Win Rate %" fill="#6366f1" radius={[4, 4, 0, 0]} opacity={0.7} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
