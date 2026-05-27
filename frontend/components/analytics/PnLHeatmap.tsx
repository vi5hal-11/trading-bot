"use client";
import { useMemo } from "react";
import { useTrades } from "@/lib/hooks/useTrades";

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

export default function PnLHeatmap() {
  const { trades, isLoading } = useTrades({ limit: 500 });

  const grid = useMemo(() => {
    const map: Record<string, number[]> = {};
    for (const t of trades) {
      if (!t.closed_at) continue;
      const d = new Date(t.closed_at);
      const key = `${d.getDay()}-${d.getHours()}`;
      if (!map[key]) map[key] = [];
      map[key].push(t.pnl ?? 0);
    }
    return map;
  }, [trades]);

  function avg(values: number[]) {
    if (!values?.length) return null;
    return values.reduce((a, b) => a + b, 0) / values.length;
  }

  function cellColor(pnl: number | null): string {
    if (pnl === null) return "rgba(255,255,255,0.03)";
    if (pnl > 0.5) return "rgba(6,182,212,0.6)";
    if (pnl > 0) return "rgba(6,182,212,0.25)";
    if (pnl > -0.5) return "rgba(239,68,68,0.25)";
    return "rgba(239,68,68,0.6)";
  }

  if (isLoading) {
    return <div className="h-48 rounded-xl animate-pulse" style={{ background: "rgba(255,255,255,0.04)" }} />;
  }

  return (
    <div className="glass-card p-5 overflow-x-auto">
      <div className="text-xs text-subtle uppercase tracking-wider mb-4">Avg PnL Heatmap (Day × Hour)</div>
      <div className="min-w-[700px]">
        <div className="flex gap-1 mb-1">
          <div className="w-8" />
          {HOURS.map((h) => (
            <div key={h} className="flex-1 text-center text-xs text-subtle" style={{ minWidth: 24 }}>
              {h}
            </div>
          ))}
        </div>
        {DAYS.map((day, di) => (
          <div key={day} className="flex gap-1 mb-1 items-center">
            <div className="w-8 text-xs text-subtle text-right pr-1">{day}</div>
            {HOURS.map((h) => {
              const pnl = avg(grid[`${di}-${h}`]);
              return (
                <div
                  key={h}
                  title={pnl !== null ? `${day} ${h}:00 — avg ${pnl.toFixed(2)} USDT (${grid[`${di}-${h}`]?.length ?? 0} trades)` : "No data"}
                  className="flex-1 rounded"
                  style={{ minWidth: 24, height: 24, background: cellColor(pnl) }}
                />
              );
            })}
          </div>
        ))}
        <div className="flex items-center gap-4 mt-3 text-xs text-subtle">
          <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block" style={{ background: "rgba(6,182,212,0.6)" }} /> Strong gain</span>
          <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block" style={{ background: "rgba(6,182,212,0.25)" }} /> Slight gain</span>
          <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block" style={{ background: "rgba(239,68,68,0.25)" }} /> Slight loss</span>
          <span className="flex items-center gap-1"><span className="w-4 h-3 rounded inline-block" style={{ background: "rgba(239,68,68,0.6)" }} /> Strong loss</span>
        </div>
      </div>
    </div>
  );
}
