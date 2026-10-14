"""Checks for the local first-administrator setup command"""
from werkzeug.security import check_password_hash

from app.models import User

PASSWORD = 'test-admin-password'




def test_create_admin_hashes_password_and_normalizes_email(database_app, database):
    """Supply hidden prompt input and verify the stored account, not prompt text"""
    result = database_app.test_cli_runner().invoke(
        args=['create-admin', '--email', 'Owner@Example.com', '--name', ' Owner '],
        input=PASSWORD + '\n' + PASSWORD + '\n')
    assert result.exit_code == 0
    owner = database.session.scalar(database.select(User))
    assert (owner.email, owner.name, owner.role) == ('owner@example.com', 'Owner', 'administrator')
    assert check_password_hash(owner.password_hash, PASSWORD)
    assert PASSWORD not in result.output
