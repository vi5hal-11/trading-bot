const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(BASE + path);
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  }
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  return res.json();
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`PATCH ${path} → ${res.status}`);
  return res.json();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, { method: "DELETE", cache: "no-store" });
  if (!res.ok) throw new Error(`DELETE ${path} → ${res.status}`);
  return res.json();
}

export const api = {
  status: () => get("/api/status"),
  summary: () => get("/api/summary"),
  positions: () => get("/api/positions"),
  signals: () => get("/api/signals"),
  trades: (params?: { limit?: number; symbol?: string }) =>
    get("/api/trades", params as Record<string, string | number>),
  equityCurve: (hours = 168) => get("/api/equity-curve", { hours }),
  models: (limit = 20) => get("/api/models", { limit }),
  activity: () => get("/api/activity"),
  config: () => get("/api/config"),

  // Bot lifecycle
  pauseBot: () => post("/api/bot/pause"),
  resumeBot: () => post("/api/bot/resume"),
  startBot: () => post("/api/bot/start"),
  stopBot: (closePositions: boolean) => post("/api/bot/stop", { close_positions: closePositions }),

  // Strategy toggles
  toggleStrategy: (name: string, enabled: boolean) =>
    post("/api/strategies/toggle", { name, enabled }),

  // Hot-reload risk params
  patchRisk: (body: Record<string, number>) => patch("/api/risk", body),

  // Symbol watchlist
  getSymbols: () => get<{ symbols: string[] }>("/api/symbols"),
  addSymbol: (symbol: string) => post("/api/symbols", { symbol }),
  removeSymbol: (symbol: string) => del(`/api/symbols/${encodeURIComponent(symbol)}`),

  // Per-position controls
  closePosition: (symbol: string) => post(`/api/trade/close/${encodeURIComponent(symbol)}`),
  updateStop: (symbol: string, stop_loss: number) =>
    patch(`/api/positions/${encodeURIComponent(symbol)}/stop`, { stop_loss }),
  updateTp: (symbol: string, take_profit: number) =>
    patch(`/api/positions/${encodeURIComponent(symbol)}/tp`, { take_profit }),

  // Config (file-backed, applies on restart)
  patchConfig: (body: unknown) => post("/api/config", body),
  explain: (signal: unknown, symbol: string, price: number) =>
    post("/api/explain", { signal, symbol, price }),
};
