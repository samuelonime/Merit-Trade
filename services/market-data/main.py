"""
Merit-Trade AI — Market Data Service
Collects, normalizes, and stores OHLCV data.
Computes all technical indicators and market structure features.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd
import structlog
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

engine = create_async_engine(settings.DATABASE_URL, pool_size=10)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: RedisClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_client = await RedisClient.create()
    yield
    await redis_client.close()


app = FastAPI(title="Market Data Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Technical Indicator Engine ────────────────────

class FeatureEngineer:
    """
    Computes all technical indicators from OHLCV data.
    Uses pandas/numpy for efficiency.
    """

    @staticmethod
    def compute_all(df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all features for a given OHLCV DataFrame.
        df must have columns: open, high, low, close, volume
        Rows must be in chronological order (oldest first).
        """
        df = df.copy()
        close  = df["close"]
        high   = df["high"]
        low    = df["low"]
        volume = df["volume"]

        # ── Moving Averages ────────────────────────
        df["ema_20"]  = close.ewm(span=20, adjust=False).mean()
        df["ema_50"]  = close.ewm(span=50, adjust=False).mean()
        df["ema_200"] = close.ewm(span=200, adjust=False).mean()
        df["sma_20"]  = close.rolling(20).mean()
        df["sma_50"]  = close.rolling(50).mean()

        # ── RSI ────────────────────────────────────
        df["rsi_14"] = FeatureEngineer._rsi(close, 14)

        # ── MACD ───────────────────────────────────
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        df["macd_line"]   = ema_12 - ema_26
        df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["macd_hist"]   = df["macd_line"] - df["macd_signal"]

        # ── ATR ────────────────────────────────────
        df["atr_14"] = FeatureEngineer._atr(high, low, close, 14)

        # ── Bollinger Bands ────────────────────────
        df["bb_middle"] = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        df["bb_upper"] = df["bb_middle"] + (2 * bb_std)
        df["bb_lower"] = df["bb_middle"] - (2 * bb_std)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

        # ── VWAP (rolling 20-period) ────────────────────────────────────────
        # FIX #4: The original used cumsum() which resets to zero on every ingest
        # batch, producing wrong values for all but the first daily batch.
        # Rolling VWAP is stateless across batches and always correct.
        typical_price  = (high + low + close) / 3
        df["vwap"] = (
            (typical_price * volume).rolling(20).sum() /
            volume.rolling(20).sum()
        )

        # ── Volume SMA ─────────────────────────────
        df["volume_sma_20"] = volume.rolling(20).mean()

        # ── Market Structure ───────────────────────
        df = FeatureEngineer._market_structure(df)

        # ── Support & Resistance ───────────────────
        df = FeatureEngineer._support_resistance(df)

        # ── Fair Value Gaps ────────────────────────
        df = FeatureEngineer._fair_value_gaps(df)

        return df

    @staticmethod
    def _rsi(close: pd.Series, period: int) -> pd.Series:
        delta = close.diff()
        gain  = delta.where(delta > 0, 0.0).rolling(window=period).mean()
        loss  = -delta.where(delta < 0, 0.0).rolling(window=period).mean()
        rs    = gain / loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low  - prev_close).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _market_structure(df: pd.DataFrame) -> pd.DataFrame:
        """Identify Higher Highs, Higher Lows, Lower Highs, Lower Lows."""
        highs = df["high"]
        lows  = df["low"]
        structures = []

        for i in range(2, len(df)):
            prev_high = highs.iloc[i - 1]
            prev_low  = lows.iloc[i - 1]
            curr_high = highs.iloc[i]
            curr_low  = lows.iloc[i]

            if curr_high > prev_high and curr_low > prev_low:
                structures.append("HH_HL")
            elif curr_high < prev_high and curr_low < prev_low:
                structures.append("LH_LL")
            elif curr_high > prev_high and curr_low < prev_low:
                structures.append("HH_LL")   # expansion
            else:
                structures.append("LH_HL")   # contraction

        df["structure"] = ["UNKNOWN", "UNKNOWN"] + structures

        def get_trend(s):
            if s == "HH_HL":
                return "UP"
            elif s == "LH_LL":
                return "DOWN"
            else:
                return "SIDEWAYS"

        df["trend_direction"] = df["structure"].apply(get_trend)
        return df

    @staticmethod
    def _support_resistance(df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
        """Identify recent support and resistance levels."""
        df["support_level"]    = df["low"].rolling(lookback).min()
        df["resistance_level"] = df["high"].rolling(lookback).max()
        return df

    @staticmethod
    def _fair_value_gaps(df: pd.DataFrame) -> pd.DataFrame:
        """
        Identify Fair Value Gaps (FVG) / imbalances.
        Bullish FVG: candle[i-2].high < candle[i].low
        Bearish FVG: candle[i-2].low  > candle[i].high
        """
        fvg_bullish = []
        fvg_bearish = []

        for i in range(2, len(df)):
            bull = df["high"].iloc[i - 2] < df["low"].iloc[i]
            bear = df["low"].iloc[i - 2]  > df["high"].iloc[i]
            fvg_bullish.append(bull)
            fvg_bearish.append(bear)

        df["fvg_bullish"]   = [False, False] + fvg_bullish
        df["fvg_bearish"]   = [False, False] + fvg_bearish
        df["imbalance_zone"] = df["fvg_bullish"] | df["fvg_bearish"]
        return df


fe = FeatureEngineer()


# ── Routes ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "market-data"}


@app.post("/market/ingest")
async def ingest_candles(payload: dict):
    """
    Ingest OHLCV data and compute features.
    Called by data collectors (scheduled Celery tasks).
    """
    symbol    = payload.get("symbol", "").upper()
    timeframe = payload.get("timeframe", "1h")
    candles   = payload.get("candles", [])

    if not candles:
        raise HTTPException(status_code=400, detail="No candles provided")

    df = pd.DataFrame(candles, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms", utc=True)
    df = df.sort_values("time").drop_duplicates("time")

    # Store raw OHLCV
    async with AsyncSessionFactory() as session:
        for _, row in df.iterrows():
            await session.execute(
                text("""
                    INSERT INTO market_data (time, symbol, timeframe, open, high, low, close, volume)
                    VALUES (:t, :s, :tf, :o, :h, :l, :c, :v)
                    ON CONFLICT (time, symbol, timeframe) DO UPDATE
                    SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                        close=EXCLUDED.close, volume=EXCLUDED.volume
                """),
                {
                    "t": row["time"], "s": symbol, "tf": timeframe,
                    "o": float(row["open"]),   "h": float(row["high"]),
                    "l": float(row["low"]),    "c": float(row["close"]),
                    "v": float(row["volume"]),
                },
            )
        await session.commit()

    # Compute features
    df = fe.compute_all(df)

    # Store features
    # FIX #5: ON CONFLICT now updates ALL feature columns, not just 3.
    async with AsyncSessionFactory() as session:
        for _, row in df.dropna(subset=["ema_20"]).iterrows():
            await session.execute(
                text("""
                    INSERT INTO features (
                        time, symbol, timeframe,
                        ema_20, ema_50, ema_200, sma_20, sma_50,
                        rsi_14, macd_line, macd_signal, macd_hist,
                        atr_14, bb_upper, bb_middle, bb_lower, bb_width,
                        vwap, volume_sma_20,
                        structure, trend_direction,
                        support_level, resistance_level,
                        fvg_bullish, fvg_bearish, imbalance_zone
                    ) VALUES (
                        :t, :s, :tf,
                        :ema20, :ema50, :ema200, :sma20, :sma50,
                        :rsi, :macd_l, :macd_s, :macd_h,
                        :atr, :bb_u, :bb_m, :bb_l, :bb_w,
                        :vwap, :vol_sma,
                        :struct, :trend,
                        :sup, :res,
                        :fvg_b, :fvg_br, :imbalance
                    )
                    ON CONFLICT (time, symbol, timeframe) DO UPDATE SET
                        ema_20=EXCLUDED.ema_20,           ema_50=EXCLUDED.ema_50,
                        ema_200=EXCLUDED.ema_200,         sma_20=EXCLUDED.sma_20,
                        sma_50=EXCLUDED.sma_50,           rsi_14=EXCLUDED.rsi_14,
                        macd_line=EXCLUDED.macd_line,     macd_signal=EXCLUDED.macd_signal,
                        macd_hist=EXCLUDED.macd_hist,     atr_14=EXCLUDED.atr_14,
                        bb_upper=EXCLUDED.bb_upper,       bb_middle=EXCLUDED.bb_middle,
                        bb_lower=EXCLUDED.bb_lower,       bb_width=EXCLUDED.bb_width,
                        vwap=EXCLUDED.vwap,               volume_sma_20=EXCLUDED.volume_sma_20,
                        structure=EXCLUDED.structure,     trend_direction=EXCLUDED.trend_direction,
                        support_level=EXCLUDED.support_level,
                        resistance_level=EXCLUDED.resistance_level,
                        fvg_bullish=EXCLUDED.fvg_bullish,
                        fvg_bearish=EXCLUDED.fvg_bearish,
                        imbalance_zone=EXCLUDED.imbalance_zone
                """),
                {
                    "t": row["time"], "s": symbol, "tf": timeframe,
                    "ema20":  _safe(row, "ema_20"),   "ema50":  _safe(row, "ema_50"),
                    "ema200": _safe(row, "ema_200"),
                    "sma20":  _safe(row, "sma_20"),   "sma50":  _safe(row, "sma_50"),
                    "rsi":    _safe(row, "rsi_14"),
                    "macd_l": _safe(row, "macd_line"), "macd_s": _safe(row, "macd_signal"),
                    "macd_h": _safe(row, "macd_hist"),
                    "atr":    _safe(row, "atr_14"),
                    "bb_u":   _safe(row, "bb_upper"),  "bb_m":   _safe(row, "bb_middle"),
                    "bb_l":   _safe(row, "bb_lower"),  "bb_w":   _safe(row, "bb_width"),
                    "vwap":   _safe(row, "vwap"),      "vol_sma": _safe(row, "volume_sma_20"),
                    "struct": row.get("structure",       "UNKNOWN"),
                    "trend":  row.get("trend_direction", "SIDEWAYS"),
                    "sup":    _safe(row, "support_level"),
                    "res":    _safe(row, "resistance_level"),
                    "fvg_b":  bool(row.get("fvg_bullish",    False)),
                    "fvg_br": bool(row.get("fvg_bearish",    False)),
                    "imbalance": bool(row.get("imbalance_zone", False)),
                },
            )
        await session.commit()

    # Cache latest price
    last = df.iloc[-1]
    await redis_client.set(
        f"price:{symbol}:{timeframe}",
        str(float(last["close"])),
        ex=300,
    )

    logger.info("market.ingest.success", symbol=symbol, timeframe=timeframe, candles=len(df))
    return {"ingested": len(df), "symbol": symbol, "timeframe": timeframe}


def _safe(row, col, default=None):
    val = row.get(col, default)
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    return float(val)


@app.get("/market/candles/{symbol}")
async def get_candles(symbol: str, timeframe: str = "1h", limit: int = 100):
    symbol = symbol.upper()
    cache_key = f"candles:{symbol}:{timeframe}:{limit}"
    cached = await redis_client.get(cache_key)
    if cached:
        import json
        return json.loads(cached)

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("""
                SELECT time, open, high, low, close, volume
                FROM market_data
                WHERE symbol = :symbol AND timeframe = :tf
                ORDER BY time DESC LIMIT :limit
            """),
            {"symbol": symbol, "tf": timeframe, "limit": limit},
        )
        rows = [dict(r) for r in result.mappings().all()]

    import json
    await redis_client.set(cache_key, json.dumps(rows, default=str), ex=60)
    return rows


@app.get("/market/features/{symbol}")
async def get_features(symbol: str, timeframe: str = "1h", limit: int = 50):
    symbol = symbol.upper()
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("""
                SELECT * FROM features
                WHERE symbol = :symbol AND timeframe = :tf
                ORDER BY time DESC LIMIT :limit
            """),
            {"symbol": symbol, "tf": timeframe, "limit": limit},
        )
        return [dict(r) for r in result.mappings().all()]


@app.get("/market/price/{symbol}")
async def get_price(symbol: str, timeframe: str = "1h"):
    symbol = symbol.upper()
    price = await redis_client.get(f"price:{symbol}:{timeframe}")
    if price:
        return {"symbol": symbol, "price": float(price), "cached": True}

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT close FROM market_data WHERE symbol = :s AND timeframe = :tf ORDER BY time DESC LIMIT 1"),
            {"s": symbol, "tf": timeframe},
        )
        row = result.first()
        if not row:
            raise HTTPException(status_code=404, detail=f"No price data for {symbol}")
        return {"symbol": symbol, "price": float(row[0]), "cached": False}
