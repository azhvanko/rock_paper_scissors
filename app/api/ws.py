import typing as t

from fastapi import (
    APIRouter,
    Depends,
    status,
    WebSocket,
    WebSocketDisconnect,
)

from app.config import settings
from app.logging import logger
from app.services import BattleApp
from app.ws import messenger


router = APIRouter()


async def get_user_id(websocket: WebSocket) -> t.Optional[int]:
    #TODO Token-based authentication
    user_id: t.Optional[str] = websocket.headers.get(settings.BATTLE_USERNAME_HEADER, None)
    # check if websocket has valid username header
    if isinstance(user_id, str) and user_id.isdigit():
        return int(user_id)

    websocket.send_json({  # noqa
        'error': 'Invalid username. Username must be a positive integer',
    })
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


@router.websocket("/")
async def websocket_endpoint(
    websocket: WebSocket,
    battle_service: BattleApp = Depends(),
    user_id: t.Optional[int] = Depends(get_user_id),
):
    if user_id is None:
        return

    await websocket.accept()

    try:
        messenger.connect(user_id, websocket)
        while True:
            data: str = await websocket.receive_text()
            await battle_service.process_message(data, websocket)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception(e)
    finally:
        messenger.disconnect(user_id, websocket)
