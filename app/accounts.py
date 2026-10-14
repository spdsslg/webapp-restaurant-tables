"""Create the initial administrator through a local terminal"""
import click
from email_validator import EmailNotValidError, validate_email
from flask import current_app
from flask.cli import with_appcontext
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from .extensions import db
from .models import User


@click.command("create-admin")
@click.option("--email", required=True)
@click.option("--name", required=True)
@with_appcontext
def create_admin(email, name):
    """Create the first administrator without placing a password in shell history"""
    if not current_app.config["SQLALCHEMY_DATABASE_URI"]:
        raise click.ClickException("Configure the database before creating an administrator.")
    if db.session.scalar(db.select(User.id).filter_by(role="administrator")):
        raise click.ClickException("An administrator already exists; use account management later.")
    try:
        email = validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as error:
        raise click.ClickException("Enter a valid email address.") from error
    name = name.strip()
    if not 1 <= len(name) <= 100 or len(email) > 254:
        raise click.ClickException("Name must be 1–100 characters and email at most 254.")
    password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
    if not 8 <= len(password) <= 128:
        raise click.ClickException("Password must be 8–128 characters.")
    db.session.add(User(email=email, name=name, password_hash=generate_password_hash(password),
                        role="administrator", is_active=True))
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        raise click.ClickException("That email is already registered.") from error
    click.echo("Initial administrator created.")


def register_account_commands(app):
    app.cli.add_command(create_admin)
