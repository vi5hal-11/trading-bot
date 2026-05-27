"use client";
import AppShell from "@/components/layout/AppShell";
import TradesTable from "@/components/trades/TradesTable";

export default function TradesPage() {
  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Trade History</h1>
          <p className="text-subtle text-sm">All closed trades — click Explain on any row for a full breakdown</p>
        </div>
        <TradesTable />
      </div>
    </AppShell>
  );
}
