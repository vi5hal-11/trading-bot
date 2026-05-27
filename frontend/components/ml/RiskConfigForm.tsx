"use client";
import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type { BotConfig } from "@/lib/types";

const RISK_FIELDS: { key: keyof BotConfig["risk"]; label: string; step: string }[] = [
  { key: "max_loss_pct_per_trade", label: "Max Loss % / Trade", step: "0.001" },
  { key: "max_open_positions", label: "Max Open Positions", step: "1" },
  { key: "daily_loss_circuit_breaker", label: "Daily Circuit Breaker", step: "0.01" },
  { key: "trailing_stop_atr_multiplier", label: "ATR Stop Multiplier", step: "0.1" },
  { key: "max_portfolio_drawdown", label: "Max Portfolio Drawdown", step: "0.01" },
  { key: "max_total_exposure_pct", label: "Max Total Exposure", step: "0.05" },
];

export default function RiskConfigForm() {
  const [config, setConfig] = useState<BotConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.config().then((c) => { setConfig(c as BotConfig); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  function setRisk(key: string, val: string) {
    setConfig((c) => c ? { ...c, risk: { ...c.risk, [key]: key === "max_open_positions" ? parseInt(val) : parseFloat(val) } } : c);
  }

  function setEnsThreshold(val: string) {
    setConfig((c) => c ? { ...c, ensemble: { threshold: parseFloat(val) } } : c);
  }

  async function save() {
    if (!config) return;
    setSaving(true);
    try {
      const res = await api.patchConfig(config) as { updated: string[] };
      toast.success(`Saved: ${res.updated?.join(", ") || "config"}`);
    } catch {
      toast.error("Save failed");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="h-40 rounded-xl animate-pulse" style={{ background: "rgba(255,255,255,0.04)" }} />;
  }

  if (!config) {
    return <div className="text-subtle text-sm">Failed to load config</div>;
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {RISK_FIELDS.map(({ key, label, step }) => (
          <div key={key}>
            <label className="block text-xs text-subtle mb-1.5">{label}</label>
            <input
              type="number"
              step={step}
              value={config.risk[key] ?? ""}
              onChange={(e) => setRisk(key, e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
              style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.25)" }}
            />
          </div>
        ))}
        <div>
          <label className="block text-xs text-subtle mb-1.5">Ensemble Threshold</label>
          <input
            type="number"
            step="0.01"
            value={config.ensemble.threshold}
            onChange={(e) => setEnsThreshold(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
            style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.25)" }}
          />
        </div>
      </div>
      <button
        onClick={save}
        disabled={saving}
        className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-all disabled:opacity-50"
        style={{ background: "rgba(99,102,241,0.25)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.4)" }}
      >
        {saving ? "Saving..." : "Save Config"}
      </button>
      <p className="text-subtle text-xs">Changes apply on the next bot loop or restart.</p>
    </div>
  );
}
