"""
Merit-Trade AI — Execution Engine
Handles trade execution for both Forex (MT5) and Crypto (CCXT).
ALL trades must pass the Risk Engine before execution.
"""
import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID, uuid4

import ccxt.async_support as ccxt
import httpx
import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, "/app/../shared")

from core.config import settings
from core.security import decrypt_value
from core.redis_client import RedisClient
from core.exceptions import RiskEngineRejection, BrokerConnectionError

logger = structlog.get_logger()

engine = create_async_engine(settings.DATABASE_URL, pool_size=10)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: RedisClient | None = None
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, http_client
    redis_client = await RedisClient.create()
    http_client = httpx.AsyncClient(timeout=30.0)
    yield
    await redis_client.close()
    await http_client.aclose()


app = FastAPI(title="Execution Engine", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Schemas ───────────────────────────────────────

class ExecuteTradeRequest(BaseModel):
    user_id: UUID
    signal_id: Optional[UUID] = None
    account_id: UUID
    account_type: str               # forex | crypto
    symbol: str
    direction: str                  # BUY | SELL
    order_type: str = "market"
    lot_size: Optional[float] = None
    quantity: Optional[float] = None
    entry_price: Optional[float] = None
    stop_loss: float
    take_profit: float
    confidence_score: int
    atr_value: Optional[float] = None
    current_spread_pips: Optional[float] = None


class TradeUpdateRequest(BaseModel):
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


# ── Risk Gate ─────────────────────────────────────

async def run_risk_check(req: ExecuteTradeRequest, balance: float, equity: float) -> dict:
    """
    Call Risk Engine service. Trade CANNOT execute if rejected.
    This is a HARD BLOCK - no bypassing allowed.
    """
    risk_payload = {
        "user_id": str(req.user_id),
        "account_id": str(req.account_id),
        "account_type": req.account_type,
        "symbol": req.symbol,
        "direction": req.direction,
        "entry_price": req.entry_price or 0,
        "stop_loss": req.stop_loss,
        "take_profit": req.take_profit,
        "confidence_score": req.confidence_score,
        "lot_size": req.lot_size,
        "quantity": req.quantity,
        "atr_value": req.atr_value,
        "current_spread_pips": req.current_spread_pips,
        "account_balance": balance,
        "account_equity": equity,
    }

    resp = await http_client.post(
        f"{settings.RISK_ENGINE_URL}/risk/check",
        json=risk_payload,
    )

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Risk engine unavailable")

    risk_result = resp.json()

    if not risk_result["approved"]:
        reasons = risk_result.get("rejection_reasons", [])
        logger.warning("execution.risk_rejected", user_id=str(req.user_id), reasons=reasons)
        raise HTTPException(
            status_code=400,
            detail={
                "error": "RISK_REJECTED",
                "message": "Trade rejected by risk engine",
                "reasons": reasons,
            },
        )

    return risk_result


# ── MT5 Forex Execution ───────────────────────────

class MT5Executor:
    """
    MetaTrader 5 execution interface.
    Note: MT5 Python library only runs on Windows natively.
    In Linux containers, use MT5 bridge via socket or REST bridge.
    """

    def __init__(self, account_number: int, password: str, server: str):
        self.account_number = account_number
        self.password = password
        self.server = server
        self._connected = False

    async def connect(self) -> bool:
        """Connect to MT5 terminal via bridge."""
        # In production: connect to MT5 bridge service (e.g., MetaApi or custom bridge)
        # mt5.initialize() is blocking and Windows-only, so use async bridge
        logger.info("mt5.connecting", account=self.account_number, server=self.server)
        self._connected = True  # Replace with actual connection
        return True

    async def get_account_info(self) -> dict:
        """Fetch account balance, equity, margin."""
        # Replace with actual MT5 bridge call
        return {
            "balance": 10000.0,
            "equity": 9850.0,
            "margin": 150.0,
            "free_margin": 9700.0,
            "currency": "USD",
            "leverage": 100,
        }

    async def open_position(
        self,
        symbol: str,
        direction: str,
        lot_size: float,
        stop_loss: float,
        take_profit: float,
        order_type: str = "market",
        price: Optional[float] = None,
        magic: int = 20250101,
        comment: str = "MeritTradeAI",
    ) -> dict:
        """
        Open a position via MT5.
        Returns broker response with ticket number.
        """
        start_time = time.time()

        # MT5 action types
        trade_action = "TRADE_ACTION_DEAL" if order_type == "market" else "TRADE_ACTION_PENDING"
        order_type_mt5 = {
            ("BUY", "market"): "ORDER_TYPE_BUY",
            ("SELL", "market"): "ORDER_TYPE_SELL",
            ("BUY", "limit"): "ORDER_TYPE_BUY_LIMIT",
            ("SELL", "limit"): "ORDER_TYPE_SELL_LIMIT",
        }.get((direction, order_type), "ORDER_TYPE_BUY")

        request = {
            "action": trade_action,
            "symbol": symbol,
            "volume": lot_size,
            "type": order_type_mt5,
            "price": price or 0,  # 0 for market orders
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 20,       # max slippage in points
            "magic": magic,
            "comment": comment,
            "type_time": "ORDER_TIME_GTC",
            "type_filling": "ORDER_FILLING_FOK",
        }

        # TODO: Replace with actual MT5 bridge call
        # result = mt5.order_send(request)
        # For now, return a mock successful response
        latency_ms = int((time.time() - start_time) * 1000)
        ticket = int(time.time() * 1000) % 10000000

        logger.info(
            "mt5.order_sent",
            symbol=symbol, direction=direction,
            lot_size=lot_size, ticket=ticket,
        )

        return {
            "retcode": 10009,   # TRADE_RETCODE_DONE
            "deal": ticket,
            "order": ticket,
            "volume": lot_size,
            "price": price or 0,
            "comment": "Request executed",
            "latency_ms": latency_ms,
        }

    async def close_position(self, ticket: int, symbol: str, direction: str, lot_size: float) -> dict:
        """Close an existing position by ticket."""
        # Opposite direction to close
        close_type = "SELL" if direction == "BUY" else "BUY"
        return await self.open_position(symbol, close_type, lot_size, 0, 0)

    async def modify_position(self, ticket: int, stop_loss: float, take_profit: float) -> dict:
        """Modify SL/TP of an existing position."""
        # TODO: MT5 bridge call
        return {"retcode": 10009, "comment": "Modified successfully"}

    async def disconnect(self):
        self._connected = False


# ── CCXT Crypto Execution ─────────────────────────

class CCXTExecutor:
    """
    Unified crypto exchange execution via CCXT.
    Supports any CCXT-compatible exchange.
    """

    def __init__(self, exchange_id: str, api_key: str, api_secret: str, passphrase: Optional[str] = None, testnet: bool = True):
        exchange_class = getattr(ccxt, exchange_id, None)
        if not exchange_class:
            raise ValueError(f"Unsupported exchange: {exchange_id}")

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if passphrase:
            config["password"] = passphrase
        if testnet:
            config["sandbox"] = True

        self.exchange: ccxt.Exchange = exchange_class(config)
        self.testnet = testnet

    async def get_account_info(self) -> dict:
        balance = await self.exchange.fetch_balance()
        return {
            "balance": balance.get("total", {}).get("USDT", 0),
            "equity": balance.get("total", {}).get("USDT", 0),
            "free": balance.get("free", {}),
            "used": balance.get("used", {}),
        }

    async def open_position(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        order_type: str = "market",
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        side = direction.lower()  # buy | sell
        max_retries = 3

        for attempt in range(max_retries):
            try:
                if order_type == "market":
                    order = await self.exchange.create_market_order(symbol, side, quantity)
                elif order_type == "limit" and price:
                    order = await self.exchange.create_limit_order(symbol, side, quantity, price)
                else:
                    raise ValueError(f"Unsupported order type: {order_type}")

                logger.info(
                    "ccxt.order_placed",
                    exchange=self.exchange.id, symbol=symbol,
                    side=side, quantity=quantity, order_id=order["id"],
                )
                return order

            except ccxt.NetworkError as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning("ccxt.retry", attempt=attempt+1, error=str(e), wait=wait)
                    await asyncio.sleep(wait)
                else:
                    raise BrokerConnectionError(self.exchange.id, str(e))
            except ccxt.ExchangeError as e:
                raise BrokerConnectionError(self.exchange.id, str(e))

    async def close_position(self, symbol: str, direction: str, quantity: float) -> dict:
        close_side = "sell" if direction.upper() == "BUY" else "buy"
        return await self.exchange.create_market_order(symbol, close_side, quantity)

    async def close(self):
        await self.exchange.close()


# ── Credential Loader ─────────────────────────────

async def load_forex_credentials(account_id: UUID) -> dict:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM accounts_forex WHERE id = :id AND is_active = true"),
            {"id": str(account_id)},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Forex account not found")
        row = dict(row)
        row["password"] = decrypt_value(bytes(row["encrypted_password"]))
        return row


async def load_crypto_credentials(account_id: UUID) -> dict:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM accounts_crypto WHERE id = :id AND is_active = true"),
            {"id": str(account_id)},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="Crypto account not found")
        row = dict(row)
        row["api_key"] = decrypt_value(bytes(row["encrypted_api_key"]))
        row["api_secret"] = decrypt_value(bytes(row["encrypted_api_secret"]))
        if row.get("encrypted_passphrase"):
            row["passphrase"] = decrypt_value(bytes(row["encrypted_passphrase"]))
        return row


# ── Routes ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "execution-engine"}


@app.post("/execute/trade")
async def execute_trade(req: ExecuteTradeRequest, request: Request):
    """
    Execute a trade after passing all risk checks.
    This is the ONLY entry point for trade execution.
    """
    user_id = str(req.user_id)

    # ── Step 1: Load account and get balance ──────
    if req.account_type == "forex":
        creds = await load_forex_credentials(req.account_id)
        executor = MT5Executor(
            creds["account_number"], creds["password"], creds["server"]
        )
        await executor.connect()
        account_info = await executor.get_account_info()
    else:
        creds = await load_crypto_credentials(req.account_id)
        executor = CCXTExecutor(
            exchange_id=creds["exchange"],
            api_key=creds["api_key"],
            api_secret=creds["api_secret"],
            passphrase=creds.get("passphrase"),
            testnet=creds.get("is_testnet", True),
        )
        account_info = await executor.get_account_info()

    balance = account_info["balance"]
    equity = account_info["equity"]

    # ── Step 2: MANDATORY risk check ──────────────
    risk_result = await run_risk_check(req, balance, equity)

    approved_lot = risk_result.get("approved_lot_size")
    risk_amount = risk_result.get("risk_amount")
    risk_pct = risk_result.get("risk_pct")

    # ── Step 3: Create trade record (pending) ─────
    trade_id = uuid4()
    async with AsyncSessionFactory() as session:
        await session.execute(
            text("""
                INSERT INTO trades (
                    id, user_id, signal_id, account_id, account_type,
                    symbol, direction, order_type, status,
                    lot_size, stop_loss, take_profit,
                    risk_amount, risk_pct
                ) VALUES (
                    :id, :user_id, :signal_id, :account_id, :account_type,
                    :symbol, :direction, :order_type, 'pending',
                    :lot_size, :sl, :tp, :risk_amount, :risk_pct
                )
            """),
            {
                "id": str(trade_id), "user_id": user_id,
                "signal_id": str(req.signal_id) if req.signal_id else None,
                "account_id": str(req.account_id), "account_type": req.account_type,
                "symbol": req.symbol, "direction": req.direction,
                "order_type": req.order_type,
                "lot_size": approved_lot, "sl": req.stop_loss, "tp": req.take_profit,
                "risk_amount": risk_amount, "risk_pct": risk_pct,
            },
        )
        await session.commit()

    # ── Step 4: Execute with broker ───────────────
    broker_response = None
    broker_ticket = None
    error_message = None
    executed_price = None

    try:
        if req.account_type == "forex":
            broker_response = await executor.open_position(
                symbol=req.symbol,
                direction=req.direction,
                lot_size=approved_lot,
                stop_loss=req.stop_loss,
                take_profit=req.take_profit,
                order_type=req.order_type,
            )
            broker_ticket = broker_response.get("order")
            executed_price = broker_response.get("price", req.entry_price)
        else:
            qty = req.quantity or (risk_amount / req.stop_loss if req.stop_loss else 0)
            broker_response = await executor.open_position(
                symbol=req.symbol,
                direction=req.direction,
                quantity=qty,
                order_type=req.order_type,
                price=req.entry_price,
                stop_loss=req.stop_loss,
                take_profit=req.take_profit,
            )
            broker_ticket = broker_response.get("id")
            executed_price = float(broker_response.get("average", req.entry_price or 0))

        trade_status = "open"
        logger.info("execution.success", trade_id=str(trade_id), ticket=broker_ticket)

    except Exception as e:
        trade_status = "cancelled"
        error_message = str(e)
        logger.error("execution.failed", trade_id=str(trade_id), error=error_message)

    # ── Step 5: Update trade record ───────────────
    async with AsyncSessionFactory() as session:
        await session.execute(
            text("""
                UPDATE trades SET
                    status = :status, broker_ticket = :ticket,
                    entry_price = :entry, opened_at = CASE WHEN :status = 'open' THEN NOW() ELSE NULL END
                WHERE id = :id
            """),
            {
                "id": str(trade_id), "status": trade_status,
                "ticket": broker_ticket, "entry": executed_price,
            },
        )

        # Record execution audit
        await session.execute(
            text("""
                INSERT INTO executions (
                    trade_id, user_id, action, risk_approved,
                    requested_price, executed_price, broker_response, error_message
                ) VALUES (
                    :trade_id, :user_id, 'open', :approved,
                    :requested, :executed, :response, :error
                )
            """),
            {
                "trade_id": str(trade_id), "user_id": user_id,
                "approved": True,
                "requested": req.entry_price, "executed": executed_price,
                "response": json.dumps(broker_response) if broker_response else None,
                "error": error_message,
            },
        )
        await session.commit()

    # Update open trades counter in Redis
    if trade_status == "open":
        await redis_client.incr(f"open_trades:{user_id}")

    # Publish to WebSocket channel
    await redis_client.publish(
        "channel:trades",
        json.dumps({
            "type": "trade_opened" if trade_status == "open" else "trade_failed",
            "user_id": user_id,
            "trade_id": str(trade_id),
            "symbol": req.symbol,
            "direction": req.direction,
            "status": trade_status,
            "entry_price": executed_price,
        }),
    )

    if trade_status == "cancelled" and error_message:
        raise HTTPException(status_code=500, detail=f"Execution failed: {error_message}")

    return {
        "trade_id": str(trade_id),
        "status": trade_status,
        "broker_ticket": broker_ticket,
        "executed_price": executed_price,
        "lot_size": approved_lot,
        "risk_amount": risk_amount,
        "risk_pct": risk_pct,
        "warnings": risk_result.get("warnings", []),
    }


@app.post("/execute/close/{trade_id}")
async def close_trade(trade_id: UUID, request: Request):
    user_id = request.headers.get("X-User-ID")

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM trades WHERE id = :id AND user_id = :uid AND status = 'open'"),
            {"id": str(trade_id), "uid": user_id},
        )
        trade = result.mappings().first()
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found or not open")
        trade = dict(trade)

    if trade["account_type"] == "forex":
        creds = await load_forex_credentials(trade["account_id"])
        executor = MT5Executor(creds["account_number"], creds["password"], creds["server"])
        await executor.connect()
        broker_resp = await executor.close_position(
            trade["broker_ticket"], trade["symbol"], trade["direction"], trade["lot_size"]
        )
    else:
        creds = await load_crypto_credentials(trade["account_id"])
        executor = CCXTExecutor(
            creds["exchange"], creds["api_key"], creds["api_secret"],
            creds.get("passphrase"), creds.get("is_testnet", True),
        )
        broker_resp = await executor.close_position(
            trade["symbol"], trade["direction"], trade.get("quantity", 0)
        )

    close_price = float(broker_resp.get("price", 0) or broker_resp.get("average", 0) or 0)
    pnl = (close_price - (trade["entry_price"] or 0)) * (1 if trade["direction"] == "BUY" else -1)

    async with AsyncSessionFactory() as session:
        await session.execute(
            text("""
                UPDATE trades SET status = 'closed', close_price = :close_price,
                    realized_pnl = :pnl, closed_at = NOW()
                WHERE id = :id
            """),
            {"id": str(trade_id), "close_price": close_price, "pnl": pnl},
        )
        await session.commit()

    # Update open trades counter
    current = await redis_client.get(f"open_trades:{user_id}")
    if current and int(current) > 0:
        await redis_client.decr(f"open_trades:{user_id}")

    # Record loss for daily limit tracking
    if pnl < 0:
        balance = trade.get("risk_amount", 0) / trade.get("risk_pct", 0.02)
        loss_pct = abs(pnl) / balance if balance > 0 else 0
        await http_client.post(
            f"{settings.RISK_ENGINE_URL}/risk/daily-loss/record",
            params={"user_id": user_id, "loss_pct": loss_pct},
        )

    return {
        "trade_id": str(trade_id),
        "status": "closed",
        "close_price": close_price,
        "realized_pnl": pnl,
    }


@app.get("/execute/trades")
async def list_trades(request: Request, status: Optional[str] = None):
    user_id = request.headers.get("X-User-ID")
    async with AsyncSessionFactory() as session:
        where = "WHERE user_id = :uid"
        params = {"uid": user_id}
        if status:
            where += " AND status = :status"
            params["status"] = status

        result = await session.execute(
            text(f"SELECT * FROM trades {where} ORDER BY created_at DESC LIMIT 50"),
            params,
        )
        return [dict(r) for r in result.mappings().all()]
