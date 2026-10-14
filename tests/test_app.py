import pytest

from app import create_app

#creates a client for all the tests
@pytest.fixture
def client():
    return create_app({"TESTING": True}).test_client()


def test_health_reports_only_application_status(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok", "scope": "application"}
