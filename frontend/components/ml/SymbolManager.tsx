"use client";
import { useState } from "react";
import { useLive } from "@/lib/live-context";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { toDisplayName } from "@/lib/binance";

const COMMON_SYMBOLS = [
  "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "HYPE/USDT:USDT",
  "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
  "LINK/USDT:USDT", "DOT/USDT:USDT", "ADA/USDT:USDT", "MATIC/USDT:USDT",
];

export default function SymbolManager() {
  const { status } = useLive();
  const symbols: string[] = status?.symbols ?? [];

  const [custom, setCustom] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function add(symbol: string) {
    if (!symbol.trim()) return;
    setBusy(symbol);
    try {
      await api.addSymbol(symbol.trim());
      toast.success(`Added ${toDisplayName(symbol)}`);
      setCustom("");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed";
      toast.error(msg.includes("409") ? `${toDisplayName(symbol)} already in watchlist` : "Failed to add symbol");
    } finally {
      setBusy(null);
    }
  }

  async function remove(symbol: string) {
    if (!confirm(`Remove ${toDisplayName(symbol)} from watchlist? Any open position will be closed.`)) return;
    setBusy(symbol);
    try {
      await api.removeSymbol(symbol);
      toast.success(`Removed ${toDisplayName(symbol)}`);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed";
      toast.error(msg.includes("400") ? "Cannot remove last symbol" : "Failed to remove symbol");
    } finally {
      setBusy(null);
    }
  }

  const suggestions = COMMON_SYMBOLS.filter((s) => !symbols.includes(s));

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs text-subtle mb-3">Active Watchlist ({symbols.length})</div>
        <div className="flex flex-wrap gap-2">
          {symbols.map((s) => (
            <div
              key={s}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm"
              style={{ background: "rgba(99,102,241,0.15)", border: "1px solid rgba(99,102,241,0.3)" }}
            >
              <span className="font-semibold" style={{ color: "#a5b4fc" }}>{toDisplayName(s)}</span>
              <button
                onClick={() => remove(s)}
                disabled={busy === s || symbols.length <= 1}
                className="text-xs transition-colors disabled:opacity-30 hover:text-red-400"
                style={{ color: "#6b7280" }}
                title="Remove from watchlist"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>

      {suggestions.length > 0 && (
        <div>
          <div className="text-xs text-subtle mb-2">Quick Add</div>
          <div className="flex flex-wrap gap-2">
            {suggestions.slice(0, 8).map((s) => (
              <button
                key={s}
                onClick={() => add(s)}
                disabled={busy === s}
                className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all disabled:opacity-50"
                style={{ background: "rgba(255,255,255,0.04)", color: "#9ca3af", border: "1px solid rgba(255,255,255,0.1)" }}
              >
                + {toDisplayName(s)}
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs text-subtle mb-2">Custom Symbol</div>
        <div className="flex gap-3">
          <input
            type="text"
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add(custom)}
            placeholder="e.g. DOGE/USDT:USDT"
            className="flex-1 px-3 py-2 rounded-lg text-sm text-white focus:outline-none focus:ring-1 focus:ring-primary"
            style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(99,102,241,0.25)" }}
          />
          <button
            onClick={() => add(custom)}
            disabled={!custom.trim() || busy === custom}
            className="px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-50"
            style={{ background: "rgba(99,102,241,0.25)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.4)" }}
          >
            Add
          </button>
        </div>
        <p className="text-xs text-subtle mt-2">
          Format: <span className="text-gray-400">TOKEN/USDT:USDT</span>.
          Changes take effect on the next bot loop. Removing a symbol closes any open position instantly.
        </p>
      </div>
    </div>
  );
}
