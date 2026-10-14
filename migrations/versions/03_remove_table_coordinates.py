"""Remove unused restaurant-map coordinates from physical tables"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("table_position", "dining_tables", type_="check")
    op.drop_column("dining_tables", "x")
    op.drop_column("dining_tables", "y")


def downgrade():
    """Restore the old columns with neutral positions; removed coordinates cannot be recovered"""
    op.add_column("dining_tables", sa.Column("x", sa.Integer(), server_default="0", nullable=False))
    op.add_column("dining_tables", sa.Column("y", sa.Integer(), server_default="0", nullable=False))
    op.alter_column("dining_tables", "x", server_default=None)
    op.alter_column("dining_tables", "y", server_default=None)
    op.create_check_constraint("table_position", "dining_tables", "x >= 0 AND y >= 0")
