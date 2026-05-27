"use client";
import { Suspense, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import AppShell from "@/components/layout/AppShell";
import RuleBasedBreakdown from "@/components/explain/RuleBasedBreakdown";
import OllamaPanel from "@/components/explain/OllamaPanel";
import { toDisplayName } from "@/lib/binance";
import type { Trade, Signal } from "@/lib/types";

function ExplainContent() {
  const params = useSearchParams();
  const tradeParam = params.get("trade");

  const trade = useMemo<Trade | null>(() => {
    if (!tradeParam) return null;
    try {
      return JSON.parse(decodeURIComponent(tradeParam));
    } catch {
      return null;
    }
  }, [tradeParam]);

  if (!trade) {
    return (
      <div className="glass-card p-12 text-center text-subtle text-sm">
        No trade selected. Go to the Trades page and click Explain on a row.
      </div>
    );
  }

  // Reconstruct a best-effort signal from stored trade data
  const signal: Signal = {
    action: trade.side,
    confidence: trade.signal_confidence ?? trade.confidence ?? 0,
    consensus_score: 0,
    price: trade.exit_price ?? trade.entry_price ?? 0,
    strategy: trade.strategy,
  };

  const price = trade.entry_price ?? 0;

  return (
    <div className="space-y-6">
      {/* Trade summary header */}
      <div className="glass-card p-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-xs text-subtle mb-1">Symbol</div>
            <div className="font-bold text-white">{toDisplayName(trade.symbol)}</div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Side</div>
            <span className={trade.side === "BUY" ? "badge-buy" : "badge-sell"}>{trade.side}</span>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">PnL</div>
            <div className="font-bold" style={{ color: (trade.pnl ?? 0) >= 0 ? "#06b6d4" : "#ef4444" }}>
              {(trade.pnl ?? 0) >= 0 ? "+" : ""}{(trade.pnl ?? 0).toFixed(2)} USDT
            </div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Reason</div>
            <div className="text-gray-300">{trade.reason ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Entry Price</div>
            <div className="text-gray-300">{trade.entry_price?.toFixed(4) ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Exit Price</div>
            <div className="text-gray-300">{trade.exit_price?.toFixed(4) ?? "—"}</div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Strategy</div>
            <div className="text-gray-300">{trade.strategy}</div>
          </div>
          <div>
            <div className="text-xs text-subtle mb-1">Opened</div>
            <div className="text-gray-300 text-xs">
              {trade.opened_at ? new Date(trade.opened_at).toLocaleString() : "—"}
            </div>
          </div>
        </div>
      </div>

      <RuleBasedBreakdown signal={signal} symbol={trade.symbol} />
      <OllamaPanel signal={signal} symbol={trade.symbol} price={price} />
    </div>
  );
}

export default function ExplainPage() {
  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in max-w-4xl">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Trade Explanation</h1>
          <p className="text-subtle text-sm">Rule-based breakdown + optional AI narrative (requires Ollama locally)</p>
        </div>
        <Suspense fallback={<div className="text-subtle text-sm">Loading trade data...</div>}>
          <ExplainContent />
        </Suspense>
      </div>
    </AppShell>
  );
}
