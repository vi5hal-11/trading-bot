"use client";
import AppShell from "@/components/layout/AppShell";
import StrategyPnLChart from "@/components/analytics/StrategyPnLChart";
import PnLHeatmap from "@/components/analytics/PnLHeatmap";

export default function AnalyticsPage() {
  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Strategy Analytics</h1>
          <p className="text-subtle text-sm">Performance breakdown by strategy and time-of-day patterns</p>
        </div>
        <StrategyPnLChart />
        <PnLHeatmap />
      </div>
    </AppShell>
  );
}
