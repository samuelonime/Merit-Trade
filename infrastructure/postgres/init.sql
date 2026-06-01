-- ═══════════════════════════════════════════════════
--   MERIT-TRADE AI — POSTGRESQL SCHEMA
--   Version: 1.0.0
-- ═══════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE;

-- ─── ENUMS ────────────────────────────────────────

CREATE TYPE subscription_plan AS ENUM ('free', 'pro', 'enterprise', 'expired_free');
CREATE TYPE signal_direction AS ENUM ('BUY', 'SELL', 'HOLD');
CREATE TYPE trade_status AS ENUM ('pending', 'open', 'closed', 'cancelled', 'rejected');
CREATE TYPE order_type AS ENUM ('market', 'limit', 'stop', 'stop_limit');
CREATE TYPE asset_class AS ENUM ('forex', 'crypto', 'indices', 'commodities');
CREATE TYPE notification_channel AS ENUM ('telegram', 'email', 'push');
CREATE TYPE log_level AS ENUM ('info', 'warning', 'error', 'critical');
CREATE TYPE execution_mode AS ENUM ('manual', 'semi_auto', 'full_auto');

-- ─── USERS ────────────────────────────────────────

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    username        VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255),
    is_active       BOOLEAN DEFAULT true,
    is_verified     BOOLEAN DEFAULT false,
    is_admin        BOOLEAN DEFAULT false,
    plan            subscription_plan DEFAULT 'free',
    execution_mode  execution_mode DEFAULT 'manual',
    timezone        VARCHAR(50) DEFAULT 'UTC',
    country         VARCHAR(100),
    phone           VARCHAR(20),
    ip_whitelist    TEXT[],
    failed_logins   INTEGER DEFAULT 0,
    locked_until    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    last_login      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,
    trial_ends_at   TIMESTAMPTZ GENERATED ALWAYS AS (created_at + INTERVAL '7 days') STORED
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_plan ON users(plan);

-- ─── SESSIONS ─────────────────────────────────────

CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token   VARCHAR(512) UNIQUE NOT NULL,
    ip_address      INET,
    user_agent      TEXT,
    is_revoked      BOOLEAN DEFAULT false,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_refresh_token ON sessions(refresh_token);

-- ─── SUBSCRIPTIONS ────────────────────────────────

CREATE TABLE subscriptions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan                subscription_plan NOT NULL,
    provider            VARCHAR(50) NOT NULL,    -- stripe | paystack
    provider_sub_id     VARCHAR(255),
    status              VARCHAR(50) DEFAULT 'active',
    current_period_start TIMESTAMPTZ,
    current_period_end  TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT false,
    amount              NUMERIC(12,2),
    currency            VARCHAR(10) DEFAULT 'USD',
    metadata            JSONB,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── FOREX ACCOUNTS ───────────────────────────────

CREATE TABLE accounts_forex (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    broker_name         VARCHAR(100) NOT NULL,
    account_number      BIGINT NOT NULL,
    -- Credentials encrypted with AES-256 at application level
    encrypted_password  BYTEA NOT NULL,
    server              VARCHAR(255) NOT NULL,
    is_demo             BOOLEAN DEFAULT true,
    is_active           BOOLEAN DEFAULT true,
    balance             NUMERIC(20,8) DEFAULT 0,
    equity              NUMERIC(20,8) DEFAULT 0,
    margin              NUMERIC(20,8) DEFAULT 0,
    free_margin         NUMERIC(20,8) DEFAULT 0,
    currency            VARCHAR(10) DEFAULT 'USD',
    leverage            INTEGER DEFAULT 100,
    last_sync           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_accounts_forex_user ON accounts_forex(user_id);

-- ─── CRYPTO ACCOUNTS ──────────────────────────────

CREATE TABLE accounts_crypto (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange            VARCHAR(100) NOT NULL,   -- binance, coinbase, etc.
    label               VARCHAR(255),
    -- Encrypted at application level
    encrypted_api_key   BYTEA NOT NULL,
    encrypted_api_secret BYTEA NOT NULL,
    encrypted_passphrase BYTEA,                  -- some exchanges require this
    is_testnet          BOOLEAN DEFAULT true,
    is_active           BOOLEAN DEFAULT true,
    supported_types     TEXT[] DEFAULT ARRAY['spot'],
    last_sync           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_accounts_crypto_user ON accounts_crypto(user_id);

-- ─── RISK SETTINGS ────────────────────────────────

CREATE TABLE risk_settings (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                 UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    max_risk_per_trade      NUMERIC(5,4) DEFAULT 0.02,   -- 2%
    max_daily_loss          NUMERIC(5,4) DEFAULT 0.05,   -- 5%
    max_drawdown            NUMERIC(5,4) DEFAULT 0.15,   -- 15%
    min_confidence          INTEGER DEFAULT 65,           -- 0-100
    max_open_trades         INTEGER DEFAULT 5,
    max_spread_pips         NUMERIC(8,2) DEFAULT 3.0,
    allowed_assets          TEXT[],
    allowed_sessions        TEXT[] DEFAULT ARRAY['london','new_york'],
    news_filter_enabled     BOOLEAN DEFAULT true,
    high_impact_news_block  BOOLEAN DEFAULT true,
    auto_trade_enabled      BOOLEAN DEFAULT false,
    execution_delay_seconds INTEGER DEFAULT 0,
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ─── MARKET DATA (TimescaleDB hypertable) ─────────

CREATE TABLE market_data (
    time            TIMESTAMPTZ NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    timeframe       VARCHAR(5) NOT NULL,    -- 1m,5m,15m,1h,4h,1d
    open            NUMERIC(20,8) NOT NULL,
    high            NUMERIC(20,8) NOT NULL,
    low             NUMERIC(20,8) NOT NULL,
    close           NUMERIC(20,8) NOT NULL,
    volume          NUMERIC(20,8) NOT NULL,
    spread          NUMERIC(10,5),
    source          VARCHAR(50),
    PRIMARY KEY (time, symbol, timeframe)
);

SELECT create_hypertable('market_data', 'time', if_not_exists => TRUE);
CREATE INDEX idx_market_data_symbol ON market_data(symbol, time DESC);

-- ─── FEATURES ─────────────────────────────────────

CREATE TABLE features (
    time            TIMESTAMPTZ NOT NULL,
    symbol          VARCHAR(20) NOT NULL,
    timeframe       VARCHAR(5) NOT NULL,
    -- Trend indicators
    ema_20          NUMERIC(20,8),
    ema_50          NUMERIC(20,8),
    ema_200         NUMERIC(20,8),
    sma_20          NUMERIC(20,8),
    sma_50          NUMERIC(20,8),
    -- Oscillators
    rsi_14          NUMERIC(8,4),
    macd_line       NUMERIC(20,8),
    macd_signal     NUMERIC(20,8),
    macd_hist       NUMERIC(20,8),
    -- Volatility
    atr_14          NUMERIC(20,8),
    bb_upper        NUMERIC(20,8),
    bb_middle       NUMERIC(20,8),
    bb_lower        NUMERIC(20,8),
    bb_width        NUMERIC(20,8),
    -- Volume
    vwap            NUMERIC(20,8),
    volume_sma_20   NUMERIC(20,8),
    -- Market structure
    structure       VARCHAR(20),    -- HH,HL,LH,LL
    trend_direction VARCHAR(10),    -- UP,DOWN,SIDEWAYS
    support_level   NUMERIC(20,8),
    resistance_level NUMERIC(20,8),
    -- Smart money
    fvg_bullish     BOOLEAN DEFAULT false,
    fvg_bearish     BOOLEAN DEFAULT false,
    liquidity_zone  BOOLEAN DEFAULT false,
    imbalance_zone  BOOLEAN DEFAULT false,
    PRIMARY KEY (time, symbol, timeframe)
);

SELECT create_hypertable('features', 'time', if_not_exists => TRUE);
CREATE INDEX idx_features_symbol ON features(symbol, time DESC);

-- ─── SIGNALS ──────────────────────────────────────

CREATE TABLE signals (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol              VARCHAR(20) NOT NULL,
    asset_class         asset_class NOT NULL,
    timeframe           VARCHAR(5) NOT NULL,
    direction           signal_direction NOT NULL,
    entry_price         NUMERIC(20,8) NOT NULL,
    stop_loss           NUMERIC(20,8) NOT NULL,
    take_profit_1       NUMERIC(20,8) NOT NULL,
    take_profit_2       NUMERIC(20,8),
    take_profit_3       NUMERIC(20,8),
    confidence_score    INTEGER NOT NULL,   -- 0-100
    risk_score          INTEGER NOT NULL,   -- 0-100
    -- Model breakdown
    xgboost_score       NUMERIC(5,4),
    xgboost_direction   signal_direction,
    lstm_score          NUMERIC(5,4),
    lstm_direction      signal_direction,
    transformer_score   NUMERIC(5,4),
    transformer_direction signal_direction,
    ensemble_score      NUMERIC(5,4),
    -- AI explanation from Anthropic API
    ai_explanation      TEXT,
    ai_sentiment        VARCHAR(20),        -- bullish|bearish|neutral
    sentiment_score     NUMERIC(5,4),
    -- Risk params
    risk_reward_ratio   NUMERIC(8,4),
    atr_value           NUMERIC(20,8),
    pip_value           NUMERIC(20,8),
    -- Status
    is_active           BOOLEAN DEFAULT true,
    expired_at          TIMESTAMPTZ,
    generated_at        TIMESTAMPTZ DEFAULT NOW(),
    metadata            JSONB
);

CREATE INDEX idx_signals_symbol ON signals(symbol, generated_at DESC);
CREATE INDEX idx_signals_active ON signals(is_active, generated_at DESC);

-- ─── TRADES ───────────────────────────────────────

CREATE TABLE trades (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID NOT NULL REFERENCES users(id),
    signal_id           UUID REFERENCES signals(id),
    account_id          UUID NOT NULL,              -- forex or crypto account id
    account_type        VARCHAR(10) NOT NULL,       -- forex | crypto
    symbol              VARCHAR(20) NOT NULL,
    direction           signal_direction NOT NULL,
    order_type          order_type DEFAULT 'market',
    status              trade_status DEFAULT 'pending',
    -- Sizing
    lot_size            NUMERIC(10,4),
    quantity            NUMERIC(20,8),
    -- Prices
    entry_price         NUMERIC(20,8),
    current_price       NUMERIC(20,8),
    close_price         NUMERIC(20,8),
    stop_loss           NUMERIC(20,8),
    take_profit         NUMERIC(20,8),
    -- P&L
    unrealized_pnl      NUMERIC(20,8) DEFAULT 0,
    realized_pnl        NUMERIC(20,8),
    commission          NUMERIC(20,8) DEFAULT 0,
    swap                NUMERIC(20,8) DEFAULT 0,
    -- Risk info
    risk_amount         NUMERIC(20,8),
    risk_pct            NUMERIC(5,4),
    -- Broker data
    broker_order_id     VARCHAR(255),
    broker_ticket       BIGINT,
    -- Timing
    opened_at           TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    metadata            JSONB
);

CREATE INDEX idx_trades_user ON trades(user_id, created_at DESC);
CREATE INDEX idx_trades_status ON trades(status);
CREATE INDEX idx_trades_symbol ON trades(symbol);

-- ─── EXECUTIONS (audit trail) ─────────────────────

CREATE TABLE executions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trade_id            UUID NOT NULL REFERENCES trades(id),
    user_id             UUID NOT NULL REFERENCES users(id),
    action              VARCHAR(50) NOT NULL,       -- open|close|modify|cancel
    -- Risk gate results
    risk_approved       BOOLEAN NOT NULL,
    risk_rejection_reasons TEXT[],
    -- Execution details
    requested_price     NUMERIC(20,8),
    executed_price      NUMERIC(20,8),
    slippage_pips       NUMERIC(8,4),
    latency_ms          INTEGER,
    -- Response from broker/exchange
    broker_response     JSONB,
    error_message       TEXT,
    retry_count         INTEGER DEFAULT 0,
    executed_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_executions_trade ON executions(trade_id);
CREATE INDEX idx_executions_user ON executions(user_id, executed_at DESC);

-- ─── AI OUTPUTS ───────────────────────────────────

CREATE TABLE ai_outputs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id       UUID REFERENCES signals(id),
    type            VARCHAR(50) NOT NULL,       -- sentiment|explanation|commentary|insight
    symbol          VARCHAR(20),
    model           VARCHAR(100),
    prompt_tokens   INTEGER,
    output_tokens   INTEGER,
    input_text      TEXT,
    output_text     TEXT NOT NULL,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ai_outputs_signal ON ai_outputs(signal_id);
CREATE INDEX idx_ai_outputs_type ON ai_outputs(type, created_at DESC);

-- ─── NOTIFICATIONS ────────────────────────────────

CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel         notification_channel NOT NULL,
    type            VARCHAR(50) NOT NULL,
    title           VARCHAR(255),
    body            TEXT NOT NULL,
    is_read         BOOLEAN DEFAULT false,
    is_sent         BOOLEAN DEFAULT false,
    sent_at         TIMESTAMPTZ,
    error           TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id, created_at DESC);
CREATE INDEX idx_notifications_unread ON notifications(user_id, is_read) WHERE NOT is_read;

-- ─── NOTIFICATION PREFERENCES ─────────────────────

CREATE TABLE notification_preferences (
    user_id             UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    telegram_chat_id    VARCHAR(100),
    telegram_enabled    BOOLEAN DEFAULT false,
    email_enabled       BOOLEAN DEFAULT true,
    push_enabled        BOOLEAN DEFAULT false,
    push_subscription   JSONB,
    signal_alerts       BOOLEAN DEFAULT true,
    trade_alerts        BOOLEAN DEFAULT true,
    risk_alerts         BOOLEAN DEFAULT true,
    news_alerts         BOOLEAN DEFAULT false,
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── LOGS ─────────────────────────────────────────

CREATE TABLE logs (
    id          BIGSERIAL,
    time        TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    level       log_level NOT NULL,
    service     VARCHAR(50) NOT NULL,
    user_id     UUID REFERENCES users(id),
    action      VARCHAR(100),
    message     TEXT NOT NULL,
    context     JSONB,
    ip_address  INET,
    trace_id    UUID
);

SELECT create_hypertable('logs', 'time', if_not_exists => TRUE);
CREATE INDEX idx_logs_level ON logs(level, time DESC);
CREATE INDEX idx_logs_user ON logs(user_id, time DESC);
CREATE INDEX idx_logs_service ON logs(service, time DESC);

-- ─── SYSTEM HEALTH METRICS ────────────────────────

CREATE TABLE system_metrics (
    time        TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    service     VARCHAR(50) NOT NULL,
    metric      VARCHAR(100) NOT NULL,
    value       NUMERIC NOT NULL,
    labels      JSONB
);

SELECT create_hypertable('system_metrics', 'time', if_not_exists => TRUE);

-- ─── TRIGGERS: updated_at auto-update ─────────────

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_trades_updated_at
    BEFORE UPDATE ON trades FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON subscriptions FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── DEFAULT ADMIN USER (change password immediately) ─

INSERT INTO users (email, username, password_hash, full_name, is_active, is_verified, is_admin, plan)
VALUES (
    'admin@merittrade.ai',
    'admin',
    crypt('CHANGE_ME_ON_FIRST_LOGIN', gen_salt('bf', 12)),
    'System Admin',
    true, true, true, 'enterprise'
);
