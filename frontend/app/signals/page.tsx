"use client";
import AppShell from "@/components/layout/AppShell";
import SignalFeed from "@/components/signals/SignalFeed";
import ActivityLog from "@/components/signals/ActivityLog";
import StrategyToggles from "@/components/signals/StrategyToggles";
import BotLogStream from "@/components/monitor/BotLogStream";

export default function SignalsPage() {
  return (
    <AppShell>
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-xl font-bold text-white mb-1">Signal Feed</h1>
          <p className="text-subtle text-sm">Live ensemble signals + strategy controls</p>
        </div>
        <StrategyToggles />
        <SignalFeed />
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <ActivityLog />
          <BotLogStream maxHeight="380px" />
        </div>
      </div>
    </AppShell>
  );
}
