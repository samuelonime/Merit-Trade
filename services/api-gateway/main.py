"""
Merit-Trade AI — API Gateway
Central ingress for all client traffic. Handles auth validation,
rate limiting, request routing, and WebSocket hub.
"""
import time
import uuid
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
import structlog
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/../shared")

from core.config import settings
from core.jwt_handler import verify_token
from core.exceptions import AuthenticationError, AuthorizationError
from core.redis_client import RedisClient
from websocket_manager import WebSocketManager

logger = structlog.get_logger()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

ws_manager = WebSocketManager()
redis_client: RedisClient | None = None
http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, http_client
    redis_client = await RedisClient.create()
    http_client = httpx.AsyncClient(timeout=30.0)
    logger.info("api_gateway.started", env=settings.APP_ENV)
    yield
    await http_client.aclose()
    await redis_client.close()
    logger.info("api_gateway.shutdown")


app = FastAPI(
    title="Merit-Trade AI — API Gateway",
    version="1.0.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Middleware: request tracing & logging ──────────

@app.middleware("http")
async def request_tracing(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    response.headers["X-Trace-ID"] = trace_id
    response.headers["X-Response-Time"] = str(duration_ms)

    logger.info(
        "http.request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        trace_id=trace_id,
        ip=get_remote_address(request),
    )
    return response


# ── Auth dependency ────────────────────────────────

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    # Check token blacklist in Redis
    is_blacklisted = await redis_client.get(f"blacklist:token:{token[:32]}")
    if is_blacklisted:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    try:
        payload = verify_token(token)
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))

    return payload


async def require_plan(min_plan: str):
    """Factory for plan-gated routes."""
    plan_rank = {"free": 0, "pro": 1, "enterprise": 2}

    async def _check(user: dict = Depends(get_current_user)):
        if plan_rank.get(user.get("plan", "free"), 0) < plan_rank.get(min_plan, 0):
            raise HTTPException(
                status_code=403,
                detail=f"This feature requires the '{min_plan}' plan or higher",
            )
        return user

    return _check


async def require_admin(user: dict = Depends(get_current_user)):
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Proxy helper ───────────────────────────────────

async def proxy_request(
    service_url: str,
    path: str,
    request: Request,
    user: dict | None = None,
) -> Response:
    """Forward request to internal microservice."""
    url = f"{service_url}{path}"
    headers = dict(request.headers)
    headers.pop("host", None)
    if user:
        headers["X-User-ID"] = user["sub"]
        headers["X-User-Plan"] = user.get("plan", "free")
        headers["X-User-Admin"] = str(user.get("is_admin", False))

    body = await request.body()
    resp = await http_client.request(
        method=request.method,
        url=url,
        headers=headers,
        content=body,
        params=dict(request.query_params),
    )
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )


# ── Health check ───────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway", "version": "1.0.0"}


# ── Auth routes (proxy to auth-service) ───────────

@app.post("/api/auth/register")
@limiter.limit("5/minute")
async def register(request: Request):
    return await proxy_request(settings.AUTH_SERVICE_URL, "/auth/register", request)


@app.post("/api/auth/login")
@limiter.limit("10/minute")
async def login(request: Request):
    return await proxy_request(settings.AUTH_SERVICE_URL, "/auth/login", request)


@app.post("/api/auth/refresh")
@limiter.limit("20/minute")
async def refresh(request: Request):
    return await proxy_request(settings.AUTH_SERVICE_URL, "/auth/refresh", request)


@app.post("/api/auth/logout")
@limiter.limit("20/minute")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    return await proxy_request(settings.AUTH_SERVICE_URL, "/auth/logout", request, user)


# ── User routes ───────────────────────────────────

@app.api_route("/api/users/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@limiter.limit("60/minute")
async def users_proxy(request: Request, path: str, user: dict = Depends(get_current_user)):
    return await proxy_request(settings.USER_SERVICE_URL, f"/users/{path}", request, user)


# ── Signals routes ────────────────────────────────


# ── Plan access tables ────────────────────────────
#
# These mirror the definitions in celery_app.py and are
# enforced at the API gateway so no service logic is needed.

_PLAN_PAIRS = {
    "free":         {"EURUSD", "BTCUSDT"},
    "pro":          {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSDT", "ETHUSDT", "SOLUSDT"},
    "enterprise":   {"EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "XAUUSD", "BTCUSDT", "ETHUSDT", "SOLUSDT"},
    "expired_free": set(),  # no access after trial expires
}

_PLAN_TIMEFRAMES = {
    "free":         {"1h"},
    "pro":          {"15m", "1h", "4h"},
    "enterprise":   {"15m", "1h", "4h", "1d"},
    "expired_free": set(),
}


def get_plan_limits(plan: str) -> tuple[set, set]:
    """Return (allowed_pairs, allowed_timeframes) for a plan."""
    return _PLAN_PAIRS.get(plan, set()), _PLAN_TIMEFRAMES.get(plan, set())


def check_trial_active(user: dict) -> bool:
    """Return True if user is on a free plan that is still within 7 days."""
    from datetime import datetime, timezone
    created = user.get("created_at")
    if not created:
        return True  # assume active if unknown
    if isinstance(created, str):
        created = datetime.fromisoformat(created.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now - created).days < 7


@app.api_route("/api/signals/{path:path}", methods=["GET", "POST"])
@limiter.limit("60/minute")
async def signals_proxy(request: Request, path: str, user: dict = Depends(get_current_user)):
    return await proxy_request(settings.SIGNAL_ENGINE_URL, f"/signals/{path}", request, user)


@app.get("/api/signals")
@limiter.limit("60/minute")
async def signals_list(
    request: Request,
    symbol: str | None = None,
    timeframe: str | None = None,
    user: dict = Depends(get_current_user),
):
    plan = user.get("plan", "free")

    # Block expired free users entirely
    if plan == "expired_free":
        raise HTTPException(
            status_code=402,
            detail="Your 7-day free trial has ended. Upgrade to Pro to continue accessing signals.",
        )

    # Block free users whose 7 days are up (belt + suspenders; celery also handles this)
    if plan == "free" and not check_trial_active(user):
        raise HTTPException(
            status_code=402,
            detail="Your 7-day free trial has ended. Upgrade to Pro to continue accessing signals.",
        )

    allowed_pairs, allowed_timeframes = get_plan_limits(plan)

    # Validate requested symbol
    if symbol and symbol.upper() not in allowed_pairs:
        raise HTTPException(
            status_code=403,
            detail=f"'{symbol}' is not available on your {plan} plan. "
                   f"Available pairs: {sorted(allowed_pairs)}. Upgrade to Pro for all 8 pairs.",
        )

    # Validate requested timeframe
    if timeframe and timeframe not in allowed_timeframes:
        raise HTTPException(
            status_code=403,
            detail=f"'{timeframe}' timeframe is not available on your {plan} plan. "
                   f"Available: {sorted(allowed_timeframes)}. Upgrade to Pro for 15m, 1h, 4h.",
        )

    # Forward to signal engine — it will filter by symbol/timeframe query params
    return await proxy_request(settings.SIGNAL_ENGINE_URL, "/signals", request, user)


# ── Market data routes ────────────────────────────

@app.api_route("/api/market/{path:path}", methods=["GET"])
@limiter.limit("120/minute")
async def market_proxy(request: Request, path: str, user: dict = Depends(get_current_user)):
    return await proxy_request(settings.MARKET_DATA_URL, f"/market/{path}", request, user)


# ── Execution routes (Pro+) ───────────────────────

@app.api_route("/api/execute/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@limiter.limit("30/minute")
async def execute_proxy(
    request: Request,
    path: str,
    user: dict = Depends(require_plan("pro")),
):
    return await proxy_request(settings.EXECUTION_ENGINE_URL, f"/execute/{path}", request, user)


# ── Risk settings routes ──────────────────────────

@app.api_route("/api/risk/{path:path}", methods=["GET", "POST", "PUT"])
@limiter.limit("30/minute")
async def risk_proxy(request: Request, path: str, user: dict = Depends(get_current_user)):
    return await proxy_request(settings.RISK_ENGINE_URL, f"/risk/{path}", request, user)


# ── Admin routes (admin only) ─────────────────────

@app.api_route("/api/admin/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@limiter.limit("120/minute")
async def admin_proxy(request: Request, path: str, user: dict = Depends(require_admin)):
    return await proxy_request(settings.ADMIN_SERVICE_URL, f"/admin/{path}", request, user)


# ── WebSocket: real-time feed ─────────────────────

@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str, token: str):
    """
    WebSocket endpoint for real-time data.
    Channels: signals | trades | portfolio | alerts
    """
    try:
        payload = verify_token(token)
        user_id = payload["sub"]
    except (AuthenticationError, Exception):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await ws_manager.connect(websocket, user_id, channel)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong keepalive
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, user_id, channel)
