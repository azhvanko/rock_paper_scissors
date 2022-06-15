import typing as t
from time import sleep

from app.config import settings


def test_battle(client):
    # user ids
    john = 1
    jack = 2

    with client.websocket_connect('/', headers={settings.BATTLE_USERNAME_HEADER: str(john)}) as john_ws:
        with client.websocket_connect('/', headers={settings.BATTLE_USERNAME_HEADER: str(jack)}) as jack_ws:
            # create offer
            payload = {
                'action': 'battles_create',
                'payload': {
                    'userId': john,
                }
            }
            john_ws.send_json(payload)
            offer: dict[str, int] = john_ws.receive_json()

            assert 'userId' in offer and offer['userId'] == john, offer
            offer_id = offer['offerId']

            # get list offers
            payload = {
                'action': 'battles_list',
                'payload': {},
            }
            jack_ws.send_json(payload)
            offers: list[dict[str, int]] = jack_ws.receive_json()

            assert offers, offers
            assert offers[0]['offerId'] == offer_id, (offer, offers,)

            # accept offer
            payload = {
                'action': 'battles_accept',
                'payload': {
                    'userId': jack,
                    'offerId': offer_id,
                }
            }
            jack_ws.send_json(payload)
            accept: dict[str, int] = jack_ws.receive_json()

            assert accept['offerId'] == offer_id, (offer, accept,)
            accept_id = accept['acceptId']

            # start battle
            payload = {
                'action': 'battles_start',
                'payload': {
                    'acceptId': accept_id,
                    'offerId': offer_id,
                }
            }
            jack_ws.send_json(payload)
            john_battle: dict[str, int] = john_ws.receive_json()
            jack_battle: dict[str, int] = jack_ws.receive_json()

            assert (
                john_battle == jack_battle
                and 'battleId' in john_battle,
                (john_battle, jack_battle)
            )
            battle_id = john_battle['battleId']

            # John always winning
            battle_round = 0
            battle_result = None
            while battle_round <= settings.BATTLE_USER_HP // settings.BATTLE_USER_DAMAGE_MIN:
                # John is moving
                payload = {
                    'action': 'battles_move',
                    'payload': {
                        'userId': john,
                        'battleId': battle_id,
                        'round': battle_round,
                        'choice': 0,  # rock
                    }
                }
                john_ws.send_json(payload)
                sleep(0.75)  # TODO

                # Jack is moving
                payload = {
                    'action': 'battles_move',
                    'payload': {
                        'userId': jack,
                        'battleId': battle_id,
                        'round': battle_round,
                        'choice': 2,  # scissors
                    }
                }
                jack_ws.send_json(payload)
                sleep(0.75)  # TODO

                # get round info
                john_round: dict[str, t.Any] = john_ws.receive_json()
                jack_round: dict[str, t.Any] = jack_ws.receive_json()
                assert john_round == jack_round, (john_round, jack_round,)

                if 'winner' in john_round:
                    battle_result = john_round
                    break

                battle_round += 1

            assert battle_result is not None, battle_round
            assert battle_result['winner']['userId'] == john, battle_result
            assert battle_result['roundCount'] == battle_round, (battle_round, battle_result,)
