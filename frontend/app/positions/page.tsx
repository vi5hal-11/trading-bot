"use client";
import AppShell from "@/components/layout/AppShell";
import PositionsTable from "@/components/positions/PositionsTable";

export default function PositionsPage() {
  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Open Positions</h1>
          <p className="text-subtle text-sm">Live positions with unrealized PnL — refreshes every 3s</p>
        </div>
        <PositionsTable />
      </div>
    </AppShell>
  );
}
