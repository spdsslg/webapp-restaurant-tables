"""Explicit development seed command; never creates staff credentials."""

from datetime import time

import click
from flask.cli import with_appcontext

from .extensions import db
from .models import DiningTable, OpeningHours, RestaurantSettings


@click.command("seed-demo")
@with_appcontext
def seed_demo():
    """Adds missing initial restaurant settings, hours, and eight sample tables.
       Manager and Admin will later be able to change them. This is just basic intialisation"""
    if db.session.get(RestaurantSettings, 1) is None:
        db.session.add(RestaurantSettings(id=1))
    for weekday in range(7):
        if db.session.get(OpeningHours, weekday) is None:
            weekend = weekday >= 5
            db.session.add(OpeningHours(
                weekday=weekday, opens_at=time(10 if weekend else 9),
                closes_at=time(21 if weekend else 22),
            ))
    for index, capacity in enumerate((2, 2, 2, 2, 4, 4, 6, 6)):
        label = f"T{index + 1}"
        if db.session.scalar(db.select(DiningTable).filter_by(label=label)) is None:
            db.session.add(DiningTable(
                label=label, capacity=capacity, x=80 + (index % 4) * 120,
                y=80 + (index // 4) * 140,
            ))
    db.session.commit()
    
    click.echo("Initial restaurant settings, hours, and sample tables are ready.")


def register_commands(app):
    app.cli.add_command(seed_demo)
