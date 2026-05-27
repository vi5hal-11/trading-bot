"use client";
import { useEffect, useRef } from "react";
import { SYMBOL_MAP } from "@/lib/binance";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window { TradingView: any; }
}

const CONTAINER_ID = "tv_advanced_chart";

interface Props {
  symbol: string; // e.g. "BTC/USDT:USDT"
}

export default function TradingViewChart({ symbol }: Props) {
  const widgetRef = useRef<any>(null);
  // Always holds the latest symbol so the async script-load callback uses it
  const symbolRef = useRef(symbol);
  symbolRef.current = symbol;

  function buildWidget() {
    const container = document.getElementById(CONTAINER_ID);
    if (!container || typeof window.TradingView === "undefined") return;

    // Tear down previous widget before creating a new one
    try { widgetRef.current?.remove(); } catch { /* ignore */ }
    container.innerHTML = "";
    widgetRef.current = null;

    widgetRef.current = new window.TradingView.widget({
      autosize: true,
      symbol: `BINANCE:${SYMBOL_MAP[symbolRef.current] ?? "BTCUSDT"}`,
      interval: "15",
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "en",
      toolbar_bg: "#0d0f1a",
      enable_publishing: false,
      allow_symbol_change: true,
      hide_side_toolbar: false,
      withdateranges: true,
      save_image: true,
      container_id: CONTAINER_ID,
      studies: ["Volume@tv-basicstudies", "RSI@tv-basicstudies", "MACD@tv-basicstudies"],
      overrides: {
        "paneProperties.background": "#0d0f1a",
        "paneProperties.backgroundGradientStartColor": "#0d0f1a",
        "paneProperties.backgroundGradientEndColor": "#0d0f1a",
        "paneProperties.vertGridProperties.color": "rgba(99,102,241,0.08)",
        "paneProperties.horzGridProperties.color": "rgba(99,102,241,0.08)",
        "scalesProperties.textColor": "#9ca3af",
        "scalesProperties.lineColor": "rgba(99,102,241,0.2)",
        "candleStyle.upColor": "#06b6d4",
        "candleStyle.downColor": "#ef4444",
        "candleStyle.borderUpColor": "#06b6d4",
        "candleStyle.borderDownColor": "#ef4444",
        "candleStyle.wickUpColor": "#06b6d4",
        "candleStyle.wickDownColor": "#ef4444",
      },
    });
  }

  // Load script once and create initial widget
  useEffect(() => {
    if (typeof window.TradingView !== "undefined") {
      buildWidget();
    } else {
      // Avoid duplicate script tags (strict mode / HMR)
      const existing = document.querySelector<HTMLScriptElement>(
        'script[src="https://s3.tradingview.com/tv.js"]'
      );
      if (existing) {
        existing.addEventListener("load", buildWidget, { once: true });
      } else {
        const script = document.createElement("script");
        script.src = "https://s3.tradingview.com/tv.js";
        script.async = true;
        script.onload = buildWidget;
        document.head.appendChild(script);
      }
    }

    return () => {
      try { widgetRef.current?.remove(); } catch { /* ignore */ }
      widgetRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Recreate widget on symbol tab change (skip on initial mount — [] handles it)
  useEffect(() => {
    if (!widgetRef.current) return;
    buildWidget();
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ height: "640px" }}>
      <div id={CONTAINER_ID} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
