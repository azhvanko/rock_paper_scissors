import pytest
from fastapi import WebSocketDisconnect

from app.config import settings


def test_ws_auth_without_user_headers(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/'):
            pass


def test_ws_auth_with_user_headers(client):
    user_id = 1
    headers = {
        settings.BATTLE_USERNAME_HEADER: str(user_id),
    }

    with client.websocket_connect('/', headers=headers) as websocket:
        payload = {
            'action': 'battles_create',
            'payload': {
                'userId': user_id,
            }
        }
        websocket.send_json(payload)
        data: dict = websocket.receive_json()

        assert 'userId' in data and data['userId'] == user_id, data
