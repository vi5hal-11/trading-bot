"use client";
import { useState } from "react";
import { useTrades } from "@/lib/hooks/useTrades";
import { toDisplayName, DISPLAY_SYMBOLS } from "@/lib/binance";
import Link from "next/link";
import type { Trade } from "@/lib/types";

export default function TradesTable() {
  const [filterSymbol, setFilterSymbol] = useState("");
  const [filterSide, setFilterSide] = useState<"" | "BUY" | "SELL">("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 20;

  const { trades, isLoading } = useTrades({ limit: 200, symbol: filterSymbol || undefined });

  const filtered = trades.filter((t) => {
    if (filterSide && t.side !== filterSide) return false;
    return true;
  });

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  function tradeParam(t: Trade): string {
    return encodeURIComponent(JSON.stringify(t));
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <select
          value={filterSymbol}
          onChange={(e) => { setFilterSymbol(e.target.value); setPage(0); }}
          className="px-3 py-2 rounded-lg text-sm text-gray-300 focus:outline-none"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.25)" }}
        >
          <option value="">All Symbols</option>
          {DISPLAY_SYMBOLS.map((s) => (
            <option key={s} value={s}>{toDisplayName(s)}</option>
          ))}
        </select>
        <select
          value={filterSide}
          onChange={(e) => { setFilterSide(e.target.value as "" | "BUY" | "SELL"); setPage(0); }}
          className="px-3 py-2 rounded-lg text-sm text-gray-300 focus:outline-none"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.25)" }}
        >
          <option value="">All Sides</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
        <div className="text-xs text-subtle self-center">
          {filtered.length} trade{filtered.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Table */}
      <div className="glass-card overflow-hidden">
        <table className="w-full text-left">
          <thead>
            <tr className="text-xs text-subtle uppercase border-b" style={{ borderColor: "rgba(99,102,241,0.15)" }}>
              {["Symbol", "Side", "Entry", "Exit", "PnL", "PnL%", "Strategy", "Conf", "Reason", "Duration", "Explain"].map((h) => (
                <th key={h} className="px-4 py-3 font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={11} className="px-4 py-8 text-center text-subtle text-sm">Loading...</td>
              </tr>
            ) : paged.length === 0 ? (
              <tr>
                <td colSpan={11} className="px-4 py-8 text-center text-subtle text-sm">No trades yet</td>
              </tr>
            ) : (
              paged.map((t, i) => {
                const pnlColor = (t.pnl ?? 0) >= 0 ? "#06b6d4" : "#ef4444";
                const durationMs = t.opened_at && t.closed_at
                  ? new Date(t.closed_at).getTime() - new Date(t.opened_at).getTime()
                  : null;
                const duration = durationMs
                  ? durationMs < 3600000
                    ? `${Math.round(durationMs / 60000)}m`
                    : `${(durationMs / 3600000).toFixed(1)}h`
                  : "—";
                return (
                  <tr
                    key={i}
                    className="border-b hover:bg-white/5 transition-colors"
                    style={{ borderColor: "rgba(99,102,241,0.08)" }}
                  >
                    <td className="px-4 py-3 text-sm font-semibold text-white">{toDisplayName(t.symbol)}</td>
                    <td className="px-4 py-3">
                      <span className={t.side === "BUY" ? "badge-buy" : "badge-sell"}>{t.side}</span>
                    </td>
                    <td className="px-4 py-3 text-sm">{t.entry_price?.toFixed(4) ?? "—"}</td>
                    <td className="px-4 py-3 text-sm">{t.exit_price?.toFixed(4) ?? "—"}</td>
                    <td className="px-4 py-3 text-sm font-semibold" style={{ color: pnlColor }}>
                      {(t.pnl ?? 0) >= 0 ? "+" : ""}{(t.pnl ?? 0).toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-sm" style={{ color: pnlColor }}>
                      {((t.pnl_pct ?? 0) * 100).toFixed(2)}%
                    </td>
                    <td className="px-4 py-3 text-xs text-subtle">{t.strategy}</td>
                    <td className="px-4 py-3 text-xs text-subtle">
                      {((t.signal_confidence ?? t.confidence ?? 0) * 100).toFixed(0)}%
                    </td>
                    <td className="px-4 py-3 text-xs text-subtle">{t.reason ?? "—"}</td>
                    <td className="px-4 py-3 text-xs text-subtle">{duration}</td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/trades/explain?trade=${tradeParam(t)}`}
                        className="px-2 py-1 rounded text-xs font-semibold transition-colors"
                        style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.3)" }}
                      >
                        Explain
                      </Link>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="px-3 py-1.5 rounded text-xs disabled:opacity-40 transition-colors"
            style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.2)", color: "#9ca3af" }}
          >
            Prev
          </button>
          <span className="text-xs text-subtle">{page + 1} / {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1.5 rounded text-xs disabled:opacity-40 transition-colors"
            style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.2)", color: "#9ca3af" }}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
