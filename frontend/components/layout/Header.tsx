"use client";
import NotificationBell from "@/components/notifications/NotificationBell";
import { useLive } from "@/lib/live-context";
import { useNotifications } from "@/components/notifications/useNotifications";
import type { Notification } from "@/components/notifications/useNotifications";

export default function Header() {
  const { status, signals, activity, connected } = useLive();
  const { notifications } = useNotifications(signals, activity);

  const uptime = status?.uptime_seconds ?? 0;
  const hours = Math.floor(uptime / 3600);
  const mins = Math.floor((uptime % 3600) / 60);

  return (
    <header
      className="flex items-center justify-between px-6 py-3 border-b"
      style={{ borderColor: "rgba(99,102,241,0.15)", background: "rgba(13,15,26,0.9)" }}
    >
      <div className="flex items-center gap-3">
        {/* Live indicator */}
        <span className="flex items-center gap-1.5 text-xs text-subtle mr-1">
          <span className={`w-1.5 h-1.5 rounded-full ${connected ? "bg-green-400 animate-pulse" : "bg-red-500"}`} />
          {connected ? "Live" : "Offline"}
        </span>

        {status && (
          <>
            <span
              className="text-xs px-2 py-0.5 rounded font-semibold"
              style={{
                background: status.mode === "PAPER" ? "rgba(99,102,241,0.2)" : "rgba(6,182,212,0.2)",
                color: status.mode === "PAPER" ? "#a5b4fc" : "#06b6d4",
              }}
            >
              {status.mode}
            </span>
            {!status.running && (
              <span className="text-xs px-2 py-0.5 rounded font-semibold"
                style={{ background: "rgba(239,68,68,0.2)", color: "#ef4444" }}>
                STOPPED
              </span>
            )}
            {status.paused && (
              <span className="text-xs px-2 py-0.5 rounded font-semibold"
                style={{ background: "rgba(245,158,11,0.2)", color: "#f59e0b" }}>
                PAUSED
              </span>
            )}
            {status.circuit_breaker_active && (
              <span className="text-xs px-2 py-0.5 rounded font-semibold"
                style={{ background: "rgba(239,68,68,0.2)", color: "#ef4444" }}>
                CB ACTIVE
              </span>
            )}
            <span className="text-xs text-subtle">
              Loop #{status.loop_count} | {hours}h {mins}m
            </span>
          </>
        )}
      </div>
      <NotificationBell notifications={notifications as Notification[]} />
    </header>
  );
}
