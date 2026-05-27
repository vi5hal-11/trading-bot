"use client";
import { LiveProvider } from "@/lib/live-context";
import { Toaster } from "sonner";
import type { ReactNode } from "react";

export default function ClientProviders({ children }: { children: ReactNode }) {
  return (
    <LiveProvider>
      {children}
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: "rgba(13,20,40,0.95)",
            border: "1px solid rgba(99,102,241,0.3)",
            color: "#e2e8f0",
          },
        }}
      />
    </LiveProvider>
  );
}
