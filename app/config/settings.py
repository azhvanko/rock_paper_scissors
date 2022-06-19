import typing as t

import structlog
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

    class Config:
        env_file = '.env'

    @property
    def SQLALCHEMY_DATABASE_URL(self) -> str:  # noqa
        return (
            f'postgresql+{self.DB_API}://{self.DB_USER}:{self.DB_USER_PASSWORD}@'
            f'{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}'
        )

    @property
    def LOGGING(self) -> dict[str, t.Any]:  # noqa
        json_params = {
            'ensure_ascii': False,
            'sort_keys': True,
        }
        if self.BATTLE_DEBUG:
            json_params['indent'] = 2

        def add_app_context(_, __, event_dict: dict[str, t.Any]) -> dict[str, t.Any]:
            # remove processors meta
            event_dict.pop('_from_structlog')
            event_dict.pop('_record')

            frame, _ = structlog._frames._find_first_app_frame_and_name(['logging', __name__])  # noqa
            event_dict['file'] = frame.f_code.co_filename
            event_dict['line'] = frame.f_lineno
            event_dict['function'] = frame.f_code.co_name

            return event_dict

        if self.BATTLE_DEBUG:
            dev_processors = [
                structlog.processors.ExceptionPrettyPrinter(),
            ]
        else:
            dev_processors = []

        processors = [
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.TimeStamper(fmt='iso'),
            add_app_context,
            *dev_processors,
            structlog.processors.JSONRenderer(**json_params),
        ]

        return {
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'json': {
                    '()': structlog.stdlib.ProcessorFormatter,
                    'processors': processors,
                },
            },
            'handlers': {
                'console': {
                    'level': 'DEBUG' if self.BATTLE_DEBUG else 'INFO',
                    'class': 'logging.StreamHandler',
                    'formatter': 'json',
                    'stream': 'ext://sys.stdout',
                },
            },
            'loggers': {
                '': {
                    'handlers': ['console',],
                    'level': 'DEBUG' if self.BATTLE_DEBUG else 'INFO',
                },
            },
        }


settings = Settings()
