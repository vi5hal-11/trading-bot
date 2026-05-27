"use client";
import { useModels } from "@/lib/hooks/useModels";

export default function ModelHistory() {
  const { models, isLoading } = useModels();

  if (isLoading) {
    return <div className="h-32 rounded-xl animate-pulse" style={{ background: "rgba(255,255,255,0.04)" }} />;
  }

  if (!models.length) {
    return (
      <div className="glass-card p-12 text-center text-subtle text-sm">
        No model versions yet — run retrain to populate
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <table className="w-full text-left">
        <thead>
          <tr className="text-xs text-subtle uppercase border-b" style={{ borderColor: "rgba(99,102,241,0.15)" }}>
            {["Version", "Trained", "CV Acc", "Sharpe", "Win Rate", "Drawdown", "Samples", "Champion"].map((h) => (
              <th key={h} className="px-4 py-3 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr
              key={m.id}
              className="border-b hover:bg-white/5 transition-colors"
              style={{
                borderColor: "rgba(99,102,241,0.08)",
                background: m.is_champion ? "rgba(99,102,241,0.06)" : undefined,
              }}
            >
              <td className="px-4 py-3 text-sm font-mono text-gray-300">{m.version}</td>
              <td className="px-4 py-3 text-xs text-subtle">
                {new Date(m.trained_at).toLocaleDateString()}
              </td>
              <td className="px-4 py-3 text-sm">{((m.cv_accuracy ?? 0) * 100).toFixed(1)}%</td>
              <td className="px-4 py-3 text-sm" style={{ color: (m.sharpe ?? 0) > 0 ? "#06b6d4" : "#ef4444" }}>
                {(m.sharpe ?? 0).toFixed(3)}
              </td>
              <td className="px-4 py-3 text-sm">{((m.win_rate ?? 0) * 100).toFixed(1)}%</td>
              <td className="px-4 py-3 text-sm text-loss">
                {((m.max_drawdown ?? 0) * 100).toFixed(1)}%
              </td>
              <td className="px-4 py-3 text-sm text-subtle">{m.n_samples?.toLocaleString()}</td>
              <td className="px-4 py-3">
                {m.is_champion && (
                  <span className="px-2 py-0.5 rounded text-xs font-semibold"
                    style={{ background: "rgba(99,102,241,0.2)", color: "#a5b4fc" }}>
                    Champion
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
