"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */
import { useState } from "react";
import AppShell from "@/components/layout/AppShell";
import { useLive } from "@/lib/live-context";
import { api } from "@/lib/api";
import { toast } from "sonner";
import useSWR from "swr";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

// ── tiny helpers ─────────────────────────────────────────────────────────────

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl p-5 border" style={{ background: "rgba(255,255,255,0.04)", borderColor: "rgba(99,102,241,0.15)" }}>
      <div className="text-xs text-subtle uppercase tracking-wider mb-4">{title}</div>
      {children}
    </div>
  );
}

function Pill({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex justify-between items-center py-1.5 border-b last:border-0" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
      <span className="text-xs text-subtle">{label}</span>
      <span className="text-xs font-semibold font-mono" style={{ color: color ?? "#e2e8f0" }}>{value}</span>
    </div>
  );
}

// ── Bot status card ───────────────────────────────────────────────────────────

function StatusCard() {
  const { status } = useLive() as { status: any };
  const [busy, setBusy] = useState(false);

  if (!status) return (
    <Card title="Bot Status">
      <div className="text-subtle text-sm">Connecting...</div>
    </Card>
  );

  const running = status.running ?? true;
  const paused = status.paused ?? false;
  const cb = status.circuit_breaker_active;
  const uptime = status.uptime_seconds ?? 0;
  const h = Math.floor(uptime / 3600);
  const m = Math.floor((uptime % 3600) / 60);

  async function ctrl(fn: () => Promise<unknown>, msg: string) {
    setBusy(true);
    try { await fn(); toast.success(msg); } catch { toast.error("Failed"); } finally { setBusy(false); }
  }

  return (
    <Card title="Bot Status">
      <div className="flex items-center gap-2 mb-4">
        <div className={`w-2.5 h-2.5 rounded-full ${running && !paused ? "bg-green-400 animate-pulse" : paused ? "bg-yellow-400" : "bg-red-500"}`} />
        <span className="text-sm font-semibold text-white">
          {running ? (paused ? "Paused" : "Active") : "Stopped"}
        </span>
        <span className="text-xs text-subtle ml-auto">Loop #{status.loop_count}</span>
      </div>
      <Pill label="Mode" value={status.mode} />
      <Pill label="Uptime" value={`${h}h ${m}m`} />
      <Pill label="Circuit breaker" value={cb ? "🔴 TRIPPED" : "✅ OK"} color={cb ? "#ef4444" : "#4ade80"} />
      <Pill label="Open positions" value={String(Object.keys(status.strategy_enabled ?? {}).length > 0 ? "see below" : "—")} />
      <div className="flex gap-2 mt-4 flex-wrap">
        {!running && <button onClick={() => ctrl(() => api.startBot(), "Started")} disabled={busy} className="px-3 py-1.5 rounded-lg text-xs font-semibold" style={{ background: "rgba(34,197,94,0.2)", color: "#4ade80" }}>Start</button>}
        {running && !paused && <button onClick={() => ctrl(() => api.pauseBot(), "Paused")} disabled={busy} className="px-3 py-1.5 rounded-lg text-xs font-semibold" style={{ background: "rgba(245,158,11,0.2)", color: "#f59e0b" }}>Pause</button>}
        {running && paused && <button onClick={() => ctrl(() => api.resumeBot(), "Resumed")} disabled={busy} className="px-3 py-1.5 rounded-lg text-xs font-semibold" style={{ background: "rgba(6,182,212,0.2)", color: "#06b6d4" }}>Resume</button>}
        {running && <button onClick={() => ctrl(() => api.stopBot(false), "Stopped")} disabled={busy} className="px-3 py-1.5 rounded-lg text-xs font-semibold" style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444" }}>Stop</button>}
      </div>
    </Card>
  );
}

// ── Balance card ──────────────────────────────────────────────────────────────

function BalanceCard() {
  const { summary } = useLive() as { summary: any };
  if (!summary) return <Card title="Balance"><div className="text-subtle text-sm">Loading...</div></Card>;
  const pnl = summary.total_pnl ?? 0;
  const daily = summary.daily_pnl_pct ?? 0;
  const dd = summary.drawdown_from_peak ?? 0;
  return (
    <Card title="Balance">
      <div className="text-3xl font-bold text-white mb-1">{(summary.balance ?? 0).toFixed(2)} <span className="text-sm text-subtle">USDT</span></div>
      <div className="text-xs mb-4" style={{ color: pnl >= 0 ? "#06b6d4" : "#ef4444" }}>
        {pnl >= 0 ? "▲" : "▼"} {Math.abs(pnl).toFixed(2)} USDT all-time
      </div>
      <Pill label="Daily PnL" value={`${(daily * 100).toFixed(2)}%`} color={daily >= 0 ? "#06b6d4" : "#ef4444"} />
      <Pill label="Win rate" value={`${((summary.win_rate ?? 0) * 100).toFixed(1)}%`} />
      <Pill label="Total trades" value={String(summary.total_trades ?? 0)} />
      <Pill label="Drawdown" value={`${(dd * 100).toFixed(2)}%`} color={dd > 0.1 ? "#ef4444" : "#a5b4fc"} />
    </Card>
  );
}

// ── Positions card ────────────────────────────────────────────────────────────

function PositionsCard() {
  const { positions } = useLive() as { positions: any[] };
  const pos = positions ?? [];
  return (
    <Card title={`Open Positions (${pos.length})`}>
      {pos.length === 0
        ? <div className="text-subtle text-sm">No open positions</div>
        : pos.map((p: any) => {
          const pnl = p.unrealized_pnl ?? 0;
          const short = p.symbol?.replace("/USDT:USDT", "") ?? p.symbol;
          return (
            <div key={p.symbol} className="py-2 border-b last:border-0" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
              <div className="flex justify-between">
                <span className="text-sm font-semibold text-white">{short} {p.side}</span>
                <span className="text-sm font-mono" style={{ color: pnl >= 0 ? "#06b6d4" : "#ef4444" }}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}</span>
              </div>
              <div className="text-xs text-subtle mt-0.5">Entry: {p.entry_price?.toFixed(4)} | SL: {p.stop_loss?.toFixed(4)}</div>
            </div>
          );
        })}
    </Card>
  );
}

// ── Strategy toggles ──────────────────────────────────────────────────────────

const STRATEGIES = [
  { key: "momentum",       label: "Momentum",       desc: "RSI + MACD" },
  { key: "mean_reversion", label: "Mean Rev",        desc: "Bollinger Bands" },
  { key: "trend_following",label: "Trend",           desc: "EMA crossover" },
  { key: "ml_xgboost",    label: "ML",              desc: "XGBoost model" },
  { key: "sentiment",      label: "Sentiment",       desc: "News + Fear/Greed" },
  { key: "ifvg",           label: "IFVG",            desc: "Smart money" },
];

function StrategiesCard() {
  const { status } = useLive() as { status: any };
  const [busy, setBusy] = useState<string | null>(null);
  const enabled = status?.strategy_enabled ?? {};

  async function toggle(name: string, current: boolean) {
    setBusy(name);
    try {
      await api.toggleStrategy(name, !current);
      toast.success(`${name} ${!current ? "enabled" : "disabled"}`);
    } catch { toast.error("Toggle failed"); }
    finally { setBusy(null); }
  }

  return (
    <Card title="Strategy Toggles">
      <div className="space-y-2">
        {STRATEGIES.map(({ key, label, desc }) => {
          const on = enabled[key] ?? true;
          const loading = busy === key;
          return (
            <div key={key} className="flex items-center justify-between py-2 border-b last:border-0" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
              <div>
                <div className="text-sm font-medium" style={{ color: on ? "#e2e8f0" : "#6b7280" }}>{label}</div>
                <div className="text-xs text-subtle">{desc}</div>
              </div>
              <button
                onClick={() => toggle(key, on)}
                disabled={loading}
                className="w-12 h-6 rounded-full relative transition-all disabled:opacity-50"
                style={{ background: on ? "#6366f1" : "rgba(255,255,255,0.1)" }}
              >
                <div className="absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-all" style={{ left: on ? "1.6rem" : "0.1rem" }} />
              </button>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── Signals card ──────────────────────────────────────────────────────────────

function SignalsCard() {
  const { signals } = useLive() as { signals: any };
  const sigList = signals ? Object.values(signals) : [];
  return (
    <Card title="Latest Signals">
      {sigList.length === 0
        ? <div className="text-subtle text-sm">Waiting for first loop...</div>
        : (sigList as any[]).map((sig: any) => {
          const action = sig.action ?? "HOLD";
          const short = sig.symbol?.replace("/USDT:USDT", "") ?? "";
          const color = action === "BUY" ? "#06b6d4" : action === "SELL" ? "#ef4444" : "#6b7280";
          return (
            <div key={sig.symbol} className="py-2 border-b last:border-0" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-white">{short}</span>
                <span className="text-sm font-bold font-mono" style={{ color }}>{action}</span>
              </div>
              <div className="text-xs text-subtle">conf={sig.confidence?.toFixed(3)} | score={sig.consensus_score?.toFixed(3)}</div>
            </div>
          );
        })}
    </Card>
  );
}

// ── Post-mortem card ──────────────────────────────────────────────────────────

function PostMortemCard() {
  const { data } = useSWR(`${BASE}/api/postmortem`, fetcher, { refreshInterval: 30000 });
  const summary = data?.summary ?? {};
  const history = data?.history ?? [];
  const buckets = summary.buckets ?? {};
  const lossBuckets = Object.entries(buckets).filter(([k]) => k !== "win") as [string, number][];

  return (
    <Card title="Loss Attribution">
      {summary.total === 0 || !summary.total
        ? <div className="text-subtle text-sm">No closed trades yet — data appears after first trade closes</div>
        : <>
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div className="text-center">
              <div className="text-xl font-bold" style={{ color: "#06b6d4" }}>{((summary.win_rate ?? 0) * 100).toFixed(0)}%</div>
              <div className="text-xs text-subtle">Win rate</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold text-white">{summary.wins ?? 0}W</div>
              <div className="text-xs text-subtle">Winners</div>
            </div>
            <div className="text-center">
              <div className="text-xl font-bold" style={{ color: "#ef4444" }}>{summary.losses ?? 0}L</div>
              <div className="text-xs text-subtle">Losers</div>
            </div>
          </div>
          {lossBuckets.length > 0 && (
            <>
              <div className="text-xs text-subtle mb-2">Loss reasons:</div>
              {lossBuckets.sort((a, b) => (b[1] as number) - (a[1] as number)).map(([reason, count]) => (
                <div key={reason} className="flex justify-between items-center py-1">
                  <span className="text-xs text-subtle">{reason.replace(/_/g, " ")}</span>
                  <span className="text-xs font-mono font-semibold" style={{ color: "#f59e0b" }}>{count as number}×</span>
                </div>
              ))}
            </>
          )}
          {history.length > 0 && (
            <>
              <div className="text-xs text-subtle mt-4 mb-2">Recent trades:</div>
              {history.slice(0, 5).map((t: any, i: number) => (
                <div key={i} className="py-1 border-b last:border-0 text-xs" style={{ borderColor: "rgba(255,255,255,0.05)" }}>
                  <span style={{ color: t.loss_reason === "win" ? "#06b6d4" : "#ef4444" }}>
                    {t.loss_reason === "win" ? "✅" : "❌"}
                  </span>
                  {" "}{t.symbol?.replace("/USDT:USDT", "")} {t.side} — {t.loss_reason?.replace(/_/g, " ")} ({(t.pnl_pct * 100)?.toFixed(2)}%)
                </div>
              ))}
            </>
          )}
        </>
      }
    </Card>
  );
}

// ── Bandit weights card ───────────────────────────────────────────────────────

function BanditCard() {
  const { data } = useSWR(`${BASE}/api/bandit`, fetcher, { refreshInterval: 30000 });
  if (!data || !data.weights) return null;
  const weights = data.weights as Record<string, number>;
  const regime = data.regime ?? "unknown";
  const sorted = Object.entries(weights).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...Object.values(weights));

  return (
    <Card title={`Strategy Weights (${regime} regime)`}>
      <div className="space-y-2">
        {sorted.map(([name, w]) => (
          <div key={name}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-subtle">{name}</span>
              <span className="font-mono font-semibold text-white">{(w * 100).toFixed(1)}%</span>
            </div>
            <div className="h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div className="h-1.5 rounded-full transition-all" style={{ width: `${(w / max) * 100}%`, background: "#6366f1" }} />
            </div>
          </div>
        ))}
      </div>
      <div className="text-xs text-subtle mt-3">Weights adapt automatically after each trade via Thompson Sampling</div>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TrackingPage() {
  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Live Tracking</h1>
          <p className="text-subtle text-sm">Everything in one place — status, positions, strategies, learning</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <StatusCard />
          <BalanceCard />
          <PositionsCard />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <StrategiesCard />
          <SignalsCard />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <PostMortemCard />
          <BanditCard />
        </div>
      </div>
    </AppShell>
  );
}
