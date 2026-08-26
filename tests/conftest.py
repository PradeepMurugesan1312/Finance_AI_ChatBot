import pytest
from fastapi.testclient import TestClient

from ahf_agent.config import Settings
from ahf_agent.server import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(agent_base_url="http://testserver", environment="test")


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
