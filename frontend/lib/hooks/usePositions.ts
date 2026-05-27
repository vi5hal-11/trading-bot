"use client";
import useSWR from "swr";
import type { Position } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function usePositions() {
  const { data, error, isLoading, mutate } = useSWR<{ positions: Position[] }>(
    `${BASE}/api/positions`,
    fetcher,
    { refreshInterval: 3000 }
  );
  return { positions: data?.positions ?? [], error, isLoading, mutate };
}
