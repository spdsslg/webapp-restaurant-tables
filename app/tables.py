"""Staff table creation, renaming, and reversible deactivation"""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from .auth import roles_required
from .extensions import db
from .models import DiningTable, User
from .table_forms import CreateTableForm, EditTableForm

bp = Blueprint("tables", __name__, url_prefix="/staff/tables")


@bp.before_request
def require_configuration():
    """Avoid accessing database-backed forms before application setup is complete"""
    if not current_app.config.get("SQLALCHEMY_DATABASE_URI") or not current_app.secret_key:
        abort(503)


def lock_staff_actor():
    """Recheck staff access under a shared account lock before staff changes"""
    actor_id, session_id = current_user.id, session.get("_user_id")
    actor = db.session.scalar(db.select(User).where(User.id == actor_id).with_for_update(read=True)
                              .execution_options(populate_existing=True))
    if not actor or not actor.is_active or actor.role not in ("manager", "administrator") or actor.get_id() != session_id:
        db.session.rollback()
        abort(403)


def find_table(identifier, lock=False):
    """Bound identifiers and optionally lock against concurrent booking attempts"""
    if not 0 < identifier <= 2147483647:
        abort(404)
    query = db.select(DiningTable).where(DiningTable.id == identifier)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    table = db.session.scalar(query)
    if table is None:
        abort(404)
    return table


@bp.get("/")
@roles_required("manager", "administrator")
def index():
    """List active and inactive tables without exposing a permanent deletion action"""
    records = db.session.scalars(db.select(DiningTable).order_by(DiningTable.label)).all()
    return render_template("tables/index.html", tables=records)


@bp.route("/new", methods=["GET", "POST"])
@roles_required("manager", "administrator")
def create():
    """Create a table with its permanent capacity"""
    form = CreateTableForm()
    if form.validate_on_submit():
        lock_staff_actor()
        db.session.add(DiningTable(label=form.label.data, capacity=form.capacity.data, is_active=True))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.label.errors.append("A table with this label already exists.")
        else:
            flash("Table created.")
            return redirect(url_for("tables.index"))
    return render_template("tables/edit.html", form=form, table=None, title="Create table")


@bp.route("/<int:identifier>/edit", methods=["GET", "POST"])
@roles_required("manager", "administrator")
def edit(identifier):
    """Rename or change a table's active state while preserving its capacity and bookings"""
    table = find_table(identifier)
    form = EditTableForm()
    if request.method == "GET":
        form.label.data, form.state.data = table.label, "active" if table.is_active else "inactive"
    if form.validate_on_submit():
        lock_staff_actor()
        table = find_table(identifier, lock=True)
        table.label, table.is_active = form.label.data, form.state.data == "active"
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            form.label.errors.append("A table with this label already exists.")
        else:
            flash("Table saved. Existing reservations are unchanged.")
            return redirect(url_for("tables.index"))
    return render_template("tables/edit.html", form=form, table=table, title="Manage table")
