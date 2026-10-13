"""Integration fixtures operate only on an explicitly selected disposable database."""

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from flask_migrate import upgrade
from sqlalchemy.engine import make_url

from app import create_app
from app.extensions import db

MIGRATIONS = str(Path(__file__).resolve().parents[1] / "migrations")

@pytest.fixture(scope="module")
def database_app():
    """Checks the correctness of the databse URL and applies upgrade to restaurant_test table"""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL restaurant_test database")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "restaurant_test":
        pytest.fail("TEST_DATABASE_URL must select PostgreSQL database restaurant_test")
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": url})
    with app.app_context():
        upgrade(directory=MIGRATIONS)
    return app


@pytest.fixture
def database(database_app):
    """Sets up the test db table by removing all previously stored data; 
    Then gives up a `db` to some test;
    After yield, cleans the created tables"""
    with database_app.app_context():
        reset = sa.text("TRUNCATE reservations, dining_tables, opening_hours, restaurant_settings, users RESTART IDENTITY CASCADE")
        db.session.execute(reset)
        db.session.commit()
        yield db
        db.session.rollback()
        db.session.execute(reset)
        db.session.commit()
        db.session.remove()
