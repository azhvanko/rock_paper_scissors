from pydantic import BaseSettings


class Settings(BaseSettings):
    # postgres
    DB_HOST: str = 'postgres'
    DB_PORT: int = 5432
    DB_NAME: str = 'battle_db'
    DB_USER: str = 'admin'
    DB_USER_PASSWORD: str = 'password'
    DB_API: str = 'asyncpg'

    # app
    BATTLE_DEBUG: bool = False
    BATTLE_WS_HOST: str = '0.0.0.0'
    BATTLE_WS_PORT: int = 8899
    BATTLE_WS_LOOP: str = 'auto'
    BATTLE_WS_PROTOCOL_TYPE: str = 'auto'
    BATTLE_WS_PING_INTERVAL: int = 5
    BATTLE_WS_PING_TIMEOUT: int = 5
    BATTLE_OFFER_EXPIRES: int = 300  # 5 min
    BATTLE_USER_HP: int = 100
    BATTLE_USER_DAMAGE_MIN: int = 10
    BATTLE_USER_DAMAGE_MAX: int = 20
    BATTLE_USERNAME_HEADER: str = 'x-http-username'

    # TODO
    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': (
                    '[%(asctime)s] [%(levelname)-8s] [%(name)-16s] %(message)s'
                ),
                'datefmt': '%d/%m/%Y %H:%M:%S',
            },
            'verbose': {
                'format': (
                    '[%(asctime)s] [%(levelname)-8s] [%(name)-16s] '
                    '[%(module)-10s %(lineno)-4d %(funcName)-16s] %(message)s'
                ),
                'datefmt': '%d/%m/%Y %H:%M:%S',
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG' if BATTLE_DEBUG else 'INFO',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose' if BATTLE_DEBUG else 'default',
                'stream': 'ext://sys.stdout',
            },
        },
        'loggers': {
            '': {
                'handlers': ['console',],
                'level': 'DEBUG' if BATTLE_DEBUG else 'INFO',
            },
        },
    }

    class Config:
        env_file = '.env'

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:  # noqa
        return (
            f'postgresql+{self.DB_API}://{self.DB_USER}:{self.DB_USER_PASSWORD}@'
            f'{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}'
        )


settings = Settings()
