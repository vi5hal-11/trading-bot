export interface BotStatus {
  mode: "PAPER" | "LIVE";
  paused: boolean;
  running: boolean;
  loop_count: number;
  circuit_breaker_active: boolean;
  uptime_seconds: number;
  strategy_enabled: Record<string, boolean>;
  symbols: string[];
  risk_overrides: Record<string, number>;
}

export interface PortfolioSummary {
  balance: number;
  equity: number;
  open_positions: number;
  total_trades: number;
  win_rate: number;
  total_pnl: number;
  daily_pnl_pct: number;
  drawdown_from_peak: number;
}

export interface Position {
  symbol: string;
  side: "BUY" | "SELL";
  entry_price: number;
  current_price: number;
  quantity: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number;
  stop_loss: number;
  take_profit: number;
  strategy: string;
  confidence: number;
  age_minutes: number;
  tp1_done: boolean;
  tp2_done: boolean;
}

export interface ComponentSignals {
  [strategy: string]: "BUY" | "SELL" | "HOLD";
}

export interface ComponentConfidences {
  [strategy: string]: number;
}

export interface Signal {
  action: "BUY" | "SELL" | "HOLD";
  confidence: number;
  consensus_score: number;
  price: number;
  strategy: string;
  symbol?: string;
  timeframe?: string;
  component_signals?: ComponentSignals;
  component_confidences?: ComponentConfidences;
}

export interface Trade {
  id?: number;
  symbol: string;
  side: "BUY" | "SELL";
  entry_price: number;
  exit_price?: number;
  quantity?: number;
  pnl: number;
  pnl_pct: number;
  strategy: string;
  signal_confidence?: number;
  confidence?: number;
  paper?: boolean;
  reason?: string;
  opened_at?: string;
  closed_at?: string;
}

export interface PortfolioSnapshot {
  balance: number;
  equity: number;
  open_positions: number;
  daily_pnl: number;
  total_pnl: number;
  snapped_at: string;
}

export interface ModelVersion {
  id: number;
  version: string;
  trained_at: string;
  cv_accuracy: number;
  sharpe: number;
  win_rate: number;
  max_drawdown: number;
  n_samples: number;
  is_champion: boolean;
  notes?: string;
}

export interface ActivityEntry {
  type: "open" | "close" | "signal" | string;
  message: string;
  symbol: string;
  ts: string;
}

export interface RiskConfig {
  max_loss_pct_per_trade: number;
  max_open_positions: number;
  daily_loss_circuit_breaker: number;
  trailing_stop_atr_multiplier: number;
  max_portfolio_drawdown: number;
  max_total_exposure_pct: number;
}

export interface RiskHotParams {
  atr_multiplier?: number;
  max_loss_pct?: number;
  tp1_pct?: number;
  tp2_pct?: number;
  tp1_size?: number;
  tp2_size?: number;
}

export interface BotConfig {
  risk: RiskConfig;
  ensemble: { threshold: number };
}

export interface LogEntry {
  level: "INFO" | "WARNING" | "ERROR" | "DEBUG" | string;
  message: string;
  ts: string;
}

export interface IndicatorSnapshot {
  rsi: number | null;
  macd: number | null;
  macd_signal: number | null;
  macd_hist: number | null;
  bb_pct: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  adx: number | null;
  atr: number | null;
  sma_fast: number | null;
  sma_slow: number | null;
  ema_12: number | null;
  ema_26: number | null;
  vol_ratio: number | null;
}
