"use client";
import { useState } from "react";
import { Bell } from "lucide-react";
import type { Notification } from "./useNotifications";

interface Props {
  notifications: Notification[];
}

export default function NotificationBell({ notifications }: Props) {
  const [open, setOpen] = useState(false);
  const unread = notifications.length;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="relative p-2 rounded-lg hover:bg-white/5 transition-colors"
      >
        <Bell size={18} className="text-subtle" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 w-4 h-4 rounded-full text-xs flex items-center justify-center font-bold text-white"
            style={{ background: "#6366f1", fontSize: "9px" }}>
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div
            className="absolute right-0 top-10 w-80 rounded-xl border z-20 overflow-hidden animate-fade-in"
            style={{ background: "#0d1428", borderColor: "rgba(99,102,241,0.3)" }}
          >
            <div className="px-4 py-3 border-b text-xs font-semibold text-subtle"
              style={{ borderColor: "rgba(99,102,241,0.2)" }}>
              Recent Notifications ({notifications.length})
            </div>
            <div className="max-h-80 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="px-4 py-6 text-center text-subtle text-sm">No notifications yet</div>
              ) : (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    className="px-4 py-3 border-b text-xs hover:bg-white/5"
                    style={{ borderColor: "rgba(99,102,241,0.1)" }}
                  >
                    <div className="flex items-center gap-2">
                      <span
                        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                        style={{
                          background:
                            n.type === "buy" ? "#06b6d4" : n.type === "sell" ? "#ef4444" : "#6366f1",
                        }}
                      />
                      <span className="text-gray-300">{n.message}</span>
                    </div>
                    <div className="text-subtle mt-1 ml-3.5">
                      {new Date(n.ts).toLocaleTimeString()}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
