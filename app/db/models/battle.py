import typing as t
from datetime import datetime, timedelta
from random import randint

from sqlalchemy import (
    BIGINT,
    Column,
    ForeignKey,
    text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.db.base import DeclarativeBase
from app.db.models.mixins import TimeMarksMixin
from app.schemas import BattleMove
from app.schemas.enum import BattleStatus, RockPaperScissorsChoice


class BattleUser(DeclarativeBase, TimeMarksMixin):
    __tablename__ = 'battle_user'

    # columns
    user_id = Column(BIGINT, primary_key=True, autoincrement=True)

    # relations
    offers = relationship(
        'BattleOffer',
        back_populates='user',
        uselist=True,
        order_by='desc(BattleOffer.time_created)'
    )
    accept = relationship(
        'BattleOfferAccept',
        back_populates='user',
        uselist=True,
        order_by='desc(BattleOfferAccept.time_created)'
    )


class BattleOffer(DeclarativeBase, TimeMarksMixin):
    __tablename__ = 'battle_offer'

    # columns
    offer_id = Column(BIGINT, primary_key=True, autoincrement=True)
    user_id = Column(
        BIGINT,
        ForeignKey('battle_user.user_id', onupdate='CASCADE', ondelete='CASCADE'),
        nullable=False
    )

    # relations
    user = relationship('BattleUser', foreign_keys=[user_id,], back_populates='offers')
    accept = relationship('BattleOfferAccept', back_populates='offer')

    # utils
    @hybrid_property
    def is_active(self) -> bool:
        return (
            self.time_created > (
                datetime.utcnow() - timedelta(seconds=settings.BATTLE_OFFER_EXPIRES)
            )
        )


class BattleOfferAccept(DeclarativeBase, TimeMarksMixin):
    __tablename__ = 'battle_offer_accept'

    # columns
    accept_id = Column(BIGINT, primary_key=True, autoincrement=True)
    offer_id = Column(
        BIGINT,
        ForeignKey('battle_offer.offer_id', onupdate='CASCADE', ondelete='CASCADE'),
        nullable=False
    )
    user_id = Column(
        BIGINT,
        ForeignKey('battle_user.user_id', onupdate='CASCADE', ondelete='CASCADE'),
        nullable=False
    )

    # relations
    user = relationship('BattleUser', foreign_keys=[user_id,], back_populates='accept')
    offer = relationship('BattleOffer', foreign_keys=[offer_id,], back_populates='accept')
    battle = relationship('Battle', back_populates='accept')

    # meta
    __table_args__ = (
        UniqueConstraint(offer_id, user_id, name='battle_offer_accept_offer_id_user_id_key'),
    )


class Battle(DeclarativeBase, TimeMarksMixin):
    __tablename__ = 'battle'

    # columns
    battle_id = Column(BIGINT, primary_key=True, autoincrement=True)
    accept_id = Column(
        BIGINT,
        ForeignKey('battle_offer_accept.accept_id', onupdate='CASCADE', ondelete='CASCADE'),
        nullable=False
    )
    status = Column(ENUM(BattleStatus, enum='battle_status'), nullable=False)
    log = Column(
        JSONB,
        nullable=False,
        default=dict(),
        server_default=text('\'{}\'::jsonb')
    )

    # relations
    accept = relationship(
        'BattleOfferAccept',
        foreign_keys=[accept_id,],
        back_populates='battle'
    )

    # utils
    def check_battle_move(
        self,
        move: BattleMove
    ) -> tuple[bool, t.Optional[dict[str, t.Any]]]:
        # user permissions
        if move.user_id not in self.log['users'].values():
            return False, {
                'error': 'You have not access to battle',
                'payload': {
                    'battleId': move.battle_id,
                }
            }
        # battle status
        if self.status is not BattleStatus.ACTIVE:
            return False, {
                'error': 'Battle is already over',
                'payload': {
                    'battleId': move.battle_id,
                }
            }
        # round number
        if (
            move.round != self.current_round
            or any(
                item['user_id'] == move.user_id
                for item in self.log['rounds'][str(self.current_round)]['answers']
            )
        ):
            return False, {
                'error': 'Wrong battle round number',
                'payload': {
                    'battleId': move.battle_id,
                }
            }

        return True, None

    def add_battle_move(self, move: BattleMove) -> None:
        rounds = self.log['rounds']
        current_round = str(self.current_round)
        if current_round not in rounds:
            self._add_empty_battle_round()
        rounds[current_round]['answers'].append({
            'user_id': move.user_id,
            'choice': move.choice.value,
        })
        self.log['rounds'] = rounds
        flag_modified(self, 'log')

    @property
    def is_full_battle_round(self) -> bool:
        return len(self.log['rounds'][str(self.current_round)]['answers']) == 2

    def update_battle_round_winner(self) -> None:
        battle_round: dict[str, t.Union[list[dict[str, int]], int]] = (
            self.log['rounds'][str(self.current_round)]
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
        battle_round['round_damage'] = self.random_battle_round_damage
        self.log['rounds'][str(self.current_round)] = battle_round
        flag_modified(self, 'log')

    def update_battle_winner(self) -> None:
        #TODO Refactoring
        user_ids = list(self.log['users'].values())
        users = {
            user_id: settings.BATTLE_USER_HP
            for user_id in user_ids
        }

        battle_rounds: dict[str, dict[str, t.Union[list[dict[str, int]], int]]] = self.log['rounds']
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
            self.log['winner'] = {
                'user_id': battle_winner,
            }
            self.status = BattleStatus.FINISHED
        else:
            # increase battle round counter
            self.log['current_round'] += 1
            self._add_empty_battle_round()

        flag_modified(self, 'log')

    def generate_battle_round_info(self) -> tuple[t.Sequence[int], dict[str, t.Any]]:
        #TODO Refactoring
        battle_round: dict[str, t.Union[list[dict[str, int]], int]] = (
            self.log['rounds'][str(self.current_round)]
        )
        user_ids = [
            item['user_id']
            for item in battle_round['answers']
        ]
        payload = self._generate_battle_round_info(self.current_round, battle_round)

        return user_ids, payload

    def generate_battle_info(self) -> tuple[t.Sequence[int], dict[str, t.Any]]:
        #TODO Refactoring
        user_ids = list(self.log['users'].values())
        rounds = []
        for battle_round_id, battle_round in self.log['rounds'].items():
            rounds.append(self._generate_battle_round_info(battle_round_id, battle_round))

        return user_ids, {
            'winner': {
                'userId': self.log['winner']['user_id'],
            },
            'roundCount': self.current_round + 1,
            'rounds': rounds,
        }

    @staticmethod
    def get_battle_start_log(
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

    @property
    def current_round(self) -> int:
        return int(self.log['current_round'])

    @property
    def random_battle_round_damage(self) -> int:
        return randint(settings.BATTLE_USER_DAMAGE_MIN, settings.BATTLE_USER_DAMAGE_MAX)

    def _add_empty_battle_round(self) -> None:
        rounds = self.log['rounds']
        current_round = str(self.current_round)
        if current_round not in rounds:
            rounds[current_round] = {
                'answers': [],
                'round_winner': None,
            }
        self.log['rounds'] = rounds
        flag_modified(self, 'log')

    @staticmethod
    def _generate_battle_round_info(
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

    # meta
    __table_args__ = (
        UniqueConstraint(accept_id, name='battle_accept_id_key'),
    )
