from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from flask import g
from werkzeug.security import generate_password_hash

from app import admin
from app.models import User


def test_simultaneous_admin_demotions_leave_one_active_admin(database_app, database, monkeypatch):
    """Hold the database lock until both requests arrive, then let them compete"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "admin-concurrency-test-only")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    users = [User(name=name, email=f"{name}@example.com", role="administrator",
                  password_hash=generate_password_hash("admin-test-password")) for name in ("owner", "other")]
    database.session.add_all(users)
    database.session.commit()
    identifiers = [user.id for user in users]
    clients = [database_app.test_client(), database_app.test_client()]
    for client, user in zip(clients, users):
        g.pop("_login_user", None)
        assert client.post("/auth/login", data={"email": user.email, "password": "admin-test-password"}).status_code == 302

    arriving = Queue()
    original = admin.locked_accounts

    def signal_arrival(target_id=None):
        arriving.put(target_id)
        return original(target_id)

    monkeypatch.setattr(admin, "locked_accounts", signal_arrival)
    with ThreadPoolExecutor(max_workers=2) as executor:
        with database.engine.begin() as connection:
            connection.execute(database.select(database.func.pg_advisory_xact_lock(admin.ADMIN_LOCK_KEY)))
            futures = [executor.submit(client.post, f"/admin/accounts/{identifier}/edit",
                                       data={"role": "manager", "state": "active"})
                       for client, identifier in zip(clients, identifiers)]
            arriving.get(timeout=10)
            arriving.get(timeout=10)
        responses = [future.result(timeout=10) for future in futures]
    assert sorted(response.status_code for response in responses) == [200, 302]
    assert any(b"At least one active administrator" in response.data for response in responses)
    database.session.expire_all()
    assert database.session.scalar(database.select(database.func.count()).select_from(User).where(
        User.role == "administrator", User.is_active.is_(True))) == 1
