import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0d0f1a",
        foreground: "#e2e8f0",
        primary: {
          DEFAULT: "#6366f1",
          foreground: "#ffffff",
        },
        gain: "#06b6d4",
        loss: "#ef4444",
        warn: "#f59e0b",
        card: "rgba(255,255,255,0.04)",
        border: "rgba(99,102,241,0.2)",
        muted: "#374151",
        subtle: "#6b7280",
      },
      backdropBlur: {
        glass: "16px",
      },
      fontFamily: {
        mono: ["GeistMono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderColor: {
        glass: "rgba(99,102,241,0.2)",
        "glass-bright": "rgba(99,102,241,0.4)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
      },
    },
  },
  plugins: [],
};
export default config;
