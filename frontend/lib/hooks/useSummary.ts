"use client";
import useSWR from "swr";
import type { PortfolioSummary } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function useSummary() {
  const { data, error, isLoading } = useSWR<PortfolioSummary>(`${BASE}/api/summary`, fetcher, {
    refreshInterval: 5000,
  });
  return { summary: data, error, isLoading };
}
