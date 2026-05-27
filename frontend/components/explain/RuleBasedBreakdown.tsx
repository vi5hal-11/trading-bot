import type { Signal } from "@/lib/types";
import { explainRule } from "@/lib/explainer";

interface Props {
  signal: Signal;
  symbol: string;
}

const STRATEGY_LABELS: Record<string, string> = {
  momentum: "Momentum",
  mean_reversion: "Mean Reversion",
  trend_following: "Trend Following",
  sentiment: "Sentiment",
  ml_xgboost: "ML XGBoost",
};

export default function RuleBasedBreakdown({ signal, symbol }: Props) {
  const { component_signals, component_confidences, action, consensus_score, confidence } = signal;
  const cs = component_signals || {};
  const cc = component_confidences || {};

  return (
    <div className="space-y-4">
      <div className="glass-card p-5">
        <div className="text-xs text-subtle uppercase tracking-wider mb-3">Signal Summary</div>
        <p className="text-sm text-gray-300 leading-relaxed">{explainRule(signal, symbol)}</p>
      </div>

      {Object.keys(cs).length > 0 && (
        <div className="glass-card overflow-hidden">
          <div className="px-4 py-3 border-b text-xs text-subtle uppercase tracking-wider"
            style={{ borderColor: "rgba(99,102,241,0.15)" }}>
            Strategy Vote Breakdown
          </div>
          <table className="w-full">
            <thead>
              <tr className="text-xs text-subtle border-b" style={{ borderColor: "rgba(99,102,241,0.1)" }}>
                <th className="px-4 py-2 text-left font-medium">Strategy</th>
                <th className="px-4 py-2 text-left font-medium">Vote</th>
                <th className="px-4 py-2 text-left font-medium">Confidence</th>
                <th className="px-4 py-2 text-left font-medium">Agrees?</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(cs).map(([key, vote]) => {
                const conf = cc[key] || 0;
                const agrees = vote === action;
                const voteColor = vote === "BUY" ? "#06b6d4" : vote === "SELL" ? "#ef4444" : "#6b7280";
                return (
                  <tr key={key} className="border-b hover:bg-white/5"
                    style={{ borderColor: "rgba(99,102,241,0.08)" }}>
                    <td className="px-4 py-3 text-sm text-gray-300">{STRATEGY_LABELS[key] || key}</td>
                    <td className="px-4 py-3">
                      <span className={vote === "BUY" ? "badge-buy" : vote === "SELL" ? "badge-sell" : "badge-hold"}>
                        {vote}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.08)" }}>
                          <div className="h-full rounded-full" style={{ width: `${conf * 100}%`, background: voteColor }} />
                        </div>
                        <span className="text-xs text-subtle">{(conf * 100).toFixed(0)}%</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-sm" style={{ color: agrees ? "#06b6d4" : "#6b7280" }}>
                      {agrees ? "Yes" : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        <div className="glass-card p-4 text-center">
          <div className="text-xs text-subtle mb-1">Ensemble Action</div>
          <span className={action === "BUY" ? "badge-buy text-base" : action === "SELL" ? "badge-sell text-base" : "badge-hold text-base"}>{action}</span>
        </div>
        <div className="glass-card p-4 text-center">
          <div className="text-xs text-subtle mb-1">Consensus Score</div>
          <div className="text-lg font-bold" style={{ color: consensus_score >= 0 ? "#06b6d4" : "#ef4444" }}>
            {consensus_score >= 0 ? "+" : ""}{consensus_score?.toFixed(3)}
          </div>
        </div>
        <div className="glass-card p-4 text-center">
          <div className="text-xs text-subtle mb-1">Confidence</div>
          <div className="text-lg font-bold text-white">{((confidence || 0) * 100).toFixed(1)}%</div>
        </div>
      </div>
    </div>
  );
}
