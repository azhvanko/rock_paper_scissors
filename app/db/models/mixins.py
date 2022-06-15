from datetime import datetime

from sqlalchemy import (
    Column,
    text,
    TIMESTAMP,
)


class TimeMarksMixin:
    time_created = Column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow,
        server_default=text('CURRENT_TIMESTAMP')
    )
