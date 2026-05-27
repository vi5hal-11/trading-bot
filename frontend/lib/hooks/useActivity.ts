"use client";
import useSWR from "swr";
import type { ActivityEntry } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function useActivity() {
  const { data, error, isLoading } = useSWR<{ log: ActivityEntry[] }>(
    `${BASE}/api/activity`,
    fetcher,
    { refreshInterval: 3000 }
  );
  return { log: data?.log ?? [], error, isLoading };
}
