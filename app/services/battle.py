import json
import typing as t

from fastapi import Depends, WebSocket
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.models as m
import app.schemas as s
from app.db.session import get_db_session
from app.logging import logger
from app.schemas.enum import BattleStatus
from app.ws import messenger, Messenger


class BattleApp:
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
        )
        battle.log = battle.get_battle_start_log(
            offer_creator.user_id,
            offer_acceptor.user_id
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
        ok, message = battle.check_battle_move(move)
        if not ok:
            return await ws.send_json(message)

        # update battle round info
        battle.add_battle_move(move)
        if battle.is_full_battle_round:
            battle.update_battle_round_winner()
            await self.db_session.commit()
            user_ids, payload = battle.generate_battle_round_info()
            # send information about the finished round to users
            await self.messenger.send_to_users(user_ids, payload)
            # check if the battle is over
            battle.update_battle_winner()
            await self.db_session.commit()
            if battle.log['winner'] is not None:
                user_ids, payload = battle.generate_battle_info()
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
