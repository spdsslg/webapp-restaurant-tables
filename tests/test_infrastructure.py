"""Checks for readiness, safe connection configuration, and development email"""
from unittest.mock import MagicMock, patch

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

def test_test_email_uses_configured_smtp():
    smtp = MagicMock()
    app = create_app({"TESTING": True, "MAIL_HOST": 'mailpit', "MAIL_PORT": 1025})
    with patch('app.mail.smtplib.SMTP', return_value=smtp) as constructor:
        result = app.test_cli_runner().invoke(args=['send-test-email'])
    assert result.exit_code == 0
    constructor.assert_called_once_with('mailpit', 1025, timeout=5)
    send = smtp.__enter__.return_value.send_message
    send.assert_called_once()
    message = send.call_args.args[0]
    assert message['To'] == 'demo@example.test'
    assert message['Subject'] == 'Restaurant email test'
