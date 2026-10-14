import re
from datetime import datetime, timedelta, timezone

import pytest
from flask import g
from werkzeug.security import generate_password_hash

from app.booking_rules import available_tables
from app.models import DiningTable, Reservation, RestaurantSettings, User

PASSWORD = "reservation-password-123"


@pytest.fixture
def history_client(database_app, database, monkeypatch):
    """Create owned and foreign history without opening hours to prove history is independent"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "history-test-secret")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    database.session.add_all([
        User(name="Guest", email="guest@example.com", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        User(name="Other", email="other@example.com", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        DiningTable(label="T1", capacity=2),
        DiningTable(label="Private table", capacity=2),
        RestaurantSettings(id=1),
    ])
    database.session.flush()
    start = datetime(2030, 1, 6, 23, 30, tzinfo=timezone.utc)
    database.session.add_all([
        Reservation(user_id=1, table_id=1, start_at=start, end_at=start + timedelta(minutes=30), party_size=2),
        Reservation(user_id=1, table_id=1, start_at=start + timedelta(hours=1), end_at=start + timedelta(hours=2), party_size=2,
                    status="canceled", canceled_at=start),
        Reservation(user_id=1, table_id=1, start_at=start - timedelta(days=3650), end_at=start - timedelta(days=3650) + timedelta(hours=1),
                    party_size=2, status="completed"),
        Reservation(user_id=2, table_id=2, start_at=start, end_at=start + timedelta(hours=1), party_size=2),
    ])
    database.session.commit()
    client = database_app.test_client()
    call(client, "post", "/auth/login", data={"email": "guest@example.com", "password": PASSWORD})
    return client


def call(client, method, path, **kwargs):
    """Discard the outer fixture's cached login user between requests"""
    g.pop("_login_user", None)
    return getattr(client, method)(path, **kwargs)


def test_history_is_owned_and_filters_by_local_start_date(history_client):
    page = call(history_client, "get", "/reservations/")
    assert page.status_code == 200
    assert b"Confirmed" in page.data and b"Canceled" in page.data and b"Completed" in page.data
    assert b"Private table" not in page.data
    filtered = call(history_client, "get", "/reservations/filter?date_from=2030-01-07&date_to=2030-01-07&status=confirmed")
    assert filtered.json["count"] == 1
    assert "2030-01-07" in filtered.json["html"] and "00:30" in filtered.json["html"]
    assert "Private table" not in filtered.json["html"]
    assert "/reservations/4/cancel" not in filtered.json["html"]


def test_reversed_date_range_returns_clear_error(history_client):
    query = "date_from=2030-01-08&date_to=2030-01-07"
    response = call(history_client, "get", f"/reservations/filter?{query}")
    assert response.status_code == 400
    assert response.json["error"]
    assert call(history_client, "get", f"/reservations/?{query}").status_code == 400


def test_cancellation_preserves_times_is_idempotent_and_releases_availability(history_client, database):
    """Cancel twice to ensure the cancellation timestamp is stable and the slot reopens"""
    reservation = database.session.get(Reservation, 1)
    start, end = reservation.start_at, reservation.end_at
    assert 1 not in {table.id for table in available_tables(start, end, 2)}
    response = call(history_client, "post", "/reservations/1/cancel", headers={"Accept": "application/json"})
    assert response.status_code == 200 and response.json["message"] == "Reservation canceled."
    database.session.expire_all()
    canceled_at = reservation.canceled_at
    assert reservation.status == "canceled" and canceled_at is not None
    assert (reservation.start_at, reservation.end_at) == (start, end)
    assert 1 in {table.id for table in available_tables(start, end, 2)}
    assert call(history_client, "post", "/reservations/1/cancel").status_code == 302
    database.session.expire_all()
    assert reservation.canceled_at == canceled_at


def test_past_completed_reservation_can_be_canceled(history_client, database):
    reservation = database.session.get(Reservation, 3)
    original_start = reservation.start_at
    assert call(history_client, "post", "/reservations/3/cancel").status_code == 302
    assert reservation.status == "canceled" and reservation.start_at == original_start


def test_other_owners_cancellation_is_denied(history_client, database, database_app):
    assert call(history_client, "post", "/reservations/4/cancel").status_code == 404
    assert database.session.get(Reservation, 4).status == "confirmed"
    anonymous = database_app.test_client()
    assert call(anonymous, "get", "/reservations/filter").status_code == 401
    assert call(anonymous, "get", "/reservations/").status_code == 302


def test_cancellation_requires_real_csrf_token(history_client, database_app, monkeypatch):
    """Read a rendered row's CSRF token and submit the normal cancellation form"""
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", True)
    assert call(history_client, "post", "/reservations/1/cancel").status_code == 400
    html = call(history_client, "get", "/reservations/").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    assert call(history_client, "post", "/reservations/1/cancel", data={"csrf_token": token}).status_code == 302
