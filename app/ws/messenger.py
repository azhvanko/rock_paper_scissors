import asyncio
import typing as t

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from app.logging import logger


class Messenger:
    _websockets: dict[int, set[WebSocket]]

    def __init__(self):
        self._websockets = dict()

    def connect(self, user_id: int, ws: WebSocket) -> None:
        if user_id not in self._websockets:
            self._websockets[user_id] = set()

        self._websockets[user_id].add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        if user_id not in self._websockets:
            logger.error(f'Remove not existing ws. user_id - {user_id}')
            return

        self._websockets[user_id].discard(ws)

        if not self._websockets[user_id]:
            self._websockets.pop(user_id)

    async def send_to_users(
        self,
        user_ids: t.Sequence[int],
        message: dict[str, t.Any]
    ) -> None:
        websockets = []

        for user_id in user_ids:
            if ws := self._websockets.get(user_id, None):
                websockets.extend(ws)

        if websockets:
            await asyncio.gather(*(self.send_to_ws(ws, message) for ws in websockets))
            logger.debug(f'Message {message} sent to {len(websockets)} connections.')

    @staticmethod
    async def send_to_ws(ws: WebSocket, message: dict[str, t.Any]) -> None:
        try:
            if ws.application_state == WebSocketState.CONNECTED:
                await ws.send_json(message)
        except RuntimeError:
            pass


messenger = Messenger()
