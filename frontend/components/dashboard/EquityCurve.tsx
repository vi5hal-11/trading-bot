"use client";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { useEquityCurve } from "@/lib/hooks/useEquityCurve";

export default function EquityCurve() {
  const { snapshots, isLoading } = useEquityCurve();

  if (isLoading) {
    return (
      <div className="glass-card p-5">
        <div className="text-xs text-subtle mb-4 uppercase tracking-wider">Equity Curve</div>
        <div className="h-40 rounded animate-pulse" style={{ background: "rgba(255,255,255,0.04)" }} />
      </div>
    );
  }

  if (!snapshots.length) {
    return (
      <div className="glass-card p-5">
        <div className="text-xs text-subtle mb-4 uppercase tracking-wider">Equity Curve</div>
        <div className="h-40 flex items-center justify-center text-subtle text-sm">
          No data yet — snapshots update every 10 loops
        </div>
      </div>
    );
  }

  const data = snapshots.map((s) => ({
    time: new Date(s.snapped_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    equity: parseFloat(s.equity.toFixed(2)),
    balance: parseFloat(s.balance.toFixed(2)),
  }));

  const fmt = (v: number) => `${v.toFixed(0)}`;

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="text-xs text-subtle uppercase tracking-wider">Equity Curve</div>
        <div className="flex items-center gap-4 text-xs text-subtle">
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 inline-block rounded" style={{ background: "#06b6d4" }} /> Equity
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-0.5 inline-block rounded" style={{ background: "#6366f1" }} /> Balance
          </span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 5, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="balanceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,102,241,0.1)" />
          <XAxis dataKey="time" tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} />
          <YAxis tickFormatter={fmt} tick={{ fill: "#6b7280", fontSize: 10 }} tickLine={false} axisLine={false} width={55} />
          <Tooltip
            contentStyle={{ background: "#0d1428", border: "1px solid rgba(99,102,241,0.3)", borderRadius: 8, fontSize: 12 }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: unknown) => [`${(v as number).toFixed(2)} USDT`]}
          />
          <Area type="monotone" dataKey="equity" stroke="#06b6d4" strokeWidth={2} fill="url(#equityGrad)" dot={false} />
          <Area type="monotone" dataKey="balance" stroke="#6366f1" strokeWidth={1.5} fill="url(#balanceGrad)" dot={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
