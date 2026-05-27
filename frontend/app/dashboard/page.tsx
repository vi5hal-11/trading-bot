"use client";
import { useState } from "react";
import AppShell from "@/components/layout/AppShell";
import MetricGrid from "@/components/dashboard/MetricGrid";
import EquityCurve from "@/components/dashboard/EquityCurve";
import { useLive } from "@/lib/live-context";
import { api } from "@/lib/api";
import { toast } from "sonner";
import type { BotStatus } from "@/lib/types";

function BotControlBar() {
  const { status } = useLive() as { status: BotStatus | null };
  const mutate = () => {}; // WS handles updates automatically
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<unknown>, msg: string, isError = false) {
    setBusy(true);
    try {
      await fn();
      if (isError) toast.error(msg); else toast.success(msg);
      mutate();
    } catch {
      toast.error("Request failed");
    } finally {
      setBusy(false);
    }
  }

  const running = status?.running ?? true;
  const paused = status?.paused ?? false;

  return (
    <div className="glass-card p-5 space-y-4">
      <div className="text-xs text-subtle uppercase tracking-wider">Bot Controls</div>

      {/* Running state indicator */}
      <div className="flex items-center gap-3">
        <div className={`w-2.5 h-2.5 rounded-full ${running ? "bg-green-400 animate-pulse" : "bg-red-500"}`} />
        <span className="text-sm font-semibold text-white">
          {running ? (paused ? "Running — paused (no new positions)" : "Running — active") : "Stopped"}
        </span>
      </div>

      {/* Primary lifecycle controls */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={() => run(() => api.startBot(), "Bot started")}
          disabled={busy || running}
          className="px-4 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-40"
          style={{ background: "rgba(34,197,94,0.15)", color: "#4ade80", border: "1px solid rgba(34,197,94,0.3)" }}
        >
          Start Bot
        </button>
        <button
          onClick={() => run(() => api.stopBot(false), "Bot stopped — positions held")}
          disabled={busy || !running}
          className="px-4 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-40"
          style={{ background: "rgba(245,158,11,0.15)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.3)" }}
        >
          Stop (hold positions)
        </button>
        <button
          onClick={() => {
            if (!confirm("Stop bot AND close all open positions now?")) return;
            run(() => api.stopBot(true), "Bot stopped — all positions closed");
          }}
          disabled={busy || !running}
          className="px-4 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-40"
          style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}
        >
          Stop + Close All
        </button>

        {/* Divider */}
        <div className="w-px self-stretch" style={{ background: "rgba(99,102,241,0.2)" }} />

        <button
          onClick={() => run(() => api.pauseBot(), "Trading paused")}
          disabled={busy || !running || paused}
          className="px-4 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-40"
          style={{ background: "rgba(99,102,241,0.15)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.3)" }}
        >
          Pause
        </button>
        <button
          onClick={() => run(() => api.resumeBot(), "Trading resumed")}
          disabled={busy || !running || !paused}
          className="px-4 py-2 rounded-lg text-xs font-semibold transition-all disabled:opacity-40"
          style={{ background: "rgba(6,182,212,0.15)", color: "#06b6d4", border: "1px solid rgba(6,182,212,0.3)" }}
        >
          Resume
        </button>
      </div>

      <p className="text-xs text-subtle">
        <span className="text-gray-400">Stop (hold)</span> — halts signal loop, open positions keep running with stops active. &nbsp;
        <span className="text-gray-400">Stop + Close All</span> — immediately closes every open position at market price.&nbsp;
        <span className="text-gray-400">Pause</span> — signals still generate but no new entries are opened.
      </p>
    </div>
  );
}

export default function DashboardPage() {
  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Portfolio Overview</h1>
          <p className="text-subtle text-sm">Real-time portfolio metrics — refreshes every 5s</p>
        </div>
        <MetricGrid />
        <EquityCurve />
        <BotControlBar />
      </div>
    </AppShell>
  );
}
