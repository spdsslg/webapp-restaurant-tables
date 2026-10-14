from datetime import datetime, timedelta, timezone

import pytest
from flask import g
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import DiningTable, Reservation, User

PASSWORD = "test-password-123"


@pytest.fixture
def admin_client(database_app, database, monkeypatch):
    """Use the guarded PostgreSQL fixture; shared CSRF protection is tested in test_auth"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "admin-test-only-secret")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    return database_app.test_client()

def add_user(database, email="owner@example.com", role="administrator"):
    user = User(name="Owner", email=email, password_hash=generate_password_hash(PASSWORD, method="scrypt"), role=role)
    database.session.add(user)
    database.session.commit()
    return user

def call(client, method, path, **kwargs):
    """Discard the outer fixture's cached user to simulate independent requests"""
    g.pop("_login_user", None)
    return getattr(client, method)(path, **kwargs)


def sign_in(client, email="owner@example.com"):
    return call(client, "post", "/auth/login", data={"email": email, "password": PASSWORD})

def create_data(**extra):
    return {"name": "New Manager", "email": "manager@example.com", "password": PASSWORD,
            "confirm_password": PASSWORD, "role": "manager", **extra}

@pytest.mark.parametrize("role", ["customer", "manager"])
def test_non_admin_cannot_read_or_modify_accounts(admin_client, database, role):
    user = add_user(database, role=role)
    assert call(admin_client, "get", "/admin/accounts").status_code == 302
    sign_in(admin_client)
    assert call(admin_client, "get", "/admin/accounts").status_code == 403
    assert call(admin_client, "post", "/admin/accounts/new", data=create_data()).status_code == 403
    assert call(admin_client, "post", f"/admin/accounts/{user.id}/edit", data={"role": "administrator", "state": "active"}).status_code == 403
    assert user.role == role


def test_admin_creates_hashed_account_and_filters_list(admin_client, database):
    add_user(database)
    sign_in(admin_client)
    assert call(admin_client, "get", "/admin/accounts/new").status_code == 200
    assert call(admin_client, "post", "/admin/accounts/new", data=create_data()).status_code == 302
    user = database.session.scalar(database.select(User).filter_by(email="manager@example.com"))
    assert user.role == "manager" and user.is_active
    assert check_password_hash(user.password_hash, PASSWORD)
    response = call(admin_client, "get", "/admin/accounts?role=manager&state=active&search=New")
    assert b"manager@example.com" in response.data
    assert b"owner@example.com" not in response.data

def test_invalid_role_and_duplicate_creation_show_feedback(admin_client, database):
    """Invalid selections cannot change access; duplicate inserts roll back cleanly"""
    owner = add_user(database)
    sign_in(admin_client)
    invalid = call(admin_client, "post", f"/admin/accounts/{owner.id}/edit", data={"role": "superuser", "state": "active"})
    assert invalid.status_code == 200 and b"Not a valid choice" in invalid.data
    duplicate = call(admin_client, "post", "/admin/accounts/new", data=create_data(email=owner.email))
    assert b"already exists" in duplicate.data
    assert len(database.session.scalars(database.select(User)).all()) == 1
    assert owner.role == "administrator"

def test_manager_access_changes_revoke_sessions(admin_client, database_app, database):
    """A manager's existing cookie is invalidated by any access change"""
    add_user(database)
    manager = add_user(database, "manager@example.com", "manager")
    manager_client = database_app.test_client()
    sign_in(manager_client, manager.email)
    sign_in(admin_client)
    path = f"/admin/accounts/{manager.id}/edit"
    assert call(admin_client, "post", path, data={"role": "administrator", "state": "active"}).status_code == 302
    assert manager.auth_version == 1 and manager.role == "administrator"
    assert call(manager_client, "get", "/auth/account").status_code == 302
    assert call(admin_client, "post", path, data={"role": "manager", "state": "active"}).status_code == 302
    assert manager.auth_version == 2 and manager.role == "manager"

def test_deactivation_preserves_account_and_reservation_history(admin_client, database):
    add_user(database)
    customer = add_user(database, "customer@example.com", "customer")
    table = DiningTable(label="T1", capacity=2)
    database.session.add(table)
    database.session.flush()
    start = datetime(2030, 1, 7, 12, tzinfo=timezone.utc)
    reservation = Reservation(user_id=customer.id, table_id=table.id, start_at=start, end_at=start + timedelta(hours=1), party_size=2)
    database.session.add(reservation)
    database.session.commit()
    sign_in(admin_client)
    response = call(admin_client, "post", f"/admin/accounts/{customer.id}/edit", data={"role": "customer", "state": "inactive", "email": "hijack@example.com", "name": "Injected"})
    assert response.status_code == 302
    assert not customer.is_active and customer.auth_version == 1
    assert customer.email == "customer@example.com" and customer.name == "Owner"
    assert database.session.get(Reservation, reservation.id).user_id == customer.id

@pytest.mark.parametrize("role,state", [("administrator", "inactive"), ("manager", "active")])
def test_last_active_administrator_cannot_be_removed(admin_client, database, role, state):
    owner = add_user(database)
    add_user(database, "inactive@example.com").is_active = False
    database.session.commit()
    sign_in(admin_client)
    response = call(admin_client, "post", f"/admin/accounts/{owner.id}/edit", data={"role": role, "state": state})
    assert response.status_code == 200
    assert b"At least one active administrator must remain" in response.data
    assert owner.role == "administrator" and owner.is_active and owner.auth_version == 0
