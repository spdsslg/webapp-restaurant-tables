import re
from datetime import datetime, timezone

import pytest
from flask import g
from werkzeug.security import generate_password_hash
from psycopg.errors import DeadlockDetected
from sqlalchemy.exc import OperationalError

from app.models import DiningTable, Reservation, RestaurantSettings, User

PASSWORD = "booking-password-123"


@pytest.fixture
def booking_client(database_app, database, monkeypatch):
    """Seed the disposable PostgreSQL database and freeze time before a Monday booking"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "booking-test-secret")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr("app.booking_rules.now_utc", lambda: datetime(2030, 1, 6, tzinfo=timezone.utc))
    monkeypatch.setattr("app.bookings.now_utc", lambda: datetime(2030, 1, 6, tzinfo=timezone.utc))
    assert database_app.test_cli_runner().invoke(args=["seed-demo"]).exit_code == 0
    database.session.add_all([
        User(name="Guest", email="guest@example.com", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        User(name="Other", email="other@example.com", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
    ])
    database.session.commit()
    client = database_app.test_client()
    call(client, "post", "/auth/login", data={"email": "guest@example.com", "password": PASSWORD})
    return client


def call(client, method, path, **kwargs):
    """Clear the outer database fixture's user cache to model separate requests"""
    g.pop("_login_user", None)
    return getattr(client, method)(path, **kwargs)


def booking_data(**changes):
    return {"date": "2030-01-07", "start": "09:00", "duration": "60", "party_size": "2", "table_id": "1", **changes}


@pytest.mark.parametrize("day,utc_hour", [("2030-01-07", 8), ("2030-07-01", 7)], ids=["winter", "summer"])
def test_booking_stores_utc_for_current_owner_and_protects_confirmation(booking_client, database, database_app, day, utc_hour):
    """A normal 09:00 Warsaw booking uses the correct winter or summer UTC offset"""
    response = call(booking_client, "post", "/bookings/create", data=booking_data(date=day, user_id="2"))
    assert response.status_code == 302
    reservation = database.session.scalar(database.select(Reservation))
    assert reservation.user_id == 1
    assert reservation.start_at == datetime.fromisoformat(day).replace(hour=utc_hour, tzinfo=timezone.utc)
    assert call(booking_client, "get", response.location).status_code == 200
    other_client = database_app.test_client()
    call(other_client, "post", "/auth/login", data={"email": "other@example.com", "password": PASSWORD})
    assert call(other_client, "get", response.location).status_code == 404


@pytest.mark.parametrize("changes,inactive", [
    ({"start": "09:15"}, False),
    ({"duration": "45"}, False),
    ({"date": "2030-01-05"}, False),
    ({"start": "21:30"}, False),
    ({"party_size": "9"}, False),
    ({}, True),
], ids=["invalid-slot", "invalid-duration", "past-date", "after-closing", "over-capacity", "inactive-table"])
def test_server_rejects_invalid_booking_rules(booking_client, database, changes, inactive):
    if inactive:
        database.session.get(DiningTable, 1).is_active = False
        database.session.commit()
    response = call(booking_client, "post", "/bookings/create", data=booking_data(**changes))
    assert response.status_code == 400
    assert database.session.scalar(database.select(Reservation)) is None


def test_full_interval_availability_and_back_to_back_booking(booking_client, database, database_app):
    """Availability examines the entire interval and exposes no other booking details"""
    anonymous = database_app.test_client()
    assert call(anonymous, "get", "/bookings/availability").status_code == 401
    assert call(booking_client, "post", "/bookings/create", data=booking_data(duration="120")).status_code == 302
    overlap = call(booking_client, "get", "/bookings/availability", query_string=booking_data(start="10:00"))
    assert overlap.status_code == 200
    assert "T1" not in {item["label"] for item in overlap.json["tables"]}
    assert set(overlap.json["tables"][0]) == {"id", "label", "capacity"}
    assert call(booking_client, "post", "/bookings/create", data=booking_data(start="10:00")).status_code == 409
    adjacent = call(booking_client, "get", "/bookings/availability", query_string=booking_data(start="11:00"))
    assert "T1" in {item["label"] for item in adjacent.json["tables"]}
    assert call(booking_client, "post", "/bookings/create", data=booking_data(start="11:00")).status_code == 302


def test_options_use_opening_hours_and_configured_minimum(booking_client, database):
    monday = call(booking_client, "get", "/bookings/options?date=2030-01-07&duration=180")
    assert monday.json["starts"][0] == "09:00" and monday.json["starts"][-1] == "19:00"
    assert monday.json["durations"] == [30, 60, 90, 120, 150, 180]
    weekend = call(booking_client, "get", "/bookings/options?date=2030-01-12&duration=180")
    assert weekend.json["starts"][0] == "10:00" and weekend.json["starts"][-1] == "18:00"
    database.session.get(RestaurantSettings, 1).min_duration_minutes = 60
    database.session.commit()
    changed = call(booking_client, "get", "/bookings/options?date=2030-01-07")
    assert changed.json["durations"] == [60, 90, 120, 150, 180]


def test_creation_requires_real_csrf_token(booking_client, database_app, monkeypatch):
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", True)
    assert call(booking_client, "post", "/bookings/create", data=booking_data()).status_code == 400
    html = call(booking_client, "get", "/bookings/").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    assert call(booking_client, "post", "/bookings/create", data=booking_data(csrf_token=token)).status_code == 302


def test_competing_exclusion_deadlock_returns_conflict_and_rolls_back(booking_client, database, monkeypatch):
    """Inject PostgreSQL's deadlock error at commit to verify the retry response and rollback"""
    def deadlocked_commit():
        raise OperationalError("INSERT INTO reservations", {}, DeadlockDetected("deadlock detected"))
    with monkeypatch.context() as commit_patch:
        commit_patch.setattr(database.session, "commit", deadlocked_commit)
        response = call(booking_client, "post", "/bookings/create", data=booking_data())
    assert response.status_code == 409
    assert b"Please retry" in response.data
    assert database.session.scalar(database.select(Reservation)) is None
