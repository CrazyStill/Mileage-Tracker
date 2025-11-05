from collections import defaultdict
from datetime import datetime, date

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from openpyxl import Workbook

db = SQLAlchemy()

# -----------------------------
# Work module models
# -----------------------------
class WorkDay(db.Model):
    __tablename__ = 'work_day'

    id = db.Column(db.Integer, primary_key=True)
    # Single-user for now, future-proof with a user_id
    user_id = db.Column(db.Integer, nullable=False, default=1)

    # Logical work day (CST date chosen by you). Only this date matters.
    day = db.Column(db.Date, nullable=False, index=True)

    # started | ended
    status = db.Column(db.String(16), nullable=False, default='started')

    # Integers only (no decimals) per your requirement
    start_odo = db.Column(db.Integer, nullable=True)
    end_odo   = db.Column(db.Integer, nullable=True)

    # If backfilling without odometers, allow manual total miles
    total_miles = db.Column(db.Integer, nullable=True)

    start_location   = db.Column(db.String(255), nullable=True)
    trip_explanation = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    segments = db.relationship(
        'WorkSegment',
        back_populates='work_day',
        cascade='all, delete-orphan',
        order_by='WorkSegment.seq'
    )

    __table_args__ = (
        db.CheckConstraint("status in ('started','ended')", name='ck_work_day_status'),
        db.CheckConstraint(
            '(start_odo IS NULL OR start_odo >= 0) AND '
            '(end_odo IS NULL OR end_odo >= 0) AND '
            '(total_miles IS NULL OR total_miles >= 0)',
            name='ck_work_day_nonneg'
        ),
    )

    def compute_total_miles(self) -> int:
        """Prefer end-start when both present; otherwise use manual total_miles; never negative."""
        if self.start_odo is not None and self.end_odo is not None:
            return max(0, self.end_odo - self.start_odo)
        return self.total_miles or 0


class WorkSegment(db.Model):
    __tablename__ = 'work_segment'

    id = db.Column(db.Integer, primary_key=True)
    work_day_id = db.Column(
        db.Integer,
        db.ForeignKey('work_day.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    seq = db.Column(db.Integer, nullable=False, default=0)  # order in the day
    location_name = db.Column(db.String(255), nullable=False)

    work_day = db.relationship('WorkDay', back_populates='segments')


# -----------------------------
# Officiating models & helpers
# -----------------------------
class Trip(db.Model):
    __tablename__ = 'trips'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String, nullable=False)
    time = db.Column(db.String, nullable=False)
    sport = db.Column(db.String, nullable=False)
    venue = db.Column(db.String, nullable=False)
    home_team = db.Column(db.String, nullable=False)
    away_team = db.Column(db.String, nullable=False)
    odometer_start = db.Column(db.Float, nullable=False)
    odometer_end = db.Column(db.Float)
    Level_of_Play = db.Column(db.String, nullable=True)
    miles = db.Column(db.Float)
    amount_paid = db.Column(db.Float)
    status = db.Column(db.String, nullable=False, default='started')
    # Null means active/current year; integer year (e.g. 2024) means archived into that year
    archived_year = db.Column(db.Integer, nullable=True, index=True)

    def __init__(self, date, time, sport, venue, home_team, away_team, odometer_start):
        self.date = date
        self.time = time
        self.sport = sport
        self.venue = venue
        self.home_team = home_team
        self.away_team = away_team
        self.odometer_start = odometer_start
        self.status = 'started'

    def format_time_12h(self):
        if not self.time:
            return 'N/A'
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                dt = datetime.strptime(self.time, fmt)
                return dt.strftime("%I:%M %p")
            except ValueError:
                pass
        return self.time


class PreparedTrip(db.Model):
    __tablename__ = 'prepared_trips'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String,  nullable=False)
    time = db.Column(db.String,  nullable=False)
    sport = db.Column(db.String, nullable=False)
    venue = db.Column(db.String, nullable=False)
    home_team = db.Column(db.String, nullable=False)
    away_team = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    archived_year = db.Column(db.Integer, nullable=True, index=True)


def start_new_trip(date, time, sport, venue, home_team, away_team, odometer_start):
    new_trip = Trip(date, time, sport, venue, home_team, away_team, odometer_start)
    db.session.add(new_trip    )
    db.session.commit()


def finish_trip(Level_of_Play, trip_id, odometer_end, amount_paid):
    trip = Trip.query.get(trip_id)
    if trip and trip.status == 'started':
        trip.odometer_end = odometer_end
        trip.miles = odometer_end - trip.odometer_start
        trip.Level_of_Play = Level_of_Play
        trip.amount_paid = amount_paid
        trip.status = 'completed'
        db.session.commit()
    else:
        raise ValueError("Invalid trip ID or the trip is already completed.")


def get_started_trips():
    # exclude archived trips from active lists
    return Trip.query.filter(Trip.status == 'started', Trip.archived_year == None).all()


def export_to_excel(year: int = None):
    """Export completed trips to Excel.

    If year is None, export current (non-archived) completed trips.
    If year is provided, export trips archived for that year or trips whose date year matches when not archived.
    """
    if year is None:
        entries = Trip.query.filter(Trip.status == 'completed', Trip.archived_year == None).all()
    else:
        # Prefer archived_year marker; fall back to date field parsing for safety
        entries = Trip.query.filter(
            (Trip.archived_year == year) | (func.substr(Trip.date, 1, 4) == str(year)),
            Trip.status == 'completed'
        ).all()
    if not entries:
        return None

    entries_by_year = defaultdict(list)
    for entry in entries:
        date_obj = datetime.strptime(entry.date, '%Y-%m-%d')
        year = date_obj.strftime('%Y')
        entries_by_year[year].append(entry)

    filenames = []
    for year, year_entries in entries_by_year.items():
        filename = f"mileage_data_{year}.xlsx"
        wb = Workbook()
        summary_ws = wb.active
        summary_ws.title = 'Summary'

        total_miles = sum(entry.miles or 0 for entry in year_entries)
        total_revenue = sum(entry.amount_paid or 0 for entry in year_entries)

        summary_ws.append(['Year', year])
        summary_ws.append(['Total Miles', total_miles])
        summary_ws.append(['Total Revenue', total_revenue])

        month_sheets = {}
        for entry in year_entries:
            date_obj = datetime.strptime(entry.date, '%Y-%m-%d')
            month_name = date_obj.strftime('%B')

            if month_name not in month_sheets:
                ws = wb.create_sheet(title=month_name)
                ws.append(['ID', 'Date', 'Time', 'Sport', 'Venue', 'Home Team', 'Away Team',
                           'Odometer Start', 'Odometer End', 'Miles', 'Level of Play', 'Amount Paid', 'Status'])
                month_sheets[month_name] = ws
            ws = month_sheets[month_name]
            ws.append([
                entry.id, entry.date, entry.time, entry.sport, entry.venue, entry.home_team,
                entry.away_team, entry.odometer_start, entry.odometer_end,
                entry.miles, entry.Level_of_Play, entry.amount_paid, entry.status
            ])

        wb.save(filename)
        filenames.append(filename)

    return filenames


def create_prepared_trip(date, time, sport, venue, home_team, away_team):
    p = PreparedTrip(
        date=date, time=time, sport=sport,
        venue=venue, home_team=home_team, away_team=away_team
    )
    db.session.add(p)
    db.session.commit()


def archive_year(year: int):
    """Mark all trips and prepared trips for the given year as archived.

    This sets the `archived_year` integer on matching rows so they are excluded
    from normal current views but allow separate archived views and exports.
    """
    str_year = str(year)
    # Update Trip rows where the date starts with 'YYYY-' OR already have that year
    trips = Trip.query.filter(
        (func.substr(Trip.date, 1, 4) == str_year) & (Trip.archived_year == None)
    ).all()
    for t in trips:
        t.archived_year = year

    preps = PreparedTrip.query.filter(
        (func.substr(PreparedTrip.date, 1, 4) == str_year) & (PreparedTrip.archived_year == None)
    ).all()
    for p in preps:
        p.archived_year = year

    db.session.commit()


def list_archived_years():
    years = db.session.query(Trip.archived_year).filter(Trip.archived_year != None).distinct().all()
    # Flatten tuples and sort descending
    ys = sorted({y[0] for y in years if y[0] is not None}, reverse=True)
    return ys


def get_trips_by_archived_year(year: int):
    return Trip.query.filter(Trip.archived_year == year).order_by(Trip.id.desc()).all()


def ensure_archive_columns(engine):
    """Ensure archived_year columns exist in the SQLite tables. Adds columns if missing.

    This is a small, idempotent migration helper so adding this feature doesn't
    require external migration tooling.
    """
    # Only implemented for SQLite (simple ALTER TABLE ADD COLUMN)
    try:
        if engine.dialect.name != 'sqlite':
            return
        # Resolve sqlite DB path
        db_path = None
        try:
            db_path = engine.url.database
        except Exception:
            db_path = None
        if not db_path:
            return

        # Use sqlite3 directly to run PRAGMA and ALTER statements reliably
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info('trips')")
        cols = [r[1] for r in cur.fetchall()]
        if 'archived_year' not in cols:
            cur.execute("ALTER TABLE trips ADD COLUMN archived_year INTEGER;")
        cur.execute("PRAGMA table_info('prepared_trips')")
        cols = [r[1] for r in cur.fetchall()]
        if 'archived_year' not in cols:
            cur.execute("ALTER TABLE prepared_trips ADD COLUMN archived_year INTEGER;")
        conn.commit()
        conn.close()
    except Exception:
        # If anything goes wrong, silently continue; the app can still run but archiving will fail until fixed.
        pass


def get_prepared_trips():
    # Exclude archived prepared trips from the active prepared list
    return PreparedTrip.query.filter(PreparedTrip.archived_year == None).order_by(PreparedTrip.created_at).all()


def delete_prepared_trip(prep_id):
    p = PreparedTrip.query.get(prep_id)
    if p:
        db.session.delete(p)
        db.session.commit()
