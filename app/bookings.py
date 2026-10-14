"""Customer availability endpoints and reservation confirmation screens"""

from datetime import timedelta

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user

from .booking_forms import BookingForm
from .booking_rules import BookingError, available_tables, configuration, now_utc, options_for_date, parse_day, reserve, validated_interval
from .extensions import db, login_manager
from .models import DiningTable, Reservation

bp = Blueprint("bookings", __name__, url_prefix="/bookings")


@bp.before_request
def require_customer():
    """Require configured booking services and authenticate HTML or JSON requests"""
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI") or not current_app.secret_key:
        return {"error": "Booking is not configured yet."}, 503
    if not current_user.is_authenticated:
        if request.endpoint in ("bookings.options", "bookings.availability"):
            return {"error": "Sign in to view availability."}, 401
        return login_manager.unauthorized()


@bp.get("/")
def index():
    """Show the booking form without claiming availability before a search"""
    form = BookingForm()
    try:
        _, _, zone = configuration(now_utc().date())
        form.date.data = now_utc().astimezone(zone).date() + timedelta(days=1)
        options = options_for_date(form.date.data)
        form.duration.data = options["durations"][0]
        form.party_size.data = 2
        form.start.data = options["starts"][0] if options["starts"] else ""
    except (BookingError, OverflowError) as error:
        message = str(error) if isinstance(error, BookingError) else "Choose an earlier booking date."
        return render_template("bookings/index.html", form=form, options=None, tables=None, error=message), 503
    return render_template("bookings/index.html", form=form, options=options, tables=None, error=None)


@bp.get("/options")
def options():
    """Return start slots and allowed durations for a selected date"""
    try:
        return options_for_date(request.args.get("date"), request.args.get("duration"))
    except BookingError as error:
        return {"error": str(error)}, error.status


@bp.get("/availability")
def availability():
    """Return suitable tables without exposing other customers' reservation details"""
    try:
        start, end = validated_interval(request.args.get("date"), request.args.get("start"),
                                        request.args.get("duration"), request.args.get("party_size"))
        tables = available_tables(start, end, request.args.get("party_size"))
        _, _, zone = configuration(parse_day(request.args.get("date")))
        return {"tables": [{"id": table.id, "label": table.label, "capacity": table.capacity} for table in tables], "timezone": zone.key}
    except BookingError as error:
        return {"error": str(error)}, error.status


@bp.post("/create")
def create():
    """Validate the submitted booking and handle tables taken during the request"""
    form = BookingForm()
    error, status = "Please correct the reservation fields.", 400
    if form.validate_on_submit():
        try:
            reservation = reserve(current_user.id, form.table_id.data, form.date.data, form.start.data,
                                  form.duration.data, form.party_size.data, current_user.auth_version)
            return redirect(url_for("bookings.confirmation", identifier=reservation.id))
        except BookingError as failure:
            db.session.rollback()
            error, status = str(failure), failure.status
    try:
        choices = options_for_date(form.date.data, form.duration.data) if form.date.data else None
    except BookingError:
        choices = None
    return render_template("bookings/index.html", form=form, options=choices, tables=None, error=error), status


@bp.get("/<int:identifier>/confirmation")
def confirmation(identifier):
    """Show a saved reservation only to its owner in restaurant local time"""
    if not 0 < identifier <= 2147483647:
        abort(404)
    reservation = db.session.scalar(db.select(Reservation).where(Reservation.id == identifier, Reservation.user_id == current_user.id))
    if reservation is None:
        abort(404)
    _, _, zone = configuration(reservation.start_at.date())
    return render_template("bookings/confirmation.html", reservation=reservation,
                           table=db.session.get(DiningTable, reservation.table_id),
                           start_local=reservation.start_at.astimezone(zone), end_local=reservation.end_at.astimezone(zone), timezone=zone.key)
