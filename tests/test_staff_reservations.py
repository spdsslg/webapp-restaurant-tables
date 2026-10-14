from datetime import datetime, timedelta, timezone

import pytest
from flask import g
from werkzeug.security import generate_password_hash

from app.booking_rules import available_tables
from app.models import DiningTable, Reservation, RestaurantSettings, User

PASSWORD = "staff-reservation-password"


@pytest.fixture
def staff_history_client(database_app, database, monkeypatch):
    """Create two customers' bookings so staff-wide access and customer privacy are distinguishable"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "staff-history-test-secret")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    database.session.add_all([
        User(name="Staff", email="staff@example.com", role="manager", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        User(name="Alice", email="alice@example.com", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        User(name="Bob", email="bob@example.com", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        DiningTable(label="T1", capacity=2), DiningTable(label="T2", capacity=4), RestaurantSettings(id=1),
    ])
    database.session.flush()
    start = datetime(2030, 1, 6, 23, 30, tzinfo=timezone.utc)
    database.session.add_all([
        Reservation(user_id=2, table_id=1, start_at=start, end_at=start + timedelta(hours=1), party_size=2),
        Reservation(user_id=3, table_id=2, start_at=start + timedelta(hours=2), end_at=start + timedelta(hours=3), party_size=3, status="completed"),
    ])
    database.session.commit()
    client = database_app.test_client()
    call(client, "post", "/auth/login", data={"email": "staff@example.com", "password": PASSWORD})
    return client


def call(client, method, path, **kwargs):
    """Discard the outer database fixture's login cache between requests"""
    g.pop("_login_user", None)
    return getattr(client, method)(path, **kwargs)


def test_customer_cannot_manage_staff_reservations_or_view_other_customers(staff_history_client, database, database_app):
    database.session.get(User, 1).role = "customer"
    database.session.commit()
    assert call(staff_history_client, "get", "/staff/reservations/").status_code == 403
    assert call(staff_history_client, "get", "/staff/reservations/filter").status_code == 403
    response = call(staff_history_client, "post", "/staff/reservations/1/cancel")
    assert response.status_code == 403
    customer = database_app.test_client()
    call(customer, "post", "/auth/login", data={"email": "alice@example.com", "password": PASSWORD})
    own = call(customer, "get", "/reservations/filter?all_customers=true")
    assert own.json["count"] == 1
    assert "T2" not in own.json["html"] and "bob@example.com" not in own.json["html"]


def test_staff_history_shows_customer_contacts_and_filters_local_date(staff_history_client):
    page = call(staff_history_client, "get", "/staff/reservations/")
    assert b"alice@example.com" in page.data and b"bob@example.com" in page.data
    assert b"scrypt:" not in page.data
    filtered = call(staff_history_client, "get", "/staff/reservations/filter?date_from=2030-01-07&date_to=2030-01-07&status=confirmed")
    assert filtered.json["count"] == 1
    assert "Alice" in filtered.json["html"] and "bob@example.com" not in filtered.json["html"]
    assert "2030-01-07" in filtered.json["html"] and "00:30" in filtered.json["html"]


def test_staff_cancellation_preserves_history_is_repeatable_and_releases_slot(staff_history_client, database):
    """Staff cancellation is an idempotent state change rather than record deletion"""
    reservation = database.session.get(Reservation, 1)
    start, end = reservation.start_at, reservation.end_at
    assert 1 not in {table.id for table in available_tables(start, end, 2)}
    response = call(staff_history_client, "post", "/staff/reservations/1/cancel", headers={"Accept": "application/json"})
    assert response.status_code == 200 and response.json["message"] == "Reservation canceled."
    timestamp = reservation.canceled_at
    assert reservation.status == "canceled" and timestamp is not None
    assert (reservation.user_id, reservation.table_id, reservation.start_at, reservation.end_at) == (2, 1, start, end)
    assert call(staff_history_client, "post", "/staff/reservations/1/cancel").status_code == 302
    assert reservation.canceled_at == timestamp
    assert 1 in {table.id for table in available_tables(start, end, 2)}


def test_staff_filters_validate_range_and_require_login(staff_history_client, database_app):
    response = call(staff_history_client, "get", "/staff/reservations/filter?date_from=2030-01-08&date_to=2030-01-07")
    assert response.status_code == 400 and response.json["error"]
    anonymous = database_app.test_client()
    assert call(anonymous, "get", "/staff/reservations/filter").status_code == 401
    assert call(anonymous, "get", "/staff/reservations/").status_code == 302
