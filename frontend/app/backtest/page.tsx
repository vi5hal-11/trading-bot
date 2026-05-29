"use client";
import { useState, useEffect, useRef } from "react";
import AppShell from "@/components/layout/AppShell";

const API = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

interface Metrics {
  total_trades: number;
  win_rate: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  total_return: number;
  profit_factor: number;
  expectancy: number;
  avg_r_multiple: number;
  max_loss_streak: number;
  initial_balance: number;
  final_balance: number;
  cagr: number;
}

interface RunResult {
  status: string;
  started_at?: string;
  finished_at?: string;
  result?: { results: Record<string, { metrics?: Metrics; error?: string; windows?: { label: string; metrics: Metrics }[] }> };
  error?: string;
}

function MetricCard({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="rounded-xl p-4 border" style={{ background: "rgba(255,255,255,0.04)", borderColor: "rgba(99,102,241,0.15)" }}>
      <div className="text-xs text-subtle mb-1">{label}</div>
      <div className="text-xl font-bold" style={{ color: color ?? "#e2e8f0" }}>{value}</div>
      {sub && <div className="text-xs text-subtle mt-0.5">{sub}</div>}
    </div>
  );
}

function MetricsGrid({ m }: { m: Metrics }) {
  const ret = m.total_return;
  const retColor = ret >= 0 ? "#06b6d4" : "#ef4444";
  const sharpeColor = m.sharpe >= 1 ? "#06b6d4" : m.sharpe >= 0 ? "#a5b4fc" : "#ef4444";
  const edgeColor = m.expectancy > 0 ? "#06b6d4" : "#ef4444";

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      <MetricCard label="Total Return" value={`${(ret * 100).toFixed(2)}%`} sub={`$${m.initial_balance.toLocaleString()} → $${m.final_balance.toLocaleString()}`} color={retColor} />
      <MetricCard label="Sharpe Ratio" value={m.sharpe.toFixed(3)} sub={m.sharpe >= 1 ? "Good" : m.sharpe >= 0 ? "Marginal" : "Poor"} color={sharpeColor} />
      <MetricCard label="Win Rate" value={`${(m.win_rate * 100).toFixed(1)}%`} sub={`${m.total_trades} trades`} />
      <MetricCard label="Max Drawdown" value={`${(m.max_drawdown * 100).toFixed(2)}%`} color={m.max_drawdown > 0.15 ? "#ef4444" : "#a5b4fc"} />
      <MetricCard label="Profit Factor" value={m.profit_factor === Infinity ? "∞" : m.profit_factor.toFixed(3)} sub="> 1.5 is solid" color={m.profit_factor >= 1.5 ? "#06b6d4" : m.profit_factor >= 1 ? "#a5b4fc" : "#ef4444"} />
      <MetricCard label="Sortino Ratio" value={m.sortino.toFixed(3)} />
      <MetricCard label="Expectancy / trade" value={`${(m.expectancy * 100).toFixed(3)}%`} sub={m.expectancy > 0 ? "Edge exists ✓" : "No edge ✗"} color={edgeColor} />
      <MetricCard label="Avg R-Multiple" value={`${m.avg_r_multiple.toFixed(3)}R`} sub={`Max losing streak: ${m.max_loss_streak}`} />
    </div>
  );
}

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("");
  const [months, setMonths] = useState(3);
  const [walkForward, setWalkForward] = useState(false);
  const [threshold, setThreshold] = useState(0.10);
  const [status, setStatus] = useState<RunResult | null>(null);
  const [loading, setLoading] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const poll = async () => {
    try {
      const r = await fetch(`${API}/api/backtest/result`);
      const data: RunResult = await r.json();
      setStatus(data);
      if (data.status === "running") {
        pollRef.current = setTimeout(poll, 3000);
      } else {
        setLoading(false);
      }
    } catch {
      setLoading(false);
    }
  };

  const startBacktest = async () => {
    setLoading(true);
    setStatus({ status: "starting" });
    try {
      await fetch(`${API}/api/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: symbol || undefined, months, walk_forward: walkForward, threshold }),
      });
      pollRef.current = setTimeout(poll, 2000);
    } catch (e) {
      setLoading(false);
      setStatus({ status: "error", error: String(e) });
    }
  };

  useEffect(() => () => { if (pollRef.current) clearTimeout(pollRef.current); }, []);

  const results = status?.result?.results ?? {};

  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Backtester</h1>
          <p className="text-subtle text-sm">Test strategies on historical data before going live</p>
        </div>

        {/* Config panel */}
        <div className="rounded-xl p-5 border space-y-4" style={{ background: "rgba(255,255,255,0.04)", borderColor: "rgba(99,102,241,0.15)" }}>
          <div className="text-sm font-semibold text-white">Configuration</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="text-xs text-subtle block mb-1">Symbol (blank = all)</label>
              <select
                value={symbol}
                onChange={e => setSymbol(e.target.value)}
                className="w-full rounded-lg px-3 py-2 text-sm text-white border"
                style={{ background: "rgba(255,255,255,0.06)", borderColor: "rgba(99,102,241,0.2)" }}
              >
                <option value="">All symbols</option>
                <option value="BTC/USDT:USDT">BTC</option>
                <option value="ETH/USDT:USDT">ETH</option>
                <option value="SOL/USDT:USDT">SOL</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-subtle block mb-1">Months of history</label>
              <select
                value={months}
                onChange={e => setMonths(Number(e.target.value))}
                className="w-full rounded-lg px-3 py-2 text-sm text-white border"
                style={{ background: "rgba(255,255,255,0.06)", borderColor: "rgba(99,102,241,0.2)" }}
              >
                {[1, 2, 3, 6, 12].map(m => <option key={m} value={m}>{m} month{m > 1 ? "s" : ""}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-subtle block mb-1">Entry threshold</label>
              <select
                value={threshold}
                onChange={e => setThreshold(Number(e.target.value))}
                className="w-full rounded-lg px-3 py-2 text-sm text-white border"
                style={{ background: "rgba(255,255,255,0.06)", borderColor: "rgba(99,102,241,0.2)" }}
              >
                <option value={0.05}>0.05 (sensitive)</option>
                <option value={0.10}>0.10 (default)</option>
                <option value={0.20}>0.20 (selective)</option>
                <option value={0.30}>0.30 (live bot)</option>
              </select>
            </div>
            <div className="flex flex-col justify-between">
              <label className="text-xs text-subtle block mb-1">Walk-forward</label>
              <label className="flex items-center gap-2 cursor-pointer">
                <div
                  onClick={() => setWalkForward(v => !v)}
                  className="w-10 h-5 rounded-full relative transition-all cursor-pointer"
                  style={{ background: walkForward ? "#6366f1" : "rgba(255,255,255,0.1)" }}
                >
                  <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all" style={{ left: walkForward ? "1.25rem" : "0.125rem" }} />
                </div>
                <span className="text-sm text-subtle">{walkForward ? "On" : "Off"}</span>
              </label>
            </div>
          </div>

          <button
            onClick={startBacktest}
            disabled={loading}
            className="px-6 py-2.5 rounded-lg text-sm font-semibold text-white transition-all disabled:opacity-50"
            style={{ background: loading ? "rgba(99,102,241,0.4)" : "#6366f1" }}
          >
            {loading ? "⏳ Running backtest..." : "▶ Run Backtest"}
          </button>
        </div>

        {/* Status */}
        {status && status.status !== "no_run_yet" && (
          <div className="rounded-xl p-4 border text-sm" style={{ background: "rgba(255,255,255,0.03)", borderColor: "rgba(99,102,241,0.12)" }}>
            <span className="text-subtle">Status: </span>
            <span className={status.status === "complete" ? "text-green-400" : status.status === "error" ? "text-red-400" : "text-yellow-400"}>
              {status.status === "running" ? "⏳ Running — this may take 1-2 minutes while data loads from Binance..." : status.status}
            </span>
            {status.error && <span className="text-red-400 ml-2">— {status.error}</span>}
            {status.finished_at && <span className="text-subtle ml-4">Finished: {new Date(status.finished_at).toLocaleTimeString()}</span>}
          </div>
        )}

        {/* Results */}
        {Object.entries(results).map(([sym, r]) => (
          <div key={sym} className="rounded-xl p-5 border space-y-4" style={{ background: "rgba(255,255,255,0.03)", borderColor: "rgba(99,102,241,0.12)" }}>
            <div className="font-semibold text-white">{sym.replace("/USDT:USDT", "")} Results</div>

            {r.error && <div className="text-red-400 text-sm">{r.error}</div>}

            {r.metrics && <MetricsGrid m={r.metrics} />}

            {r.windows && (
              <div>
                <div className="text-xs text-subtle mb-2">Walk-Forward Windows</div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead>
                      <tr className="text-subtle border-b" style={{ borderColor: "rgba(99,102,241,0.15)" }}>
                        {["Window", "Trades", "Win Rate", "Return", "Sharpe", "Expectancy"].map(h => (
                          <th key={h} className="pb-2 pr-6 font-medium">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {r.windows.map(w => (
                        <tr key={w.label} className="border-b" style={{ borderColor: "rgba(255,255,255,0.04)" }}>
                          <td className="py-2 pr-6 text-white">{w.label.split("(")[1]?.replace(")", "") ?? w.label}</td>
                          <td className="py-2 pr-6">{w.metrics.total_trades}</td>
                          <td className="py-2 pr-6" style={{ color: w.metrics.win_rate >= 0.5 ? "#06b6d4" : "#ef4444" }}>{(w.metrics.win_rate * 100).toFixed(1)}%</td>
                          <td className="py-2 pr-6" style={{ color: w.metrics.total_return >= 0 ? "#06b6d4" : "#ef4444" }}>{(w.metrics.total_return * 100).toFixed(2)}%</td>
                          <td className="py-2 pr-6" style={{ color: w.metrics.sharpe >= 1 ? "#06b6d4" : "#a5b4fc" }}>{w.metrics.sharpe.toFixed(3)}</td>
                          <td className="py-2 pr-6" style={{ color: w.metrics.expectancy > 0 ? "#06b6d4" : "#ef4444" }}>{(w.metrics.expectancy * 100).toFixed(3)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ))}

        {status?.status === "complete" && Object.keys(results).length === 0 && (
          <div className="text-subtle text-sm">No results — try a lower threshold or more months.</div>
        )}
      </div>
    </AppShell>
  );
}
