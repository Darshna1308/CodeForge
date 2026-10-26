import pytest
from fastapi.testclient import TestClient

from codeforge_api.main import app

from api_helpers import register


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth(client):
    return register(client)[1]
