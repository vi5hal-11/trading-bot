"use client";
import useSWR from "swr";
import type { BotStatus } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function useStatus() {
  const { data, error, isLoading, mutate } = useSWR<BotStatus>(`${BASE}/api/status`, fetcher, {
    refreshInterval: 3000,
  });
  return { status: data, error, isLoading, mutate };
}
