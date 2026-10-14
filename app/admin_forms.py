"""Account administration forms with explicit role and account-state choices"""

from flask_wtf import FlaskForm
from wtforms import SelectField, SubmitField
from wtforms.validators import DataRequired

from .forms import RegisterForm

ROLE_CHOICES = [("customer", "Customer"), ("manager", "Manager"), ("administrator", "Administrator")]
STATE_CHOICES = [("active", "Active"), ("inactive", "Inactive")]


class CreateAccountForm(RegisterForm):
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Create account")


class EditAccountForm(FlaskForm):
    role = SelectField("Role", choices=ROLE_CHOICES, validators=[DataRequired()])
    state = SelectField("Account status", choices=STATE_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Save access settings")
