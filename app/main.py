from flask import Blueprint, render_template

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    return render_template("main/home.html")


@bp.get("/health")
def health():
    """Report application availability; does not check external services."""
    return {"status": "ok", "scope": "application"}
