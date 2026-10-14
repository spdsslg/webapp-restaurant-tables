"""CSRF protection for reservation cancellation without editable booking fields"""

from flask_wtf import FlaskForm


class CancelForm(FlaskForm):
    pass
