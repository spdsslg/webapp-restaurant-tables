"""Staff access to restaurant-wide reservation history and cancellation"""

from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from .auth import roles_required
from .booking_rules import BookingError
from .extensions import db, login_manager
from .models import Reservation
from .reservation_forms import CancelForm
from .reservations import STATUSES, history_rows
from .tables import lock_staff_actor

bp = Blueprint("staff_reservations", __name__, url_prefix="/staff/reservations")


def wants_json():
    return request.endpoint == "staff_reservations.filter_history" or request.accept_mimetypes.best == "application/json"


@bp.before_request
def require_staff_configuration():
    """Return an explicit authentication error for asynchronous staff requests"""
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI") or not current_app.secret_key:
        return {"error": "Reservation management is not configured yet."}, 503
    if not current_user.is_authenticated:
        if wants_json():
            return {"error": "Sign in to manage reservations."}, 401
        return login_manager.unauthorized()


@bp.get("/")
@roles_required("manager", "administrator")
def index():
    """Show restaurant-wide history including customer contact details for authorized staff"""
    error, status = None, 200
    try:
        rows, zone = history_rows(all_customers=True)
    except BookingError as failure:
        rows, zone, error, status = [], "", str(failure), failure.status
    return render_template("staff_reservations/index.html", rows=rows, timezone=zone, error=error,
                           statuses=STATUSES, cancel_form=CancelForm()), status


@bp.get("/filter")
@roles_required("manager", "administrator")
def filter_history():
    """Refresh the staff table using the same local-date and status rules as customer history"""
    try:
        rows, _ = history_rows(all_customers=True)
    except BookingError as failure:
        return {"error": str(failure)}, failure.status
    return {"html": render_template("staff_reservations/_rows.html", rows=rows, cancel_form=CancelForm()), "count": len(rows)}


@bp.post("/<int:identifier>/cancel")
@roles_required("manager", "administrator")
def cancel(identifier):
    """Cancel a customer booking once without altering its identity or original times"""
    if not CancelForm().validate_on_submit():
        abort(400)
    if not 0 < identifier <= 2147483647:
        abort(404)
    lock_staff_actor()
    if db.session.get(Reservation, identifier) is None:
        abort(404)
    db.session.execute(db.update(Reservation).where(
        Reservation.id == identifier, Reservation.status != "canceled",
    ).values(status="canceled", canceled_at=datetime.now(timezone.utc)))
    db.session.commit()
    message = "Reservation canceled."
    if wants_json():
        return {"message": message}
    flash(message)
    return redirect(url_for("staff_reservations.index"))
