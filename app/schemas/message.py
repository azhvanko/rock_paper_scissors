import typing as t

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    action: str
    payload: t.Union[dict, list]
