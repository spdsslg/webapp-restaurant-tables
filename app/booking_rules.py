"""Shared availability and reservation rules enforced against PostgreSQL"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError, OperationalError

from .extensions import db
from .models import DiningTable, OpeningHours, Reservation, RestaurantSettings, User


class BookingError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now_utc():
    return datetime.now(timezone.utc)


def parse_day(value):
    """Accept calendar dates or strict ISO date inputs"""
    if isinstance(value, date):
        return value
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError, OverflowError):
        raise BookingError("Choose a valid date in YYYY-MM-DD format.") from None


def integer(value, label):
    """Validate positive integers within PostgreSQL's integer range"""
    try:
        parsed = int(value)
        if str(parsed) != str(value) or not 0 < parsed <= 2147483647:
            raise ValueError
        return parsed
    except (TypeError, ValueError, OverflowError):
        raise BookingError(f"Choose a positive whole number for {label}.") from None


def configuration(day, lock=False):
    """Load the day's configured hours, duration rules, and restaurant timezone"""
    settings_query = db.select(RestaurantSettings).where(RestaurantSettings.id == 1)
    hours_query = db.select(OpeningHours).where(OpeningHours.weekday == day.weekday())
    if lock:
        settings_query = settings_query.with_for_update(read=True)
        hours_query = hours_query.with_for_update(read=True)
    settings = db.session.scalar(settings_query.execution_options(populate_existing=True))
    hours = db.session.scalar(hours_query.execution_options(populate_existing=True))
    if not settings or not hours:
        raise BookingError("Restaurant booking settings are not ready yet.", 503)
    try:
        zone = ZoneInfo(settings.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise BookingError("The restaurant timezone needs to be configured.", 503) from None
    if not (0 < settings.min_duration_minutes <= settings.max_duration_minutes <= 180
            and settings.duration_step_minutes > 0 and settings.slot_interval_minutes > 0):
        raise BookingError("Restaurant duration settings are invalid.", 503)
    return settings, hours, zone


def local_instant(day, clock, zone):
    """Reject ambiguous or nonexistent local times rather than guessing a DST fold"""
    local = datetime.combine(day, clock)
    instants = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == local:
            instants.add(instant)
    if len(instants) != 1:
        raise BookingError("That local time is unavailable due to a daylight-saving change.")
    return instants.pop()


def allowed_duration(settings, value):
    """Require a duration in the configured minimum-based increment sequence"""
    duration = integer(value, "duration")
    if not (settings.min_duration_minutes <= duration <= settings.max_duration_minutes
            and (duration - settings.min_duration_minutes) % settings.duration_step_minutes == 0):
        raise BookingError("Choose one of the allowed reservation durations.")
    return duration


def validated_interval(day, start, duration, party_size, lock=False):
    """Validate local booking inputs and return the full interval in UTC"""
    day = parse_day(day)
    settings, hours, zone = configuration(day, lock=lock)
    duration = allowed_duration(settings, duration)
    integer(party_size, "party size")
    try:
        clock = time.fromisoformat(start)
        if clock.strftime("%H:%M") != start:
            raise ValueError
        offset = (datetime.combine(day, clock) - datetime.combine(day, hours.opens_at)).total_seconds()
        if offset < 0 or offset % (settings.slot_interval_minutes * 60):
            raise BookingError("Choose a predefined booking start time.")
        start_at = local_instant(day, clock, zone)
        end_at = start_at + timedelta(minutes=duration)
        closing = local_instant(day, hours.closes_at, zone)
    except (TypeError, ValueError, OverflowError) as error:
        if isinstance(error, BookingError):
            raise
        raise BookingError("Choose a valid booking start time.") from None
    if end_at > closing:
        raise BookingError("The whole reservation must fit within opening hours.")
    if start_at <= now_utc():
        raise BookingError("Choose a booking start time in the future.")
    return start_at, end_at


def options_for_date(day, duration=None):
    """Generate future start slots whose full selected duration fits before closing"""
    day = parse_day(day)
    settings, hours, zone = configuration(day)
    duration = allowed_duration(settings, settings.min_duration_minutes if duration is None else duration)
    durations = list(range(settings.min_duration_minutes, settings.max_duration_minutes + 1, settings.duration_step_minutes))
    starts = []
    opening_wall = datetime.combine(day, hours.opens_at)
    closing_wall = datetime.combine(day, hours.closes_at)
    closing = local_instant(day, hours.closes_at, zone)
    current = now_utc()
    span = int((closing_wall - opening_wall).total_seconds() // 60)
    for offset in range(0, span, settings.slot_interval_minutes):
        slot = opening_wall + timedelta(minutes=offset)
        try:
            start_at = local_instant(day, slot.time(), zone)
            end_at = start_at + timedelta(minutes=duration)
        except (BookingError, OverflowError):
            continue
        else:
            if start_at > current and end_at <= closing:
                starts.append(slot.strftime("%H:%M"))
    return {"starts": starts, "durations": durations, "timezone": zone.key}


def available_tables(start_at, end_at, party_size):
    """Find active tables with sufficient capacity and no confirmed interval overlap"""
    overlap = db.select(Reservation.id).where(
        Reservation.table_id == DiningTable.id, Reservation.status == "confirmed",
        Reservation.start_at < end_at, Reservation.end_at > start_at,
    ).exists()
    return db.session.scalars(db.select(DiningTable).where(
        DiningTable.is_active.is_(True), DiningTable.capacity >= integer(party_size, "party size"), ~overlap,
    ).order_by(DiningTable.label)).all()


def reserve(user_id, table_id, day, start, duration, party_size, auth_version):
    """Shared row locks coordinate configuration edits without serializing bookings"""
    table_id = integer(table_id, "table")
    party_size = integer(party_size, "party size")
    start_at, end_at = validated_interval(day, start, duration, party_size, lock=True)
    user = db.session.scalar(db.select(User).where(User.id == user_id).with_for_update(read=True)
                             .execution_options(populate_existing=True))
    if not user or not user.is_active or user.auth_version != auth_version:
        raise BookingError("Your account changed. Please sign in again.", 401)
    table = db.session.scalar(db.select(DiningTable).where(DiningTable.id == table_id)
                              .with_for_update(read=True).execution_options(populate_existing=True))
    if not table or not table.is_active or table.capacity < party_size:
        raise BookingError("Choose an active table with enough seats.")
    if table_id not in {item.id for item in available_tables(start_at, end_at, party_size)}:
        raise BookingError("That table is no longer available for this interval.", 409)
    if start_at <= now_utc():
        raise BookingError("Choose a booking start time in the future.")
    reservation = Reservation(user_id=user_id, table_id=table_id, start_at=start_at, end_at=end_at, party_size=party_size)
    db.session.add(reservation)
    try:
        db.session.commit()
    except IntegrityError as error:
        db.session.rollback()
        if getattr(getattr(error.orig, "diag", None), "constraint_name", None) == "reservation_no_overlap":
            raise BookingError("That table was just booked. Choose another table or time.", 409) from None
        raise
    except OperationalError as error:
        db.session.rollback()
        if getattr(error.orig, "sqlstate", None) == "40P01":
            raise BookingError("Another booking competed for this table. Please retry or choose another time.", 409) from None
        raise
    return reservation
