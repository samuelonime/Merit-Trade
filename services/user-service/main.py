"""
Merit-Trade AI — User Service
Manages user profiles, broker account CRUD (with encrypted credentials),
risk settings, and subscription status.
"""
from contextlib import asynccontextmanager
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
from core.security import encrypt_value, decrypt_value, mask_credential

logger = structlog.get_logger()

engine = create_async_engine(settings.DATABASE_URL, pool_size=10)
AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="User Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health():
    return {"status": "ok", "service": "user"}

@app.get("/users/me")
async def get_me(request: Request):
    user_id = request.headers.get("X-User-ID")
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            text("SELECT id, email, username, full_name, plan, is_verified, created_at, last_login FROM users WHERE id = :id"),
            {"id": user_id},
        )
        row = result.mappings().first()
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(row)

@app.post("/users/forex-accounts")
async def add_forex_account(payload: dict, request: Request):
    user_id = request.headers.get("X-User-ID")
    # Encrypt credentials before storage
    encrypted_pw = encrypt_value(payload["password"])
    async with AsyncSessionFactory() as session:
        await session.execute(
            text("""
                INSERT INTO accounts_forex (user_id, broker_name, account_number, encrypted_password, server, is_demo)
                VALUES (:uid, :broker, :acct, :pw, :server, :demo)
            """),
            {
                "uid": user_id, "broker": payload["broker_name"],
                "acct": payload["account_number"], "pw": encrypted_pw,
                "server": payload["server"], "demo": payload.get("is_demo", True),
            },
        )
        await session.commit()
    return {"message": "Forex account added (credentials encrypted)"}

@app.post("/users/crypto-accounts")
async def add_crypto_account(payload: dict, request: Request):
    user_id = request.headers.get("X-User-ID")
    encrypted_key = encrypt_value(payload["api_key"])
    encrypted_secret = encrypt_value(payload["api_secret"])
    encrypted_pass = encrypt_value(payload["passphrase"]) if payload.get("passphrase") else None
    async with AsyncSessionFactory() as session:
        await session.execute(
            text("""
                INSERT INTO accounts_crypto (user_id, exchange, label, encrypted_api_key, encrypted_api_secret, encrypted_passphrase, is_testnet)
                VALUES (:uid, :exchange, :label, :key, :secret, :pass, :testnet)
            """),
            {
                "uid": user_id, "exchange": payload["exchange"],
                "label": payload.get("label"), "key": encrypted_key,
                "secret": encrypted_secret, "pass": encrypted_pass,
                "testnet": payload.get("is_testnet", True),
            },
        )
        await session.commit()
    return {"message": "Crypto account added (credentials encrypted)"}

@app.get("/users/accounts")
async def list_accounts(request: Request):
    user_id = request.headers.get("X-User-ID")
    async with AsyncSessionFactory() as session:
        forex = await session.execute(
            text("SELECT id, broker_name, account_number, server, is_demo, is_active, balance, currency, last_sync FROM accounts_forex WHERE user_id = :uid"),
            {"uid": user_id},
        )
        crypto = await session.execute(
            text("SELECT id, exchange, label, is_testnet, is_active, supported_types, last_sync FROM accounts_crypto WHERE user_id = :uid"),
            {"uid": user_id},
        )
        return {
            "forex": [dict(r) for r in forex.mappings().all()],
            "crypto": [dict(r) for r in crypto.mappings().all()],
        }
