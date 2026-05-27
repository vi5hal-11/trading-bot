"use client";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import type { Signal, ActivityEntry } from "@/lib/types";

export interface Notification {
  id: string;
  type: "buy" | "sell" | "close" | "system";
  message: string;
  symbol?: string;
  ts: string;
}

export function useNotifications(signals: Record<string, Signal>, activity: ActivityEntry[]) {
  const prevSignals = useRef<Record<string, string>>({});
  const prevActivityLength = useRef(0);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const initialized = useRef(false);

  useEffect(() => {
    if (!initialized.current) {
      Object.entries(signals).forEach(([sym, sig]) => {
        prevSignals.current[sym] = sig.action;
      });
      prevActivityLength.current = activity.length;
      initialized.current = true;
      return;
    }

    // Check for new signals
    Object.entries(signals).forEach(([sym, sig]) => {
      const prev = prevSignals.current[sym];
      if (sig.action !== prev && (sig.action === "BUY" || sig.action === "SELL")) {
        const shortSym = sym.replace("/USDT:USDT", "");
        const msg = `${sig.action} signal on ${shortSym} — conf ${(sig.confidence * 100).toFixed(0)}%`;
        const notif: Notification = {
          id: `${sym}-${Date.now()}`,
          type: sig.action === "BUY" ? "buy" : "sell",
          message: msg,
          symbol: sym,
          ts: new Date().toISOString(),
        };
        setNotifications((prev) => [notif, ...prev].slice(0, 20));
        if (sig.action === "BUY") {
          toast.success(msg, { duration: 5000 });
        } else {
          toast.error(msg, { duration: 5000 });
        }
      }
      prevSignals.current[sym] = sig.action;
    });

    // Check for new activity (closed trades)
    if (activity.length > prevActivityLength.current) {
      const newEntries = activity.slice(0, activity.length - prevActivityLength.current);
      newEntries.forEach((entry) => {
        if (entry.type === "close") {
          const notif: Notification = {
            id: `close-${Date.now()}-${Math.random()}`,
            type: "close",
            message: entry.message,
            symbol: entry.symbol,
            ts: entry.ts,
          };
          setNotifications((prev) => [notif, ...prev].slice(0, 20));
          toast.info(entry.message, { duration: 4000 });
        }
      });
    }
    prevActivityLength.current = activity.length;
  }, [signals, activity]);

  return { notifications };
}
