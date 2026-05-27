"use client";
import { useState } from "react";
import { useLive } from "@/lib/live-context";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { toDisplayName } from "@/lib/binance";
import type { Position } from "@/lib/types";

interface EditState {
  symbol: string;
  field: "stop" | "tp";
  value: string;
}

function EditCell({
  pos,
  field,
  edit,
  onEdit,
  onSave,
  onCancel,
}: {
  pos: Position;
  field: "stop" | "tp";
  edit: EditState | null;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const isEditing = edit?.symbol === pos.symbol && edit?.field === field;
  const value = field === "stop" ? pos.stop_loss : pos.take_profit;

  if (isEditing) {
    return (
      <td className="px-2 py-3">
        <div className="flex items-center gap-1">
          <input
            type="number"
            step="0.0001"
            value={edit!.value}
            onChange={(e) => (edit!.value = e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") onSave(); if (e.key === "Escape") onCancel(); }}
            autoFocus
            className="w-24 px-2 py-1 rounded text-xs text-white focus:outline-none focus:ring-1 focus:ring-primary"
            style={{ background: "rgba(255,255,255,0.08)", border: "1px solid rgba(99,102,241,0.4)" }}
          />
          <button
            onClick={onSave}
            className="px-1.5 py-1 rounded text-xs font-semibold"
            style={{ background: "rgba(99,102,241,0.25)", color: "#a5b4fc" }}
          >✓</button>
          <button
            onClick={onCancel}
            className="px-1.5 py-1 rounded text-xs"
            style={{ color: "#6b7280" }}
          >✕</button>
        </div>
      </td>
    );
  }

  return (
    <td className="px-4 py-3 text-sm text-subtle group">
      <span className="cursor-pointer hover:text-white transition-colors" onClick={onEdit} title={`Click to edit ${field === "stop" ? "stop-loss" : "take-profit"}`}>
        {value.toFixed(4)}
        <span className="ml-1 opacity-0 group-hover:opacity-60 text-xs">✎</span>
      </span>
    </td>
  );
}

export default function PositionsTable() {
  const { positions, connected } = useLive();
  const [edit, setEdit] = useState<EditState | null>(null);

  function startEdit(symbol: string, field: "stop" | "tp", currentVal: number) {
    setEdit({ symbol, field, value: currentVal.toFixed(4) });
  }

  async function saveEdit() {
    if (!edit) return;
    const val = parseFloat(edit.value);
    if (isNaN(val) || val <= 0) { toast.error("Invalid value"); return; }
    try {
      if (edit.field === "stop") {
        await api.updateStop(edit.symbol, val);
        toast.success(`Stop updated → ${val.toFixed(4)}`);
      } else {
        await api.updateTp(edit.symbol, val);
        toast.success(`Take-profit updated → ${val.toFixed(4)}`);
      }
      setEdit(null);
      // WS broadcast from server updates positions automatically
    } catch {
      toast.error("Update failed");
    }
  }

  async function closePosition(symbol: string) {
    if (!confirm(`Close ${toDisplayName(symbol)}?`)) return;
    try {
      await api.closePosition(symbol);
      toast.success(`${toDisplayName(symbol)} position closed`);
    } catch {
      toast.error("Failed to close position");
    }
  }

  if (!connected && !positions.length) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 rounded-lg animate-pulse" style={{ background: "rgba(255,255,255,0.04)" }} />
        ))}
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="glass-card p-12 text-center text-subtle text-sm">
        No open positions
      </div>
    );
  }

  return (
    <div className="glass-card overflow-hidden">
      <div className="px-4 py-2.5 text-xs text-subtle border-b" style={{ borderColor: "rgba(99,102,241,0.1)" }}>
        Click any Stop or TP value to edit — changes apply immediately to the bot.
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-xs text-subtle uppercase border-b" style={{ borderColor: "rgba(99,102,241,0.15)" }}>
              {["Symbol", "Side", "Entry", "Current", "Qty", "uPnL", "uPnL%", "Stop ✎", "TP ✎", "Strategy", "Age", "TP1", "TP2", "Close"].map(
                (h) => <th key={h} className="px-4 py-3 font-medium whitespace-nowrap">{h}</th>
              )}
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => {
              const pnlColor = p.unrealized_pnl >= 0 ? "#06b6d4" : "#ef4444";
              const isEditingStop = edit?.symbol === p.symbol && edit.field === "stop";
              const isEditingTp = edit?.symbol === p.symbol && edit.field === "tp";
              return (
                <tr key={p.symbol} className="border-b hover:bg-white/5 transition-colors" style={{ borderColor: "rgba(99,102,241,0.08)" }}>
                  <td className="px-4 py-3 text-sm font-semibold text-white">{toDisplayName(p.symbol)}</td>
                  <td className="px-4 py-3">
                    <span className={p.side === "BUY" ? "badge-buy" : "badge-sell"}>{p.side}</span>
                  </td>
                  <td className="px-4 py-3 text-sm">{p.entry_price.toFixed(4)}</td>
                  <td className="px-4 py-3 text-sm">{p.current_price.toFixed(4)}</td>
                  <td className="px-4 py-3 text-sm text-subtle">{p.quantity.toFixed(4)}</td>
                  <td className="px-4 py-3 text-sm font-semibold" style={{ color: pnlColor }}>
                    {p.unrealized_pnl >= 0 ? "+" : ""}{p.unrealized_pnl.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-sm" style={{ color: pnlColor }}>
                    {(p.unrealized_pnl_pct * 100).toFixed(2)}%
                  </td>

                  <EditCell
                    pos={p}
                    field="stop"
                    edit={isEditingStop ? edit : null}
                    onEdit={() => startEdit(p.symbol, "stop", p.stop_loss)}
                    onSave={saveEdit}
                    onCancel={() => setEdit(null)}
                  />
                  <EditCell
                    pos={p}
                    field="tp"
                    edit={isEditingTp ? edit : null}
                    onEdit={() => startEdit(p.symbol, "tp", p.take_profit)}
                    onSave={saveEdit}
                    onCancel={() => setEdit(null)}
                  />

                  <td className="px-4 py-3 text-xs text-subtle">{p.strategy} ({(p.confidence * 100).toFixed(0)}%)</td>
                  <td className="px-4 py-3 text-xs text-subtle">{p.age_minutes}m</td>
                  <td className="px-4 py-3 text-xs">
                    <span style={{ color: p.tp1_done ? "#06b6d4" : "#374151" }}>{p.tp1_done ? "Done" : "—"}</span>
                  </td>
                  <td className="px-4 py-3 text-xs">
                    <span style={{ color: p.tp2_done ? "#06b6d4" : "#374151" }}>{p.tp2_done ? "Done" : "—"}</span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => closePosition(p.symbol)}
                      className="px-2 py-1 rounded text-xs font-semibold transition-colors"
                      style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444", border: "1px solid rgba(239,68,68,0.3)" }}
                    >
                      Close
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
