export const SYMBOL_MAP: Record<string, string> = {
  "BTC/USDT:USDT": "BTCUSDT",
  "ETH/USDT:USDT": "ETHUSDT",
  "SOL/USDT:USDT": "SOLUSDT",
  "HYPE/USDT:USDT": "HYPEUSDT",
};

export const DISPLAY_SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "HYPE/USDT:USDT"];

export function toBinanceSymbol(symbol: string): string {
  return SYMBOL_MAP[symbol] || symbol.replace("/USDT:USDT", "USDT");
}

export function toDisplayName(symbol: string): string {
  return symbol.replace("/USDT:USDT", "");
}

export interface Kline {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function fetchKlines(
  symbol: string,
  interval = "15m",
  limit = 500
): Promise<Kline[]> {
  const binanceSymbol = toBinanceSymbol(symbol);
  const url = `https://api.binance.com/api/v3/klines?symbol=${binanceSymbol}&interval=${interval}&limit=${limit}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Binance klines error: ${res.status}`);
  const data: unknown[][] = await res.json();
  return data.map((k) => ({
    time: Math.floor(Number(k[0]) / 1000),
    open: parseFloat(k[1] as string),
    high: parseFloat(k[2] as string),
    low: parseFloat(k[3] as string),
    close: parseFloat(k[4] as string),
    volume: parseFloat(k[5] as string),
  }));
}
