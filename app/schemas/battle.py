from pydantic import (
    BaseConfig,
    BaseModel,
    Field,
    validator,
)

from app.schemas.enum import RockPaperScissorsChoice


def _alias_generator(field: str) -> str:
    words = field.split('_')
    if len(words) == 1:
        return words[0].lower()

    return ''.join([words[0], *[s.capitalize() for s in words[1:]]])


# base
class BaseBattleConfig(BaseConfig):
    orm_mode = True
    allow_population_by_field_name = True
    alias_generator = _alias_generator


class BaseBattleUser(BaseModel):
    user_id: int = Field(..., alias='userId')


class BaseBattleOffer(BaseModel):
    offer_id: int = Field(..., alias='offerId')


class BaseBattleOfferAccept(BaseModel):
    accept_id: int = Field(..., alias='acceptId')


class BaseBattle(BaseModel):
    battle_id: int = Field(..., alias='battleId')


# plain
class BattleMove(BaseBattle, BaseBattleUser):
    round: int
    choice: RockPaperScissorsChoice

    @validator('round')
    def _round(cls, value: int) -> int:  # noqa
        if value < 0:
            raise ValueError('Round number must be a positive integer')
        return value


# orm
class BattleUser(BaseBattleUser):
    class Config(BaseBattleConfig):
        pass


class BattleOffer(BaseBattleUser, BaseBattleOffer):
    class Config(BaseBattleConfig):
        pass


class BattleOfferAccept(BaseBattleOffer, BaseBattleOfferAccept):
    class Config(BaseBattleConfig):
        pass


class Battle(BaseBattle):
    class Config(BaseBattleConfig):
        pass
