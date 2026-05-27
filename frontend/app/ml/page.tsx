"use client";
import { useState } from "react";
import AppShell from "@/components/layout/AppShell";
import BotControls from "@/components/ml/BotControls";
import RiskHotForm from "@/components/ml/RiskHotForm";
import RiskConfigForm from "@/components/ml/RiskConfigForm";
import SymbolManager from "@/components/ml/SymbolManager";
import ModelHistory from "@/components/ml/ModelHistory";

const TABS = ["Bot Controls", "Live Risk", "Symbols", "Config (File)", "Model History"] as const;
type Tab = (typeof TABS)[number];

export default function MLPage() {
  const [tab, setTab] = useState<Tab>("Bot Controls");

  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">ML & Controls</h1>
          <p className="text-subtle text-sm">Bot controls, live risk tuning, symbol watchlist, and ML model history</p>
        </div>

        <div className="flex gap-2 border-b flex-wrap" style={{ borderColor: "rgba(99,102,241,0.15)" }}>
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="px-4 py-2.5 text-sm font-semibold transition-all border-b-2 -mb-px whitespace-nowrap"
              style={{
                borderColor: tab === t ? "#6366f1" : "transparent",
                color: tab === t ? "#a5b4fc" : "#6b7280",
              }}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="glass-card p-5 animate-fade-in">
          {tab === "Bot Controls" && <BotControls />}
          {tab === "Live Risk" && <RiskHotForm />}
          {tab === "Symbols" && <SymbolManager />}
          {tab === "Config (File)" && <RiskConfigForm />}
          {tab === "Model History" && <ModelHistory />}
        </div>
      </div>
    </AppShell>
  );
}
