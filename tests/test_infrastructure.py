"""Check that database readiness failures return a safe unavailable response"""
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db


def database_app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI":
                       "postgresql+psycopg://unused@localhost/unused"})



def test_database_failure_returns_unavailable_without_details():
    app = database_app()
    with app.app_context(), patch.object(db.engine, 'connect', side_effect=
            OperationalError('private connection detail', {}, Exception('secret'))):
        response = app.test_client().get('/ready')
    assert response.status_code == 503
    assert response.json == {'status': 'unavailable', 'scope': 'database'}
    assert b'secret' not in response.data
