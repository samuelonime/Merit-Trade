"""
Merit-Trade AI — Risk Engine
HARD BLOCKER: No trade executes without passing all risk checks.
This is a deterministic rules-based system, NOT AI-controlled.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, "/app/../shared")

from core.config import settings
from core.redis_client import RedisClient

logger = structlog.get_logger()

engine = create_async_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: RedisClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    redis_client = await RedisClient.create()
    yield
    await redis_client.close()


app = FastAPI(title="Risk Engine", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Schemas ───────────────────────────────────────

class RiskCheckRequest(BaseModel):
    user_id: UUID
    account_id: UUID
    account_type: str               # forex | crypto
    symbol: str
    direction: str                  # BUY | SELL
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence_score: int           # 0-100
    lot_size: Optional[float] = None
    quantity: Optional[float] = None
    atr_value: Optional[float] = None
    current_spread_pips: Optional[float] = None
    account_balance: float
    account_equity: float

class RiskCheckResponse(BaseModel):
    approved: bool
    rejection_reasons: List[str] = []
    approved_lot_size: Optional[float] = None
    risk_amount: Optional[float] = None
    risk_pct: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    position_size_recommendation: Optional[float] = None
    warnings: List[str] = []


class RiskSettings(BaseModel):
    max_risk_per_trade: float = 0.02
    max_daily_loss: float = 0.05
    max_drawdown: float = 0.15
    min_confidence: int = 65
    max_open_trades: int = 5
    max_spread_pips: float = 3.0
    news_filter_enabled: bool = True
    high_impact_news_block: bool = True
    auto_trade_enabled: bool = False


# ── Risk Calculation Engine ────────────────────────

class RiskEngine:
    """
    Deterministic rule-based risk management.
    ALL rules must pass for trade approval.
    Rules are applied in sequence; first failure is reported.
    """

    def __init__(self, risk_settings: RiskSettings, redis: RedisClient):
        self.cfg = risk_settings
        self.redis = redis

    async def check_all(self, req: RiskCheckRequest) -> RiskCheckResponse:
        rejections: List[str] = []
        warnings: List[str] = []

        # ── Rule 1: Confidence threshold ──────────
        if req.confidence_score < self.cfg.min_confidence:
            rejections.append(
                f"Signal confidence {req.confidence_score}% is below minimum threshold {self.cfg.min_confidence}%"
            )

        # ── Rule 2: Spread check ──────────────────
        if req.current_spread_pips and req.current_spread_pips > self.cfg.max_spread_pips:
            rejections.append(
                f"Current spread {req.current_spread_pips:.2f} pips exceeds maximum {self.cfg.max_spread_pips:.2f} pips"
            )

        # ── Rule 3: Daily loss limit ──────────────
        daily_loss_pct = await self._get_daily_loss_pct(str(req.user_id))
        if daily_loss_pct >= self.cfg.max_daily_loss:
            rejections.append(
                f"Daily loss limit reached: {daily_loss_pct*100:.2f}% of {self.cfg.max_daily_loss*100:.2f}% max"
            )

        # ── Rule 4: Max drawdown check ────────────
        drawdown = self._calc_drawdown(req.account_balance, req.account_equity)
        if drawdown >= self.cfg.max_drawdown:
            rejections.append(
                f"Maximum drawdown exceeded: {drawdown*100:.2f}% of {self.cfg.max_drawdown*100:.2f}% limit"
            )

        # ── Rule 5: Max open trades ───────────────
        open_trades = await self._get_open_trades_count(str(req.user_id))
        if open_trades >= self.cfg.max_open_trades:
            rejections.append(
                f"Maximum concurrent trades reached: {open_trades}/{self.cfg.max_open_trades}"
            )

        # ── Rule 6: News filter ───────────────────
        if self.cfg.news_filter_enabled and self.cfg.high_impact_news_block:
            high_impact_news = await self._check_news_events(req.symbol)
            if high_impact_news:
                rejections.append(
                    f"High-impact news event within 30 minutes for {req.symbol}: {high_impact_news}"
                )

        # ── Rule 7: Stop Loss validation ──────────
        sl_check = self._validate_sl_tp(req)
        if sl_check:
            rejections.append(sl_check)

        # ── Rule 8: Risk/Reward ratio ─────────────
        rr_ratio = self._calc_risk_reward(req)
        if rr_ratio < 1.5:
            warnings.append(f"Low risk/reward ratio: {rr_ratio:.2f} (recommended: ≥1.5)")

        # ── Compute position sizing ───────────────
        approved_lot, risk_amount, risk_pct = self._compute_position_size(req)

        if risk_pct > self.cfg.max_risk_per_trade:
            rejections.append(
                f"Calculated risk {risk_pct*100:.2f}% exceeds max per-trade risk {self.cfg.max_risk_per_trade*100:.2f}%"
            )

        # ── Liquidity check ───────────────────────
        if approved_lot < 0.01:
            warnings.append("Very small position size: account may be too small for this trade")

        approved = len(rejections) == 0

        if approved:
            logger.info(
                "risk.check.approved",
                user_id=str(req.user_id),
                symbol=req.symbol,
                lot_size=approved_lot,
                risk_pct=risk_pct,
                rr_ratio=rr_ratio,
            )
        else:
            logger.warning(
                "risk.check.rejected",
                user_id=str(req.user_id),
                symbol=req.symbol,
                reasons=rejections,
            )

        return RiskCheckResponse(
            approved=approved,
            rejection_reasons=rejections,
            approved_lot_size=approved_lot if approved else None,
            risk_amount=risk_amount if approved else None,
            risk_pct=risk_pct if approved else None,
            risk_reward_ratio=rr_ratio,
            position_size_recommendation=approved_lot,
            warnings=warnings,
        )

    def _validate_sl_tp(self, req: RiskCheckRequest) -> str | None:
        """Ensure SL and TP are on correct side of entry."""
        if req.direction == "BUY":
            if req.stop_loss >= req.entry_price:
                return f"BUY: Stop loss ({req.stop_loss}) must be below entry ({req.entry_price})"
            if req.take_profit <= req.entry_price:
                return f"BUY: Take profit ({req.take_profit}) must be above entry ({req.entry_price})"
        elif req.direction == "SELL":
            if req.stop_loss <= req.entry_price:
                return f"SELL: Stop loss ({req.stop_loss}) must be above entry ({req.entry_price})"
            if req.take_profit >= req.entry_price:
                return f"SELL: Take profit ({req.take_profit}) must be below entry ({req.entry_price})"
        return None

    def _calc_risk_reward(self, req: RiskCheckRequest) -> float:
        sl_distance = abs(req.entry_price - req.stop_loss)
        tp_distance = abs(req.take_profit - req.entry_price)
        if sl_distance == 0:
            return 0.0
        return tp_distance / sl_distance

    def _calc_drawdown(self, balance: float, equity: float) -> float:
        if balance == 0:
            return 0.0
        return max(0.0, (balance - equity) / balance)

    def _compute_position_size(self, req: RiskCheckRequest) -> tuple[float, float, float]:
        """
        ATR-based position sizing.
        risk_amount = account_equity * max_risk_per_trade
        lot_size = risk_amount / (SL_distance_in_pips * pip_value)
        Simplified: use SL distance as risk measure.
        """
        risk_amount = req.account_equity * self.cfg.max_risk_per_trade
        sl_distance = abs(req.entry_price - req.stop_loss)
        if sl_distance == 0:
            return 0.01, 0.0, 0.0
        # Simplified lot size (forex standard lot = 100,000 units)
        # For crypto, this is quantity directly
        if req.account_type == "forex":
            pip_value = 0.0001 * 100000  # approximate for EURUSD-type pairs
            sl_pips = sl_distance / 0.0001
            lot_size = risk_amount / (sl_pips * 10)  # $10 per pip per lot
            lot_size = round(max(0.01, min(lot_size, 100.0)), 2)
        else:
            # Crypto: quantity in base asset
            lot_size = risk_amount / sl_distance
            lot_size = round(lot_size, 6)

        actual_risk = lot_size * sl_distance * (100000 if req.account_type == "forex" else 1)
        risk_pct = actual_risk / req.account_equity if req.account_equity > 0 else 0.0
        return lot_size, risk_amount, risk_pct

    async def _get_daily_loss_pct(self, user_id: str) -> float:
        """Get today's realized P&L from Redis cache."""
        val = await self.redis.get(f"daily_loss:{user_id}:{datetime.now(timezone.utc).date()}")
        return float(val) if val else 0.0

    async def _get_open_trades_count(self, user_id: str) -> int:
        val = await self.redis.get(f"open_trades:{user_id}")
        return int(val) if val else 0

    async def _check_news_events(self, symbol: str) -> str | None:
        """Check Redis for upcoming high-impact news events for symbol's currencies."""
        currencies = self._extract_currencies(symbol)
        for ccy in currencies:
            event = await self.redis.get(f"news:high_impact:{ccy}")
            if event:
                return event.decode() if isinstance(event, bytes) else event
        return None

    def _extract_currencies(self, symbol: str) -> List[str]:
        """Extract currency codes from forex symbol. e.g. EURUSD -> [EUR, USD]"""
        symbol = symbol.upper().replace("/", "")
        if len(symbol) == 6:
            return [symbol[:3], symbol[3:]]
        return [symbol[:3]]


# ── Routes ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "risk-engine"}


@app.post("/risk/check", response_model=RiskCheckResponse)
async def check_risk(req: RiskCheckRequest, request: Request):
    """
    Primary risk gate. Called by execution engine before every trade.
    Returns approval decision with reasoning.
    """
    user_id = str(req.user_id)

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM risk_settings WHERE user_id = :uid"),
            {"uid": user_id},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Risk settings not found")
        cfg = RiskSettings(**dict(row))

    engine = RiskEngine(cfg, redis_client)
    return await engine.check_all(req)


@app.get("/risk/settings/{user_id}")
async def get_settings(user_id: UUID, request: Request):
    calling_user = request.headers.get("X-User-ID")
    if calling_user != str(user_id) and not request.headers.get("X-User-Admin") == "True":
        raise HTTPException(status_code=403, detail="Access denied")

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM risk_settings WHERE user_id = :uid"),
            {"uid": str(user_id)},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Risk settings not found")
        return dict(row)


@app.put("/risk/settings/{user_id}")
async def update_settings(user_id: UUID, settings_update: dict, request: Request):
    calling_user = request.headers.get("X-User-ID")
    if calling_user != str(user_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate ranges
    if "max_risk_per_trade" in settings_update:
        val = float(settings_update["max_risk_per_trade"])
        if val < 0.001 or val > 0.05:
            raise HTTPException(status_code=400, detail="max_risk_per_trade must be between 0.1% and 5%")

    if "max_daily_loss" in settings_update:
        val = float(settings_update["max_daily_loss"])
        if val < 0.01 or val > 0.20:
            raise HTTPException(status_code=400, detail="max_daily_loss must be between 1% and 20%")

    async with AsyncSessionFactory() as session:
        set_clauses = ", ".join(f"{k} = :{k}" for k in settings_update.keys() if k != "user_id")
        await session.execute(
            text(f"UPDATE risk_settings SET {set_clauses}, updated_at = NOW() WHERE user_id = :user_id"),
            {**settings_update, "user_id": str(user_id)},
        )
        await session.commit()

    # Invalidate cached settings
    await redis_client.delete(f"risk_settings:{user_id}")
    return {"message": "Risk settings updated"}


@app.post("/risk/daily-loss/record")
async def record_daily_loss(user_id: UUID, loss_pct: float):
    """Called by execution engine when a trade closes in loss."""
    key = f"daily_loss:{user_id}:{datetime.now(timezone.utc).date()}"
    current = await redis_client.get(key)
    current_val = float(current) if current else 0.0
    new_val = current_val + loss_pct

    # Set with expiry at end of trading day
    seconds_till_midnight = (
        datetime.now(timezone.utc).replace(hour=23, minute=59, second=59) -
        datetime.now(timezone.utc)
    ).seconds
    await redis_client.set(key, str(new_val), ex=seconds_till_midnight)
    return {"daily_loss_pct": new_val}
