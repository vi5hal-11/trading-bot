import type { Signal } from "@/lib/types";
import { toDisplayName } from "@/lib/binance";

interface Props {
  symbol: string;
  signal: Signal;
}

const STRATEGY_LABELS: Record<string, string> = {
  momentum: "Momentum",
  mean_reversion: "Mean Rev",
  trend_following: "Trend",
  sentiment: "Sentiment",
  ml_xgboost: "ML",
};

export default function SignalCard({ symbol, signal }: Props) {
  const { action, confidence, consensus_score, price, component_signals, component_confidences } = signal;
  const cs = component_signals || {};
  const cc = component_confidences || {};

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="font-bold text-white text-base">{toDisplayName(symbol)}</span>
        <span className={action === "BUY" ? "badge-buy" : action === "SELL" ? "badge-sell" : "badge-hold"}>
          {action}
        </span>
      </div>

      <div className="space-y-1 mb-3">
        <div className="flex justify-between text-xs">
          <span className="text-subtle">Confidence</span>
          <span className="text-white">{(confidence * 100).toFixed(1)}%</span>
        </div>
        <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.08)" }}>
          <div
            className="h-full rounded-full transition-all"
            style={{
              width: `${confidence * 100}%`,
              background: action === "BUY" ? "#06b6d4" : action === "SELL" ? "#ef4444" : "#6b7280",
            }}
          />
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-subtle">Consensus</span>
          <span style={{ color: consensus_score >= 0 ? "#06b6d4" : "#ef4444" }}>
            {consensus_score >= 0 ? "+" : ""}{consensus_score?.toFixed(3)}
          </span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-subtle">Price</span>
          <span className="text-white">{price?.toFixed(4)}</span>
        </div>
      </div>

      {Object.keys(cs).length > 0 && (
        <div className="border-t pt-3 space-y-1" style={{ borderColor: "rgba(99,102,241,0.15)" }}>
          <div className="text-xs text-subtle mb-2">Strategy Votes</div>
          {Object.entries(cs).map(([strat, act]) => {
            const conf = cc[strat] || 0;
            const actColor = act === "BUY" ? "#06b6d4" : act === "SELL" ? "#ef4444" : "#6b7280";
            return (
              <div key={strat} className="flex items-center justify-between text-xs">
                <span className="text-subtle">{STRATEGY_LABELS[strat] || strat}</span>
                <div className="flex items-center gap-2">
                  <span style={{ color: actColor }} className="font-semibold w-8 text-right">{act}</span>
                  <span className="text-subtle w-10 text-right">{(conf * 100).toFixed(0)}%</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
