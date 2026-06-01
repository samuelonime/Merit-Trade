"""
Merit-Trade AI — Notification Service
Multi-channel notification delivery: Telegram, Email, Web Push
"""
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional
from uuid import UUID

import httpx
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

engine = create_async_engine(settings.DATABASE_URL, pool_size=5)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

redis_client: RedisClient | None = None
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, http_client
    redis_client = await RedisClient.create()
    http_client = httpx.AsyncClient(timeout=15.0)
    asyncio.create_task(listen_for_events())
    yield
    await redis_client.close()
    await http_client.aclose()


app = FastAPI(title="Notification Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Schemas ───────────────────────────────────────

class NotificationRequest(BaseModel):
    user_id: UUID
    type: str               # signal | trade | risk | news
    title: str
    body: str
    channels: list[str] = ["email"]
    metadata: Optional[dict] = None


# ── Channel Senders ───────────────────────────────

async def send_telegram(chat_id: str, text_msg: str) -> bool:
    if not settings.TELEGRAM_BOT_TOKEN:
        return False
    try:
        resp = await http_client.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text_msg,
                "parse_mode": "HTML",
            },
        )
        return resp.status_code == 200
    except Exception as e:
        logger.error("telegram.send_failed", error=str(e))
        return False


async def send_email(to_email: str, subject: str, html_body: str) -> bool:
    if not settings.SENDGRID_API_KEY:
        return False
    try:
        resp = await http_client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
            json={
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": settings.EMAIL_FROM, "name": "Merit-Trade AI"},
                "subject": subject,
                "content": [{"type": "text/html", "value": html_body}],
            },
        )
        return resp.status_code in (200, 202)
    except Exception as e:
        logger.error("email.send_failed", error=str(e))
        return False


async def send_web_push(subscription: dict, title: str, body: str) -> bool:
    """Send Web Push notification using VAPID."""
    if not settings.VAPID_PRIVATE_KEY:
        return False
    try:
        from pywebpush import webpush, WebPushException
        webpush(
            subscription_info=subscription,
            data=json.dumps({"title": title, "body": body}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": f"mailto:{settings.EMAIL_FROM}"},
        )
        return True
    except Exception as e:
        logger.error("webpush.send_failed", error=str(e))
        return False


# ── Dispatcher ────────────────────────────────────

async def dispatch_notification(user_id: str, notification_type: str, title: str, body: str, metadata: dict = None):
    """Fetch user preferences and dispatch to enabled channels."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT u.email, np.* FROM notification_preferences np JOIN users u ON u.id = np.user_id WHERE np.user_id = :uid"),
            {"uid": user_id},
        )
        prefs = result.mappings().first()
        if not prefs:
            return

        prefs = dict(prefs)

    results = {}

    # Telegram
    if prefs.get("telegram_enabled") and prefs.get("telegram_chat_id"):
        msg = f"<b>🤖 Merit-Trade AI</b>\n<b>{title}</b>\n\n{body}"
        if metadata:
            if "symbol" in metadata:
                msg += f"\n\n📊 <b>Symbol:</b> {metadata['symbol']}"
            if "direction" in metadata:
                emoji = "🟢" if metadata["direction"] == "BUY" else "🔴"
                msg += f"\n{emoji} <b>Direction:</b> {metadata['direction']}"
            if "confidence" in metadata:
                msg += f"\n📈 <b>Confidence:</b> {metadata['confidence']}%"
        results["telegram"] = await send_telegram(prefs["telegram_chat_id"], msg)

    # Email
    if prefs.get("email_enabled") and prefs.get("email"):
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
            <div style="background:#0f172a;color:#fff;padding:20px;border-radius:8px 8px 0 0">
                <h2 style="margin:0">Merit-Trade AI</h2>
            </div>
            <div style="background:#1e293b;color:#e2e8f0;padding:24px;border-radius:0 0 8px 8px">
                <h3 style="color:#38bdf8;margin-top:0">{title}</h3>
                <p style="line-height:1.6">{body}</p>
                {_meta_to_html(metadata) if metadata else ""}
                <hr style="border-color:#334155;margin:20px 0"/>
                <p style="font-size:12px;color:#64748b">Merit-Trade AI | <a href="#" style="color:#38bdf8">Manage Notifications</a></p>
            </div>
        </div>
        """
        results["email"] = await send_email(prefs["email"], f"Merit-Trade: {title}", html)

    # Web Push
    if prefs.get("push_enabled") and prefs.get("push_subscription"):
        results["push"] = await send_web_push(prefs["push_subscription"], title, body)

    # Store notification record
    async with AsyncSessionFactory() as session:
        for channel, success in results.items():
            await session.execute(
                text("""
                    INSERT INTO notifications (user_id, channel, type, title, body, is_sent, sent_at, metadata)
                    VALUES (:uid, :channel, :type, :title, :body, :sent, CASE WHEN :sent THEN NOW() ELSE NULL END, :meta)
                """),
                {
                    "uid": user_id, "channel": channel, "type": notification_type,
                    "title": title, "body": body, "sent": success,
                    "meta": json.dumps(metadata) if metadata else None,
                },
            )
        await session.commit()

    logger.info("notification.dispatched", user_id=user_id, type=notification_type, channels=list(results.keys()))


def _meta_to_html(metadata: dict) -> str:
    if not metadata:
        return ""
    rows = "".join(
        f'<tr><td style="color:#94a3b8;padding:4px 8px">{k.replace("_"," ").title()}</td>'
        f'<td style="color:#e2e8f0;padding:4px 8px">{v}</td></tr>'
        for k, v in metadata.items()
    )
    return f'<table style="width:100%;border-collapse:collapse;margin-top:16px">{rows}</table>'


# ── Redis Event Listener ──────────────────────────

async def listen_for_events():
    """
    Subscribe to Redis pub/sub channels and dispatch notifications.
    Listens for: signals, trades, risk alerts.
    """
    pubsub = await redis_client.get_pubsub()
    await pubsub.subscribe("channel:signals", "channel:trades", "channel:alerts")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            data = json.loads(message["data"])
            event_type = data.get("type")

            if event_type == "new_signal":
                # Notify users who have signal alerts enabled
                await _notify_signal_subscribers(data)
            elif event_type == "trade_opened":
                await dispatch_notification(
                    data["user_id"], "trade",
                    "Trade Opened",
                    f"New {data['direction']} trade opened on {data['symbol']} at {data.get('entry_price')}",
                    data,
                )
            elif event_type == "trade_closed":
                pnl = data.get("realized_pnl", 0)
                emoji = "✅" if pnl >= 0 else "❌"
                await dispatch_notification(
                    data["user_id"], "trade",
                    f"{emoji} Trade Closed",
                    f"{data['symbol']} trade closed. P&L: {pnl:+.2f}",
                    data,
                )
        except Exception as e:
            logger.error("event_listener.error", error=str(e))


async def _notify_signal_subscribers(signal_data: dict):
    """Find users with signal notifications enabled and dispatch."""
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("""
                SELECT u.id FROM users u
                JOIN notification_preferences np ON np.user_id = u.id
                WHERE np.signal_alerts = true AND u.is_active = true
            """)
        )
        user_ids = [str(r[0]) for r in result.all()]

    symbol = signal_data.get("symbol", "")
    direction = signal_data.get("direction", "")
    confidence = signal_data.get("confidence", 0)

    for user_id in user_ids:
        await dispatch_notification(
            user_id, "signal",
            f"New Signal: {symbol}",
            f"{direction} signal on {symbol} with {confidence}% confidence",
            signal_data,
        )


# ── Routes ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "notification"}


@app.post("/notify/send")
async def send_notification(req: NotificationRequest):
    await dispatch_notification(
        str(req.user_id), req.type, req.title, req.body, req.metadata
    )
    return {"message": "Notification dispatched"}


@app.get("/notify/history/{user_id}")
async def get_history(user_id: UUID, limit: int = 20):
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT * FROM notifications WHERE user_id = :uid ORDER BY created_at DESC LIMIT :limit"),
            {"uid": str(user_id), "limit": limit},
        )
        return [dict(r) for r in result.mappings().all()]


@app.put("/notify/preferences/{user_id}")
async def update_preferences(user_id: UUID, prefs: dict):
    async with AsyncSessionFactory() as session:
        allowed = {
            "telegram_chat_id", "telegram_enabled", "email_enabled",
            "push_enabled", "push_subscription", "signal_alerts",
            "trade_alerts", "risk_alerts", "news_alerts",
        }
        filtered = {k: v for k, v in prefs.items() if k in allowed}
        if not filtered:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        set_clause = ", ".join(f"{k} = :{k}" for k in filtered)
        await session.execute(
            text(f"UPDATE notification_preferences SET {set_clause}, updated_at = NOW() WHERE user_id = :uid"),
            {**filtered, "uid": str(user_id)},
        )
        await session.commit()
    return {"message": "Preferences updated"}
