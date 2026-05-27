"use client";
import { useLive } from "@/lib/live-context";
import { toDisplayName } from "@/lib/binance";
import type { IndicatorSnapshot, Signal } from "@/lib/types";

/* ── Indicator rows ───────────────────────────────────────────── */

interface IndicatorRowProps {
  label: string;
  value: number | null;
  format?: (v: number) => string;
  colorFn?: (v: number) => string;
}

function IndicatorRow({ label, value, format, colorFn }: IndicatorRowProps) {
  const display = value == null ? "—" : (format ? format(value) : String(value));
  const color = value != null && colorFn ? colorFn(value) : "#9ca3af";
  return (
    <div className="flex justify-between items-center py-1 border-b" style={{ borderColor: "rgba(99,102,241,0.06)" }}>
      <span className="text-xs text-subtle">{label}</span>
      <span className="text-xs font-mono font-semibold" style={{ color }}>{display}</span>
    </div>
  );
}

function rsiColor(v: number) {
  if (v >= 70) return "#ef4444";
  if (v <= 30) return "#06b6d4";
  return "#9ca3af";
}

function macdColor(v: number) {
  return v >= 0 ? "#06b6d4" : "#ef4444";
}

function adxColor(v: number) {
  if (v >= 25) return "#a5b4fc";
  return "#6b7280";
}

/* ── Strategy vote bars ───────────────────────────────────────── */

interface VoteBarProps {
  name: string;
  action: string;
  confidence: number;
}

function VoteBar({ name, action, confidence }: VoteBarProps) {
  const color = action === "BUY" ? "#06b6d4" : action === "SELL" ? "#ef4444" : "#4b5563";
  const pct = Math.round(confidence * 100);
  return (
    <div className="space-y-0.5">
      <div className="flex justify-between text-xs">
        <span className="text-subtle capitalize">{name.replace(/_/g, " ")}</span>
        <div className="flex items-center gap-2">
          <span className="font-semibold" style={{ color }}>{action}</span>
          <span className="text-gray-500">{pct}%</span>
        </div>
      </div>
      <div className="h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────── */

interface Props {
  symbol: string;
}

export default function AnalysisPanel({ symbol }: Props) {
  const { indicators, signals } = useLive();
  const ind: IndicatorSnapshot | undefined = indicators[symbol];
  const sig: Signal | undefined = signals[symbol];
  const short = toDisplayName(symbol);

  const actionColor = sig?.action === "BUY" ? "#06b6d4" : sig?.action === "SELL" ? "#ef4444" : "#6b7280";

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
      {/* Indicators */}
      <div className="glass-card p-4">
        <div className="text-xs text-subtle uppercase tracking-wider mb-3">{short} — Indicators</div>
        {!ind ? (
          <p className="text-gray-600 text-xs text-center py-4">Waiting for first loop...</p>
        ) : (
          <div>
            <IndicatorRow label="RSI (14)" value={ind.rsi} format={(v) => v.toFixed(1)} colorFn={rsiColor} />
            <IndicatorRow label="MACD Histogram" value={ind.macd_hist} format={(v) => v.toFixed(6)} colorFn={macdColor} />
            <IndicatorRow label="MACD Line" value={ind.macd} format={(v) => v.toFixed(6)} />
            <IndicatorRow label="MACD Signal" value={ind.macd_signal} format={(v) => v.toFixed(6)} />
            <IndicatorRow label="BB % (position)" value={ind.bb_pct} format={(v) => `${(v * 100).toFixed(1)}%`} />
            <IndicatorRow label="BB Upper" value={ind.bb_upper} format={(v) => v.toFixed(4)} />
            <IndicatorRow label="BB Lower" value={ind.bb_lower} format={(v) => v.toFixed(4)} />
            <IndicatorRow label="ADX" value={ind.adx} format={(v) => v.toFixed(1)} colorFn={adxColor} />
            <IndicatorRow label="ATR" value={ind.atr} format={(v) => v.toFixed(6)} />
            <IndicatorRow label="SMA Fast" value={ind.sma_fast} format={(v) => v.toFixed(4)} />
            <IndicatorRow label="SMA Slow" value={ind.sma_slow} format={(v) => v.toFixed(4)} />
            <IndicatorRow label="EMA 12" value={ind.ema_12} format={(v) => v.toFixed(4)} />
            <IndicatorRow label="EMA 26" value={ind.ema_26} format={(v) => v.toFixed(4)} />
            <IndicatorRow label="Volume Ratio" value={ind.vol_ratio} format={(v) => v.toFixed(2)} colorFn={(v) => v > 1.5 ? "#f59e0b" : "#9ca3af"} />
          </div>
        )}
      </div>

      {/* Signal & votes */}
      <div className="glass-card p-4">
        <div className="text-xs text-subtle uppercase tracking-wider mb-3">{short} — Signal</div>
        {!sig ? (
          <p className="text-gray-600 text-xs text-center py-4">No signal yet...</p>
        ) : (
          <div className="space-y-4">
            {/* Ensemble result */}
            <div className="flex items-center justify-between p-3 rounded-lg" style={{ background: "rgba(255,255,255,0.04)" }}>
              <div>
                <div className="text-xs text-subtle mb-0.5">Ensemble Decision</div>
                <div className="text-lg font-bold" style={{ color: actionColor }}>{sig.action}</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-subtle mb-0.5">Confidence</div>
                <div className="text-lg font-bold text-white">{(sig.confidence * 100).toFixed(1)}%</div>
              </div>
              <div className="text-right">
                <div className="text-xs text-subtle mb-0.5">Consensus</div>
                <div className="text-sm font-mono" style={{ color: (sig.consensus_score ?? 0) >= 0 ? "#06b6d4" : "#ef4444" }}>
                  {(sig.consensus_score ?? 0) >= 0 ? "+" : ""}{(sig.consensus_score ?? 0).toFixed(3)}
                </div>
              </div>
            </div>

            {/* Strategy votes */}
            {sig.component_signals && (
              <div className="space-y-2">
                <div className="text-xs text-subtle mb-1">Strategy Votes</div>
                {Object.entries(sig.component_signals).map(([name, action]) => (
                  <VoteBar
                    key={name}
                    name={name}
                    action={action}
                    confidence={sig.component_confidences?.[name] ?? 0}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
