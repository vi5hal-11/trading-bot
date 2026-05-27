"use client";
import { useLive } from "@/lib/live-context";
import { toDisplayName } from "@/lib/binance";

const TYPE_COLORS: Record<string, string> = {
  open: "#06b6d4",
  close: "#6366f1",
  signal: "#f59e0b",
  system: "#9ca3af",
};

export default function ActivityLog() {
  const { activity, connected } = useLive();

  return (
    <div className="glass-card overflow-hidden">
      <div className="px-4 py-3 border-b flex items-center justify-between"
        style={{ borderColor: "rgba(99,102,241,0.15)" }}>
        <span className="text-xs font-semibold text-subtle uppercase tracking-wider">Activity Log</span>
        <span className="flex items-center gap-1.5 text-xs text-subtle">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-400 animate-pulse" : "bg-red-500"}`} />
          {connected ? "Live" : "Offline"}
        </span>
      </div>
      <div className="overflow-y-auto max-h-72">
        {activity.length === 0 ? (
          <div className="px-4 py-6 text-center text-subtle text-sm">No activity yet</div>
        ) : (
          activity.map((entry, i) => (
            <div key={i} className="flex items-start gap-3 px-4 py-3 hover:bg-white/5 transition-colors">
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5"
                style={{ background: TYPE_COLORS[entry.type] ?? "#6b7280" }}
              />
              <div className="flex-1 min-w-0">
                <div className="text-sm text-gray-300 leading-tight">{entry.message}</div>
                <div className="text-xs text-subtle mt-0.5">
                  {new Date(entry.ts).toLocaleTimeString()}
                  {entry.symbol && (
                    <span className="ml-2 opacity-60">{toDisplayName(entry.symbol)}</span>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
