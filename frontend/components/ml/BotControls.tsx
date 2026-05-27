"use client";
import { useStatus } from "@/lib/hooks/useStatus";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function BotControls() {
  const { status, isLoading } = useStatus();

  async function pause() {
    try { await api.pauseBot(); toast.info("Trading paused"); } catch { toast.error("Failed"); }
  }
  async function resume() {
    try { await api.resumeBot(); toast.success("Trading resumed"); } catch { toast.error("Failed"); }
  }

  const uptime = status?.uptime_seconds ?? 0;
  const hours = Math.floor(uptime / 3600);
  const mins = Math.floor((uptime % 3600) / 60);
  const secs = uptime % 60;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Mode", value: status?.mode ?? "—", color: status?.mode === "PAPER" ? "#a5b4fc" : "#06b6d4" },
          { label: "Loop Count", value: status ? `#${status.loop_count}` : "—", color: "#e2e8f0" },
          { label: "Uptime", value: status ? `${hours}h ${mins}m ${secs}s` : "—", color: "#e2e8f0" },
          { label: "Status", value: status?.paused ? "PAUSED" : "RUNNING", color: status?.paused ? "#f59e0b" : "#06b6d4" },
        ].map(({ label, value, color }) => (
          <div key={label} className="glass-card p-4">
            <div className="text-xs text-subtle mb-1">{label}</div>
            <div className="text-lg font-bold" style={{ color }}>{isLoading ? "—" : value}</div>
          </div>
        ))}
      </div>

      {status?.circuit_breaker_active && (
        <div className="rounded-lg p-4 text-sm font-semibold"
          style={{ background: "rgba(239,68,68,0.12)", color: "#f87171", border: "1px solid rgba(239,68,68,0.3)" }}>
          Circuit Breaker Active — daily or intraday loss limit exceeded. Trading is halted.
        </div>
      )}

      <div className="flex gap-3 flex-wrap">
        <button
          onClick={pause}
          disabled={status?.paused}
          className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-all disabled:opacity-40"
          style={{ background: "rgba(245,158,11,0.15)", color: "#f59e0b", border: "1px solid rgba(245,158,11,0.3)" }}
        >
          Pause Trading
        </button>
        <button
          onClick={resume}
          disabled={!status?.paused}
          className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-all disabled:opacity-40"
          style={{ background: "rgba(6,182,212,0.15)", color: "#06b6d4", border: "1px solid rgba(6,182,212,0.3)" }}
        >
          Resume Trading
        </button>
      </div>
      <p className="text-subtle text-xs">Pause prevents new positions from opening. Existing positions remain active until their stop or target is hit.</p>
    </div>
  );
}
