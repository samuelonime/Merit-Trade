"""
WebSocket connection manager.
Manages user connections across channels and broadcasts from Redis pub/sub.
"""
import asyncio
import json
from collections import defaultdict
from typing import Dict, Set

import structlog
from fastapi import WebSocket

logger = structlog.get_logger()


class WebSocketManager:
    def __init__(self):
        # {channel: {user_id: set[WebSocket]}}
        self._connections: Dict[str, Dict[str, Set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )

    async def connect(self, websocket: WebSocket, user_id: str, channel: str):
        await websocket.accept()
        self._connections[channel][user_id].add(websocket)
        logger.info("ws.connected", user_id=user_id, channel=channel)
        await websocket.send_json({"type": "connected", "channel": channel})

    def disconnect(self, websocket: WebSocket, user_id: str, channel: str):
        self._connections[channel][user_id].discard(websocket)
        if not self._connections[channel][user_id]:
            del self._connections[channel][user_id]
        logger.info("ws.disconnected", user_id=user_id, channel=channel)

    async def broadcast_to_channel(self, channel: str, message: dict):
        """Broadcast to all subscribers of a channel."""
        payload = json.dumps(message)
        dead = []
        for user_id, sockets in self._connections[channel].items():
            for ws in list(sockets):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append((user_id, ws))

        for user_id, ws in dead:
            self._connections[channel][user_id].discard(ws)

    async def send_to_user(self, user_id: str, channel: str, message: dict):
        """Send message to a specific user on a channel."""
        payload = json.dumps(message)
        sockets = self._connections[channel].get(user_id, set())
        dead = []
        for ws in list(sockets):
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            sockets.discard(ws)

    @property
    def total_connections(self) -> int:
        return sum(
            len(sockets)
            for channel in self._connections.values()
            for sockets in channel.values()
        )
