"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  TrendingUp,
  Wifi,
  BarChart2,
  History,
  Lightbulb,
  PieChart,
  Cpu,
  FlaskConical,
} from "lucide-react";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/positions", label: "Positions", icon: TrendingUp },
  { href: "/signals", label: "Signals", icon: Wifi },
  { href: "/charts", label: "Charts", icon: BarChart2 },
  { href: "/trades", label: "Trades", icon: History },
  { href: "/trades/explain", label: "Explainer", icon: Lightbulb },
  { href: "/analytics", label: "Analytics", icon: PieChart },
  { href: "/ml", label: "ML & Controls", icon: Cpu },
  { href: "/backtest", label: "Backtester", icon: FlaskConical },
];

export default function Sidebar() {
  const path = usePathname();

  return (
    <aside
      className="hidden md:flex flex-col w-56 min-h-screen border-r py-6 px-3"
      style={{ background: "rgba(13,15,26,0.95)", borderColor: "rgba(99,102,241,0.15)" }}
    >
      <div className="px-3 mb-8">
        <div className="text-lg font-bold text-white">Trading Bot</div>
        <div className="text-xs text-subtle mt-0.5">Dashboard v9</div>
      </div>
      <nav className="flex flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = path === href || (href !== "/dashboard" && path.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all ${
                active
                  ? "text-white font-semibold"
                  : "text-subtle hover:text-gray-300 hover:bg-white/5"
              }`}
              style={active ? { background: "rgba(99,102,241,0.15)", color: "#a5b4fc" } : {}}
            >
              <Icon size={16} />
              {label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
