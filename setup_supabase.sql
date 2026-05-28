-- ============================================================
-- FRIDAY-MONDAY STRATEGY — SUPABASE SCHEMA
-- Project: serve-and-smash (pqhipbnjkbhlguvrjcah)
-- Prefix : fm_ (to not conflict with Whispr app tables)
-- ============================================================

-- 1. BACKTEST TRADES — one row per simulated trade (historical)
CREATE TABLE IF NOT EXISTS fm_backtest_trades (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    stock_name          TEXT,
    sector              TEXT,
    tier                TEXT,          -- 'large' | 'mid'
    friday_date         DATE NOT NULL,
    monday_date         DATE NOT NULL,
    ref_day_type        TEXT,          -- 'thursday' | 'wednesday'
    ref_day_high        NUMERIC,
    fri_high            NUMERIC,
    fri_low             NUMERIC,
    fri_close           NUMERIC,
    fri_volume_ratio    NUMERIC,
    fri_rsi             NUMERIC,
    fri_above_sma20     BOOLEAN,
    mon_open            NUMERIC,
    mon_high            NUMERIC,
    mon_low             NUMERIC,
    mon_close           NUMERIC,
    gap_pct             NUMERIC,       -- negative = gap down
    entry_price         NUMERIC,
    stop_price          NUMERIC,       -- Friday High
    target_price        NUMERIC,       -- Friday Low
    exit_price          NUMERIC,
    exit_type           TEXT,          -- 'target' | 'stop' | 'eod'
    gross_pnl_pct       NUMERIC,       -- SHORT P&L % (positive = profit)
    net_pnl_pct         NUMERIC,       -- gross − 0.05% round-trip
    is_win              BOOLEAN,
    regime              TEXT,          -- 'bull' | 'bear' | 'sideways'
    year                INTEGER,
    month               INTEGER,
    quarter             TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fm_bt_symbol  ON fm_backtest_trades(symbol);
CREATE INDEX IF NOT EXISTS idx_fm_bt_friday  ON fm_backtest_trades(friday_date);
CREATE INDEX IF NOT EXISTS idx_fm_bt_sector  ON fm_backtest_trades(sector);
CREATE INDEX IF NOT EXISTS idx_fm_bt_year    ON fm_backtest_trades(year);
CREATE INDEX IF NOT EXISTS idx_fm_bt_regime  ON fm_backtest_trades(regime);
CREATE INDEX IF NOT EXISTS idx_fm_bt_exit    ON fm_backtest_trades(exit_type);


-- 2. STOCK SUMMARY — aggregated stats per stock (rebuilt on each backtest run)
CREATE TABLE IF NOT EXISTS fm_stock_summary (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT UNIQUE NOT NULL,
    stock_name          TEXT,
    sector              TEXT,
    tier                TEXT,
    total_trades        INTEGER,
    wins                INTEGER,
    losses              INTEGER,
    targets_hit         INTEGER,
    stops_hit           INTEGER,
    eod_exits           INTEGER,
    win_rate_pct        NUMERIC,
    avg_gross_pnl       NUMERIC,
    avg_net_pnl         NUMERIC,
    total_gross_pnl     NUMERIC,
    total_net_pnl       NUMERIC,
    avg_win_pct         NUMERIC,
    avg_loss_pct        NUMERIC,
    profit_factor       NUMERIC,
    max_drawdown_pct    NUMERIC,
    avg_gap_pct         NUMERIC,
    avg_fri_rsi         NUMERIC,
    regime_stats        JSONB,         -- JSON breakdown by regime
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fm_ss_sector  ON fm_stock_summary(sector);
CREATE INDEX IF NOT EXISTS idx_fm_ss_wr      ON fm_stock_summary(win_rate_pct);


-- 3. WEEKLY WATCHLIST — generated every Friday EOD by automation
CREATE TABLE IF NOT EXISTS fm_weekly_watchlist (
    id                  BIGSERIAL PRIMARY KEY,
    week_date           DATE NOT NULL,     -- the Friday date
    symbol              TEXT NOT NULL,
    stock_name          TEXT,
    sector              TEXT,
    tier                TEXT,
    ref_day_type        TEXT,
    ref_day_high        NUMERIC,
    fri_high            NUMERIC,
    fri_low             NUMERIC,
    fri_close           NUMERIC,
    fri_rsi             NUMERIC,
    fri_volume_ratio    NUMERIC,
    fri_above_sma20     BOOLEAN,
    historical_wr_pct   NUMERIC,          -- from fm_stock_summary
    historical_trades   INTEGER,
    historical_avg_gross NUMERIC,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fm_wl_week    ON fm_weekly_watchlist(week_date);
CREATE INDEX IF NOT EXISTS idx_fm_wl_symbol  ON fm_weekly_watchlist(symbol);


-- 4. LIVE TRADES — each Monday's actual trade signals and outcomes
CREATE TABLE IF NOT EXISTS fm_live_trades (
    id                  BIGSERIAL PRIMARY KEY,
    trade_date          DATE NOT NULL,     -- Monday date
    friday_date         DATE,
    symbol              TEXT NOT NULL,
    stock_name          TEXT,
    sector              TEXT,
    gap_pct             NUMERIC,
    entry_price         NUMERIC,
    stop_price          NUMERIC,
    target_price        NUMERIC,
    position_size       NUMERIC,           -- capital allocated
    shares              INTEGER,
    capital_at_risk_pct NUMERIC,
    historical_wr_pct   NUMERIC,
    -- filled in after EOD
    exit_price          NUMERIC,
    exit_type           TEXT,
    gross_pnl_pct       NUMERIC,
    net_pnl_pct         NUMERIC,
    gross_pnl_inr       NUMERIC,           -- actual ₹ P&L
    net_pnl_inr         NUMERIC,
    is_win              BOOLEAN,
    email_sent_at       TIMESTAMPTZ,
    outcome_logged_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fm_lt_date    ON fm_live_trades(trade_date);
CREATE INDEX IF NOT EXISTS idx_fm_lt_symbol  ON fm_live_trades(symbol);


-- 5. PERFORMANCE LOG — daily/weekly equity curve for live trading
CREATE TABLE IF NOT EXISTS fm_performance_log (
    id                  BIGSERIAL PRIMARY KEY,
    log_date            DATE UNIQUE NOT NULL,
    total_signals       INTEGER,
    trades_taken        INTEGER,
    wins                INTEGER,
    losses              INTEGER,
    gross_pnl_inr       NUMERIC,
    net_pnl_inr         NUMERIC,
    running_gross_inr   NUMERIC,
    running_net_inr     NUMERIC,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);


-- Row-level security: disable for service-role access from backend
ALTER TABLE fm_backtest_trades  DISABLE ROW LEVEL SECURITY;
ALTER TABLE fm_stock_summary    DISABLE ROW LEVEL SECURITY;
ALTER TABLE fm_weekly_watchlist DISABLE ROW LEVEL SECURITY;
ALTER TABLE fm_live_trades      DISABLE ROW LEVEL SECURITY;
ALTER TABLE fm_performance_log  DISABLE ROW LEVEL SECURITY;
