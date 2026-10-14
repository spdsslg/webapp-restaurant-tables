"""Customer authentication and server-enforced role entry points"""

from functools import wraps

from flask import Blueprint, abort, current_app, redirect, render_template, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager
from .forms import LoginForm, LogoutForm, RegisterForm
from .models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.before_request
def require_account_configuration():
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI") or not current_app.secret_key:
        abort(503)


@login_manager.user_loader
def load_user(user_id):
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI"):
        return None
    try:
        identifier, version = (int(part) for part in user_id.split(":"))
    except (AttributeError, TypeError, ValueError):
        return None
    if not 0 < identifier <= 2147483647:
        return None
    user = db.session.get(User, identifier)
    return user if user is not None and user.is_active and user.auth_version == version else None


def roles_required(*roles):
    """Require authentication and one of the server-stored roles"""
    def decorator(view):
        @wraps(view)
        def checked(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return view(*args, **kwargs)
        return login_required(checked)
    return decorator


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account"))
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(name=form.name.data, email=form.email.data,
                    password_hash=generate_password_hash(form.password.data, method="scrypt"),
                    role="customer", is_active=True)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.email.errors.append("An account with this email already exists.")
        else:
            return redirect(url_for("auth.login"))
    return render_template("auth/form.html", form=form, title="Create your account")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.account"))
    form = LoginForm()
    error = None
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(email=form.email.data))
        if user is not None and user.is_active and check_password_hash(user.password_hash, form.password.data):
            session.clear()
            login_user(user)
            return redirect(url_for("auth.account"))
        error = "Invalid email or password."
    return render_template("auth/form.html", form=form, title="Sign in", error=error)


@bp.post("/logout")
@login_required
def logout():
    if not LogoutForm().validate_on_submit():
        abort(400)
    logout_user()
    session.clear()
    return redirect(url_for("main.home"))


@bp.get("/account")
@login_required
def account():
    return render_template("auth/account.html", title="Your account")


@bp.get("/staff")
@roles_required("manager", "administrator")
def staff():
    from .tables import index
    return index()


@bp.get("/admin")
@roles_required("administrator")
def admin():
    from .admin import accounts
    return accounts()
