"use client";
import { useLive } from "@/lib/live-context";
import SignalCard from "./SignalCard";

export default function SignalFeed() {
  const { signals, connected } = useLive();
  const entries = Object.entries(signals);

  if (!connected && !entries.length) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="h-48 rounded-xl animate-pulse" style={{ background: "rgba(255,255,255,0.04)" }} />
        ))}
      </div>
    );
  }

  if (!entries.length) {
    return (
      <div className="glass-card p-12 text-center text-subtle text-sm">
        No signals yet — waiting for first bot loop
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {entries.map(([symbol, signal]) => (
        <SignalCard key={symbol} symbol={symbol} signal={signal} />
      ))}
    </div>
  );
}
