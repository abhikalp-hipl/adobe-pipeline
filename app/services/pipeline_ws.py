import asyncio
import logging
from threading import Lock

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class PipelineWebSocketManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        with self._lock:
            self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def broadcast(self, data: dict[str, object]) -> None:
        with self._lock:
            targets = list(self._connections)

        stale: list[WebSocket] = []
        for connection in targets:
            try:
                await connection.send_json(data)
            except Exception:
                stale.append(connection)

        if stale:
            with self._lock:
                for connection in stale:
                    if connection in self._connections:
                        self._connections.remove(connection)

    def broadcast_from_thread(self, data: dict[str, object]) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(data), self._loop)
