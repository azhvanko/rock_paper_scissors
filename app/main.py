from fastapi import FastAPI

from app.api import ws_router


app: FastAPI = FastAPI()
app.include_router(ws_router, prefix='', tags=['ws'])
