"use client";
import { useState } from "react";
import { useLive } from "@/lib/live-context";
import { api } from "@/lib/api";
import { toast } from "sonner";

const FIELDS: { key: string; label: string; step: string; hint: string }[] = [
  { key: "atr_multiplier", label: "ATR Stop Multiplier", step: "0.1", hint: "Distance of stop from entry in ATR units" },
  { key: "max_loss_pct", label: "Max Loss % / Trade", step: "0.001", hint: "Max portfolio % risked per trade" },
  { key: "tp1_pct", label: "TP1 Trigger %", step: "0.001", hint: "Profit % to trigger first partial exit" },
  { key: "tp2_pct", label: "TP2 Trigger %", step: "0.001", hint: "Profit % to trigger second partial exit" },
  { key: "tp1_size", label: "TP1 Sell Size", step: "0.05", hint: "Fraction of position sold at TP1 (0–1)" },
  { key: "tp2_size", label: "TP2 Sell Size", step: "0.05", hint: "Fraction of position sold at TP2 (0–1)" },
];

export default function RiskHotForm() {
  const { status } = useLive();
  const overrides = status?.risk_overrides ?? {};

  const [local, setLocal] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function set(key: string, val: string) {
    setLocal((prev) => ({ ...prev, [key]: val }));
  }

  function getValue(key: string): string {
    if (key in local) return local[key];
    if (key in overrides) return String(overrides[key]);
    return "";
  }

  async function apply() {
    const payload: Record<string, number> = {};
    for (const [k, v] of Object.entries(local)) {
      const n = parseFloat(v);
      if (!isNaN(n)) payload[k] = n;
    }
    if (!Object.keys(payload).length) { toast.error("No values to apply"); return; }
    setSaving(true);
    try {
      const res = await api.patchRisk(payload) as { updated: string[] };
      toast.success(`Applied: ${res.updated?.join(", ")}`);
      setLocal({});
      // WS broadcast from server updates overrides automatically
    } catch {
      toast.error("Failed to apply risk params");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {FIELDS.map(({ key, label, step, hint }) => (
          <div key={key}>
            <label className="block text-xs text-subtle mb-1">{label}</label>
            <input
              type="number"
              step={step}
              placeholder={key in overrides ? String(overrides[key]) : "default"}
              value={getValue(key)}
              onChange={(e) => set(key, e.target.value)}
              title={hint}
              className="w-full px-3 py-2 rounded-lg text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
              style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.25)" }}
            />
            <p className="text-xs mt-1" style={{ color: "#4b5563" }}>{hint}</p>
          </div>
        ))}
      </div>

      {Object.keys(overrides).length > 0 && (
        <div className="text-xs text-subtle">
          Active overrides: {Object.entries(overrides).map(([k, v]) => `${k}=${v}`).join(", ")}
        </div>
      )}

      <button
        onClick={apply}
        disabled={saving}
        className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-all disabled:opacity-50"
        style={{ background: "rgba(99,102,241,0.25)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.4)" }}
      >
        {saving ? "Applying..." : "Apply Immediately"}
      </button>
      <p className="text-xs text-subtle">
        Changes apply to the <strong className="text-gray-400">running bot immediately</strong> — no restart needed.
      </p>
    </div>
  );
}
