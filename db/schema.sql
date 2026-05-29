CREATE TABLE IF NOT EXISTS trades (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20)  NOT NULL,
    side        VARCHAR(4)   NOT NULL,  -- BUY | SELL
    entry_price NUMERIC(18,8) NOT NULL,
    exit_price  NUMERIC(18,8),
    quantity    NUMERIC(18,8) NOT NULL,
    pnl         NUMERIC(18,8),
    pnl_pct     NUMERIC(8,4),
    strategy    VARCHAR(50),
    signal_confidence NUMERIC(5,4),
    paper       BOOLEAN DEFAULT TRUE,
    opened_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS signals (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20)  NOT NULL,
    action      VARCHAR(4)   NOT NULL,  -- BUY | SELL | HOLD
    confidence  NUMERIC(5,4) NOT NULL,
    consensus   NUMERIC(6,4),
    strategy    VARCHAR(50),
    timeframe   VARCHAR(5),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id          SERIAL PRIMARY KEY,
    balance     NUMERIC(18,8) NOT NULL,
    equity      NUMERIC(18,8) NOT NULL,
    open_positions INT DEFAULT 0,
    daily_pnl   NUMERIC(18,8) DEFAULT 0,
    total_pnl   NUMERIC(18,8) DEFAULT 0,
    snapped_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS model_versions (
    id            SERIAL PRIMARY KEY,
    version       VARCHAR(50)  NOT NULL,
    trained_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    cv_accuracy   FLOAT,
    sharpe        FLOAT,
    win_rate      FLOAT,
    max_drawdown  FLOAT,
    n_samples     INT,
    is_champion   BOOLEAN      NOT NULL DEFAULT FALSE,
    model_path    VARCHAR(255),
    scaler_path   VARCHAR(255),
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS ifvg_signals (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(20)  NOT NULL,
    direction       VARCHAR(4)   NOT NULL,  -- BULL | BEAR
    zone_high       NUMERIC(18,8),
    zone_low        NUMERIC(18,8),
    ce              NUMERIC(18,8),
    confluence      INT,
    bias_confirmed  BOOLEAN,
    structure_ok    BOOLEAN,
    strong_sweep    BOOLEAN,
    strong_disp     BOOLEAN,
    ob_aligned      BOOLEAN,
    smt_divergence  BOOLEAN,
    killzone        VARCHAR(20),
    entry_mode      VARCHAR(10),  -- LIMIT | CONFIRM
    entry_price     NUMERIC(18,8),
    sl_price        NUMERIC(18,8),
    tp1_price       NUMERIC(18,8),
    tp2_price       NUMERIC(18,8),
    dol_level       NUMERIC(18,8),
    outcome         VARCHAR(10),  -- SL | DOL | TRAIL | null
    pnl_r           NUMERIC(8,4),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS trade_postmortem (
    id               SERIAL PRIMARY KEY,
    trade_id         INT REFERENCES trades(id) ON DELETE SET NULL,
    symbol           VARCHAR(20)  NOT NULL,
    side             VARCHAR(4)   NOT NULL,
    pnl              NUMERIC(18,8),
    pnl_pct          NUMERIC(8,4),
    loss_reason      VARCHAR(30)  NOT NULL,  -- win | wrong_regime | stop_too_tight | strategy_conflict | low_liquidity | news_shock | time_stop | normal_loss
    details          TEXT,
    adx              NUMERIC(6,2),
    atr              NUMERIC(18,8),
    vol_ratio        NUMERIC(6,3),
    strategy         VARCHAR(50),
    confidence       NUMERIC(5,4),
    consensus_score  NUMERIC(6,4),
    component_signals JSONB,
    entry_hour_utc   SMALLINT,
    closed_at        TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              SERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol          VARCHAR(20),          -- NULL = all symbols
    months          INT,
    walk_forward    BOOLEAN DEFAULT FALSE,
    threshold       NUMERIC(4,2),
    initial_balance NUMERIC(18,2),
    total_trades    INT,
    win_rate        NUMERIC(5,4),
    sharpe          FLOAT,
    sortino         FLOAT,
    max_drawdown    NUMERIC(6,4),
    total_return    NUMERIC(8,4),
    profit_factor   FLOAT,
    expectancy      FLOAT,
    summary_path    TEXT
);

CREATE INDEX idx_trades_symbol    ON trades(symbol);
CREATE INDEX idx_trades_opened_at ON trades(opened_at);
CREATE INDEX idx_signals_created  ON signals(created_at);
CREATE INDEX idx_model_champion   ON model_versions(is_champion, trained_at DESC);
CREATE INDEX idx_ifvg_symbol      ON ifvg_signals(symbol, created_at DESC);
CREATE INDEX idx_postmortem_reason ON trade_postmortem(loss_reason, created_at DESC);
