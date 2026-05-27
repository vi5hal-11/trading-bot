"use client";
import useSWR from "swr";
import type { Trade } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function useTrades(params?: { limit?: number; symbol?: string }) {
  const qs = new URLSearchParams();
  if (params?.limit) qs.set("limit", String(params.limit));
  if (params?.symbol) qs.set("symbol", params.symbol);
  const url = `${BASE}/api/trades${qs.toString() ? "?" + qs.toString() : ""}`;

  const { data, error, isLoading, mutate } = useSWR<{ trades: Trade[] }>(url, fetcher, {
    refreshInterval: 30000,
  });
  return { trades: data?.trades ?? [], error, isLoading, mutate };
}
