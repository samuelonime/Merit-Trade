"""
Merit-Trade AI — Signal Engine
Orchestrates the full ML pipeline:
  1. Fetch features from DB
  2. Run XGBoost → LSTM → Transformer
  3. Compute weighted ensemble
  4. Call Anthropic API for explanation (NOT for trading decisions)
  5. Store and publish signal
"""
import asyncio
import json
import pickle
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID, uuid4

import anthropic
import httpx
import numpy as np
import structlog
import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, "/app/../shared")

from core.config import settings
from core.redis_client import RedisClient

logger = structlog.get_logger()

engine = create_async_engine(settings.DATABASE_URL, pool_size=5)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: RedisClient | None = None
anthropic_client: anthropic.AsyncAnthropic | None = None
xgb_model = None
lstm_model = None
transformer_model = None
feature_scaler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, anthropic_client, xgb_model, lstm_model, transformer_model, feature_scaler
    redis_client = await RedisClient.create()
    anthropic_client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    _load_models()
    yield
    await redis_client.close()
    await anthropic_client.close()


def _load_models():
    """Load pre-trained ML models from disk."""
    global xgb_model, lstm_model, transformer_model, feature_scaler
    import xgboost as xgb
    import os

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


app = FastAPI(title="Signal Engine", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Feature names (must match training data) ───────

FEATURE_COLUMNS = [
    "ema_20", "ema_50", "ema_200", "sma_20", "sma_50",
    "rsi_14", "macd_line", "macd_signal", "macd_hist",
    "atr_14", "bb_upper", "bb_middle", "bb_lower", "bb_width",
    "vwap", "volume_sma_20",
    "open", "high", "low", "close", "volume",
]

# Ensemble weights (must sum to 1.0)
XGBOOST_WEIGHT = 0.4
LSTM_WEIGHT = 0.3
TRANSFORMER_WEIGHT = 0.3


# ── Schemas ───────────────────────────────────────

class SignalRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    asset_class: str = "forex"


class ModelOutput(BaseModel):
    direction: str      # BUY | SELL | HOLD
    score: float        # 0.0 - 1.0 probability
    confidence: float   # model-internal confidence


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


# ── ML Inference ───────────────────────────────────

class MLPipeline:
    """
    Runs the three-model ensemble pipeline.
    XGBoost: tabular features → BUY/SELL/HOLD probabilities
    LSTM: sequence of OHLCV → direction prediction
    Transformer: multi-timeframe context → trend + volatility
    """

    def run_xgboost(self, features: np.ndarray) -> ModelOutput:
        if xgb_model is None:
            return self._fallback_model("XGBoost", features)

        probs = xgb_model.predict_proba(features.reshape(1, -1))[0]
        # Assume classes: 0=SELL, 1=HOLD, 2=BUY
        direction_idx = np.argmax(probs)
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
            probs = torch.softmax(output, dim=-1).numpy()[0]
        direction_idx = np.argmax(probs)
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
            probs = torch.softmax(output["logits"], dim=-1).numpy()[0]
        direction_idx = np.argmax(probs)
        direction_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
        return ModelOutput(
            direction=direction_map[direction_idx],
            score=float(probs[direction_idx]),
            confidence=float(output.get("confidence", max(probs))),
        )

    def _fallback_model(self, name: str, features: np.ndarray) -> ModelOutput:
        """
        Deterministic fallback when model file is not loaded.
        Uses simple rule-based logic from features.
        NOT for production — models must be trained and loaded.
        """
        logger.warning("ml.model.fallback", model=name)
        # RSI-based fallback rule
        rsi = features[5] if len(features) > 5 else 50.0
        if rsi < 30:
            direction, score = "BUY", 0.60
        elif rsi > 70:
            direction, score = "SELL", 0.60
        else:
            direction, score = "HOLD", 0.50
        return ModelOutput(direction=direction, score=score, confidence=score)

    def compute_ensemble(
        self, xgb_out: ModelOutput, lstm_out: ModelOutput, tf_out: ModelOutput
    ) -> tuple[str, float]:
        """
        Weighted ensemble: 0.4*XGB + 0.3*LSTM + 0.3*Transformer
        Converts directions to numeric scores, computes weighted average.
        """
        direction_score = {"BUY": 1.0, "HOLD": 0.0, "SELL": -1.0}

        xgb_val = direction_score[xgb_out.direction] * xgb_out.score
        lstm_val = direction_score[lstm_out.direction] * lstm_out.score
        tf_val = direction_score[tf_out.direction] * tf_out.score

        ensemble = (
            XGBOOST_WEIGHT * xgb_val +
            LSTM_WEIGHT * lstm_val +
            TRANSFORMER_WEIGHT * tf_val
        )

        # Convert ensemble score to direction + confidence
        if ensemble > 0.3:
            direction = "BUY"
        elif ensemble < -0.3:
            direction = "SELL"
        else:
            direction = "HOLD"

        confidence = min(100, int(abs(ensemble) * 100))
        return direction, ensemble, confidence


# ── AI Explanation (ONLY use of Anthropic API) ────

async def generate_ai_explanation(
    symbol: str,
    direction: str,
    confidence: int,
    features: dict,
    news_context: str = "",
) -> tuple[str, str, float]:
    """
    Use Anthropic API STRICTLY for:
    1. Generating human-readable explanation of the signal
    2. News sentiment context
    This NEVER influences the trading decision.
    """
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
        raw = response.content[0].text.strip()
        data = json.loads(raw)
        return (
            data.get("explanation", "Signal generated by ML ensemble."),
            data.get("sentiment", "neutral"),
            float(data.get("sentiment_score", 0.0)),
        )
    except Exception as e:
        logger.warning("ai.explanation.failed", error=str(e))
        return f"Signal generated by ML ensemble for {symbol}.", "neutral", 0.0


# ── SL/TP Calculation ─────────────────────────────

def calculate_sl_tp(direction: str, entry: float, atr: float) -> tuple[float, float, float]:
    """ATR-based stop loss and take profit calculation."""
    sl_multiplier = 1.5
    tp1_multiplier = 2.0
    tp2_multiplier = 3.5

    if direction == "BUY":
        stop_loss = entry - (atr * sl_multiplier)
        take_profit_1 = entry + (atr * tp1_multiplier)
        take_profit_2 = entry + (atr * tp2_multiplier)
    elif direction == "SELL":
        stop_loss = entry + (atr * sl_multiplier)
        take_profit_1 = entry - (atr * tp1_multiplier)
        take_profit_2 = entry - (atr * tp2_multiplier)
    else:
        stop_loss = entry - atr
        take_profit_1 = entry + atr
        take_profit_2 = entry + (atr * 2)

    return round(stop_loss, 5), round(take_profit_1, 5), round(take_profit_2, 5)


# ── Pipeline ───────────────────────────────────────

ml_pipeline = MLPipeline()


async def fetch_latest_features(symbol: str, timeframe: str) -> dict:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("""
                SELECT f.*, m.open, m.high, m.low, m.close, m.volume
                FROM features f
                JOIN market_data m ON f.time = m.time AND f.symbol = m.symbol AND f.timeframe = m.timeframe
                WHERE f.symbol = :symbol AND f.timeframe = :tf
                ORDER BY f.time DESC
                LIMIT 60
            """),
            {"symbol": symbol, "tf": timeframe},
        )
        rows = result.mappings().all()
        if not rows:
            raise HTTPException(status_code=404, detail=f"No features found for {symbol}/{timeframe}")
        return [dict(r) for r in rows]


async def generate_signal(symbol: str, timeframe: str, asset_class: str) -> SignalResponse:
    # 1. Fetch features
    feature_rows = await fetch_latest_features(symbol, timeframe)
    latest = feature_rows[0]

    # 2. Build feature vector for XGBoost
    feature_vec = np.array([float(latest.get(col, 0) or 0) for col in FEATURE_COLUMNS])
    if feature_scaler:
        feature_vec = feature_scaler.transform(feature_vec.reshape(1, -1))[0]

    # 3. Build sequence for LSTM (last 30 candles)
    sequence = np.array([[
        float(row.get("open", 0) or 0),
        float(row.get("high", 0) or 0),
        float(row.get("low", 0) or 0),
        float(row.get("close", 0) or 0),
        float(row.get("volume", 0) or 0),
    ] for row in feature_rows[:30]])

    # 4. Build multi-TF features for Transformer
    # In production this would include 4h + daily features
    multi_tf = np.array([[float(row.get(col, 0) or 0) for col in FEATURE_COLUMNS] for row in feature_rows[:20]])

    # 5. Run models
    xgb_out = ml_pipeline.run_xgboost(feature_vec)
    lstm_out = ml_pipeline.run_lstm(sequence)
    tf_out = ml_pipeline.run_transformer(multi_tf)

    # 6. Ensemble
    direction, ensemble_score, confidence = ml_pipeline.compute_ensemble(xgb_out, lstm_out, tf_out)

    # Only generate BUY/SELL signals with meaningful confidence
    if direction == "HOLD" or confidence < settings.MIN_CONFIDENCE_THRESHOLD:
        raise HTTPException(status_code=204, detail="No signal: insufficient confidence or HOLD condition")

    # 7. ATR-based SL/TP
    entry = float(latest.get("close", 0))
    atr = float(latest.get("atr_14", 0) or entry * 0.001)  # fallback to 0.1% if no ATR
    sl, tp1, tp2 = calculate_sl_tp(direction, entry, atr)

    rr_ratio = abs(tp1 - entry) / abs(sl - entry) if abs(sl - entry) > 0 else 0

    # 8. Risk score (inverse of confidence, plus spread/volatility factors)
    risk_score = max(0, min(100, 100 - confidence + int(atr / entry * 10000)))

    # 9. AI explanation (ONLY for human-readable context, not decision making)
    features_for_ai = {col: float(latest.get(col, 0) or 0) for col in FEATURE_COLUMNS[:10]}
    news_context = await redis_client.get(f"news:latest:{symbol[:6].upper()}")
    if news_context:
        news_context = news_context.decode() if isinstance(news_context, bytes) else news_context
    explanation, sentiment, sentiment_score = await generate_ai_explanation(
        symbol, direction, confidence, features_for_ai, news_context or ""
    )

    # 10. Persist signal
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

    # 11. Publish to Redis pub/sub for real-time clients
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

    logger.info(
        "signal.generated",
        signal_id=str(signal_id), symbol=symbol,
        direction=direction, confidence=confidence,
    )

    return SignalResponse(
        id=signal_id,
        symbol=symbol,
        asset_class=asset_class,
        timeframe=timeframe,
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit_1=tp1,
        take_profit_2=tp2,
        confidence_score=confidence,
        risk_score=risk_score,
        xgboost=xgb_out,
        lstm=lstm_out,
        transformer=tf_out,
        ensemble_score=float(ensemble_score),
        ai_explanation=explanation,
        ai_sentiment=sentiment,
        sentiment_score=sentiment_score,
        risk_reward_ratio=rr_ratio,
        atr_value=atr,
        generated_at=datetime.now(timezone.utc),
    )


# ── Routes ────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "signal-engine",
        "models": {
            "xgboost": xgb_model is not None,
            "lstm": lstm_model is not None,
            "transformer": transformer_model is not None,
        },
    }


@app.post("/signals/generate", response_model=SignalResponse)
async def generate(req: SignalRequest):
    return await generate_signal(req.symbol, req.timeframe, req.asset_class)


@app.get("/signals")
async def list_signals(
    symbol: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    async with AsyncSessionFactory() as session:
        where = "WHERE is_active = true"
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
async def get_signal(signal_id: UUID):
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM signals WHERE id = :id"),
            {"id": str(signal_id)},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Signal not found")
        return dict(row)
