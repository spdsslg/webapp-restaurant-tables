"""Booking inputs validated independently of the browser's availability results"""

from flask_wtf import FlaskForm
from wtforms import DateField, IntegerField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange


class BookingForm(FlaskForm):
    date = DateField("Date", validators=[DataRequired()])
    start = StringField("Start time", validators=[DataRequired(), Length(min=5, max=5)])
    duration = IntegerField("Duration (minutes)", validators=[DataRequired(), NumberRange(min=1, max=180)])
    party_size = IntegerField("Party size", validators=[DataRequired(), NumberRange(min=1, max=2147483647)])
    table_id = IntegerField("Table", validators=[DataRequired(), NumberRange(min=1, max=2147483647)])
    submit = SubmitField("Reserve table")
