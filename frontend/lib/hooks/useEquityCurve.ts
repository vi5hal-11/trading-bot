"use client";
import useSWR from "swr";
import type { PortfolioSnapshot } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function useEquityCurve(hours = 168) {
  const { data, error, isLoading } = useSWR<{ snapshots: PortfolioSnapshot[] }>(
    `${BASE}/api/equity-curve?hours=${hours}`,
    fetcher,
    { refreshInterval: 30000 }
  );
  return { snapshots: data?.snapshots ?? [], error, isLoading };
}
