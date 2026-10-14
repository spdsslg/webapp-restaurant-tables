"""Validated account forms shared by server-rendered authentication screens"""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional


def normalize_email(value):
    return value.strip().lower() if value else value


class LoginForm(FlaskForm):
    email = StringField("Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=254)],
                        render_kw={"autocomplete": "email", "type": "email"})
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)],
                             render_kw={"autocomplete": "current-password"})
    submit = SubmitField("Sign in")


class RegisterForm(FlaskForm):
    name = StringField("Name", filters=[lambda value: value.strip() if value else value],
                       validators=[DataRequired(), Length(max=100)], render_kw={"autocomplete": "name"})
    email = StringField("Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=254)],
                        render_kw={"autocomplete": "email", "type": "email"})
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)],
                             render_kw={"autocomplete": "new-password"})
    confirm_password = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password")],
                                     render_kw={"autocomplete": "new-password"})
    submit = SubmitField("Create account")


class LogoutForm(FlaskForm):
    pass


class ProfileForm(FlaskForm):
    name = StringField("Name", filters=[lambda value: value.strip() if value else value],
                       validators=[DataRequired(), Length(max=100)], render_kw={"autocomplete": "name"})
    email = StringField("Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=254)],
                        render_kw={"autocomplete": "email", "type": "email"})
    current_password = PasswordField("Current password (required to change email)",
                                     validators=[Optional(), Length(max=128)],
                                     render_kw={"autocomplete": "current-password"})
    submit = SubmitField("Save contact details")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128)],
                             render_kw={"autocomplete": "new-password"})
    confirm_password = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("password")],
                                     render_kw={"autocomplete": "new-password"})
    submit = SubmitField("Reset password")


class ChangePasswordForm(ResetPasswordForm):
    current_password = PasswordField("Current password", validators=[DataRequired(), Length(max=128)],
                                     render_kw={"autocomplete": "current-password"})
    submit = SubmitField("Change password")


class ResetRequestForm(FlaskForm):
    email = StringField("Email", filters=[normalize_email], validators=[DataRequired(), Email(), Length(max=254)],
                        render_kw={"autocomplete": "email", "type": "email"})
    submit = SubmitField("Send reset link")
