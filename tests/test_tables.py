from datetime import datetime, timedelta, timezone

import pytest
from flask import g
from werkzeug.security import generate_password_hash

from app.booking_rules import available_tables
from app.models import DiningTable, Reservation, User

PASSWORD = "table-test-password"


@pytest.fixture
def table_client(database_app, database, monkeypatch):
    """Prepare staff, a customer, and two physical tables in the guarded test database"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "table-test-secret")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    database.session.add_all([
        User(name="Manager", email="staff@example.com", role="manager", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        User(name="Customer", email="customer@example.com", password_hash=generate_password_hash(PASSWORD, method="scrypt")),
        DiningTable(label="T1", capacity=2), DiningTable(label="T2", capacity=4),
    ])
    database.session.commit()
    client = database_app.test_client()
    sign_in(client)
    return client


def call(client, method, path, **kwargs):
    """Discard the outer database fixture's login cache between requests"""
    g.pop("_login_user", None)
    return getattr(client, method)(path, **kwargs)


def sign_in(client):
    return call(client, "post", "/auth/login", data={"email": "staff@example.com", "password": PASSWORD})


def test_customer_cannot_read_or_modify_tables(table_client, database):
    database.session.get(User, 1).role = "customer"
    database.session.commit()
    assert call(table_client, "get", "/staff/tables/").status_code == 403
    assert call(table_client, "post", "/staff/tables/new", data={"label": "T3", "capacity": "4"}).status_code == 403
    assert call(table_client, "post", "/staff/tables/1/edit", data={"label": "T1", "state": "active"}).status_code == 403


def test_create_table_trims_label_and_handles_duplicates(table_client, database):
    assert call(table_client, "post", "/staff/tables/new", data={"label": " T3 ", "capacity": "7"}).status_code == 302
    created = database.session.scalar(database.select(DiningTable).filter_by(label="T3"))
    assert created.capacity == 7 and created.is_active
    duplicate = call(table_client, "post", "/staff/tables/new", data={"label": "T3", "capacity": "2"})
    assert duplicate.status_code == 200 and b"already exists" in duplicate.data
    duplicate_edit = call(table_client, "post", "/staff/tables/1/edit", data={"label": "T2", "state": "active"})
    assert duplicate_edit.status_code == 200 and b"already exists" in duplicate_edit.data
    assert database.session.get(DiningTable, 1).label == "T1"


def test_rename_deactivate_and_reactivate_preserve_capacity_and_bookings(table_client, database):
    """A table with history can change label and status while keeping its capacity and booking times"""
    start = datetime(2030, 1, 7, 8, tzinfo=timezone.utc)
    reservation = Reservation(user_id=2, table_id=1, start_at=start, end_at=start + timedelta(hours=1), party_size=2)
    database.session.add(reservation)
    database.session.commit()
    response = call(table_client, "post", "/staff/tables/1/edit", data={"label": "Window table", "state": "inactive", "capacity": "99"})
    assert response.status_code == 302
    table = database.session.get(DiningTable, 1)
    assert (table.label, table.capacity, table.is_active) == ("Window table", 2, False)
    assert reservation.table_id == table.id and reservation.start_at == start
    after = start + timedelta(hours=2)
    assert 1 not in {item.id for item in available_tables(after, after + timedelta(hours=1), 2)}
    assert call(table_client, "post", "/staff/tables/1/edit", data={"label": "Window table", "state": "active"}).status_code == 302
    assert 1 in {item.id for item in available_tables(after, after + timedelta(hours=1), 2)}
    assert table.capacity == 2


def test_invalid_creation_fields_do_not_create_table(table_client, database):
    response = call(table_client, "post", "/staff/tables/new", data={"label": " ", "capacity": "-1"})
    assert response.status_code == 200
    assert b"This field is required" in response.data and b"Number must be" in response.data
    assert len(database.session.scalars(database.select(DiningTable)).all()) == 2
