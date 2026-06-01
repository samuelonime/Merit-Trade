"""
Merit-Trade AI — Auth Service
Handles user registration, login, JWT issuance/refresh,
password reset, and session management.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, "/app/../shared")

from core.config import settings
from core.security import hash_password, verify_password
from core.jwt_handler import create_access_token, create_refresh_token, verify_token
from core.exceptions import AuthenticationError
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


app = FastAPI(title="Auth Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ───────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    @field_validator("username")
    @classmethod
    def username_valid(cls, v: str) -> str:
        if not v.isalnum() and "_" not in v:
            raise ValueError("Username can only contain letters, numbers, and underscores")
        if len(v) < 3 or len(v) > 50:
            raise ValueError("Username must be between 3 and 50 characters")
        return v.lower()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60


# ── Helpers ───────────────────────────────────────

async def get_user_by_email(session: AsyncSession, email: str) -> dict | None:
    result = await session.execute(
        text("SELECT id, email, username, password_hash, is_active, is_verified, is_admin, plan, failed_logins, locked_until FROM users WHERE email = :email AND deleted_at IS NULL"),
        {"email": email},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_user_by_id(session: AsyncSession, user_id: str) -> dict | None:
    result = await session.execute(
        text("SELECT id, email, username, is_active, is_verified, is_admin, plan FROM users WHERE id = :id AND deleted_at IS NULL"),
        {"id": user_id},
    )
    row = result.mappings().first()
    return dict(row) if row else None


# ── Routes ────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "auth"}


@app.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, request: Request):
    async with AsyncSessionFactory() as session:
        # Check uniqueness
        existing = await session.execute(
            text("SELECT id FROM users WHERE email = :email OR username = :username"),
            {"email": req.email, "username": req.username},
        )
        if existing.first():
            raise HTTPException(status_code=409, detail="Email or username already registered")

        # Create user
        user_id = uuid4()
        pw_hash = hash_password(req.password)

        await session.execute(
            text("""
                INSERT INTO users (id, email, username, password_hash, full_name, is_active)
                VALUES (:id, :email, :username, :password_hash, :full_name, true)
            """),
            {
                "id": str(user_id),
                "email": req.email,
                "username": req.username,
                "password_hash": pw_hash,
                "full_name": req.full_name,
            },
        )

        # Create default risk settings
        await session.execute(
            text("INSERT INTO risk_settings (user_id) VALUES (:user_id)"),
            {"user_id": str(user_id)},
        )

        # Create default notification preferences
        await session.execute(
            text("INSERT INTO notification_preferences (user_id) VALUES (:user_id)"),
            {"user_id": str(user_id)},
        )

        await session.commit()

    access_token = create_access_token(user_id, req.email, "free")
    refresh_token = create_refresh_token(user_id)

    # Store refresh token in Redis (hashed for lookup)
    await redis_client.set(
        f"refresh:{str(user_id)}:{refresh_token[-16:]}",
        refresh_token,
        ex=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    logger.info("auth.register.success", user_id=str(user_id), email=req.email)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown")

    async with AsyncSessionFactory() as session:
        user = await get_user_by_email(session, req.email)

        if not user:
            logger.warning("auth.login.user_not_found", email=req.email, ip=ip)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Check account lock
        if user.get("locked_until") and user["locked_until"] > datetime.now(timezone.utc):
            raise HTTPException(status_code=423, detail="Account temporarily locked due to failed attempts")

        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Account disabled")

        # Verify password
        if not verify_password(req.password, user["password_hash"]):
            # Increment failed logins
            new_fails = (user["failed_logins"] or 0) + 1
            lock_until = None
            if new_fails >= 10:
                from datetime import timedelta
                lock_until = datetime.now(timezone.utc) + timedelta(minutes=30)

            await session.execute(
                text("UPDATE users SET failed_logins = :fails, locked_until = :lock WHERE id = :id"),
                {"fails": new_fails, "lock": lock_until, "id": str(user["id"])},
            )
            await session.commit()
            logger.warning("auth.login.bad_password", user_id=str(user["id"]), ip=ip, attempts=new_fails)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Reset failed logins on success
        await session.execute(
            text("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login = NOW() WHERE id = :id"),
            {"id": str(user["id"])},
        )
        await session.commit()

    access_token = create_access_token(
        user["id"], user["email"], user["plan"], user["is_admin"]
    )
    refresh_token = create_refresh_token(user["id"])

    await redis_client.set(
        f"refresh:{str(user['id'])}:{refresh_token[-16:]}",
        refresh_token,
        ex=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    logger.info("auth.login.success", user_id=str(user["id"]), ip=ip)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest):
    try:
        payload = verify_token(req.refresh_token, expected_type="refresh")
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))

    user_id = payload["sub"]

    async with AsyncSessionFactory() as session:
        user = await get_user_by_id(session, user_id)
        if not user or not user["is_active"]:
            raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(
        user["id"], user["email"], user["plan"], user["is_admin"]
    )
    return TokenResponse(access_token=access_token, refresh_token=req.refresh_token)


@app.post("/auth/logout")
async def logout(request: Request):
    user_id = request.headers.get("X-User-ID")
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.replace("Bearer ", "")

    if token:
        # Blacklist the access token for its remaining TTL
        await redis_client.set(
            f"blacklist:token:{token[:32]}",
            "1",
            ex=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    logger.info("auth.logout", user_id=user_id)
    return {"message": "Logged out successfully"}
