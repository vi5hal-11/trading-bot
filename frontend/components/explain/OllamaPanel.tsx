"use client";
import { useState } from "react";
import type { Signal } from "@/lib/types";
import { explainOllama } from "@/lib/explainer";

interface Props {
  signal: Signal;
  symbol: string;
  price: number;
}

export default function OllamaPanel({ signal, symbol, price }: Props) {
  const [narrative, setNarrative] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";

  async function handleExplain() {
    setLoading(true);
    setError(null);
    try {
      const result = await explainOllama(signal, symbol, price, apiUrl);
      if (result) {
        setNarrative(result);
      } else {
        setError("Ollama is not running locally. Install it from ollama.ai and run: ollama pull llama3.2");
      }
    } catch {
      setError("Failed to connect to AI service");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="glass-card p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-sm font-semibold text-white">AI Narrative</div>
          <div className="text-xs text-subtle mt-0.5">Powered by Ollama (llama3.2 — free, local)</div>
        </div>
        {!narrative && (
          <button
            onClick={handleExplain}
            disabled={loading}
            className="px-4 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-50"
            style={{ background: "rgba(99,102,241,0.2)", color: "#a5b4fc", border: "1px solid rgba(99,102,241,0.4)" }}
          >
            {loading ? "Thinking..." : "Explain with AI"}
          </button>
        )}
      </div>

      {error && (
        <div className="text-sm rounded-lg p-3" style={{ background: "rgba(239,68,68,0.1)", color: "#f87171", border: "1px solid rgba(239,68,68,0.2)" }}>
          {error}
        </div>
      )}

      {narrative && (
        <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{narrative}</div>
      )}

      {!narrative && !error && !loading && (
        <p className="text-subtle text-sm">
          Click the button above to generate an AI narrative explanation. Requires Ollama running locally on port 11434.
        </p>
      )}
    </div>
  );
}
