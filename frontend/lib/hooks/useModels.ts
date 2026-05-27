"use client";
import useSWR from "swr";
import type { ModelVersion } from "@/lib/types";

const fetcher = (url: string) => fetch(url).then((r) => r.json());
const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

export function useModels() {
  const { data, error, isLoading } = useSWR<{ models: ModelVersion[] }>(
    `${BASE}/api/models`,
    fetcher,
    { refreshInterval: 60000 }
  );
  return { models: data?.models ?? [], error, isLoading };
}
