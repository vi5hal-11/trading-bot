"use client";
import { useState } from "react";
import AppShell from "@/components/layout/AppShell";
import TradingViewChart from "@/components/charts/TradingViewChart";
import AnalysisPanel from "@/components/charts/AnalysisPanel";
import { useLive } from "@/lib/live-context";
import { DISPLAY_SYMBOLS, toDisplayName } from "@/lib/binance";

export default function ChartsPage() {
  const [selected, setSelected] = useState(DISPLAY_SYMBOLS[0]);
  const { prices, connected } = useLive();

  const currentPrice = prices[selected];

  return (
    <AppShell>
      <div className="space-y-4 animate-fade-in">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-xl font-bold text-white mb-1">Live Charts</h1>
            <p className="text-subtle text-sm">
              TradingView Advanced Chart — full indicators, drawing tools, multi-timeframe
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-400 animate-pulse" : "bg-red-500"}`} />
            <span className="text-subtle">{connected ? "Live" : "Reconnecting..."}</span>
            {currentPrice && (
              <span className="font-semibold text-white ml-2">
                {toDisplayName(selected)} ${currentPrice.toFixed(2)}
              </span>
            )}
          </div>
        </div>

        {/* Quick-switch tabs for bot symbols */}
        <div className="flex gap-2 flex-wrap">
          {DISPLAY_SYMBOLS.map((sym) => (
            <button
              key={sym}
              onClick={() => setSelected(sym)}
              className="px-4 py-2 rounded-lg text-sm font-semibold transition-all"
              style={{
                background: selected === sym ? "rgba(99,102,241,0.2)" : "rgba(255,255,255,0.04)",
                color: selected === sym ? "#a5b4fc" : "#6b7280",
                border: `1px solid ${selected === sym ? "rgba(99,102,241,0.4)" : "rgba(99,102,241,0.15)"}`,
              }}
            >
              {toDisplayName(sym)}
              {prices[sym] && (
                <span className="ml-2 text-xs opacity-70">${prices[sym].toFixed(0)}</span>
              )}
            </button>
          ))}
          <span className="text-xs text-subtle self-center ml-2">
            You can also search any symbol directly inside the chart
          </span>
        </div>

        {/* Persistent chart — never remounted, symbol changes via widget API */}
        <div className="rounded-xl overflow-hidden" style={{ border: "1px solid rgba(99,102,241,0.15)" }}>
          <TradingViewChart symbol={selected} />
        </div>

        {/* Analysis panel — indicator values + strategy votes for selected symbol */}
        <AnalysisPanel symbol={selected} />
      </div>
    </AppShell>
  );
}
