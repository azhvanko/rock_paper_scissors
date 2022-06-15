import uvicorn

from app.config import settings


uvicorn.run(
    'app.main:app',
    host=settings.BATTLE_WS_HOST,
    port=settings.BATTLE_WS_PORT,
    loop=settings.BATTLE_WS_LOOP,
    ws=settings.BATTLE_WS_PROTOCOL_TYPE,
    ws_ping_interval=settings.BATTLE_WS_PING_INTERVAL,
    ws_ping_timeout=settings.BATTLE_WS_PING_TIMEOUT,
    log_config=settings.LOGGING,
    reload=settings.BATTLE_DEBUG
)
