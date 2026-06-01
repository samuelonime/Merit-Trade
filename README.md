# Merit-Trade AI
### Production-Ready Multi-Asset AI Trading Platform

[![CI/CD](https://github.com/your-org/merit-trade-ai/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/your-org/merit-trade-ai/actions)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         NGINX Reverse Proxy                       │
│                    (SSL termination, rate limiting)               │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                    ┌───────▼────────┐
                    │  API Gateway   │  :8000
                    │  (FastAPI)     │  Auth · Rate Limit · WS Hub
                    └──┬──┬──┬──┬───┘
                       │  │  │  │
        ┌──────────────┘  │  │  └─────────────────┐
        │                 │  │                      │
   ┌────▼──────┐    ┌─────▼──▼────┐         ┌──────▼─────┐
   │   Auth    │    │   Signal    │         │ Execution  │
   │  Service  │    │   Engine    │         │  Engine    │
   │   :8001   │    │   :8003     │         │   :8005    │
   └──────┬────┘    │  XGBoost    │         │  MT5+CCXT  │
          │         │  LSTM       │         └──────┬─────┘
   ┌──────▼────┐    │  Transformer│                │
   │   User    │    └──────┬──────┘         ┌──────▼─────┐
   │  Service  │           │                │   Risk     │
   │   :8002   │    ┌──────▼──────┐         │  Engine    │
   └───────────┘    │  Market     │         │   :8006    │
                    │  Data       │         │  HARD GATE │
                    │   :8004     │         └────────────┘
                    └─────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼────┐ ┌─────▼─────┐ ┌───▼──────┐
       │PostgreSQL │ │  Redis    │ │RabbitMQ  │
       │(TimescaleDB│ │Cache+PubSub│ │+ Celery  │
       └───────────┘ └───────────┘ └──────────┘
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose v2
- 8GB+ RAM recommended for ML models
- PostgreSQL with TimescaleDB extension

### 1. Clone and configure

```bash
git clone https://github.com/your-org/merit-trade-ai
cd merit-trade-ai
cp .env.example .env
# Edit .env and fill in ALL required values
```

### 2. Start infrastructure

```bash
docker compose up -d postgres redis rabbitmq
# Wait for health checks to pass
docker compose ps
```

### 3. Start all services

```bash
docker compose up -d
```

### 4. Access
- **Frontend:** http://localhost:3000
- **API Docs:** http://localhost:8000/api/docs
- **RabbitMQ UI:** http://localhost:15672
- **Admin:** POST /api/auth/login with admin credentials

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| api-gateway | 8000 | Central ingress, auth validation, WS hub |
| auth-service | 8001 | JWT auth, registration, sessions |
| user-service | 8002 | User profiles, broker accounts |
| signal-engine | 8003 | ML pipeline + signal generation |
| market-data | 8004 | OHLCV ingestion + feature engineering |
| execution-engine | 8005 | MT5 + CCXT trade execution |
| risk-engine | 8006 | Hard-rule risk gate (MANDATORY) |
| notification-service | 8007 | Telegram + Email + Web Push |
| admin-service | 8008 | Admin panel backend |

---

## Trading Pipeline

```
Market Data (OHLCV)
       ↓
Feature Engineering
  RSI · MACD · EMA · ATR · Bollinger · VWAP
  Market Structure · FVG · Support/Resistance
       ↓
ML Ensemble
  XGBoost (40%) → BUY/SELL/HOLD probability
  LSTM (30%)    → Sequential direction
  Transformer(30%)→ Multi-TF context
       ↓
  Final Score = 0.4*XGB + 0.3*LSTM + 0.3*TF
       ↓
AI Explanation (Anthropic API — explanation ONLY)
       ↓
Risk Engine (HARD GATE — cannot be bypassed)
  ✓ Confidence ≥ threshold
  ✓ Spread within limit
  ✓ No high-impact news
  ✓ Daily loss not exceeded
  ✓ Drawdown within limit
  ✓ Max open trades not exceeded
  ✓ Valid SL/TP placement
  ✓ Risk/Reward ≥ 1.5
       ↓
Execution Engine
  Forex → MT5
  Crypto → CCXT
```

---

## ML Model Training

```bash
# Export historical data from DB to parquet
python scripts/export_training_data.py --symbol EURUSD --timeframe 1h --output data/eurusd_1h.parquet

# Train all three models
python ml/training/train_models.py \
  --data data/eurusd_1h.parquet \
  --output-dir ml/models/

# Models saved:
#   ml/models/xgboost_v1.json
#   ml/models/lstm_v1.pt
#   ml/models/transformer_v1.pt
#   ml/models/scaler_v1.pkl
```

---

## API Reference

### Authentication
```
POST /api/auth/register     Register new user
POST /api/auth/login        Login → JWT tokens
POST /api/auth/refresh      Refresh access token
POST /api/auth/logout       Revoke token
```

### Signals
```
GET  /api/signals           List active signals
GET  /api/signals/{id}      Signal detail + model breakdown
POST /api/signals/generate  Trigger signal for symbol (internal)
```

### Trades (Pro+)
```
POST /api/execute/trade     Execute a trade (passes risk gate)
POST /api/execute/close/{id} Close a trade
GET  /api/execute/trades    Trade history
```

### Risk
```
GET  /api/risk/settings/{user_id}   Get risk settings
PUT  /api/risk/settings/{user_id}   Update risk settings
POST /api/risk/check                Run risk check on trade params
```

### Brokers
```
POST /api/users/forex-accounts      Add MT5 account
POST /api/users/crypto-accounts     Add crypto exchange account
GET  /api/users/accounts            List all accounts
```

---

## Security

- **AES-256-GCM** encryption for all broker credentials (stored as BYTEA)
- **bcrypt** (rounds=12) for password hashing  
- **JWT** HS256 with short-lived access tokens (30min) + refresh tokens (7d)
- **Rate limiting** per IP (60 req/min API, 10 req/min auth)
- **Token blacklisting** via Redis on logout
- **Account lockout** after 10 failed logins (30-minute lock)
- **Role-based access** (free/pro/enterprise + admin)
- **Audit logs** for every trade execution in `executions` table
- **No secrets in code** — all via environment variables

---

## Subscription Plans

| Feature | Free | Pro | Enterprise |
|---------|------|-----|------------|
| View signals | ✓ | ✓ | ✓ |
| Semi-auto trading | ✗ | ✓ | ✓ |
| Full automation | ✗ | ✗ | ✓ |
| Multi-account | ✗ | ✗ | ✓ |
| AI explanations | ✓ | ✓ | ✓ |
| Telegram alerts | ✓ | ✓ | ✓ |

---

## Environment Variables

See `.env.example` for the complete list. Critical required variables:

```bash
SECRET_KEY              # 64+ random bytes
DATABASE_URL            # PostgreSQL async DSN
REDIS_URL               # Redis connection string
JWT_SECRET_KEY          # JWT signing secret
AES_ENCRYPTION_KEY      # 32 bytes base64 for credential encryption
ANTHROPIC_API_KEY       # Only for explanation generation
CELERY_BROKER_URL       # RabbitMQ AMQP URL
```

---

## Production Deployment

```bash
# SSL certificates (Let's Encrypt recommended)
certbot certonly --standalone -d app.merittrade.ai

# Copy certs
cp /etc/letsencrypt/live/app.merittrade.ai/fullchain.pem infrastructure/nginx/ssl/
cp /etc/letsencrypt/live/app.merittrade.ai/privkey.pem infrastructure/nginx/ssl/

# Production deploy
docker compose -f docker-compose.yml up -d --build
```

---

## ⚠️ IMPORTANT DISCLAIMERS

1. **NOT financial advice.** This is a technology platform. Trading involves substantial risk of loss.
2. **Test thoroughly** on demo accounts before using real money.
3. **The risk engine** enforces hard limits but cannot guarantee against losses.
4. **AI explanations** are for informational purposes only and do NOT drive trading decisions.
5. **Regulatory compliance** is your responsibility in your jurisdiction.

---

## License

Proprietary. All rights reserved. © Merit-Trade AI.
