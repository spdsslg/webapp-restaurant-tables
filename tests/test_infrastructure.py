"""Checks for readiness, safe connection configuration, and development email"""
import smtplib
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app
from app.extensions import db


def test_readiness_without_database_configuration():
    client = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": None,
                         "DATABASE_HOST": None}).test_client()
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json == {'status': 'unavailable', 'scope': 'database'}
    assert client.get('/health').status_code == 200


def database_app():
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI":
                       "postgresql+psycopg://unused@localhost/unused"})


def test_readiness_queries_database():
    app = database_app()
    with app.app_context(), patch.object(db.engine, 'connect') as connect:
        response = app.test_client().get('/ready')
        connect.return_value.__enter__.return_value.execute.assert_called_once()
    assert response.status_code == 200
    assert response.json == {'status': 'ok', 'scope': 'database'}


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


def test_email_failure_reports_clear_cli_error():
    app = create_app({"TESTING": True})
    with patch('app.mail.smtplib.SMTP', side_effect=smtplib.SMTPException('private error')):
        result = app.test_cli_runner().invoke(args=['send-test-email'])
    assert result.exit_code != 0
    assert 'SMTP delivery failed' in result.output
    assert 'private error' not in result.output
