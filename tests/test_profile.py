import re

import pytest
from flask import g
from werkzeug.security import check_password_hash, generate_password_hash

from app.models import User
from app.profile import create_reset_token, update_credentials

OLD_PASSWORD = "old-password-123"
NEW_PASSWORD = "new-password-456"


@pytest.fixture
def profile_client(database_app, database, monkeypatch):
    """Uses the guarded PostgreSQL fixture and test-only configuration"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "profile-test-secret")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setitem(database_app.config, "PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setitem(database_app.config, "RESET_TOKEN_MAX_AGE", 1800)
    return database_app.test_client()


def add_user(database, email="guest@example.com", active=True):
    user = User(name="Guest", email=email, password_hash=generate_password_hash(OLD_PASSWORD, method="scrypt"), is_active=active)
    database.session.add(user)
    database.session.commit()
    return user

def call(client, method, path, **kwargs):
    """Discards the outer database fixture's user cache to model separate real requests"""
    g.pop("_login_user", None)
    return getattr(client, method)(path, **kwargs)


def sign_in(client, email="guest@example.com"):
    return call(client, "post", "/auth/login", data={"email": email, "password": OLD_PASSWORD})

def new_password_data(**extra):
    return {"password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD, **extra}

def test_profile_changes_only_current_user_fields(profile_client, database):
    owner = add_user(database)
    other = add_user(database, "other@example.com")
    assert call(profile_client, "get", "/account/profile").status_code == 302
    sign_in(profile_client)
    response = call(profile_client, "post", "/account/profile", data={
        "name": "Updated", "email": owner.email, "user_id": other.id,
        "role": "administrator", "is_active": "false",
    })
    assert response.status_code == 302
    database.session.expire_all()
    assert (owner.name, owner.role, owner.is_active, owner.auth_version) == ("Updated", "customer", True, 0)
    assert other.name == "Guest"


def test_email_change_requires_password_handles_duplicate_and_revokes_session(profile_client, database):
    user = add_user(database)
    add_user(database, "other@example.com")
    sign_in(profile_client)
    assert call(profile_client, "post", "/account/profile", data={"name": "Guest", "email": "new@example.com"}).status_code == 200
    assert user.email == "guest@example.com"
    duplicate = call(profile_client, "post", "/account/profile", data={"name": "Guest", "email": "other@example.com", "current_password": OLD_PASSWORD})
    assert b"already exists" in duplicate.data
    response = call(profile_client, "post", "/account/profile", data={"name": "Guest", "email": " NEW@example.com ", "current_password": OLD_PASSWORD})
    assert response.location.endswith("/auth/login")
    database.session.expire_all()
    assert (user.email, user.auth_version) == ("new@example.com", 1)
    assert call(profile_client, "get", "/auth/account").status_code == 302

def test_password_change_checks_old_password_and_revokes_other_session(profile_client, database_app, database):
    """Two independent browser sessions must lose access after a password change"""
    user = add_user(database)
    other_client = database_app.test_client()
    sign_in(profile_client)
    sign_in(other_client)
    wrong = call(profile_client, "post", "/account/password", data=new_password_data(current_password="wrong"))
    assert b"Current password is incorrect" in wrong.data
    response = call(profile_client, "post", "/account/password", data=new_password_data(current_password=OLD_PASSWORD))
    assert response.location.endswith("/auth/login")
    database.session.expire_all()
    assert check_password_hash(user.password_hash, NEW_PASSWORD)
    assert user.auth_version == 1
    assert call(other_client, "get", "/auth/account").status_code == 302

def test_reset_request_is_generic_and_uses_configured_origin(profile_client, database, monkeypatch):
    """Captures mail locally to inspect the reset URL without sending SMTP messages"""
    user = add_user(database)
    add_user(database, "disabled@example.com", active=False)
    sent = []
    monkeypatch.setattr("app.profile.send_email", lambda *args: sent.append(args))
    known = call(profile_client, "post", "/account/forgot-password", data={"email": user.email}, headers={"Host": "attacker.example"})
    unknown = call(profile_client, "post", "/account/forgot-password", data={"email": "unknown@example.com"}, headers={"Host": "attacker.example"})
    inactive = call(profile_client, "post", "/account/forgot-password", data={"email": "disabled@example.com"}, headers={"Host": "attacker.example"})
    assert known.status_code == unknown.status_code == inactive.status_code == 200
    message = b"If an active account matches that email, a password reset link has been sent."
    assert message in known.data and message in unknown.data and message in inactive.data
    assert len(sent) == 1
    assert sent[0][0] == user.email
    path = re.search(r"http://localhost:8000(/account/reset-password/\S+)", sent[0][2]).group(1)
    assert "attacker.example" not in sent[0][2]
    assert call(profile_client, "get", path).status_code == 200

@pytest.mark.parametrize("kind", ["invalid", "expired"])
def test_invalid_or_expired_reset_token_is_rejected(profile_client, database_app, database, monkeypatch, kind):
    """A negative expiry deterministically expires a signed token without waiting"""
    user = add_user(database)
    token = create_reset_token(user) if kind == "expired" else "invalid-signature"
    if kind == "expired":
        monkeypatch.setitem(database_app.config, "RESET_TOKEN_MAX_AGE", -1)
    assert call(profile_client, "get", f"/account/reset-password/{token}").status_code == 400
    assert call(profile_client, "post", f"/account/reset-password/{token}", data=new_password_data()).status_code == 400
    assert check_password_hash(user.password_hash, OLD_PASSWORD)

def test_reset_is_single_use_and_revokes_sessions(profile_client, database_app, database):
    user = add_user(database)
    other_client = database_app.test_client()
    sign_in(other_client)
    token = create_reset_token(user)
    path = f"/account/reset-password/{token}"
    assert call(profile_client, "get", path).status_code == 200
    assert call(profile_client, "get", path).status_code == 200
    assert user.auth_version == 0
    assert call(profile_client, "post", path, data=new_password_data()).status_code == 302
    assert call(profile_client, "post", path, data=new_password_data()).status_code == 400
    assert call(other_client, "get", "/auth/account").status_code == 302
    database.session.expire_all()
    assert user.auth_version == 1
    assert check_password_hash(user.password_hash, NEW_PASSWORD)


def test_stale_credential_update_cannot_overwrite_newer_change(profile_client, database):
    """Another database connection changes the version after this request loads the user"""
    user = add_user(database)
    identifier = user.id
    assert user.auth_version == 0
    with database.engine.begin() as connection:
        connection.execute(database.update(User).where(User.id == identifier).values(auth_version=1))
    assert not update_credentials(user, password_hash=generate_password_hash(NEW_PASSWORD, method="scrypt"))
    database.session.expire_all()
    assert user.auth_version == 1
    assert check_password_hash(user.password_hash, OLD_PASSWORD)
