"""Customer-owned reservation history, local-date filters, and cancellation"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .booking_rules import BookingError, parse_day
from .extensions import db, login_manager
from .models import DiningTable, Reservation, RestaurantSettings
from .reservation_forms import CancelForm

bp = Blueprint("reservations", __name__, url_prefix="/reservations")
STATUSES = ("confirmed", "canceled", "completed")


def wants_json():
    return request.endpoint == "reservations.filter_history" or request.accept_mimetypes.best == "application/json"


@bp.before_request
def require_customer():
    """Require authentication without redirecting asynchronous requests to a login page"""
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI") or not current_app.secret_key:
        return {"error": "Reservation history is not configured yet."}, 503
    if not current_user.is_authenticated:
        if wants_json():
            return {"error": "Sign in to view your reservations."}, 401
        return login_manager.unauthorized()


def history_rows():
    """Filter only the signed-in customer's bookings by their local start date"""
    settings = db.session.get(RestaurantSettings, 1)
    try:
        if settings is None:
            raise ValueError
        zone = ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise BookingError("The restaurant timezone is not configured yet.", 503) from None
    start_text, end_text = request.args.get("date_from", ""), request.args.get("date_to", "")
    status = request.args.get("status", "")
    if status not in ("", *STATUSES):
        raise BookingError("Choose a valid reservation status.")
    start_day = parse_day(start_text) if start_text else None
    end_day = parse_day(end_text) if end_text else None
    if start_day and end_day and start_day > end_day:
        raise BookingError("The start date must not be after the end date.")
    query = db.select(Reservation, DiningTable).join(DiningTable, Reservation.table_id == DiningTable.id).where(Reservation.user_id == current_user.id)
    try:
        if start_day:
            lower = datetime.combine(start_day, time(), zone).astimezone(timezone.utc)
            query = query.where(Reservation.start_at >= lower)
        if end_day:
            upper = datetime.combine(end_day + timedelta(days=1), time(), zone).astimezone(timezone.utc)
            query = query.where(Reservation.start_at < upper)
    except (ValueError, OverflowError):
        raise BookingError("Choose dates within the supported calendar range.") from None
    if status:
        query = query.where(Reservation.status == status)
    records = db.session.execute(query.order_by(Reservation.start_at.desc(), Reservation.id.desc())).all()
    rows = [{"reservation": reservation, "table": table, "start_local": reservation.start_at.astimezone(zone),
             "end_local": reservation.end_at.astimezone(zone)} for reservation, table in records]
    return rows, zone.key


@bp.get("/")
def index():
    """Render all owned reservation history with optional initial filters"""
    error, status = None, 200
    try:
        rows, zone = history_rows()
    except BookingError as failure:
        rows, zone, error, status = [], "", str(failure), failure.status
    return render_template("reservations/index.html", rows=rows, timezone=zone, error=error,
                           statuses=STATUSES, cancel_form=CancelForm()), status


@bp.get("/filter")
def filter_history():
    """Return escaped HTML rows for asynchronous filtering without exposing other owners"""
    try:
        rows, _ = history_rows()
    except BookingError as failure:
        return {"error": str(failure)}, failure.status
    return {"html": render_template("reservations/_rows.html", rows=rows, cancel_form=CancelForm()), "count": len(rows)}


@bp.post("/<int:identifier>/cancel")
def cancel(identifier):
    """Cancel any owned booking once, preserving its original times and history"""
    if not CancelForm().validate_on_submit():
        abort(400)
    if not 0 < identifier <= 2147483647:
        abort(404)
    owned = db.session.scalar(db.select(Reservation.id).where(Reservation.id == identifier, Reservation.user_id == current_user.id))
    if owned is None:
        abort(404)
    db.session.execute(db.update(Reservation).where(
        Reservation.id == identifier, Reservation.user_id == current_user.id, Reservation.status != "canceled",
    ).values(status="canceled", canceled_at=datetime.now(timezone.utc)))
    db.session.commit()
    message = "Reservation canceled."
    if wants_json():
        return {"message": message}
    flash(message)
    return redirect(url_for("reservations.index"))
