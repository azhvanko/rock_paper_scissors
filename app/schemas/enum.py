import enum


@enum.unique
class BattleStatus(str, enum.Enum):
    ACTIVE = 'ACTIVE'
    FINISHED = 'FINISHED'


@enum.unique
class RockPaperScissorsChoice(int, enum.Enum):
    ROCK = 0
    PAPER = 1
    SCISSORS = 2
