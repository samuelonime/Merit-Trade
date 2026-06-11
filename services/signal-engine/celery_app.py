"""
Merit-Trade AI — Celery Task Queue
Scheduled and async tasks for market data collection, signal generation,
and system maintenance.
"""
from celery import Celery
from celery.schedules import crontab
import httpx
import asyncio
import structlog

import sys
sys.path.insert(0, "/app/../shared")

from core.config import settings

logger = structlog.get_logger()

app = Celery("merit_trade")
app.config_from_object({
    "broker_url": settings.CELERY_BROKER_URL,
    "result_backend": settings.CELERY_RESULT_BACKEND,
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "UTC",
    "enable_utc": True,
    "worker_prefetch_multiplier": 1,
    "task_acks_late": True,
})

# ── Supported pairs & timeframes ──────────────────────────────────
#
# 8 pairs across forex, crypto, gold, and indices
# 4 timeframes: 15m, 1h, 4h, 1d
#
# Plan access matrix:
#   free (trial 7 days) → 2 pairs (EURUSD, BTCUSDT),  1 timeframe (1h)
#   pro                 → 8 pairs, 3 timeframes (15m, 1h, 4h)
#   enterprise          → 8 pairs, all 4 timeframes (15m, 1h, 4h, 1d)

ALL_PAIRS = [
    # Forex majors
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    # Commodities
    "XAUUSD",   # Gold
    # Crypto
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
]

FREE_PAIRS        = ["EURUSD", "BTCUSDT"]
PRO_PAIRS         = ALL_PAIRS
ENTERPRISE_PAIRS  = ALL_PAIRS

ALL_TIMEFRAMES        = ["15m", "1h", "4h", "1d"]
FREE_TIMEFRAMES       = ["1h"]
PRO_TIMEFRAMES        = ["15m", "1h", "4h"]
ENTERPRISE_TIMEFRAMES = ["15m", "1h", "4h", "1d"]

# Crypto symbols that use Binance API (no auth required for OHLCV)
CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}

# ── Beat schedule ─────────────────────────────────────────────────

app.conf.beat_schedule = {

    # ── 15-minute data & signals ──────────────────
    # FIX #6: Use crontab(minute="0,15,30,45") so collection is always pinned
    # to bar-close times, regardless of when the worker was started.
    # The old schedule: 900.0 fired 900s after the worker last ran, causing
    # drift that made the signal generator run before fresh data arrived.
    "collect-15m-data": {
        "task": "celery_app.collect_market_data",
        "schedule": crontab(minute="0,15,30,45"),
        "args": (ALL_PAIRS, "15m"),
    },
    "generate-signals-15m": {
        "task": "celery_app.generate_signals_batch",
        "schedule": crontab(minute="3,18,33,48"),  # 3 mins after each 15m bar closes
        "args": (ALL_PAIRS, "15m"),
    },

    # ── 1-hour data & signals ─────────────────────
    "collect-1h-data": {
        "task": "celery_app.collect_market_data",
        "schedule": crontab(minute=0),
        "args": (ALL_PAIRS, "1h"),
    },
    "generate-signals-1h": {
        "task": "celery_app.generate_signals_batch",
        "schedule": crontab(minute=5),  # 5 mins after top of hour
        "args": (ALL_PAIRS, "1h"),
    },

    # ── 4-hour data & signals ─────────────────────
    "collect-4h-data": {
        "task": "celery_app.collect_market_data",
        "schedule": crontab(minute=0, hour="0,4,8,12,16,20"),
        "args": (ALL_PAIRS, "4h"),
    },
    "generate-signals-4h": {
        "task": "celery_app.generate_signals_batch",
        "schedule": crontab(minute=10, hour="0,4,8,12,16,20"),  # 10 mins after 4h close
        "args": (ALL_PAIRS, "4h"),
    },

    # ── Daily data & signals ──────────────────────
    "collect-1d-data": {
        "task": "celery_app.collect_market_data",
        "schedule": crontab(hour=0, minute=15),   # 00:15 UTC daily
        "args": (ALL_PAIRS, "1d"),
    },
    "generate-signals-1d": {
        "task": "celery_app.generate_signals_batch",
        "schedule": crontab(hour=0, minute=30),   # 00:30 UTC daily
        "args": (ALL_PAIRS, "1d"),
    },

    # ── Housekeeping ──────────────────────────────
    "collect-economic-calendar": {
        "task": "celery_app.collect_economic_calendar",
        "schedule": crontab(hour=0, minute=45),
    },
    "sync-trade-pnl": {
        "task": "celery_app.sync_open_trades",
        "schedule": 60.0,  # every minute
    },
    "cleanup-expired-signals": {
        "task": "celery_app.cleanup_expired_signals",
        "schedule": crontab(hour=2, minute=0),
    },
    # ── Trial expiry check ─────────────────────────
    "expire-free-trials": {
        "task": "celery_app.expire_free_trials",
        "schedule": crontab(hour="*", minute=0),   # every hour
    },
}


def run_async(coro):
    """Helper to run async code in Celery task."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Shared DB engine for Celery tasks ─────────────────────────────
# FIX #14: Use a single module-level engine per worker process instead of
# creating a new engine on every task invocation. Creating engines is
# expensive and can exhaust Postgres connection slots under load.
# Each task still opens its own short-lived AsyncSession.

def _get_celery_db():
    """Lazily create and return a shared async engine for this worker process."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    if not hasattr(_get_celery_db, "_engine"):
        _get_celery_db._engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=3,
            max_overflow=5,
        )
        _get_celery_db._Session = sessionmaker(
            _get_celery_db._engine, class_=AsyncSession, expire_on_commit=False
        )
    return _get_celery_db._engine, _get_celery_db._Session


# ── Market data collection ────────────────────────────────────────

@app.task(bind=True, max_retries=3, default_retry_delay=30)
def collect_market_data(self, symbols: list, timeframe: str):
    """Fetch and ingest OHLCV data for all supported symbols."""
    async def _run():
        async with httpx.AsyncClient(timeout=30) as client:
            for symbol in symbols:
                try:
                    candles = await fetch_ohlcv_from_provider(client, symbol, timeframe)
                    if candles:
                        await client.post(
                            f"{settings.MARKET_DATA_URL}/market/ingest",
                            json={"symbol": symbol, "timeframe": timeframe, "candles": candles},
                        )
                        logger.info("celery.data_collected", symbol=symbol, tf=timeframe, count=len(candles))
                except Exception as e:
                    logger.error("celery.data_collect_failed", symbol=symbol, tf=timeframe, error=str(e))
    try:
        run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


async def fetch_ohlcv_from_provider(client: httpx.AsyncClient, symbol: str, timeframe: str) -> list:
    """
    Fetch OHLCV candles from the appropriate provider.
    Crypto  → Binance public API (no auth needed)
    Forex   → Twelve Data API (set TWELVE_DATA_API_KEY in .env)
    Gold    → Twelve Data API (XAUUSD supported)
    Returns list of [timestamp_ms, open, high, low, close, volume]
    """
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
        # Forex + XAUUSD via Twelve Data
        api_key = getattr(settings, "TWELVE_DATA_API_KEY", None)
        if not api_key:
            logger.warning("celery.twelve_data_key_missing", symbol=symbol)
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
                logger.error("celery.twelve_data_error", symbol=symbol, msg=data.get("message"))
                return []
            values = data.get("values", [])
            # Twelve Data returns newest first — reverse to chronological
            values.reverse()
            result = []
            for row in values:
                try:
                    from datetime import datetime
                    ts = int(datetime.fromisoformat(row["datetime"]).timestamp() * 1000)
                    result.append([
                        ts,
                        float(row["open"]),
                        float(row["high"]),
                        float(row["low"]),
                        float(row["close"]),
                        float(row.get("volume", 0)),
                    ])
                except Exception:
                    continue
            return result

    return []


# ── Signal generation ─────────────────────────────────────────────

@app.task(bind=True, max_retries=2)
def generate_signals_batch(self, symbols: list, timeframe: str):
    """Generate signals for all symbols on a given timeframe."""
    async def _run():
        internal_token = getattr(settings, "INTERNAL_SERVICE_TOKEN", "")
        headers = {"X-Internal-Token": internal_token} if internal_token else {}
        async with httpx.AsyncClient(timeout=60, headers=headers) as client:
            for symbol in symbols:
                try:
                    resp = await client.post(
                        f"{settings.SIGNAL_ENGINE_URL}/signals/generate",
                        json={"symbol": symbol, "timeframe": timeframe},
                    )
                    if resp.status_code == 200:
                        signal = resp.json()
                        logger.info(
                            "celery.signal_generated",
                            symbol=symbol, timeframe=timeframe,
                            direction=signal.get("direction"),
                            confidence=signal.get("confidence_score"),
                        )
                    elif resp.status_code == 204:
                        logger.info("celery.signal_no_trade", symbol=symbol, timeframe=timeframe)
                except Exception as e:
                    logger.error("celery.signal_failed", symbol=symbol, timeframe=timeframe, error=str(e))
    try:
        run_async(_run())
    except Exception as exc:
        raise self.retry(exc=exc)


# ── Free trial expiry ─────────────────────────────────────────────

@app.task
def expire_free_trials():
    """
    Downgrade free users whose 7-day trial has expired to a locked state.
    Sets plan to 'expired_free'. Runs every hour.
    """
    async def _run():
        # FIX #14: use shared engine instead of creating a new one per call
        _, Session = _get_celery_db()

        async with Session() as session:
            result = await session.execute(text("""
                UPDATE users
                SET plan = 'expired_free', updated_at = NOW()
                WHERE plan = 'free'
                  AND created_at < NOW() - INTERVAL '7 days'
                  AND id NOT IN (
                      SELECT user_id FROM subscriptions
                      WHERE status = 'active'
                        AND current_period_end > NOW()
                  )
                RETURNING id, email
            """))
            expired = result.mappings().all()
            await session.commit()

            if expired:
                logger.info("celery.trials_expired", count=len(expired),
                            users=[str(u["id"]) for u in expired])

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
                            logger.error("celery.trial_notify_failed",
                                         user_id=str(user["id"]), error=str(e))

    run_async(_run())


# ── Economic calendar ─────────────────────────────────────────────

@app.task
def collect_economic_calendar():
    """
    Fetch high-impact economic events and cache in Redis for risk engine.

    FIX #10: Was a stub (events = []) — now fetches from ForexFactory's
    public JSON feed. High-impact events are cached per currency so the
    risk engine's news filter actually fires.

    ForexFactory feed: https://nfs.faireconomy.media/ff_calendar_thisweek.json
    Returns events with fields: title, country, date, time, impact, forecast, previous
    """
    async def _run():
        from core.redis_client import RedisClient
        from datetime import datetime, timezone, timedelta

        redis = await RedisClient.create()

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                    headers={"Accept": "application/json"},
                )
                if resp.status_code != 200:
                    logger.warning("celery.calendar_fetch_failed", status=resp.status_code)
                    await redis.close()
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

                # Parse event datetime (ForexFactory uses format "MM-DD-YYYY" + "HH:MMam/pm")
                try:
                    event_dt_str = f"{raw_date} {raw_time}"
                    event_dt = datetime.strptime(event_dt_str, "%m-%d-%Y %I:%M%p").replace(
                        tzinfo=timezone.utc
                    )
                except Exception:
                    continue

                # Only cache events within the next 30 minutes or past 5 minutes
                minutes_until = (event_dt - now_utc).total_seconds() / 60
                if -5 <= minutes_until <= 30:
                    cache_key = f"news:high_impact:{country}"
                    ttl = max(60, int((event_dt - now_utc + timedelta(minutes=5)).total_seconds()))
                    await redis.set(
                        cache_key,
                        f"{title} at {raw_time} UTC",
                        ex=ttl,
                    )
                    logger.info("celery.calendar_cached", country=country, title=title,
                                minutes_until=round(minutes_until, 1))

        except Exception as e:
            logger.error("celery.calendar_error", error=str(e))
        finally:
            await redis.close()

    run_async(_run())


# ── P&L sync ─────────────────────────────────────────────────────

@app.task
def sync_open_trades():
    """Sync current price and unrealized P&L for all open trades."""
    async def _run():
        _, Session = _get_celery_db()   # FIX #14: shared engine

        async with Session() as session:
            result = await session.execute(
                text("SELECT id, account_id, account_type, symbol, direction, entry_price, lot_size FROM trades WHERE status = 'open'")
            )
            open_trades = result.mappings().all()

        if not open_trades:
            return

        # FIX #13: create ONE httpx client for all trades, not one per trade
        async with httpx.AsyncClient(timeout=10) as client:
            for trade in open_trades:
                try:
                    resp = await client.get(
                        f"{settings.MARKET_DATA_URL}/market/price/{trade['symbol']}"
                    )
                    if resp.status_code != 200:
                        continue

                    current_price = resp.json().get("price", 0)
                    entry         = float(trade["entry_price"] or 0)
                    direction_mult = 1 if trade["direction"] == "BUY" else -1
                    unrealized_pnl = (
                        (current_price - entry)
                        * direction_mult
                        * float(trade["lot_size"] or 1)
                        * 100000
                    )

                    async with Session() as upd_session:
                        await upd_session.execute(
                            text("UPDATE trades SET current_price = :price, unrealized_pnl = :pnl WHERE id = :id"),
                            {"price": current_price, "pnl": unrealized_pnl, "id": str(trade["id"])},
                        )
                        await upd_session.commit()

                except Exception as e:
                    logger.error("sync_trades.failed", trade_id=str(trade["id"]), error=str(e))

    run_async(_run())


# ── Signal cleanup ────────────────────────────────────────────────

@app.task
def cleanup_expired_signals():
    """Mark signals older than 24h (untouched) as inactive."""
    async def _run():
        _, Session = _get_celery_db()   # FIX #14: shared engine

        async with Session() as session:
            result = await session.execute(text("""
                UPDATE signals SET is_active = false
                WHERE is_active = true
                  AND generated_at < NOW() - INTERVAL '24 hours'
                  AND id NOT IN (SELECT signal_id FROM trades WHERE signal_id IS NOT NULL)
            """))
            await session.commit()
            logger.info("cleanup.signals", deactivated=result.rowcount)

    run_async(_run())
