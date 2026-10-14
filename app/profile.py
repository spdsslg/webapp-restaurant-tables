"""Profile updates and password recovery with versioned, expiring reset links"""

import smtplib

from flask import Blueprint, abort, current_app, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, logout_user
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db
from .forms import ChangePasswordForm, ProfileForm, ResetPasswordForm, ResetRequestForm
from .mail import send_email
from .models import User

bp = Blueprint("profile", __name__, url_prefix="/account")
RESET_MESSAGE = "If an active account matches that email, a password reset link has been sent."


@bp.before_request
def require_account_configuration():
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI") or not current_app.secret_key:
        abort(503)


def reset_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt="password-reset")


def create_reset_token(user):
    return reset_serializer().dumps({"id": user.id, "version": user.auth_version})


def reset_user(token):
    try:
        data = reset_serializer().loads(token, max_age=current_app.config["RESET_TOKEN_MAX_AGE"])
        if not isinstance(data, dict) or type(data.get("id")) is not int or type(data.get("version")) is not int:
            return None
        if not 0 < data["id"] <= 2147483647 or data["version"] < 0:
            return None
    except BadSignature:
        return None
    user = db.session.get(User, data["id"])
    return user if user and user.is_active and user.auth_version == data["version"] else None


def end_account_session():
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


def update_credentials(user, **values):
    """Only one request using the current account version can change credentials"""
    result = db.session.execute(db.update(User).where(
        User.id == user.id, User.auth_version == user.auth_version, User.is_active.is_(True),
    ).values(**values, auth_version=User.auth_version + 1))
    if result.rowcount != 1:
        db.session.rollback()
        return False
    db.session.commit()
    return True


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def edit():
    form = ProfileForm()
    if request.method == "GET":
        form.name.data = current_user.name
        form.email.data = current_user.email
    error = None
    if form.validate_on_submit():
        email_changed = form.email.data != current_user.email
        if email_changed and not check_password_hash(current_user.password_hash, form.current_password.data or ""):
            form.current_password.errors.append("Enter your current password to change your email.")
        else:
            try:
                if email_changed:
                    if update_credentials(current_user, name=form.name.data, email=form.email.data):
                        return end_account_session()
                    error = "Your account changed. Please sign in again."
                else:
                    current_user.name = form.name.data
                    db.session.commit()
                    return redirect(url_for("auth.account"))
            except IntegrityError:
                db.session.rollback()
                form.email.errors.append("An account with this email already exists.")
    return render_template("auth/form.html", form=form, title="Edit profile", error=error)


@bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    error = None
    if form.validate_on_submit():
        if not check_password_hash(current_user.password_hash, form.current_password.data):
            form.current_password.errors.append("Current password is incorrect.")
        elif update_credentials(current_user, password_hash=generate_password_hash(form.password.data, method="scrypt")):
            return end_account_session()
        else:
            error = "Your account changed. Please sign in again."
    return render_template("auth/form.html", form=form, title="Change password", error=error)


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    form = ResetRequestForm()
    message = None
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(email=form.email.data, is_active=True))
        if user is not None:
            path = url_for("profile.reset_password", token=create_reset_token(user))
            link = current_app.config["PUBLIC_BASE_URL"].rstrip("/") + path
            try:
                send_email(user.email, "Reset your restaurant password",
                           f"To reset your password, open this link:\n{link}\n\nIf you did not request this, ignore this email.")
            except (OSError, smtplib.SMTPException):
                current_app.logger.warning("Password reset email delivery failed")
        message = RESET_MESSAGE
    return render_template("auth/form.html", form=form, title="Forgot password", message=message)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = reset_user(token)
    if user is None:
        return render_template("auth/reset_invalid.html"), 400
    form = ResetPasswordForm()
    if form.validate_on_submit():
        if not update_credentials(user, password_hash=generate_password_hash(form.password.data, method="scrypt")):
            return render_template("auth/reset_invalid.html"), 400
        return end_account_session()
    return render_template("auth/form.html", form=form, title="Reset password")
