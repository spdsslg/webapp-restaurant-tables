"""Creates tables and schema defined in models.py"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ExcludeConstraint

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    #Retain this shared extension on downgrade; other schemas may depend on it.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table("users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("role IN ('customer', 'manager', 'administrator')", name="user_role"),
    )
    op.create_table("restaurant_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Europe/Warsaw"),
        sa.Column("min_duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_duration_minutes", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("duration_step_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("slot_interval_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.CheckConstraint("id = 1", name="settings_singleton"),
        sa.CheckConstraint("min_duration_minutes > 0 AND min_duration_minutes <= max_duration_minutes AND max_duration_minutes <= 180", name="settings_duration_bounds"),
        sa.CheckConstraint("duration_step_minutes > 0 AND duration_step_minutes <= 180 AND slot_interval_minutes > 0 AND slot_interval_minutes <= 180", name="settings_positive_steps"),
    )
    op.create_table("opening_hours",
        sa.Column("weekday", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="hours_weekday"),
        sa.CheckConstraint("opens_at < closes_at", name="hours_order"),
    )
    op.create_table("dining_tables",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("label", sa.String(30), nullable=False, unique=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("capacity > 0", name="table_capacity"),
        sa.CheckConstraint("x >= 0 AND y >= 0", name="table_position"),
    )
    op.create_table("reservations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("table_id", sa.Integer(), sa.ForeignKey("dining_tables.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("party_size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="confirmed"),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("end_at > start_at AND end_at <= start_at + INTERVAL '180 minutes'", name="reservation_interval"),
        sa.CheckConstraint("party_size > 0", name="reservation_party_size"),
        sa.CheckConstraint("status IN ('confirmed', 'canceled', 'completed')", name="reservation_status"),
        sa.CheckConstraint("(status = 'canceled') = (canceled_at IS NOT NULL)", name="reservation_cancellation"),
        ExcludeConstraint(
            ("table_id", "="),
            (sa.func.tstzrange(sa.column("start_at"), sa.column("end_at"), "[)"), "&&"),
            where=sa.text("status = 'confirmed'"), using="gist", name="reservation_no_overlap",
        ),
    )


def downgrade():
    op.drop_table("reservations")
    op.drop_table("dining_tables")
    op.drop_table("opening_hours")
    op.drop_table("restaurant_settings")
    op.drop_table("users")
