import re

import pytest
from flask import g
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import User

PASSWORD = "test-password-123"


@pytest.fixture
def auth_client(database_app, database, monkeypatch):
    """Use PostgreSQL fixtures with a test-only key; CSRF has a separate enabled test"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "test-only-secret")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    return database_app.test_client()


def add_user(database, *, role="customer", active=True):
    user = User(name="Guest", email="guest@example.com", role=role, is_active=active,
                password_hash=generate_password_hash(PASSWORD, method="scrypt"))
    database.session.add(user)
    database.session.commit()
    return user


def registration(**overrides):
    return {"name": " Guest ", "email": " Guest@Example.com ", "password": PASSWORD,
            "confirm_password": PASSWORD, **overrides}


def test_registration_normalizes_and_cannot_assign_staff_role(auth_client, database):
    response = auth_client.post("/auth/register", data=registration(role="administrator", is_active="false"))
    assert response.status_code == 302
    assert response.location.endswith("/auth/login")
    user = database.session.scalar(database.select(User))
    assert (user.name, user.email, user.role, user.is_active) == ("Guest", "guest@example.com", "customer", True)
    assert user.password_hash.startswith("scrypt:")
    assert check_password_hash(user.password_hash, PASSWORD)


def test_registration_rejects_invalid_email(auth_client, database):
    response = auth_client.post("/auth/register", data=registration(email="invalid"))
    assert response.status_code == 200
    assert b'role="alert"' in response.data
    assert database.session.scalar(database.select(User)) is None


def test_duplicate_registration_rolls_back_and_shows_feedback(auth_client, database):
    """A duplicate insert must recover the session and keep just the original account"""
    add_user(database)
    response = auth_client.post("/auth/register", data=registration())
    assert response.status_code == 200
    assert b"An account with this email already exists" in response.data
    assert len(database.session.scalars(database.select(User)).all()) == 1


def test_login_rejects_wrong_password(auth_client, database):
    add_user(database)
    response = auth_client.post("/auth/login", data={"email": "guest@example.com", "password": "wrong"})
    assert response.status_code == 200
    assert b"Invalid email or password." in response.data
    with auth_client.session_transaction() as session:
        assert "_user_id" not in session


def test_login_logout_clear_session_and_ignore_external_next(auth_client, database):
    """Replace prior session state and ignore an external redirect destination"""
    add_user(database)
    with auth_client.session_transaction() as session:
        session["untrusted_marker"] = "old-session"
    response = auth_client.post("/auth/login?next=https://example.org", data={"email": " GUEST@example.com ", "password": PASSWORD})
    assert response.location.endswith("/auth/account")
    cookie = response.headers.get('Set-Cookie', '')
    assert 'HttpOnly' in cookie
    assert 'SameSite=Lax' in cookie
    with auth_client.session_transaction() as session:
        assert "_user_id" in session
        assert "untrusted_marker" not in session
    assert auth_client.get("/auth/account").status_code == 200
    assert auth_client.get("/auth/logout").status_code == 405
    assert auth_client.post("/auth/logout").status_code == 302
    with auth_client.session_transaction() as session:
        assert not session
    assert auth_client.get("/auth/account").status_code == 302


@pytest.mark.parametrize("role,staff_status,admin_status", [("customer", 403, 403), ("manager", 200, 403), ("administrator", 200, 200)])
def test_roles_enforced_by_server(auth_client, database, role, staff_status, admin_status):
    """Exercise the same protected URLs as each role, independently of navigation"""
    add_user(database, role=role)
    assert auth_client.get("/auth/staff").status_code == 302
    auth_client.post("/auth/login", data={"email": "guest@example.com", "password": PASSWORD})
    assert auth_client.get("/auth/staff").status_code == staff_status
    assert auth_client.get("/auth/admin").status_code == admin_status


def test_disabled_account_loses_existing_session(auth_client, database):
    """Clear the outer fixture context's user cache to simulate a new request context"""
    user = add_user(database)
    auth_client.post("/auth/login", data={"email": user.email, "password": PASSWORD})
    user.is_active = False
    database.session.commit()
    g.pop("_login_user", None)
    assert auth_client.get("/auth/account").status_code == 302


def test_csrf_rejects_missing_token_and_accepts_real_form_token(auth_client, database_app, monkeypatch):
    """Enable protection and reuse the browser session's actual hidden form token"""
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", True)
    assert auth_client.post("/auth/register", data=registration()).status_code == 400
    html = auth_client.get("/auth/register").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    assert auth_client.post("/auth/register", data=registration(csrf_token=token)).status_code == 302
