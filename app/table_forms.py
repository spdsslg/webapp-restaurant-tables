"""Validated staff inputs with table capacity editable only during creation"""

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange


def trimmed(value):
    return value.strip() if value else value


class CreateTableForm(FlaskForm):
    label = StringField("Table label", filters=[trimmed], validators=[DataRequired(), Length(max=30)])
    capacity = IntegerField("Capacity", validators=[DataRequired(), NumberRange(min=1, max=2147483647)])
    submit = SubmitField("Create table")


class EditTableForm(FlaskForm):
    label = StringField("Table label", filters=[trimmed], validators=[DataRequired(), Length(max=30)])
    state = SelectField("Status", choices=[("active", "Active"), ("inactive", "Inactive")], validators=[DataRequired()])
    submit = SubmitField("Save table")
