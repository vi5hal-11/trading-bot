import type { Signal } from "./types";

const STRATEGY_LABELS: Record<string, string> = {
  momentum: "Momentum",
  mean_reversion: "Mean Reversion",
  trend_following: "Trend Following",
  sentiment: "Sentiment",
  ml_xgboost: "ML XGBoost",
};

function label(key: string): string {
  return STRATEGY_LABELS[key] || key;
}

export function explainRule(signal: Signal, symbol?: string): string {
  const { action, consensus_score, confidence, component_signals, component_confidences } = signal;
  const cs = component_signals || {};
  const cc = component_confidences || {};

  if (!Object.keys(cs).length) {
    return `${action} signal${symbol ? ` on ${symbol}` : ""} — consensus ${
      consensus_score >= 0 ? "+" : ""
    }${consensus_score?.toFixed(3)} | confidence ${((confidence || 0) * 100).toFixed(1)}%.`;
  }

  const votes: { name: string; action: string; conf: number }[] = Object.entries(cs).map(
    ([k, a]) => ({ name: label(k), action: a, conf: cc[k] || 0 })
  );

  const agree = votes.filter((v) => v.action === action);
  const dissent = votes.filter((v) => v.action !== action && v.action !== "HOLD");
  const neutral = votes.filter((v) => v.action === "HOLD");

  const parts: string[] = [];

  if (agree.length) {
    const agreeStr = agree.map((v) => `${v.name} (${(v.conf * 100).toFixed(0)}%)`).join(", ");
    parts.push(`${agreeStr} voted ${action}.`);
  }
  if (dissent.length) {
    const dissentStr = dissent
      .map((v) => `${v.name} dissented (${v.action}, ${(v.conf * 100).toFixed(0)}%)`)
      .join(", ");
    parts.push(`${dissentStr}.`);
  }
  if (neutral.length) {
    const neutralStr = neutral.map((v) => v.name).join(", ");
    parts.push(`${neutralStr} held neutral.`);
  }

  const consensusStr = `${consensus_score >= 0 ? "+" : ""}${consensus_score?.toFixed(3)}`;
  parts.push(`Ensemble consensus ${consensusStr} | confidence ${((confidence || 0) * 100).toFixed(1)}%.`);

  return parts.join(" ");
}

export async function explainOllama(
  signal: Signal,
  symbol: string,
  price: number,
  apiUrl: string
): Promise<string | null> {
  try {
    const res = await fetch(`${apiUrl}/api/explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ signal, symbol, price }),
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (!data.ollama_available) return null;

    const prompt =
      `You are a concise crypto trading analyst. In 2-3 sentences, explain why the bot triggered ` +
      `a ${signal.action} signal on ${symbol} at price $${price.toFixed(4)}. ` +
      `Context: ${data.rule_based}`;

    const ollama = await fetch("http://localhost:11434/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: "llama3.2", prompt, stream: false }),
    });
    if (!ollama.ok) return null;
    const ollamaData = await ollama.json();
    return ollamaData.response || null;
  } catch {
    return null;
  }
}
