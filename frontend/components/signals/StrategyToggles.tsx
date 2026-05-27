"use client";
import { useState } from "react";
import { useLive } from "@/lib/live-context";
import { api } from "@/lib/api";
import { toast } from "sonner";

const STRATEGY_META: { key: string; label: string; desc: string }[] = [
  { key: "momentum", label: "Momentum", desc: "RSI + MACD trend strength" },
  { key: "mean_reversion", label: "Mean Reversion", desc: "Bollinger Band extremes" },
  { key: "trend_following", label: "Trend Following", desc: "EMA crossover + ADX" },
  { key: "ml_xgboost", label: "ML XGBoost", desc: "Trained classifier signals" },
  { key: "sentiment", label: "Sentiment", desc: "Fear/Greed + CryptoPanic" },
];

export default function StrategyToggles() {
  const { status } = useLive();
  const [busy, setBusy] = useState<string | null>(null);

  const enabled = status?.strategy_enabled ?? {};

  async function toggle(name: string, current: boolean) {
    setBusy(name);
    try {
      await api.toggleStrategy(name, !current);
      toast.success(`${name} ${!current ? "enabled" : "disabled"}`);
      // WS broadcast from server updates state automatically
    } catch {
      toast.error("Toggle failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="glass-card p-5">
      <div className="text-xs text-subtle uppercase tracking-wider mb-4">Strategy Toggles</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {STRATEGY_META.map(({ key, label, desc }) => {
          const on = enabled[key] ?? true;
          const loading = busy === key;
          return (
            <button
              key={key}
              onClick={() => toggle(key, on)}
              disabled={loading}
              className="flex flex-col gap-1.5 p-3 rounded-xl text-left transition-all disabled:opacity-50"
              style={{
                background: on ? "rgba(99,102,241,0.15)" : "rgba(255,255,255,0.03)",
                border: `1px solid ${on ? "rgba(99,102,241,0.4)" : "rgba(255,255,255,0.08)"}`,
              }}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold" style={{ color: on ? "#a5b4fc" : "#6b7280" }}>
                  {label}
                </span>
                <div
                  className="w-7 h-4 rounded-full flex items-center transition-all"
                  style={{
                    background: on ? "rgba(99,102,241,0.6)" : "rgba(255,255,255,0.1)",
                    padding: "2px",
                    justifyContent: on ? "flex-end" : "flex-start",
                  }}
                >
                  <div className="w-3 h-3 rounded-full bg-white" />
                </div>
              </div>
              <span className="text-xs" style={{ color: "#4b5563" }}>{desc}</span>
              <span className="text-xs font-medium" style={{ color: on ? "#6366f1" : "#374151" }}>
                {loading ? "..." : on ? "Active" : "Disabled"}
              </span>
            </button>
          );
        })}
      </div>
      <p className="text-xs text-subtle mt-3">
        Disabled strategies contribute HOLD with 0 confidence — takes effect on the next signal loop.
      </p>
    </div>
  );
}
