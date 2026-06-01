"""Async Redis client wrapper with pub/sub support."""
from typing import Optional
import redis.asyncio as aioredis

import sys
sys.path.insert(0, "/app/../shared")

from core.config import settings


class RedisClient:
    def __init__(self, client: aioredis.Redis):
        self._client = client

    @classmethod
    async def create(cls) -> "RedisClient":
        client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=False,
            max_connections=20,
        )
        return cls(client)

    async def get(self, key: str) -> Optional[bytes]:
        return await self._client.get(key)

    async def set(self, key: str, value, ex: Optional[int] = None):
        return await self._client.set(key, value, ex=ex)

    async def delete(self, key: str):
        return await self._client.delete(key)

    async def incr(self, key: str):
        return await self._client.incr(key)

    async def decr(self, key: str):
        return await self._client.decr(key)

    async def publish(self, channel: str, message: str):
        return await self._client.publish(channel, message)

    async def ping(self):
        return await self._client.ping()

    async def get_pubsub(self):
        return self._client.pubsub()

    async def close(self):
        await self._client.aclose()
