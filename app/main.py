from flask import Blueprint, current_app, render_template
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .extensions import db

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    return render_template("main/home.html")


@bp.get("/health")
def health():
    """Report application availability; does not check external services"""
    return {"status": "ok", "scope": "application"}


@bp.get("/ready")
def ready():
    """Check database connectivity without exposing connection details"""
    if not current_app.config["SQLALCHEMY_DATABASE_URI"]:
        return {"status": "unavailable", "scope": "database"}, 503
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return {"status": "unavailable", "scope": "database"}, 503
    return {"status": "ok", "scope": "database"}
