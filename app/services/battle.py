import json
import typing as t
from random import randint

from fastapi import Depends, WebSocket
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

import app.db.models as m
import app.schemas as s
from app.config import settings
from app.db.session import get_db_session
from app.logging import logger
from app.schemas.enum import BattleStatus, RockPaperScissorsChoice
from app.ws import messenger, Messenger


class BattleService:
    db_session: AsyncSession
    messenger: Messenger

    def __init__(self, db_session: AsyncSession = Depends(get_db_session)) -> None:
        self.db_session = db_session
        self.messenger = messenger

    async def process_message(
        self,
        message: t.Union[bytes, dict, str],
        ws: WebSocket
    ) -> None:
        data = self._parse_message(message)
        ok: bool = False

        try:
            incoming_message = s.IncomingMessage(**data)
            await self._process_message(incoming_message, ws)
            ok = True
        except ValidationError as e:
            logger.exception(e)
            await ws.send_json({
                'error': 'validationError',
                'payload': e.errors(),
            })
        except Exception as e:
            logger.exception(e)
            await ws.send_json({
                'error': 'unexpectedError',
                'payload': {
                    'message': str(e),
                },
            })
        finally:
            if not ok:
                await self.db_session.rollback()

    async def action_battles_create(self, user: dict, ws: WebSocket) -> None:
        user = s.BattleUser(**user)
        db_user = await self._get_db_user(user.user_id)
        # create new offer
        db_offer = m.BattleOffer(user=db_user)
        self.db_session.add(db_offer)
        await self.db_session.commit()

        return await ws.send_json(
            s.BattleOffer.from_orm(db_offer).dict(by_alias=True)
        )

    async def action_battles_list(self, _: t.Any, ws: WebSocket) -> None:
        _stmt = select(m.BattleOffer).where(m.BattleOffer.is_active)
        offers: list[m.BattleOffer] = (await self.db_session.execute(_stmt)).scalars().all()
        if not offers:
            return await ws.send_json([])

        await ws.send_json([
            s.BattleOffer.from_orm(offer).dict(by_alias=True)
            for offer in offers
        ])

    async def action_battles_accept(self, offer: dict, ws: WebSocket) -> None:
        offer = s.BattleOffer(**offer)
        db_offer: t.Optional[m.BattleOffer] = (
            await self.db_session.get(m.BattleOffer, offer.offer_id)
        )
        # checks
        if (
            not db_offer
            or db_offer.user_id == offer.user_id
            or not db_offer.is_active
        ):
            message = (
                'Battle offer does not exist' if not db_offer else 'Invalid battle offer'
            )
            return await ws.send_json({
                'error': message,
                'payload': {
                    'offerId': offer.offer_id,
                }
            })
        _stmt = (
            select(m.BattleOfferAccept)
                .where(
                    m.BattleOfferAccept.offer_id == offer.offer_id,
                    m.BattleOfferAccept.user_id == offer.user_id
                )
        )  # noqa
        _accept: t.Optional[m.BattleOfferAccept] = (
            (await self.db_session.execute(_stmt)).scalars().first()
        )
        if _accept:
            return await ws.send_json({
                'error': 'You already accepted this battle',
                'payload': {
                    'offerId': offer.offer_id,
                }
            })

        db_user = await self._get_db_user(offer.user_id)
        # create battle offer accept
        accept = m.BattleOfferAccept(offer_id=db_offer.offer_id, user_id=db_user.user_id)
        self.db_session.add(accept)
        await self.db_session.commit()

        return await ws.send_json(
            s.BattleOfferAccept.from_orm(accept).dict(by_alias=True)
        )

    async def action_battles_start(self, accept: dict, ws: WebSocket) -> None:
        accept = s.BattleOfferAccept(**accept)
        # checks
        db_accept: t.Optional[m.BattleOfferAccept] = (
            await self.db_session.get(m.BattleOfferAccept, accept.accept_id)
        )
        if not db_accept:
            return await ws.send_json({
                'error': 'Battle offer accept does not exist',
                'payload': {
                    'acceptId': accept.accept_id,
                }
            })
        _stmt = select(m.Battle).where(m.Battle.accept_id == db_accept.accept_id)
        _battle: t.Optional[m.Battle] = (await self.db_session.execute(_stmt)).scalars().first()
        if _battle:
            return await ws.send_json({
                'error': 'Battle has already been taken',
                'payload': {
                    'acceptId': accept.accept_id,
                }
            })

        # get battle users
        _creator_stmt = (
            select(m.BattleUser)
                .join(m.BattleOffer)
                .where(m.BattleOffer.offer_id == db_accept.offer_id)
        )  # noqa
        offer_creator: m.BattleUser = (await self.db_session.execute(_creator_stmt)).scalars().first()
        _acceptor_stmt = (
            select(m.BattleUser)
                .join(m.BattleOfferAccept)
                .where(m.BattleOfferAccept.accept_id == db_accept.accept_id)
        )  # noqa
        offer_acceptor: m.BattleUser = (await self.db_session.execute(_acceptor_stmt)).scalars().first()

        # create battle
        battle = m.Battle(
            accept_id=db_accept.accept_id,
            status=BattleStatus.ACTIVE,
            log=self._get_battle_start_log(
                offer_creator.user_id,
                offer_acceptor.user_id
            )
        )
        self.db_session.add(battle)
        await self.db_session.commit()

        return await self.messenger.send_to_users(
            [offer_creator.user_id, offer_acceptor.user_id,],
            s.Battle.from_orm(battle).dict(by_alias=True)
        )

    async def action_battles_move(self, move: dict, ws: WebSocket) -> None:
        move = s.BattleMove(**move)
        battle: t.Optional[m.Battle] = (
            await self.db_session.get(m.Battle, move.battle_id)
        )
        # checks
        if not battle:
            return await ws.send_json({
                'error': 'Battle does not exist',
                'payload': {
                    'battleId': move.battle_id,
                }
            })
        ok, message = self._check_battle_move(battle, move)
        if not ok:
            return await ws.send_json(message)

        # update battle round info
        self._add_battle_move(battle, move)
        if self._is_full_battle_round(battle):
            self._update_battle_round_winner(battle)
            await self.db_session.commit()
            user_ids, payload = self._generate_battle_round_info(battle)
            # send information about the finished round to users
            await self.messenger.send_to_users(user_ids, payload)
            # check if the battle is over
            self._update_battle_winner(battle)
            await self.db_session.commit()
            if battle.log['winner'] is not None:
                user_ids, payload = self._generate_battle_info(battle)
                # send information about the finished battle to users
                await self.messenger.send_to_users(user_ids, payload)
        else:
            await self.db_session.commit()

    @staticmethod
    def _parse_message(message: t.Union[bytes, dict, str]) -> dict[str, t.Any]:
        if isinstance(message, bytes):
            return json.loads(message.decode('utf-8'))
        if isinstance(message, str):
            return json.loads(message)

        return message

    async def _process_message(
        self,
        incoming_message: s.IncomingMessage,
        ws: WebSocket
    ) -> None:
        handler = getattr(self, f'action_{incoming_message.action}', None)
        if handler is None:
            return await ws.send_json({
                'error': 'Unexpected action',
                'payload': {
                    'action': incoming_message.action,
                }
            })

        await handler(incoming_message.payload, ws)

    async def _get_db_user(
        self,
        user_id: t.Optional[int] = None,
        user: t.Optional[s.BattleUser] = None
    ) -> m.BattleUser:
        """
        Get or create db user instance
        """
        user_id = user_id or user.user_id
        user: t.Optional[m.BattleUser] = await (
            self.db_session.get(m.BattleUser, user_id)
        )
        if user is None:
            user = m.BattleUser(user_id=user_id)
            self.db_session.add(user)
            await self.db_session.commit()

        return user

    @staticmethod
    def _get_battle_start_log(
        offer_creator_id: int,
        offer_acceptor_id: int
    ) -> dict[str, t.Any]:
        return {
            'users': {
                'offer_creator': offer_creator_id,
                'offer_acceptor': offer_acceptor_id,
            },
            'current_round': 0,
            'rounds': {
                0: {
                    'answers': [],
                    'round_winner': None,
                    'round_damage': 0,
                },
            },
            'winner': None,
        }

    @staticmethod
    def _check_battle_move(
        battle: m.Battle,
        move: s.BattleMove
    ) -> tuple[bool, t.Optional[dict[str, t.Any]]]:
        # user permissions
        if move.user_id not in battle.log['users'].values():
            return False, {
                'error': 'You have not access to battle',
                'payload': {
                    'battleId': move.battle_id,
                }
            }
        # battle status
        if battle.status is not BattleStatus.ACTIVE:
            return False, {
                'error': 'Battle is already over',
                'payload': {
                    'battleId': move.battle_id,
                }
            }
        # round number
        if (
            move.round != battle.current_round
            or any(
                item['user_id'] == move.user_id
                for item in battle.log['rounds'][str(battle.current_round)]['answers']
            )
        ):
            return False, {
                'error': 'Wrong battle round number',
                'payload': {
                    'battleId': move.battle_id,
                }
            }

        return True, None

    @staticmethod
    def _is_full_battle_round(battle: m.Battle) -> bool:
        return len(battle.log['rounds'][str(battle.current_round)]['answers']) == 2

    @staticmethod
    def _add_empty_battle_round(battle: m.Battle) -> None:
        rounds = battle.log['rounds']
        current_round = str(battle.current_round)
        if current_round not in rounds:
            rounds[current_round] = {
                'answers': [],
                'round_winner': None,
            }
        battle.log['rounds'] = rounds
        flag_modified(battle, 'log')

    def _add_battle_move(self, battle: m.Battle, move: s.BattleMove) -> None:
        rounds = battle.log['rounds']
        current_round = str(battle.current_round)
        if current_round not in rounds:
            self._add_empty_battle_round(battle)
        rounds[current_round]['answers'].append({
            'user_id': move.user_id,
            'choice': move.choice.value,
        })
        battle.log['rounds'] = rounds
        flag_modified(battle, 'log')

    def _update_battle_round_winner(self, battle: m.Battle) -> None:
        battle_round: dict[str, t.Union[list[dict[str, int]], int]] = (
            battle.log['rounds'][str(battle.current_round)]
        )
        #TODO Refactoring
        u1, u2 = battle_round['answers']
        u1_choice, u2_choice = u1['choice'], u2['choice']
        if u1_choice == u2_choice:
            return

        # find round winner
        round_winner = None
        if u1_choice == RockPaperScissorsChoice.ROCK:
            if u2_choice == RockPaperScissorsChoice.PAPER:
                round_winner = u2['user_id']
            else:
                round_winner = u1['user_id']
        elif u1_choice == RockPaperScissorsChoice.PAPER:
            if u2_choice == RockPaperScissorsChoice.ROCK:
                round_winner = u1['user_id']
            else:
                round_winner = u2['user_id']
        elif u1_choice == RockPaperScissorsChoice.SCISSORS:
            if u2_choice == RockPaperScissorsChoice.ROCK:
                round_winner = u2['user_id']
            else:
                round_winner = u1['user_id']

        # update round winner
        battle_round['round_winner'] = round_winner
        battle_round['round_damage'] = self._random_battle_round_damage()
        battle.log['rounds'][str(battle.current_round)] = battle_round
        flag_modified(battle, 'log')

    def _generate_battle_round_info(
        self,
        battle: m.Battle
    ) -> tuple[t.Sequence[int], dict[str, t.Any]]:
        #TODO Refactoring
        battle_round: dict[str, t.Union[list[dict[str, int]], int]] = (
            battle.log['rounds'][str(battle.current_round)]
        )
        user_ids = [
            item['user_id']
            for item in battle_round['answers']
        ]
        payload = self._get_battle_round_info(battle.current_round, battle_round)

        return user_ids, payload

    @staticmethod
    def _get_battle_round_info(
        round_id: t.Union[int, str],
        battle_round: dict[str, t.Union[list[dict[str, int]], int]]
    ) -> dict[str, t.Any]:
        return {
            'roundId': int(round_id),
            'roundWinner': {
                'userId': battle_round['round_winner'],
            },
            'roundDamage': battle_round['round_damage'],
            'answers': [
                {
                    'userId': item['user_id'],
                    'choice': item['choice'],
                }
                for item in battle_round['answers']
            ],
        }

    def _update_battle_winner(self, battle: m.Battle) -> None:
        #TODO Refactoring
        user_ids = list(battle.log['users'].values())
        users = {
            user_id: settings.BATTLE_USER_HP
            for user_id in user_ids
        }

        battle_rounds: dict[str, dict[str, t.Union[list[dict[str, int]], int]]] = battle.log['rounds']
        for battle_round in battle_rounds.values():
            if battle_round['round_winner'] is None:
                continue

            user_id = user_ids[1] if battle_round['round_winner'] == user_ids[0] else user_ids[0]
            # update user hp
            users[user_id] -= battle_round['round_damage']

        battle_winner = None
        for user_id, user_hp in users.items():
            if user_hp <= 0:
                battle_winner = user_ids[1] if user_id == user_ids[0] else user_ids[0]
                break

        if battle_winner is not None:
            battle.log['winner'] = {
                'user_id': battle_winner,
            }
            self.status = BattleStatus.FINISHED
        else:
            # increase battle round counter
            battle.log['current_round'] += 1
            self._add_empty_battle_round(battle)

        flag_modified(battle, 'log')

    def _generate_battle_info(self, battle: m.Battle) -> tuple[t.Sequence[int], dict[str, t.Any]]:
        #TODO Refactoring
        user_ids = list(battle.log['users'].values())
        rounds = []
        for battle_round_id, battle_round in battle.log['rounds'].items():
            rounds.append(self._get_battle_round_info(battle_round_id, battle_round))

        return user_ids, {
            'winner': {
                'userId': battle.log['winner']['user_id'],
            },
            'roundCount': battle.current_round + 1,
            'rounds': rounds,
        }

    @staticmethod
    def _random_battle_round_damage() -> int:
        return randint(settings.BATTLE_USER_DAMAGE_MIN, settings.BATTLE_USER_DAMAGE_MAX)
