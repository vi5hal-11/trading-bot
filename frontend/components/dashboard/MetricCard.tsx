interface Props {
  label: string;
  value: string;
  delta?: number;
  deltaLabel?: string;
  color?: "gain" | "loss" | "warn" | "neutral";
  isLoading?: boolean;
}

export default function MetricCard({ label, value, delta, deltaLabel, color = "neutral", isLoading }: Props) {
  const colorMap = {
    gain: "#06b6d4",
    loss: "#ef4444",
    warn: "#f59e0b",
    neutral: "#e2e8f0",
  };

  return (
    <div className="glass-card p-5">
      <div className="text-xs text-subtle mb-2 uppercase tracking-wider">{label}</div>
      {isLoading ? (
        <div className="h-7 w-24 rounded animate-pulse" style={{ background: "rgba(255,255,255,0.08)" }} />
      ) : (
        <div className="text-2xl font-bold" style={{ color: colorMap[color] }}>
          {value}
        </div>
      )}
      {delta !== undefined && !isLoading && (
        <div className="text-xs mt-1" style={{ color: delta >= 0 ? "#06b6d4" : "#ef4444" }}>
          {delta >= 0 ? "+" : ""}
          {deltaLabel ?? `${(delta * 100).toFixed(2)}%`}
        </div>
      )}
    </div>
  );
}
