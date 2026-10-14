import os

from flask import Flask
from sqlalchemy import URL

from .main import bp
from .extensions import db, migrate, login_manager, csrf
from . import models
from .database import register_commands
from .mail import register_mail_commands
from .auth import bp as auth_bp
from .accounts import register_account_commands


def create_app(test_config=None):
    """Creates an application with environment settings and optional test overrides"""
    app = Flask(__name__)
    app.config.from_mapping(
        RESTAURANT_NAME="Restaurant", RESTAURANT_TIMEZONE="Europe/Warsaw",
        SQLALCHEMY_DATABASE_URI=None,
        DATABASE_HOST=None, DATABASE_PORT=5432, DATABASE_NAME="restaurant",
        DATABASE_USER="restaurant", DATABASE_PASSWORD=None,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True, "connect_args": {"connect_timeout": 3}},
        MAIL_HOST="localhost", MAIL_PORT=1025, MAIL_SENDER="restaurant@example.test",
        SECRET_KEY=None, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
    )
    app.config.from_prefixed_env()
    #Passwords such as "1234" must stay strings rather than JSON-parsed values
    if "FLASK_DATABASE_PASSWORD" in os.environ:
        app.config["DATABASE_PASSWORD"] = os.environ["FLASK_DATABASE_PASSWORD"]
    
    #Secret key is used to create signatures
    if "FLASK_SECRET_KEY" in os.environ:
        app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]
    if test_config is not None:
        app.config.update(test_config)

    #if no complete database URL was supplied, but a database host was supplied, construct the URL from the separate settings
    if not app.config["SQLALCHEMY_DATABASE_URI"] and app.config["DATABASE_HOST"]:
        app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
            "postgresql+psycopg", username=app.config["DATABASE_USER"],
            password=app.config["DATABASE_PASSWORD"], host=app.config["DATABASE_HOST"],
            port=app.config["DATABASE_PORT"], database=app.config["DATABASE_NAME"],
        )

    if app.config["SQLALCHEMY_DATABASE_URI"]:
        db.init_app(app)
        migrate.init_app(app, db)
    register_commands(app)
    register_mail_commands(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    csrf.init_app(app)

    app.register_blueprint(auth_bp)
    register_account_commands(app)

    app.register_blueprint(bp)
    return app
