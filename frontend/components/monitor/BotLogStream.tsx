"use client";
import { useEffect, useRef } from "react";
import { useLive } from "@/lib/live-context";
import type { LogEntry } from "@/lib/types";

const LEVEL_STYLES: Record<string, { color: string; label: string }> = {
  INFO:    { color: "#9ca3af", label: "INFO " },
  WARNING: { color: "#f59e0b", label: "WARN " },
  ERROR:   { color: "#ef4444", label: "ERR  " },
  DEBUG:   { color: "#6b7280", label: "DEBUG" },
};

function LogLine({ entry }: { entry: LogEntry }) {
  const style = LEVEL_STYLES[entry.level] ?? { color: "#9ca3af", label: entry.level.padEnd(5) };
  const time = entry.ts ? new Date(entry.ts).toLocaleTimeString("en-GB", { hour12: false }) : "";
  return (
    <div className="flex gap-2 text-xs font-mono leading-5 hover:bg-white/5 px-1 rounded">
      <span className="shrink-0 text-gray-600">{time}</span>
      <span className="shrink-0 font-semibold" style={{ color: style.color }}>{style.label}</span>
      <span className="text-gray-300 break-all">{entry.message}</span>
    </div>
  );
}

interface Props {
  maxHeight?: string;
  autoScroll?: boolean;
}

export default function BotLogStream({ maxHeight = "420px", autoScroll = true }: Props) {
  const { logs, connected } = useLive();
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledUp = useRef(false);

  useEffect(() => {
    if (!autoScroll || userScrolledUp.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, autoScroll]);

  function onScroll() {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    userScrolledUp.current = !atBottom;
  }

  if (!connected && logs.length === 0) {
    return (
      <div className="glass-card p-4 text-center text-subtle text-xs font-mono">
        Connecting to bot...
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <div
        className="px-3 py-2 flex items-center justify-between border-b"
        style={{ borderColor: "rgba(99,102,241,0.15)" }}
      >
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${connected ? "bg-green-400 animate-pulse" : "bg-red-500"}`} />
          <span className="text-xs text-subtle uppercase tracking-wider">Live Bot Log</span>
        </div>
        <span className="text-xs text-gray-600">{logs.length} entries</span>
      </div>
      <div
        ref={containerRef}
        onScroll={onScroll}
        className="overflow-y-auto p-3 space-y-0.5"
        style={{
          maxHeight,
          background: "rgba(0,0,0,0.3)",
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
        }}
      >
        {logs.length === 0 ? (
          <p className="text-gray-600 text-xs font-mono text-center py-8">
            Waiting for bot logs...
          </p>
        ) : (
          logs.map((entry, i) => <LogLine key={i} entry={entry} />)
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
