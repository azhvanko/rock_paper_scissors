from datetime import datetime, timedelta

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

from app.config import settings
from app.db.base import DeclarativeBase
from app.db.models.mixins import TimeMarksMixin
from app.schemas.enum import BattleStatus


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
    @property
    def current_round(self) -> int:
        return int(self.log['current_round'])

    # meta
    __table_args__ = (
        UniqueConstraint(accept_id, name='battle_accept_id_key'),
    )
