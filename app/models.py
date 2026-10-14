"""Database records and constraints; booking workflows are added separately"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from flask_login import UserMixin

from .extensions import db

class User(UserMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint("role IN ('customer', 'manager', 'administrator')", name="user_role"),
    )
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100),nullable=False)
    role = db.Column(db.String(20), nullable=False, server_default="customer")
    is_active = db.Column(db.Boolean, nullable=False,server_default=sa.true())

class RestaurantSettings(db.Model):
    __tablename__ = "restaurant_settings"
    __table_args__ = (
        sa.CheckConstraint("id = 1", name="settings_singleton"),#because there is only one restaurant
        sa.CheckConstraint(
            "min_duration_minutes > 0 AND min_duration_minutes <= max_duration_minutes "
            "AND max_duration_minutes <= 180", name="settings_duration_bounds"
        ),
        sa.CheckConstraint(
            "duration_step_minutes > 0 AND duration_step_minutes <= 180 "
            "AND slot_interval_minutes > 0 AND slot_interval_minutes <= 180",
            name="settings_positive_steps",
        ),
    )
    id = db.Column(db.Integer, primary_key=True, autoincrement=False)#because there is only one restaurant
    timezone = db.Column(db.String(64), nullable=False, server_default="Europe/Warsaw")
    min_duration_minutes = db.Column(db.Integer, nullable=False, server_default="30")
    max_duration_minutes = db.Column(db.Integer, nullable=False, server_default="180")
    duration_step_minutes = db.Column(db.Integer, nullable=False, server_default="30")
    slot_interval_minutes = db.Column(db.Integer, nullable=False, server_default="30")


class OpeningHours(db.Model):
    __tablename__ = "opening_hours"
    __table_args__ = (
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="hours_weekday"),
        sa.CheckConstraint("opens_at < closes_at", name="hours_order"),
    )
    weekday = db.Column(db.Integer, primary_key=True, autoincrement=False)
    opens_at = db.Column(db.Time, nullable=False)
    closes_at = db.Column(db.Time, nullable=False)


class DiningTable(db.Model):
    __tablename__ = "dining_tables"
    __table_args__ = (
        sa.CheckConstraint("capacity > 0", name="table_capacity"),
        sa.CheckConstraint("x >= 0 AND y >= 0", name="table_position"),
    )
    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(30), nullable=False, unique=True)
    capacity = db.Column(db.Integer, nullable=False)
    x = db.Column(db.Integer, nullable=False)
    y = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, server_default=sa.true())


class Reservation(db.Model):
    __tablename__ = "reservations"
    __table_args__ = (
        sa.CheckConstraint(
            "end_at > start_at AND end_at <= start_at + INTERVAL '180 minutes'",
            name="reservation_interval",
        ),
        sa.CheckConstraint("party_size > 0", name="reservation_party_size"),
        sa.CheckConstraint("status IN ('confirmed', 'canceled', 'completed')", name="reservation_status"),
        sa.CheckConstraint(
            "(status = 'canceled') = (canceled_at IS NOT NULL)", name="reservation_cancellation"
        ),
        ExcludeConstraint(
            ("table_id", "="),
            #I used GiST index to compare intervals efficiently, as standard b-tree cant have range comparison between two columns
            (sa.func.tstzrange(sa.column("start_at"), sa.column("end_at"), "[)"), "&&"),
            where=sa.text("status = 'confirmed'"), using="gist", name="reservation_no_overlap",
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    table_id = db.Column(db.Integer, db.ForeignKey("dining_tables.id", ondelete="RESTRICT"), nullable=False)
    start_at = db.Column(db.DateTime(timezone=True), nullable=False)
    end_at = db.Column(db.DateTime(timezone=True), nullable=False)
    party_size = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, server_default="confirmed")
    canceled_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
