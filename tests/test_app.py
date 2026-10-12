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


def test_environment_configuration_and_test_overrides(monkeypatch):
    monkeypatch.setenv("FLASK_RESTAURANT_TIMEZONE", "UTC")
    assert create_app().config["RESTAURANT_TIMEZONE"] == "UTC"
    app = create_app({"TESTING": True, "RESTAURANT_TIMEZONE": "Europe/Warsaw"})
    assert app.testing is True
    assert app.config["RESTAURANT_TIMEZONE"] == "Europe/Warsaw"


def test_unknown_page_returns_not_found(client):
    assert client.get("/does-not-exist").status_code == 404
