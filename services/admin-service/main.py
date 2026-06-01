"""
Merit-Trade AI — Admin Service
System administration: user management, trade monitoring,
AI performance metrics, subscription management, system health.
All routes require admin role (enforced by API Gateway).
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

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


app = FastAPI(title="Admin Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Users ─────────────────────────────────────────

@app.get("/admin/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    plan: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
):
    async with AsyncSessionFactory() as session:
        where = "WHERE deleted_at IS NULL"
        params: dict = {"limit": limit, "offset": offset}
        if plan:
            where += " AND plan = :plan"
            params["plan"] = plan
        if is_active is not None:
            where += " AND is_active = :active"
            params["active"] = is_active
        if search:
            where += " AND (email ILIKE :search OR username ILIKE :search OR full_name ILIKE :search)"
            params["search"] = f"%{search}%"

        result = await session.execute(
            text(f"""
                SELECT id, email, username, full_name, is_active, is_verified, is_admin,
                       plan, created_at, last_login, failed_logins
                FROM users {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        count_result = await session.execute(
            text(f"SELECT COUNT(*) FROM users {where}"), params
        )
        return {
            "users": [dict(r) for r in result.mappings().all()],
            "total": count_result.scalar(),
        }


@app.get("/admin/users/{user_id}")
async def get_user(user_id: UUID):
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM users WHERE id = :id AND deleted_at IS NULL"),
            {"id": str(user_id)},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")

        row = dict(row)
        row.pop("password_hash", None)  # Never expose password hash

        # Get trade stats
        stats = await session.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE status = 'open') as open_trades,
                    COUNT(*) FILTER (WHERE status = 'closed') as total_trades,
                    SUM(realized_pnl) FILTER (WHERE status = 'closed') as total_pnl,
                    COUNT(*) FILTER (WHERE status = 'closed' AND realized_pnl > 0) as wins,
                    COUNT(*) FILTER (WHERE status = 'closed' AND realized_pnl <= 0) as losses
                FROM trades WHERE user_id = :uid
            """),
            {"uid": str(user_id)},
        )
        row["trade_stats"] = dict(stats.mappings().first() or {})
        return row


@app.patch("/admin/users/{user_id}/status")
async def toggle_user_status(user_id: UUID, payload: dict):
    is_active = payload.get("is_active")
    if is_active is None:
        raise HTTPException(status_code=400, detail="is_active required")

    async with AsyncSessionFactory() as session:
        await session.execute(
            text("UPDATE users SET is_active = :active, updated_at = NOW() WHERE id = :id"),
            {"active": is_active, "id": str(user_id)},
        )
        await session.commit()

    # Blacklist all user's tokens if disabling
    if not is_active:
        await redis_client.set(f"user_disabled:{user_id}", "1", ex=86400 * 30)

    action = "enabled" if is_active else "disabled"
    logger.info("admin.user_status_changed", user_id=str(user_id), action=action)
    return {"message": f"User {action}"}


@app.patch("/admin/users/{user_id}/plan")
async def change_user_plan(user_id: UUID, payload: dict):
    plan = payload.get("plan")
    if plan not in ("free", "pro", "enterprise"):
        raise HTTPException(status_code=400, detail="Invalid plan")

    async with AsyncSessionFactory() as session:
        await session.execute(
            text("UPDATE users SET plan = :plan, updated_at = NOW() WHERE id = :id"),
            {"plan": plan, "id": str(user_id)},
        )
        await session.commit()

    return {"message": f"Plan updated to {plan}"}


# ── System Health ──────────────────────────────────

@app.get("/admin/health")
async def system_health():
    services = [
        ("auth", settings.AUTH_SERVICE_URL),
        ("user", settings.USER_SERVICE_URL),
        ("signal-engine", settings.SIGNAL_ENGINE_URL),
        ("market-data", settings.MARKET_DATA_URL),
        ("execution", settings.EXECUTION_ENGINE_URL),
        ("risk-engine", settings.RISK_ENGINE_URL),
        ("notifications", settings.NOTIFICATION_SERVICE_URL),
    ]

    import httpx
    statuses = {}
    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in services:
            try:
                resp = await client.get(f"{url}/health")
                statuses[name] = {
                    "status": "healthy" if resp.status_code == 200 else "degraded",
                    "latency_ms": int(resp.elapsed.total_seconds() * 1000),
                }
            except Exception as e:
                statuses[name] = {"status": "unreachable", "error": str(e)}

    # Redis health
    try:
        await redis_client.ping()
        statuses["redis"] = {"status": "healthy"}
    except Exception:
        statuses["redis"] = {"status": "unreachable"}

    # DB health
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        statuses["postgres"] = {"status": "healthy"}
    except Exception:
        statuses["postgres"] = {"status": "unreachable"}

    overall = "healthy" if all(s["status"] == "healthy" for s in statuses.values()) else "degraded"
    return {"overall": overall, "services": statuses, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Trade Monitoring ──────────────────────────────

@app.get("/admin/trades")
async def list_all_trades(
    status: Optional[str] = None,
    symbol: Optional[str] = None,
    user_id: Optional[UUID] = None,
    limit: int = 100,
    offset: int = 0,
):
    async with AsyncSessionFactory() as session:
        where = "WHERE 1=1"
        params: dict = {"limit": limit, "offset": offset}
        if status:
            where += " AND t.status = :status"
            params["status"] = status
        if symbol:
            where += " AND t.symbol = :symbol"
            params["symbol"] = symbol.upper()
        if user_id:
            where += " AND t.user_id = :uid"
            params["uid"] = str(user_id)

        result = await session.execute(
            text(f"""
                SELECT t.*, u.email, u.username
                FROM trades t
                JOIN users u ON u.id = t.user_id
                {where}
                ORDER BY t.created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        )
        return [dict(r) for r in result.mappings().all()]


# ── Statistics & Metrics ──────────────────────────

@app.get("/admin/stats/overview")
async def overview_stats():
    async with AsyncSessionFactory() as session:
        users = await session.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE plan = 'free') as free_users,
                COUNT(*) FILTER (WHERE plan = 'pro') as pro_users,
                COUNT(*) FILTER (WHERE plan = 'enterprise') as enterprise_users,
                COUNT(*) FILTER (WHERE last_login > NOW() - INTERVAL '7 days') as active_7d,
                COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') as new_30d
            FROM users WHERE deleted_at IS NULL AND is_active = true
        """))

        trades = await session.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'open') as open,
                COUNT(*) FILTER (WHERE status = 'closed') as closed,
                SUM(realized_pnl) FILTER (WHERE status = 'closed') as total_pnl,
                COUNT(*) FILTER (WHERE status = 'closed' AND realized_pnl > 0)::float /
                    NULLIF(COUNT(*) FILTER (WHERE status = 'closed'), 0) * 100 as win_rate
            FROM trades WHERE created_at > NOW() - INTERVAL '30 days'
        """))

        signals = await session.execute(text("""
            SELECT
                COUNT(*) as total_30d,
                AVG(confidence_score) as avg_confidence,
                COUNT(*) FILTER (WHERE direction = 'BUY') as buys,
                COUNT(*) FILTER (WHERE direction = 'SELL') as sells
            FROM signals WHERE generated_at > NOW() - INTERVAL '30 days'
        """))

        ai = await session.execute(text("""
            SELECT COUNT(*) as calls, SUM(output_tokens + prompt_tokens) as total_tokens
            FROM ai_outputs WHERE created_at > NOW() - INTERVAL '30 days'
        """))

    return {
        "users": dict(users.mappings().first() or {}),
        "trades": dict(trades.mappings().first() or {}),
        "signals": dict(signals.mappings().first() or {}),
        "ai_usage": dict(ai.mappings().first() or {}),
    }


@app.get("/admin/stats/ai-performance")
async def ai_performance():
    """Analyze ML signal performance vs actual trade outcomes."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(text("""
            SELECT
                s.direction,
                s.confidence_score,
                s.timeframe,
                t.realized_pnl,
                CASE WHEN t.realized_pnl > 0 THEN true ELSE false END as was_correct
            FROM signals s
            JOIN trades t ON t.signal_id = s.id
            WHERE t.status = 'closed'
            ORDER BY s.generated_at DESC
            LIMIT 500
        """))
        rows = [dict(r) for r in result.mappings().all()]

    if not rows:
        return {"message": "No closed signal-based trades yet"}

    total = len(rows)
    wins = sum(1 for r in rows if r["was_correct"])
    by_confidence = {}
    for r in rows:
        band = f"{(r['confidence_score'] // 10) * 10}-{(r['confidence_score'] // 10) * 10 + 9}%"
        if band not in by_confidence:
            by_confidence[band] = {"total": 0, "wins": 0}
        by_confidence[band]["total"] += 1
        if r["was_correct"]:
            by_confidence[band]["wins"] += 1

    for band in by_confidence:
        b = by_confidence[band]
        b["win_rate"] = round(b["wins"] / b["total"] * 100, 1) if b["total"] else 0

    return {
        "total_signals_traded": total,
        "overall_win_rate": round(wins / total * 100, 1),
        "by_confidence_band": by_confidence,
    }


@app.get("/admin/logs")
async def get_logs(
    level: Optional[str] = None,
    service: Optional[str] = None,
    user_id: Optional[UUID] = None,
    limit: int = 100,
):
    async with AsyncSessionFactory() as session:
        where = "WHERE 1=1"
        params: dict = {"limit": limit}
        if level:
            where += " AND level = :level"
            params["level"] = level
        if service:
            where += " AND service = :service"
            params["service"] = service
        if user_id:
            where += " AND user_id = :uid"
            params["uid"] = str(user_id)

        result = await session.execute(
            text(f"SELECT * FROM logs {where} ORDER BY time DESC LIMIT :limit"),
            params,
        )
        return [dict(r) for r in result.mappings().all()]
