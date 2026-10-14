from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

from flask import g
from werkzeug.security import generate_password_hash

from app import booking_rules
from app.models import DiningTable, Reservation, User


def test_simultaneous_bookings_confirm_only_one_reservation(database_app, database, monkeypatch):
    """Both requests see the table as free before PostgreSQL resolves their inserts"""
    monkeypatch.setitem(database_app.config, "SECRET_KEY", "booking-concurrency-test-only")
    monkeypatch.setitem(database_app.config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(booking_rules, "now_utc", lambda: datetime(2030, 1, 6, tzinfo=timezone.utc))
    assert database_app.test_cli_runner().invoke(args=["seed-demo"]).exit_code == 0
    table_id = database.session.scalar(database.select(DiningTable.id).where(DiningTable.label == "T1"))
    users = [User(name=name, email=f"{name}@example.com", password_hash=generate_password_hash("booking-test-password"))
             for name in ("first", "second")]
    database.session.add_all(users)
    database.session.commit()
    clients = [database_app.test_client(), database_app.test_client()]
    for client, user in zip(clients, users):
        g.pop("_login_user", None)
        assert client.post("/auth/login", data={"email": user.email, "password": "booking-test-password"}).status_code == 302

    ready = Barrier(2)
    original = booking_rules.available_tables

    def both_observe_availability(*args):
        tables = original(*args)
        assert table_id in {table.id for table in tables}
        ready.wait(timeout=10)
        return tables

    monkeypatch.setattr(booking_rules, "available_tables", both_observe_availability)
    data = {"date": "2030-01-07", "start": "12:00", "duration": 60, "party_size": 2, "table_id": table_id}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.post, "/bookings/create", data=data) for client in clients]
        responses = [future.result(timeout=15) for future in futures]
    assert sorted(response.status_code for response in responses) == [302, 409]
    database.session.expire_all()
    assert database.session.scalar(database.select(database.func.count()).select_from(Reservation)) == 1
