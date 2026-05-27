"use client";
import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import type { BotStatus, Position, Signal, PortfolioSummary, ActivityEntry, LogEntry, IndicatorSnapshot } from "./types";

export interface LiveState {
  prices: Record<string, number>;
  signals: Record<string, Signal>;
  positions: Position[];
  summary: PortfolioSummary | null;
  status: BotStatus | null;
  activity: ActivityEntry[];
  logs: LogEntry[];
  indicators: Record<string, IndicatorSnapshot>;
  connected: boolean;
}

const initial: LiveState = {
  prices: {},
  signals: {},
  positions: [],
  summary: null,
  status: null,
  activity: [],
  logs: [],
  indicators: {},
  connected: false,
};

const LiveContext = createContext<LiveState>(initial);

export function useLive() {
  return useContext(LiveContext);
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LiveState>(initial);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const pingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    const base = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8080").replace(/^http/, "ws");
    const url = `${base}/ws`;

    function connect() {
      if (!mountedRef.current) return;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setState((s) => ({ ...s, connected: true }));
        // Heartbeat every 20s to keep the connection alive through proxies
        pingRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send("ping");
        }, 20_000);
      };

      ws.onmessage = (e) => {
        if (!mountedRef.current) return;
        try {
          const data = JSON.parse(e.data as string);
          if (data.type !== "snapshot") return;
          setState((s) => ({
            ...s,
            prices: data.prices ?? s.prices,
            signals: data.signals ?? s.signals,
            positions: data.positions ?? s.positions,
            summary: data.summary && Object.keys(data.summary as object).length
              ? (data.summary as PortfolioSummary)
              : s.summary,
            status: (data.status as BotStatus) ?? s.status,
            activity: (data.activity as ActivityEntry[]) ?? s.activity,
            logs: (data.logs as LogEntry[]) ?? s.logs,
            indicators: (data.indicators as Record<string, IndicatorSnapshot>) ?? s.indicators,
          }));
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        if (pingRef.current) clearInterval(pingRef.current);
        if (!mountedRef.current) return;
        setState((s) => ({ ...s, connected: false }));
        timerRef.current = setTimeout(connect, 3_000);
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      mountedRef.current = false;
      if (pingRef.current) clearInterval(pingRef.current);
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
    };
  }, []);

  return <LiveContext.Provider value={state}>{children}</LiveContext.Provider>;
}
