import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.db import recreate_db_schema
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
async def setup():
    await recreate_db_schema(settings.SQLALCHEMY_DATABASE_URL, echo=False)
    yield
    await recreate_db_schema(settings.SQLALCHEMY_DATABASE_URL, echo=False)
