from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from flask_migrate import downgrade, upgrade

from app.models import DiningTable, OpeningHours, Reservation, RestaurantSettings, User


@pytest.fixture
def booking(database):
    """Creates a customer and table, then returns a dictionary of reservation fields"""
    user = User(email="guest@example.test", password_hash="test-only-hash", name="Guest")
    table = DiningTable(label="T1", capacity=4, x=80, y=80)
    database.session.add_all([user, table])
    database.session.commit()
    start = datetime(2030, 1, 7, 12, tzinfo=timezone.utc)
    return dict(user_id=user.id, table_id=table.id, start_at=start,
                end_at=start + timedelta(hours=1), party_size=2)


def test_seed_is_idempotent_and_preserves_staff_changes(database_app, database):
    runner = database_app.test_cli_runner()
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    settings = database.session.get(RestaurantSettings, 1)
    settings.min_duration_minutes = 60
    database.session.commit()
    assert runner.invoke(args=["seed-demo"]).exit_code == 0
    database.session.expire_all()
    assert settings.min_duration_minutes == 60
    assert settings.timezone == "Europe/Warsaw"
    assert database.session.scalar(sa.select(sa.func.count()).select_from(DiningTable)) == 8
    assert database.session.scalar(sa.select(sa.func.count()).select_from(OpeningHours)) == 7
    assert database.session.get(OpeningHours, 0).opens_at.hour == 9
    assert database.session.get(OpeningHours, 6).closes_at.hour == 21
    assert database.session.scalar(sa.select(sa.func.count()).select_from(User)) == 0


def test_reservation_round_trip_preserves_aware_timestamps(database, booking):
    reservation = Reservation(**booking)
    database.session.add(reservation)
    database.session.commit()
    database.session.expire_all()
    assert reservation.start_at == booking["start_at"]
    assert reservation.created_at.utcoffset() is not None
    assert reservation.status == "confirmed"


def test_back_to_back_allowed_but_overlap_rejected(database, booking):
    first = Reservation(**booking)
    adjacent = Reservation(**{**booking, "start_at": booking["end_at"],
                              "end_at": booking["end_at"] + timedelta(hours=1)})
    database.session.add_all([first, adjacent])
    database.session.commit()
    database.session.add(Reservation(**{**booking, "start_at": booking["start_at"] + timedelta(minutes=30)}))
    with pytest.raises(IntegrityError, match="reservation_no_overlap"):
        database.session.commit()


def test_cancellation_preserves_record_and_releases_interval(database, booking):
    original = Reservation(**booking)
    database.session.add(original)
    database.session.commit()
    original.status = "canceled"
    original.canceled_at = datetime.now(timezone.utc)
    database.session.commit()
    database.session.add(Reservation(**booking))
    database.session.commit()
    assert original.start_at == booking["start_at"]
    assert original.status == "canceled"
    assert database.session.scalar(sa.select(sa.func.count()).select_from(Reservation)) == 2


def test_database_rejects_duration_above_three_hours(database, booking):
    database.session.add(Reservation(**{**booking, "end_at": booking["start_at"] + timedelta(minutes=181)}))
    with pytest.raises(IntegrityError, match="reservation_interval"):
        database.session.commit()


def test_referenced_table_cannot_be_deleted(database, booking):
    database.session.add(Reservation(**booking))
    database.session.commit()
    # PostgreSQL checks RESTRICT at statement execution, not just commit.
    with pytest.raises(IntegrityError):
        database.session.execute(sa.delete(DiningTable).where(DiningTable.id == booking["table_id"]))


def test_database_rejects_invalid_settings_bounds(database):
    database.session.add(RestaurantSettings(id=1, min_duration_minutes=181))
    with pytest.raises(IntegrityError, match="settings_duration_bounds"):
        database.session.commit()



