"use client";
import useSWR from "swr";
import type { Signal } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function useSignals() {
  const { data, error, isLoading } = useSWR<{ signals: Record<string, Signal> }>(
    `${BASE}/api/signals`,
    fetcher,
    { refreshInterval: 3000 }
  );
  return { signals: data?.signals ?? {}, error, isLoading };
}
