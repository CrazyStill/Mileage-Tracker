from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from openpyxl import Workbook
from collections import defaultdict

db = SQLAlchemy()

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

    def __init__(self, date, time, sport, venue, home_team, away_team, odometer_start):
        self.date = date
        self.time = time
        self.sport = sport
        self.venue = venue
        self.home_team = home_team
        self.away_team = away_team
        self.odometer_start = odometer_start

        self.status = 'started'

def start_new_trip(date, time, sport, venue, home_team, away_team, odometer_start):
    new_trip = Trip(date, time, sport, venue, home_team, away_team, odometer_start)
    db.session.add(new_trip)
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
    return Trip.query.filter_by(status='started').all()

def export_to_excel():
    entries = Trip.query.filter_by(status='completed').all()
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
                           'Odometer Start', 'Odometer End', 'Miles','Level of Play', 'Amount Paid', 'Status'])
                month_sheets[month_name] = ws
            else:
                ws = month_sheets[month_name]

            ws.append([
                entry.id, entry.date, entry.time, entry.sport, entry.venue, entry.home_team,
                entry.away_team, entry.odometer_start, entry.odometer_end, entry.miles, entry.Level_of_Play,
                entry.amount_paid, entry.status
            ])

        wb.save(filename)
        filenames.append(filename)

    return filenames
