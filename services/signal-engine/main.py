"""
Merit-Trade AI — Signal Engine
Orchestrates the full ML pipeline:
  1. Fetch features from DB
  2. Run XGBoost → LSTM → Transformer
  3. Compute weighted ensemble
  4. Call Anthropic API for explanation (NOT for trading decisions)
  5. Store and publish signal

Scheduling (replaces celery-beat + celery-worker + RabbitMQ):
  APScheduler runs inside this process and fires all background jobs
  on the same cron schedule that was previously in celery_app.py.
"""
import asyncio
import json
import os
import pickle
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID, uuid4

import anthropic
import httpx
import numpy as np
import structlog
import torch
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, "/app/../shared")

from core.config import settings
from core.redis_client import RedisClient

logger = structlog.get_logger()

# ── Shared sequence-length constants (must match train_models.py) ──
LSTM_SEQ_LEN        = 30
TRANSFORMER_SEQ_LEN = 20

engine = create_async_engine(settings.DATABASE_URL, pool_size=5)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: RedisClient | None = None
anthropic_client: anthropic.AsyncAnthropic | None = None
xgb_model = None
lstm_model = None
transformer_model = None
feature_scaler = None
scheduler: AsyncIOScheduler | None = None

# ── Supported pairs ────────────────────────────────────────────────
ALL_PAIRS     = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSDT", "ETHUSDT", "SOLUSDT"]
CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}


# ── Scheduler jobs (previously in celery_app.py) ──────────────────

async def _collect_market_data(symbols: list, timeframe: str):
    """Fetch OHLCV from Binance/Twelve Data and push to market-data service."""
    async with httpx.AsyncClient(timeout=30) as client:
        for symbol in symbols:
            try:
                candles = await _fetch_ohlcv(client, symbol, timeframe)
                if candles:
                    await client.post(
                        f"{settings.MARKET_DATA_URL}/market/ingest",
                        json={"symbol": symbol, "timeframe": timeframe, "candles": candles},
                    )
                    logger.info("scheduler.data_collected", symbol=symbol, tf=timeframe, count=len(candles))
            except Exception as e:
                logger.error("scheduler.data_failed", symbol=symbol, tf=timeframe, error=str(e))


async def _fetch_ohlcv(client: httpx.AsyncClient, symbol: str, timeframe: str) -> list:
    """Fetch candles from Binance (crypto) or Twelve Data (forex/gold)."""
    if symbol in CRYPTO_SYMBOLS:
        tf_map = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        resp = await client.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": symbol, "interval": tf_map.get(timeframe, "1h"), "limit": 200},
        )
        if resp.status_code == 200:
            return [
                [int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])]
                for r in resp.json()
            ]
    else:
        api_key = getattr(settings, "TWELVE_DATA_API_KEY", None)
        if not api_key:
            logger.warning("scheduler.twelve_data_key_missing", symbol=symbol)
            return []
        tf_map = {"15m": "15min", "1h": "1h", "4h": "4h", "1d": "1day"}
        resp = await client.get(
            "https://api.twelvedata.com/time_series",
            params={
                "symbol": symbol,
                "interval": tf_map.get(timeframe, "1h"),
                "outputsize": 200,
                "apikey": api_key,
                "format": "JSON",
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "error":
                logger.error("scheduler.twelve_data_error", symbol=symbol, msg=data.get("message"))
                return []
            values = data.get("values", [])
            values.reverse()  # Twelve Data returns newest-first
            result = []
            for row in values:
                try:
                    ts = int(datetime.fromisoformat(row["datetime"]).timestamp() * 1000)
                    result.append([ts, float(row["open"]), float(row["high"]),
                                   float(row["low"]), float(row["close"]), float(row.get("volume", 0))])
                except Exception:
                    continue
            return result
    return []


async def _generate_signals_batch(symbols: list, timeframe: str):
    """Trigger signal generation for every symbol on the given timeframe."""
    headers = {"X-Internal-Token": getattr(settings, "INTERNAL_SERVICE_TOKEN", "")}
    async with httpx.AsyncClient(timeout=60, headers=headers) as client:
        for symbol in symbols:
            try:
                resp = await client.post(
                    f"{settings.SIGNAL_ENGINE_URL}/signals/generate",
                    json={"symbol": symbol, "timeframe": timeframe},
                )
                if resp.status_code == 200:
                    sig = resp.json()
                    logger.info("scheduler.signal_generated", symbol=symbol, tf=timeframe,
                                direction=sig.get("direction"), confidence=sig.get("confidence_score"))
                elif resp.status_code == 204:
                    logger.info("scheduler.signal_no_trade", symbol=symbol, tf=timeframe)
            except Exception as e:
                logger.error("scheduler.signal_failed", symbol=symbol, tf=timeframe, error=str(e))


async def _expire_free_trials():
    """Downgrade users whose 7-day free trial has ended. Runs every hour."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(text("""
            UPDATE users
            SET plan = 'expired_free', updated_at = NOW()
            WHERE plan = 'free'
              AND created_at < NOW() - INTERVAL '7 days'
              AND id NOT IN (
                  SELECT user_id FROM subscriptions
                  WHERE status = 'active' AND current_period_end > NOW()
              )
            RETURNING id, email
        """))
        expired = result.mappings().all()
        await session.commit()

    if expired:
        logger.info("scheduler.trials_expired", count=len(expired))
        async with httpx.AsyncClient(timeout=15) as client:
            for user in expired:
                try:
                    await client.post(
                        f"{settings.NOTIFICATION_SERVICE_URL}/notify/send",
                        json={
                            "user_id": str(user["id"]),
                            "type": "trial_expired",
                            "title": "Your free trial has ended",
                            "body": (
                                "Your 7-day Merit-Trade AI free trial has ended. "
                                "Upgrade to Pro to continue receiving signals on all 8 pairs and 3 timeframes."
                            ),
                            "metadata": {"cta": "upgrade", "url": "/pricing"},
                        },
                    )
                except Exception as e:
                    logger.error("scheduler.trial_notify_failed", user_id=str(user["id"]), error=str(e))


async def _collect_economic_calendar():
    """Cache high-impact Forex Factory events in Redis for the risk engine."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                headers={"Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.warning("scheduler.calendar_fetch_failed", status=resp.status_code)
                return
            events = resp.json()

        now_utc = datetime.now(timezone.utc)
        for event in events:
            if event.get("impact") != "High":
                continue
            country  = event.get("country", "")
            title    = event.get("title", "Unknown event")
            raw_date = event.get("date", "")
            raw_time = event.get("time", "")
            try:
                event_dt = datetime.strptime(f"{raw_date} {raw_time}", "%m-%d-%Y %I:%M%p").replace(
                    tzinfo=timezone.utc
                )
            except Exception:
                continue
            minutes_until = (event_dt - now_utc).total_seconds() / 60
            if -5 <= minutes_until <= 30:
                ttl = max(60, int((event_dt - now_utc + timedelta(minutes=5)).total_seconds()))
                await redis_client.set(
                    f"news:high_impact:{country}",
                    f"{title} at {raw_time} UTC",
                    ex=ttl,
                )
                logger.info("scheduler.calendar_cached", country=country, title=title,
                            minutes_until=round(minutes_until, 1))
    except Exception as e:
        logger.error("scheduler.calendar_error", error=str(e))


async def _sync_open_trades():
    """Update current price and unrealized P&L for all open trades."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT id, symbol, direction, entry_price, lot_size FROM trades WHERE status = 'open'")
        )
        open_trades = result.mappings().all()

    if not open_trades:
        return

    async with httpx.AsyncClient(timeout=10) as client:
        for trade in open_trades:
            try:
                resp = await client.get(f"{settings.MARKET_DATA_URL}/market/price/{trade['symbol']}")
                if resp.status_code != 200:
                    continue
                current_price  = resp.json().get("price", 0)
                entry          = float(trade["entry_price"] or 0)
                direction_mult = 1 if trade["direction"] == "BUY" else -1
                unrealized_pnl = (current_price - entry) * direction_mult * float(trade["lot_size"] or 1) * 100000
                async with AsyncSessionFactory() as upd:
                    await upd.execute(
                        text("UPDATE trades SET current_price = :p, unrealized_pnl = :pnl WHERE id = :id"),
                        {"p": current_price, "pnl": unrealized_pnl, "id": str(trade["id"])},
                    )
                    await upd.commit()
            except Exception as e:
                logger.error("scheduler.sync_trade_failed", trade_id=str(trade["id"]), error=str(e))


async def _cleanup_expired_signals():
    """Mark signals older than 24 h with no linked trade as inactive."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(text("""
            UPDATE signals SET is_active = false
            WHERE is_active = true
              AND generated_at < NOW() - INTERVAL '24 hours'
              AND id NOT IN (SELECT signal_id FROM trades WHERE signal_id IS NOT NULL)
        """))
        await session.commit()
        logger.info("scheduler.signals_cleaned", deactivated=result.rowcount)


def _start_scheduler():
    """Register all jobs and start the APScheduler instance."""
    global scheduler
    scheduler = AsyncIOScheduler()

    # ── 15-minute bar ──────────────────────────────
    scheduler.add_job(_collect_market_data,   CronTrigger(minute="0,15,30,45"),  args=[ALL_PAIRS, "15m"], id="collect-15m")
    scheduler.add_job(_generate_signals_batch, CronTrigger(minute="3,18,33,48"), args=[ALL_PAIRS, "15m"], id="signals-15m")

    # ── 1-hour bar ─────────────────────────────────
    scheduler.add_job(_collect_market_data,   CronTrigger(minute=0),             args=[ALL_PAIRS, "1h"],  id="collect-1h")
    scheduler.add_job(_generate_signals_batch, CronTrigger(minute=5),            args=[ALL_PAIRS, "1h"],  id="signals-1h")

    # ── 4-hour bar ─────────────────────────────────
    scheduler.add_job(_collect_market_data,   CronTrigger(minute=0,  hour="0,4,8,12,16,20"), args=[ALL_PAIRS, "4h"], id="collect-4h")
    scheduler.add_job(_generate_signals_batch, CronTrigger(minute=10, hour="0,4,8,12,16,20"), args=[ALL_PAIRS, "4h"], id="signals-4h")

    # ── Daily bar ──────────────────────────────────
    scheduler.add_job(_collect_market_data,   CronTrigger(hour=0, minute=15),    args=[ALL_PAIRS, "1d"],  id="collect-1d")
    scheduler.add_job(_generate_signals_batch, CronTrigger(hour=0, minute=30),   args=[ALL_PAIRS, "1d"],  id="signals-1d")

    # ── Housekeeping ───────────────────────────────
    scheduler.add_job(_collect_economic_calendar, CronTrigger(hour=0, minute=45),           id="calendar")
    scheduler.add_job(_expire_free_trials,         CronTrigger(minute=0),                   id="expire-trials")
    scheduler.add_job(_cleanup_expired_signals,    CronTrigger(hour=2, minute=0),           id="cleanup-signals")
    scheduler.add_job(_sync_open_trades,           IntervalTrigger(seconds=60),             id="sync-trades")

    scheduler.start()
    logger.info("scheduler.started", jobs=len(scheduler.get_jobs()))


# ── Lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, anthropic_client
    redis_client     = await RedisClient.create()
    anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    _load_models()
    _start_scheduler()
    yield
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
    await redis_client.close()
    await anthropic_client.close()


# ── Model loading ──────────────────────────────────────────────────

def _load_models():
    """Load pre-trained ML models from disk."""
    global xgb_model, lstm_model, transformer_model, feature_scaler
    import xgboost as xgb

    try:
        if os.path.exists(settings.MODEL_XGBOOST_PATH):
            xgb_model = xgb.XGBClassifier()
            xgb_model.load_model(settings.MODEL_XGBOOST_PATH)
            logger.info("models.xgboost.loaded")
    except Exception as e:
        logger.warning("models.xgboost.load_failed", error=str(e))

    try:
        if os.path.exists(settings.MODEL_LSTM_PATH):
            lstm_model = torch.load(settings.MODEL_LSTM_PATH, map_location="cpu")
            lstm_model.eval()
            logger.info("models.lstm.loaded")
    except Exception as e:
        logger.warning("models.lstm.load_failed", error=str(e))

    try:
        if os.path.exists(settings.MODEL_TRANSFORMER_PATH):
            transformer_model = torch.load(settings.MODEL_TRANSFORMER_PATH, map_location="cpu")
            transformer_model.eval()
            logger.info("models.transformer.loaded")
    except Exception as e:
        logger.warning("models.transformer.load_failed", error=str(e))

    try:
        if os.path.exists(settings.MODEL_SCALER_PATH):
            with open(settings.MODEL_SCALER_PATH, "rb") as f:
                feature_scaler = pickle.load(f)
            logger.info("models.scaler.loaded")
    except Exception as e:
        logger.warning("models.scaler.load_failed", error=str(e))


# ── App ────────────────────────────────────────────────────────────

app = FastAPI(title="Signal Engine", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Internal auth guard ────────────────────────────────────────────

async def require_internal_or_gateway(
    x_internal_token: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_user_plan: Optional[str] = Header(None),
):
    internal_token = getattr(settings, "INTERNAL_SERVICE_TOKEN", None)
    if internal_token and x_internal_token == internal_token:
        return {"source": "internal", "plan": "enterprise"}
    if x_user_id and x_user_plan:
        return {"source": "gateway", "user_id": x_user_id, "plan": x_user_plan}
    raise HTTPException(
        status_code=403,
        detail="Direct access to signal-engine is not permitted. Route requests via the API gateway.",
    )


# ── Feature columns (must match training data) ─────────────────────

FEATURE_COLUMNS = [
    "ema_20", "ema_50", "ema_200", "sma_20", "sma_50",
    "rsi_14", "macd_line", "macd_signal", "macd_hist",
    "atr_14", "bb_upper", "bb_middle", "bb_lower", "bb_width",
    "vwap", "volume_sma_20",
    "open", "high", "low", "close", "volume",
]

XGBOOST_WEIGHT     = 0.4
LSTM_WEIGHT        = 0.3
TRANSFORMER_WEIGHT = 0.3


# ── Schemas ────────────────────────────────────────────────────────

class SignalRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    asset_class: str = "forex"


class ModelOutput(BaseModel):
    direction: str
    score: float
    confidence: float


class SignalResponse(BaseModel):
    id: UUID
    symbol: str
    asset_class: str
    timeframe: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: Optional[float] = None
    confidence_score: int
    risk_score: int
    xgboost: ModelOutput
    lstm: ModelOutput
    transformer: ModelOutput
    ensemble_score: float
    ai_explanation: str
    ai_sentiment: str
    sentiment_score: float
    risk_reward_ratio: float
    atr_value: float
    generated_at: datetime


# ── ML Inference ───────────────────────────────────────────────────

class MLPipeline:
    def run_xgboost(self, features: np.ndarray) -> ModelOutput:
        if xgb_model is None:
            return self._fallback_model("XGBoost", features)
        probs = xgb_model.predict_proba(features.reshape(1, -1))[0]
        direction_idx = int(np.argmax(probs))
        direction_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        return ModelOutput(
            direction=direction_map[direction_idx],
            score=float(probs[direction_idx]),
            confidence=float(probs[direction_idx]),
        )

    def run_lstm(self, sequence: np.ndarray) -> ModelOutput:
        if lstm_model is None:
            return self._fallback_model("LSTM", sequence[-1])
        with torch.no_grad():
            tensor = torch.FloatTensor(sequence).unsqueeze(0)
            output = lstm_model(tensor)
            probs  = torch.softmax(output, dim=-1).numpy()[0]
        direction_idx = int(np.argmax(probs))
        direction_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        return ModelOutput(
            direction=direction_map[direction_idx],
            score=float(probs[direction_idx]),
            confidence=float(max(probs)),
        )

    def run_transformer(self, multi_tf_features: np.ndarray) -> ModelOutput:
        if transformer_model is None:
            return self._fallback_model("Transformer", multi_tf_features[-1])
        with torch.no_grad():
            tensor = torch.FloatTensor(multi_tf_features).unsqueeze(0)
            output = transformer_model(tensor)
            probs  = torch.softmax(output["logits"], dim=-1).numpy()[0]
        direction_idx = int(np.argmax(probs))
        direction_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        raw_conf = output.get("confidence", None)
        if raw_conf is not None and isinstance(raw_conf, torch.Tensor):
            confidence_val = float(raw_conf.item())
        elif raw_conf is not None:
            confidence_val = float(raw_conf)
        else:
            confidence_val = float(max(probs))
        return ModelOutput(
            direction=direction_map[direction_idx],
            score=float(probs[direction_idx]),
            confidence=confidence_val,
        )

    def _fallback_model(self, name: str, raw_features: np.ndarray) -> ModelOutput:
        logger.warning("ml.model.fallback", model=name)
        rsi = float(raw_features[5]) if len(raw_features) > 5 else 50.0
        if rsi < 30:
            direction, score = "BUY", 0.60
        elif rsi > 70:
            direction, score = "SELL", 0.60
        else:
            direction, score = "HOLD", 0.50
        return ModelOutput(direction=direction, score=score, confidence=score)

    def compute_ensemble(
        self, xgb_out: ModelOutput, lstm_out: ModelOutput, tf_out: ModelOutput
    ) -> tuple[str, float, int]:
        direction_score = {"BUY": 1.0, "HOLD": 0.0, "SELL": -1.0}
        xgb_val  = direction_score[xgb_out.direction]  * xgb_out.score
        lstm_val = direction_score[lstm_out.direction] * lstm_out.score
        tf_val   = direction_score[tf_out.direction]   * tf_out.score
        ensemble = (
            XGBOOST_WEIGHT     * xgb_val +
            LSTM_WEIGHT        * lstm_val +
            TRANSFORMER_WEIGHT * tf_val
        )
        if ensemble > 0.3:
            direction = "BUY"
        elif ensemble < -0.3:
            direction = "SELL"
        else:
            direction = "HOLD"
        confidence = min(100, int(abs(ensemble) * 100))
        return direction, ensemble, confidence


# ── AI Explanation ─────────────────────────────────────────────────

async def generate_ai_explanation(
    symbol: str, direction: str, confidence: int, features: dict, news_context: str = ""
) -> tuple[str, str, float]:
    prompt = f"""You are a financial market analyst providing a brief explanation of a trading signal.

Signal Data (generated by ML models - DO NOT modify the trading direction):
- Asset: {symbol}
- ML Direction: {direction}
- Confidence: {confidence}%
- RSI(14): {features.get('rsi_14', 'N/A')}
- MACD: {features.get('macd_line', 'N/A')}
- ATR: {features.get('atr_14', 'N/A')}
- EMA20: {features.get('ema_20', 'N/A')}
- EMA50: {features.get('ema_50', 'N/A')}
- Recent news context: {news_context or 'None available'}

Task: Write a concise 2-3 sentence explanation of WHY the ML models may have generated this signal based on the technical indicators.
Also classify the overall market sentiment as: bullish, bearish, or neutral.
Format: JSON with keys "explanation" (string), "sentiment" (string), "sentiment_score" (float -1.0 to 1.0)
Respond ONLY with valid JSON, no markdown."""

    try:
        response = await anthropic_client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw  = response.content[0].text.strip()
        data = json.loads(raw)
        return (
            data.get("explanation", "Signal generated by ML ensemble."),
            data.get("sentiment", "neutral"),
            float(data.get("sentiment_score", 0.0)),
        )
    except Exception as e:
        logger.warning("ai.explanation.failed", error=str(e))
        return f"Signal generated by ML ensemble for {symbol}.", "neutral", 0.0


# ── SL/TP Calculation ──────────────────────────────────────────────

def calculate_sl_tp(direction: str, entry: float, atr: float) -> tuple[float, float, float]:
    sl_multiplier  = 1.5
    tp1_multiplier = 2.0
    tp2_multiplier = 3.5
    if direction == "BUY":
        stop_loss     = entry - (atr * sl_multiplier)
        take_profit_1 = entry + (atr * tp1_multiplier)
        take_profit_2 = entry + (atr * tp2_multiplier)
    elif direction == "SELL":
        stop_loss     = entry + (atr * sl_multiplier)
        take_profit_1 = entry - (atr * tp1_multiplier)
        take_profit_2 = entry - (atr * tp2_multiplier)
    else:
        stop_loss     = entry - atr
        take_profit_1 = entry + atr
        take_profit_2 = entry + (atr * 2)
    return round(stop_loss, 5), round(take_profit_1, 5), round(take_profit_2, 5)


# ── Pipeline ───────────────────────────────────────────────────────

ml_pipeline = MLPipeline()


async def fetch_latest_features(symbol: str, timeframe: str) -> list:
    fetch_limit = max(LSTM_SEQ_LEN, TRANSFORMER_SEQ_LEN)
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("""
                SELECT f.*, m.open, m.high, m.low, m.close, m.volume
                FROM features f
                JOIN market_data m ON f.time = m.time AND f.symbol = m.symbol AND f.timeframe = m.timeframe
                WHERE f.symbol = :symbol AND f.timeframe = :tf
                ORDER BY f.time DESC
                LIMIT :limit
            """),
            {"symbol": symbol, "tf": timeframe, "limit": fetch_limit},
        )
        rows = result.mappings().all()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No features found for {symbol}/{timeframe}")
        return [dict(r) for r in rows]


async def generate_signal(symbol: str, timeframe: str, asset_class: str) -> SignalResponse:
    feature_rows    = await fetch_latest_features(symbol, timeframe)
    latest          = feature_rows[0]
    raw_feature_vec = np.array([float(latest.get(col, 0) or 0) for col in FEATURE_COLUMNS])

    feature_vec = raw_feature_vec.copy()
    if feature_scaler:
        feature_vec = feature_scaler.transform(feature_vec.reshape(1, -1))[0]

    ohlcv_rows = feature_rows[:LSTM_SEQ_LEN]
    sequence   = np.array([
        [float(row.get("open", 0) or 0), float(row.get("high", 0) or 0),
         float(row.get("low",  0) or 0), float(row.get("close",0) or 0), float(row.get("volume",0) or 0)]
        for row in ohlcv_rows
    ])
    sequence = sequence[::-1].copy()

    tf_rows  = feature_rows[:TRANSFORMER_SEQ_LEN]
    multi_tf = np.array([[float(row.get(col, 0) or 0) for col in FEATURE_COLUMNS] for row in tf_rows])
    multi_tf = multi_tf[::-1].copy()
    if feature_scaler:
        orig_shape = multi_tf.shape
        multi_tf   = feature_scaler.transform(multi_tf.reshape(-1, orig_shape[-1])).reshape(orig_shape)

    xgb_out  = ml_pipeline.run_xgboost(feature_vec)  if xgb_model         else ml_pipeline._fallback_model("XGBoost",     raw_feature_vec)
    lstm_out = ml_pipeline.run_lstm(sequence)          if lstm_model        else ml_pipeline._fallback_model("LSTM",        raw_feature_vec)
    tf_out   = ml_pipeline.run_transformer(multi_tf)  if transformer_model else ml_pipeline._fallback_model("Transformer", raw_feature_vec)

    direction, ensemble_score, confidence = ml_pipeline.compute_ensemble(xgb_out, lstm_out, tf_out)

    if direction == "HOLD" or confidence < settings.MIN_CONFIDENCE_THRESHOLD:
        return Response(status_code=204)

    entry = float(latest.get("close", 0))
    atr   = float(latest.get("atr_14", 0) or entry * 0.001)
    sl, tp1, tp2 = calculate_sl_tp(direction, entry, atr)
    rr_ratio     = abs(tp1 - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0
    risk_score   = max(0, min(100, 100 - confidence + int(atr / entry * 10000)))

    features_for_ai = {col: float(latest.get(col, 0) or 0) for col in FEATURE_COLUMNS[:10]}
    news_context    = await redis_client.get(f"news:latest:{symbol[:6].upper()}")
    if news_context:
        news_context = news_context.decode() if isinstance(news_context, bytes) else news_context
    explanation, sentiment, sentiment_score = await generate_ai_explanation(
        symbol, direction, confidence, features_for_ai, news_context or ""
    )

    signal_id = uuid4()
    async with AsyncSessionFactory() as session:
        await session.execute(
            text("""
                INSERT INTO signals (
                    id, symbol, asset_class, timeframe, direction,
                    entry_price, stop_loss, take_profit_1, take_profit_2,
                    confidence_score, risk_score,
                    xgboost_score, xgboost_direction,
                    lstm_score, lstm_direction,
                    transformer_score, transformer_direction,
                    ensemble_score, ai_explanation, ai_sentiment, sentiment_score,
                    risk_reward_ratio, atr_value
                ) VALUES (
                    :id, :symbol, :asset_class, :timeframe, :direction,
                    :entry, :sl, :tp1, :tp2,
                    :confidence, :risk,
                    :xgb_score, :xgb_dir,
                    :lstm_score, :lstm_dir,
                    :tf_score, :tf_dir,
                    :ensemble, :explanation, :sentiment, :sentiment_score,
                    :rr, :atr
                )
            """),
            {
                "id": str(signal_id), "symbol": symbol, "asset_class": asset_class,
                "timeframe": timeframe, "direction": direction,
                "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                "confidence": confidence, "risk": risk_score,
                "xgb_score": xgb_out.score, "xgb_dir": xgb_out.direction,
                "lstm_score": lstm_out.score, "lstm_dir": lstm_out.direction,
                "tf_score": tf_out.score, "tf_dir": tf_out.direction,
                "ensemble": ensemble_score, "explanation": explanation,
                "sentiment": sentiment, "sentiment_score": sentiment_score,
                "rr": rr_ratio, "atr": atr,
            },
        )
        await session.commit()

    await redis_client.publish(
        "channel:signals",
        json.dumps({
            "type": "new_signal",
            "signal_id": str(signal_id),
            "symbol": symbol,
            "direction": direction,
            "confidence": confidence,
            "entry": entry,
            "sl": sl,
            "tp1": tp1,
        }),
    )

    logger.info("signal.generated", signal_id=str(signal_id), symbol=symbol,
                direction=direction, confidence=confidence)

    return SignalResponse(
        id=signal_id, symbol=symbol, asset_class=asset_class, timeframe=timeframe,
        direction=direction, entry_price=entry, stop_loss=sl,
        take_profit_1=tp1, take_profit_2=tp2,
        confidence_score=confidence, risk_score=risk_score,
        xgboost=xgb_out, lstm=lstm_out, transformer=tf_out,
        ensemble_score=float(ensemble_score),
        ai_explanation=explanation, ai_sentiment=sentiment, sentiment_score=sentiment_score,
        risk_reward_ratio=rr_ratio, atr_value=atr,
        generated_at=datetime.now(timezone.utc),
    )


# ── Routes ─────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "signal-engine",
        "scheduler": scheduler.running if scheduler else False,
        "jobs": len(scheduler.get_jobs()) if scheduler else 0,
        "models": {
            "xgboost":     xgb_model is not None,
            "lstm":        lstm_model is not None,
            "transformer": transformer_model is not None,
        },
    }


@app.post("/signals/generate")
async def generate(
    req: SignalRequest,
    _auth: dict = Depends(require_internal_or_gateway),
):
    return await generate_signal(req.symbol, req.timeframe, req.asset_class)


@app.get("/signals")
async def list_signals(
    symbol: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    _auth: dict = Depends(require_internal_or_gateway),
):
    async with AsyncSessionFactory() as session:
        where  = "WHERE is_active = true"
        params: dict = {"limit": limit, "offset": offset}
        if symbol:
            where += " AND symbol = :symbol"
            params["symbol"] = symbol.upper()
        result = await session.execute(
            text(f"SELECT * FROM signals {where} ORDER BY generated_at DESC LIMIT :limit OFFSET :offset"),
            params,
        )
        return [dict(r) for r in result.mappings().all()]


@app.get("/signals/{signal_id}")
async def get_signal(
    signal_id: UUID,
    _auth: dict = Depends(require_internal_or_gateway),
):
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM signals WHERE id = :id"),
            {"id": str(signal_id)},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")
        return dict(row)